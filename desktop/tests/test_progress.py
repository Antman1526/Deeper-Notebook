from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from desktop.progress import ProgressBus, ProgressEvent


def test_publish_writes_to_jsonl(tmp_path: Path):
    log = tmp_path / "progress.jsonl"
    bus = ProgressBus(log_path=log)
    bus.publish("supervisor.api", "running", "Booting uvicorn…")
    bus.publish("supervisor.api", "done")

    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0]["step"] == "supervisor.api"
    assert lines[0]["status"] == "running"
    assert lines[0]["message"] == "Booting uvicorn…"
    assert "ts" in lines[0]
    assert lines[1]["status"] == "done"


def test_subscriber_receives_events(tmp_path: Path):
    bus = ProgressBus(log_path=tmp_path / "progress.jsonl")
    received: list[ProgressEvent] = []

    def reader():
        for evt in bus.subscribe(timeout=0.5):
            received.append(evt)
            if evt["step"] == "ready":
                return

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    time.sleep(0.05)  # give subscriber time to register
    bus.publish("bootstrap.start", "running")
    bus.publish("ready", "done")
    t.join(timeout=2.0)

    assert any(e["step"] == "bootstrap.start" for e in received)
    assert any(e["step"] == "ready" for e in received)


def test_late_subscriber_gets_history(tmp_path: Path):
    """A subscriber that connects after some events should still see them."""
    bus = ProgressBus(log_path=tmp_path / "progress.jsonl")
    bus.publish("bootstrap.start", "running")
    bus.publish("bootstrap.start", "done")

    received: list[ProgressEvent] = []

    def reader():
        for evt in bus.subscribe(timeout=0.3, replay=True):
            received.append(evt)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t.join(timeout=1.0)

    assert len(received) >= 2
    assert received[0]["step"] == "bootstrap.start"
    assert received[0]["status"] == "running"
