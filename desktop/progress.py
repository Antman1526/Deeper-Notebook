"""Pub-sub progress channel for the launcher startup phase.

Publishes structured events to:
  - ~/.deeper-notebook/logs/progress.jsonl  (persistent, tailable)
  - in-process subscribers via subscribe()      (for the wizard's SSE feed)

Thread-safe; the launcher's main thread publishes, the wizard server's
SSE handler subscribes from its own request-handler thread.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TypedDict


class ProgressEvent(TypedDict):
    ts: str
    step: str
    status: str  # "running" | "done" | "error"
    message: str


_END = object()  # sentinel pushed to subscribers on close


class ProgressBus:
    # v0.5.10 — rotate progress.jsonl once it crosses this size. Otherwise
    # the file grows forever across launches (each launch writes ~30
    # supervisor.* events at ~120 bytes each = ~3.6 KB per launch).
    _MAX_LOG_BYTES = 2 * 1024 * 1024

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._history: list[ProgressEvent] = []
        self._rotate_if_oversized()

    def _rotate_if_oversized(self) -> None:
        """Cheap stat check on startup; move to .old if over the cap."""
        try:
            if (
                self.log_path.exists()
                and self.log_path.stat().st_size > self._MAX_LOG_BYTES
            ):
                old = self.log_path.with_suffix(self.log_path.suffix + ".old")
                old.unlink(missing_ok=True)
                self.log_path.rename(old)
        except Exception:
            pass  # never fatal

    def publish(self, step: str, status: str, message: str = "") -> None:
        evt: ProgressEvent = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "status": status,
            "message": message,
        }
        with self._lock:
            self._history.append(evt)
            with self.log_path.open("a") as f:
                f.write(json.dumps(evt) + "\n")
            for q in self._subscribers:
                try:
                    q.put_nowait(evt)
                except queue.Full:
                    pass

    def subscribe(
        self, timeout: float = 60.0, replay: bool = False
    ) -> Iterator[ProgressEvent]:
        """Yield events until `ready/done` arrives or timeout idles out.

        replay=True yields all events published so far (history) first, then
        any new events as they arrive.
        """
        q: queue.Queue = queue.Queue(maxsize=1024)
        with self._lock:
            self._subscribers.append(q)
            if replay:
                for evt in self._history:
                    q.put_nowait(evt)
        try:
            while True:
                try:
                    evt = q.get(timeout=timeout)
                except queue.Empty:
                    return
                if evt is _END:
                    return
                yield evt
                if evt["step"] == "ready" and evt["status"] == "done":
                    return
        finally:
            with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)

    def close(self) -> None:
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(_END)
                except queue.Full:
                    pass
            self._subscribers.clear()
