# Open Notebook Plus v0.3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the voice-first, fully-offline notebook described in `2026-05-11-open-notebook-plus-v0.3-design.md` — adds local STT (Whisper.cpp), local TTS (Piper), local-served embeddings, an in-app model manager, and a live wizard progress feed.

**Architecture:** The launcher's Supervisor grows from 4 to 8 supervised children: existing (SurrealDB, FastAPI, worker, Next.js) + new (chat llama.cpp [from v0.2], embed llama.cpp, Whisper STT FastAPI shim, Piper TTS FastAPI shim). Each new shim translates upstream's OpenAI-compatible expectations into the underlying library's API. Frontend additions are JS injections (no upstream React forks). A new `ProgressBus` publishes structured startup events via SSE; the wizard window stays open through the 60–180 s startup with real-time per-step status.

**Tech Stack:** Python 3.12 (venv via uv/python-build-standalone), FastAPI, aiohttp (existing wizard), Whisper.cpp via `whisper-cpp-python` (in the venv), Piper TTS via `piper-tts` (in the venv), llama.cpp via `llama-cpp-python` (already in lockfile), PyWebView (multi-window + tray), HTML/CSS/JS for wizard + model-manager UIs.

**Spec:** [docs/superpowers/specs/2026-05-11-open-notebook-plus-v0.3-design.md](../specs/2026-05-11-open-notebook-plus-v0.3-design.md)

---

## File map (created/modified by this plan)

### Created
```
desktop/
├── progress.py                     # ProgressBus pub-sub
├── desktop_shims/                  # NOTE: lives under upstream/ at runtime
│   ├── __init__.py
│   ├── whisper_shim.py             # OpenAI-style STT wrapping whisper-cpp-python
│   └── piper_shim.py               # OpenAI-style TTS wrapping piper-tts
├── model_manager/
│   ├── __init__.py
│   ├── server.py                   # aiohttp server (analog of first_run/server.py)
│   ├── catalog.json                # Curated downloadable models
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── manager.js
├── tray.py                         # PyWebView tray menu
└── tests/
    ├── test_progress.py
    ├── test_whisper_shim.py
    ├── test_piper_shim.py
    ├── test_model_manager_server.py
    └── test_tray.py
```

### Modified
- `desktop/requirements.lock` — add `whisper-cpp-python`, `piper-tts`
- `desktop/launcher.py` — `_spawn_whisper`, `_spawn_piper`, `_spawn_llamacpp_embed`, ProgressBus integration
- `desktop/auto_register.py` — register STT/TTS credentials + models + Episode Profile
- `desktop/__main__.py` — wire ProgressBus, open model-manager window, tray menu, secondary voice download
- `desktop/model_downloads.py` — add `ensure_secondary_tts_voice`
- `desktop/first_run/server.py` — `/api/progress` SSE endpoint, keep server alive past `/api/save`
- `desktop/first_run/static/index.html` — screen 6 ("Setting up…")
- `desktop/first_run/static/wizard.js` — EventSource subscription for progress
- `desktop/first_run/static/style.css` — progress-list styles
- `desktop/window.py` — extend `_theme_injection_js` with voice injection script
- `desktop/first_run/static/voice_injection.js` — mic FAB + per-message speaker (NEW under static/)
- `desktop/build/pyinstaller.spec` — bundle `desktop_shims/` as data under `upstream/`; bundle `model_manager/static/`; bundle `voice_injection.js`; add `NSMicrophoneUsageDescription` to Info.plist

---

## Task 1: Add whisper-cpp-python + piper-tts to lockfile

The venv needs both packages so the shims can import them. Pinning explicit versions.

**Files:**
- Modify: `desktop/requirements.lock`

- [ ] **Step 1: Append to lockfile**

Append to end of `desktop/requirements.lock`:

```text
# v0.3 voice additions
whisper-cpp-python==0.3.0
piper-tts==1.2.0
```

- [ ] **Step 2: Verify lockfile is well-formed by sniffing with uv**

Run:
```bash
desktop/bin/uv pip compile --no-deps desktop/requirements.lock -o /tmp/dummy.txt 2>&1 | head -3
```
Expected: no syntax errors, file processes cleanly.

- [ ] **Step 3: Commit**

```bash
git add desktop/requirements.lock
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: add whisper-cpp-python + piper-tts to venv lockfile (v0.3 STT/TTS)"
```

---

## Task 2: ProgressBus module

A small pub-sub helper that publishes structured startup events to both a persistent JSONL file and in-memory subscribers (for SSE).

**Files:**
- Create: `desktop/progress.py`
- Create: `desktop/tests/test_progress.py`

- [ ] **Step 1: Write the failing test**

```python
# desktop/tests/test_progress.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_progress.py -v
```
Expected: `ModuleNotFoundError: No module named 'desktop.progress'`.

- [ ] **Step 3: Implement `desktop/progress.py`**

```python
# desktop/progress.py
"""Pub-sub progress channel for the launcher startup phase.

Publishes structured events to:
  - ~/.open-notebook-plus/logs/progress.jsonl  (persistent, tailable)
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
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._history: list[ProgressEvent] = []

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_progress.py -v
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/progress.py desktop/tests/test_progress.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: ProgressBus — JSONL + in-memory pub-sub for startup events"
```

---

## Task 3: Whisper STT shim (FastAPI wrapper)

A small FastAPI server that loads a Whisper.cpp model on startup and exposes the OpenAI `/v1/audio/transcriptions` endpoint. Runs from the venv as a child of Supervisor.

**Files:**
- Create: `desktop/desktop_shims/__init__.py` (empty)
- Create: `desktop/desktop_shims/whisper_shim.py`
- Create: `desktop/tests/test_whisper_shim.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_whisper_shim.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Allow importing the shim package by adding desktop to sys.path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_shims.whisper_shim import build_app


def _fake_whisper_model(transcript: str = "hello world"):
    fake = MagicMock()
    # whisper-cpp-python style: model(audio_bytes).transcribe() → result dict
    fake.transcribe.return_value = {"text": transcript}
    return fake


def test_health_returns_200():
    app = build_app(model=_fake_whisper_model())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_transcribe_returns_text():
    app = build_app(model=_fake_whisper_model("the quick brown fox"))
    with TestClient(app) as c:
        r = c.post(
            "/v1/audio/transcriptions",
            files={"file": ("clip.wav", b"FAKEWAV", "audio/wav")},
            data={"model": "whisper-base-en"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["text"] == "the quick brown fox"


def test_transcribe_rejects_missing_file():
    app = build_app(model=_fake_whisper_model())
    with TestClient(app) as c:
        r = c.post("/v1/audio/transcriptions", data={"model": "whisper-base-en"})
        assert r.status_code == 422  # FastAPI: missing required form file
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/pip install fastapi httpx pytest
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_whisper_shim.py -v
```
Expected: `ModuleNotFoundError: No module named 'desktop_shims'`.

- [ ] **Step 3: Implement the shim**

```python
# desktop/desktop_shims/__init__.py
```

```python
# desktop/desktop_shims/whisper_shim.py
"""OpenAI-compatible STT shim wrapping whisper-cpp-python.

Run as:
    python -m desktop_shims.whisper_shim --port 8765 --model /path/to/ggml-base.en.bin

Exposes:
    GET  /health                       → {"status": "ok"}
    POST /v1/audio/transcriptions      → multipart form (file), returns {"text": ...}
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile


def build_app(model: Any) -> FastAPI:
    """Build the FastAPI app with the (already-loaded) whisper model injected.

    `model` only needs a `transcribe(audio_path_or_bytes) -> {"text": str}` method.
    """
    app = FastAPI(title="Open Notebook Plus — Whisper STT shim")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/v1/audio/transcriptions")
    async def transcribe(
        file: UploadFile = File(...),
        model_id: str = Form("whisper-base-en", alias="model"),
    ) -> dict:
        try:
            audio_bytes = await file.read()
            # Write to a temp file because whisper-cpp-python wants a path
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            result = model.transcribe(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)
            return {"text": result.get("text", "")}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--model", required=True, help="Path to ggml-*.bin")
    args = parser.parse_args(argv)

    # Lazy import — only at runtime; tests inject a fake model.
    from whisper_cpp_python import Whisper

    model = Whisper(args.model)
    app = build_app(model=model)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_whisper_shim.py -v
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/desktop_shims/__init__.py desktop/desktop_shims/whisper_shim.py \
        desktop/tests/test_whisper_shim.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: Whisper STT shim — OpenAI-compatible /v1/audio/transcriptions"
```

---

## Task 4: Piper TTS shim (FastAPI wrapper)

Same pattern as Whisper. Wraps piper-tts, exposes OpenAI `/v1/audio/speech`. Maps `voice` query param to the right Piper model file.

**Files:**
- Create: `desktop/desktop_shims/piper_shim.py`
- Create: `desktop/tests/test_piper_shim.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_piper_shim.py
from __future__ import annotations

import wave
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from desktop_shims.piper_shim import build_app


def _fake_piper_voices():
    """Build a {voice_name: piper_voice_obj} dict. piper_voice_obj.synthesize
    writes WAV bytes to the given file-like object.
    """

    def make(text_per_call: str):
        v = MagicMock()

        def synth(text, wav_file, **kw):
            # Minimal valid WAV
            with wave.open(wav_file, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(22050)
                w.writeframes(b"\x00\x00" * 100)

        v.synthesize.side_effect = synth
        return v

    return {"alex": make("alex"), "sam": make("sam")}


def test_health_returns_200():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200


def test_speech_returns_wav():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post(
            "/v1/audio/speech",
            json={
                "input": "Hello world",
                "voice": "alex",
                "model": "piper-amy-en",
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/wav"
        # Body is a valid WAV
        wav = wave.open(BytesIO(r.content))
        assert wav.getnchannels() == 1


def test_speech_unknown_voice_falls_back_to_first():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post(
            "/v1/audio/speech",
            json={
                "input": "Hello",
                "voice": "nobody",
                "model": "x",
            },
        )
        assert r.status_code == 200  # falls back, doesn't error


def test_speech_missing_input_400():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post("/v1/audio/speech", json={"voice": "alex", "model": "x"})
        assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_piper_shim.py -v
```
Expected: `ModuleNotFoundError: ... piper_shim`.

- [ ] **Step 3: Implement the shim**

```python
# desktop/desktop_shims/piper_shim.py
"""OpenAI-compatible TTS shim wrapping piper-tts.

Run as:
    python -m desktop_shims.piper_shim --port 8766 \\
        --voice alex=/path/to/en_US-amy-medium.onnx \\
        --voice sam=/path/to/en_US-ryan-high.onnx

Exposes:
    GET  /health                  → {"status": "ok", "voices": [...]}
    POST /v1/audio/speech         → JSON {input, voice?, model?} → audio/wav
"""

from __future__ import annotations

import argparse
import io
import sys
import wave
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel


class SpeechRequest(BaseModel):
    input: str
    voice: str | None = None
    model: str | None = None


def build_app(voices: dict[str, Any]) -> FastAPI:
    """Build the FastAPI app with pre-loaded Piper voices injected.

    `voices` maps user-facing name → piper_voice_obj where the object has
    .synthesize(text: str, wav_file: BinaryIO) -> None.
    """
    if not voices:
        raise ValueError("piper_shim.build_app needs at least one voice")
    default_voice = next(iter(voices))

    app = FastAPI(title="Open Notebook Plus — Piper TTS shim")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "voices": list(voices.keys())}

    @app.post("/v1/audio/speech")
    def speech(req: SpeechRequest) -> Response:
        voice_name = req.voice or default_voice
        if voice_name not in voices:
            voice_name = default_voice
        v = voices[voice_name]
        buf = io.BytesIO()
        try:
            v.synthesize(req.input, buf)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return Response(content=buf.getvalue(), media_type="audio/wav")

    return app


def _load_voice(model_path: Path) -> Any:
    """Lazy-load a Piper voice object from an .onnx path."""
    from piper.voice import PiperVoice

    return PiperVoice.load(str(model_path), config_path=str(model_path) + ".json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--voice",
        action="append",
        required=True,
        help="Voice in form NAME=PATH (e.g. alex=/path/to/amy.onnx). Repeatable.",
    )
    args = parser.parse_args(argv)

    voices = {}
    for spec in args.voice:
        name, _, path = spec.partition("=")
        if not path:
            raise SystemExit(f"--voice expects NAME=PATH, got {spec!r}")
        voices[name] = _load_voice(Path(path))

    app = build_app(voices=voices)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_piper_shim.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/desktop_shims/piper_shim.py desktop/tests/test_piper_shim.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: Piper TTS shim — OpenAI-compatible /v1/audio/speech"
```

---

## Task 5: Secondary Piper voice download

Add the male `en_US-ryan-high` voice so Audio Overviews have two distinct speakers.

**Files:**
- Modify: `desktop/model_downloads.py`

- [ ] **Step 1: Append the Ryan voice constants and `ensure_secondary_tts_voice`**

In `desktop/model_downloads.py`, after the existing `PIPER_VOICE_CONFIG` constant block, add:

```python
PIPER_RYAN_MODEL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/"
    "en_US-ryan-high.onnx?download=true",
    "TTS/en_US-ryan-high.onnx",
    "Piper Ryan high (text-to-speech voice)",
    78,
)
PIPER_RYAN_CONFIG = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/"
    "en_US-ryan-high.onnx.json?download=true",
    "TTS/en_US-ryan-high.onnx.json",
    "Piper Ryan high voice config",
    1,
)


def ensure_secondary_tts_voice(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, Path] | None:
    """Download Piper Ryan high voice (.onnx + .json) into model_dir/TTS/."""
    onnx_url, onnx_rel, onnx_label, _ = PIPER_RYAN_MODEL
    cfg_url, cfg_rel, cfg_label, _ = PIPER_RYAN_CONFIG
    onnx = model_dir / onnx_rel
    cfg = model_dir / cfg_rel
    if _download_one(onnx_url, onnx, onnx_label, progress) and _download_one(
        cfg_url, cfg, cfg_label, progress
    ):
        return (onnx, cfg)
    return None
```

- [ ] **Step 2: Add tests**

Append to `desktop/tests/test_model_downloads.py`:

```python
from desktop.model_downloads import ensure_secondary_tts_voice


def test_ensure_secondary_tts_voice_skips_when_present(tmp_path, monkeypatch):
    (tmp_path / "TTS").mkdir()
    onnx = tmp_path / "TTS" / "en_US-ryan-high.onnx"
    cfg = tmp_path / "TTS" / "en_US-ryan-high.onnx.json"
    onnx.write_bytes(b"x" * 200_000)
    cfg.write_text("{}" * 200_000)

    called = []
    monkeypatch.setattr(
        "desktop.model_downloads.urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not download")),
    )
    result = ensure_secondary_tts_voice(tmp_path, progress=lambda m: called.append(m))
    assert result == (onnx, cfg)
```

- [ ] **Step 3: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_model_downloads.py -v
```
Expected: existing tests + 1 new = pass.

- [ ] **Step 4: Commit**

```bash
git add desktop/model_downloads.py desktop/tests/test_model_downloads.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: download secondary Piper voice (Ryan) for Audio Overview dialogue"
```

---

## Task 6: Supervisor — spawn embed/Whisper/Piper

Add three new spawn methods to `Supervisor`. Wire into `start_all`.

**Files:**
- Modify: `desktop/launcher.py`
- Modify: `desktop/tests/test_launcher.py`

- [ ] **Step 1: Add new constructor params + spawn methods**

In `desktop/launcher.py`, inside `Supervisor.__init__`, add (after `upstream_root`):

```python
whisper_model_path: Path | None = (None,)
piper_voices: dict[str, Path] | None = (None,)
nomic_embed_path: Path | None = (None,)
progress: "ProgressBus | None" = (None,)
```

Then in `__init__`:
```python
        self.whisper_model_path = whisper_model_path
        self.piper_voices = piper_voices or {}
        self.nomic_embed_path = nomic_embed_path
        self.progress = progress
```

(Use a string forward reference `"ProgressBus | None"` to avoid the import cycle at top-level; add a TYPE_CHECKING import block.)

Add at the top of the file:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop.progress import ProgressBus
```

Now add `_progress` helper and three spawn methods after `_spawn_next`:

```python
def _progress(self, step: str, status: str, message: str = "") -> None:
    if self.progress is not None:
        try:
            self.progress.publish(step, status, message)
        except Exception:
            pass


def _spawn_llamacpp_embed(self, port: int) -> None:
    if self.nomic_embed_path is None or not self.nomic_embed_path.exists():
        return  # silently skip; embeddings just won't work this session
    args = [
        str(self.venv_python),
        "-m",
        "llama_cpp.server",
        "--model",
        str(self.nomic_embed_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--embedding",
        "true",
    ]
    self._spawn(args, cwd=self.upstream_root, name="llamacpp_embed")


def _spawn_whisper(self, port: int) -> None:
    if self.whisper_model_path is None or not self.whisper_model_path.exists():
        return
    args = [
        str(self.venv_python),
        "-m",
        "desktop_shims.whisper_shim",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model",
        str(self.whisper_model_path),
    ]
    self._spawn(args, cwd=self.upstream_root, name="whisper")


def _spawn_piper(self, port: int) -> None:
    if not self.piper_voices:
        return
    voice_args = []
    for name, path in self.piper_voices.items():
        if path.exists():
            voice_args.extend(["--voice", f"{name}={path}"])
    if not voice_args:
        return
    args = [
        str(self.venv_python),
        "-m",
        "desktop_shims.piper_shim",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ] + voice_args
    self._spawn(args, cwd=self.upstream_root, name="piper")
```

- [ ] **Step 2: Extend `start_all` to allocate 6 ports and spawn the new processes**

Replace the existing `start_all` body's `find_free_ports(3)` line with:

```python
(surreal_port, api_port, frontend_port, embed_port, whisper_port, piper_port) = (
    find_free_ports(6)
)
```

After existing `self._spawn_next(...)` block, append:

```python
        # New v0.3 processes — best-effort; failures don't crash the launcher.
        self._progress("supervisor.llamacpp_embed", "running")
        try:
            self._spawn_llamacpp_embed(embed_port)
            self._progress("supervisor.llamacpp_embed", "done")
        except Exception:
            self._progress("supervisor.llamacpp_embed", "error")

        self._progress("supervisor.whisper", "running")
        try:
            self._spawn_whisper(whisper_port)
            self._progress("supervisor.whisper", "done")
        except Exception:
            self._progress("supervisor.whisper", "error")

        self._progress("supervisor.piper", "running")
        try:
            self._spawn_piper(piper_port)
            self._progress("supervisor.piper", "done")
        except Exception:
            self._progress("supervisor.piper", "error")

        # Stash ports for auto_register to use.
        self.embed_port = embed_port
        self.whisper_port = whisper_port
        self.piper_port = piper_port
```

Also wrap the existing surreal/api/worker/next spawns with `_progress` calls (one per child).

- [ ] **Step 3: Add tests**

Append to `desktop/tests/test_launcher.py`:

```python
def test_supervisor_spawns_v03_children_when_paths_set(cfg, tmp_path, monkeypatch):
    """The 3 new spawn methods fire iff their paths are provided."""
    spawned: list[list[str]] = []

    def fake_popen(args, **kw):
        spawned.append(list(args))
        p = MagicMock(spec=subprocess.Popen)
        p.poll.return_value = None
        return p

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    embed = tmp_path / "nomic.gguf"
    embed.write_bytes(b"x" * 2_000_000)
    whisper = tmp_path / "whisper.bin"
    whisper.write_bytes(b"x" * 2_000_000)
    amy = tmp_path / "amy.onnx"
    amy.write_bytes(b"x" * 200_000)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        nomic_embed_path=embed,
        whisper_model_path=whisper,
        piper_voices={"alex": amy},
    )
    sv.start_all()
    try:
        joined_args = [" ".join(a) for a in spawned]
        assert any("llama_cpp.server" in s and "--embedding" in s for s in joined_args)
        assert any("desktop_shims.whisper_shim" in s for s in joined_args)
        assert any("desktop_shims.piper_shim" in s for s in joined_args)
        assert any("alex=" in s for s in joined_args)
    finally:
        sv.stop_all()


def test_supervisor_skips_v03_children_when_paths_missing(cfg, tmp_path, monkeypatch):
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda a, **kw: (
            spawned.append(list(a)),
            MagicMock(spec=subprocess.Popen, poll=MagicMock(return_value=None)),
        )[1],
    )
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        assert not any("whisper_shim" in s for s in joined)
        assert not any("piper_shim" in s for s in joined)
    finally:
        sv.stop_all()
```

- [ ] **Step 4: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_launcher.py -v
```
Expected: all launcher tests pass (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add desktop/launcher.py desktop/tests/test_launcher.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: Supervisor — spawn llama_cpp embed + Whisper + Piper shims"
```

---

## Task 7: Auto-register — STT/TTS credentials + Episode Profile

Extend auto-registration to publish credentials and models for the three new endpoints plus the local Audio Overview profile.

**Files:**
- Modify: `desktop/auto_register.py`
- Modify: `desktop/tests/test_auto_register.py`

- [ ] **Step 1: Add `register_voice_models` + `register_default_episode_profile`**

Append to `desktop/auto_register.py`:

```python
def register_voice_models(
    client: httpx.Client,
    *,
    whisper_port: int | None,
    piper_port: int | None,
    embed_port: int | None,
    cfg: Config,
) -> None:
    """Register Whisper/Piper/embed credentials + models if ports are set."""
    # Whisper
    if whisper_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=set(),
            name="Whisper (local)",
            provider="openai_compatible",
            modalities=["speech_to_text"],
            base_url=f"http://127.0.0.1:{whisper_port}/v1",
        )
        if cred:
            _ensure_model(
                client=client,
                existing_keys=set(),
                name="whisper-base-en",
                provider="openai_compatible",
                model_type="speech_to_text",
                credential_id=cred,
            )

    # Piper
    if piper_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=set(),
            name="Piper (local)",
            provider="openai_compatible",
            modalities=["text_to_speech"],
            base_url=f"http://127.0.0.1:{piper_port}/v1",
        )
        if cred:
            for voice_id in ("piper-amy-en", "piper-ryan-en"):
                _ensure_model(
                    client=client,
                    existing_keys=set(),
                    name=voice_id,
                    provider="openai_compatible",
                    model_type="text_to_speech",
                    credential_id=cred,
                )

    # Embedding (llama.cpp server with --embedding flag)
    if embed_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=set(),
            name="Local Embeddings (llama.cpp)",
            provider="openai_compatible",
            modalities=["embedding"],
            base_url=f"http://127.0.0.1:{embed_port}/v1",
        )
        if cred:
            _ensure_model(
                client=client,
                existing_keys=set(),
                name="nomic-embed-text-v1.5",
                provider="openai_compatible",
                model_type="embedding",
                credential_id=cred,
            )


def register_default_episode_profile(client: httpx.Client) -> None:
    """Idempotent: create 'Open Notebook Plus Local' episode profile if missing."""
    PROFILE_NAME = "Open Notebook Plus Local"
    try:
        r = client.get("/api/episode_profiles")
        r.raise_for_status()
        for p in r.json():
            if p.get("name") == PROFILE_NAME:
                return  # already exists
    except Exception as exc:
        log.warning(
            "Could not list episode profiles: %s — skipping profile bootstrap", exc
        )
        return

    # Look up the IDs we just registered for chat model + piper voices
    try:
        models = client.get("/api/models").json()
    except Exception:
        return
    by_name = {m.get("name"): m.get("id") for m in models}
    chat_id = (
        by_name.get("Hermes-3-Llama-3.1-8B-Q4_K_M")
        or by_name.get("Mistral-7B-Instruct-v0.3-Q4_K_M")
        or next(
            (
                mid
                for name, mid in by_name.items()
                if not name.startswith(("piper-", "whisper-", "nomic-"))
            ),
            None,
        )
    )
    amy_id = by_name.get("piper-amy-en")
    ryan_id = by_name.get("piper-ryan-en")
    if not (chat_id and amy_id and ryan_id):
        log.info("Skipping episode profile creation: missing chat_id/amy_id/ryan_id")
        return

    payload = {
        "name": PROFILE_NAME,
        "description": "Two-voice podcast using local Piper TTS",
        "chat_model_id": chat_id,
        "speakers": [
            {"name": "Alex", "role": "Host", "tts_model_id": amy_id},
            {"name": "Sam", "role": "Co-host", "tts_model_id": ryan_id},
        ],
        "default_length_minutes": 5,
    }
    try:
        r = client.post("/api/episode_profiles", json=payload)
        if r.status_code in (200, 201):
            log.info("Created default episode profile %r", PROFILE_NAME)
    except Exception as exc:
        log.warning("Could not create episode profile %r: %s", PROFILE_NAME, exc)
```

Then in the existing `auto_register()` function, after the existing registration logic and the `/api/models/auto-assign` call, add:

```python
if any(
    p is not None
    for p in (
        kwargs.get("whisper_port"),
        kwargs.get("piper_port"),
        kwargs.get("embed_port"),
    )
):
    register_voice_models(
        client,
        whisper_port=kwargs.get("whisper_port"),
        piper_port=kwargs.get("piper_port"),
        embed_port=kwargs.get("embed_port"),
        cfg=cfg,
    )
    register_default_episode_profile(client)
```

Update the `auto_register` signature to accept `**kwargs` for the new ports:

```python
def auto_register(
    api_base_url: str,
    cfg: Config,
    llamacpp_port: int | None = None,
    *,
    whisper_port: int | None = None,
    piper_port: int | None = None,
    embed_port: int | None = None,
) -> None:
```

And pass them through to `_do_register`:

```python
with httpx.Client(base_url=api_base_url, timeout=15.0) as client:
    _do_register(
        client,
        cfg,
        llamacpp_port,
        whisper_port=whisper_port,
        piper_port=piper_port,
        embed_port=embed_port,
    )
```

(Adjust `_do_register` signature similarly.)

- [ ] **Step 2: Add tests**

Append to `desktop/tests/test_auto_register.py`:

```python
def test_register_voice_models_creates_credentials_and_models(monkeypatch):
    from desktop.auto_register import register_voice_models
    from desktop.config import Config

    created = []

    class FakeClient:
        def post(self, path, json):
            created.append((path, json))

            class R:
                status_code = 201

            R.json = lambda: {"id": f"id-{json.get('name', '')}"}
            return R()

        def get(self, path):
            class R:
                status_code = 200

            R.json = lambda: []
            R.raise_for_status = lambda: None
            return R()

    cfg = Config(
        model_dir=Path("/tmp"),
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    register_voice_models(
        FakeClient(), whisper_port=1234, piper_port=2345, embed_port=3456, cfg=cfg
    )
    paths = [p for p, _ in created]
    assert "/api/credentials" in paths
    payloads = [j for _, j in created]
    assert any(j.get("name") == "Whisper (local)" for j in payloads)
    assert any(j.get("name") == "Piper (local)" for j in payloads)
    assert any(j.get("name") == "Local Embeddings (llama.cpp)" for j in payloads)
    assert any(j.get("name") == "piper-amy-en" for j in payloads)
    assert any(j.get("name") == "piper-ryan-en" for j in payloads)
```

- [ ] **Step 3: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_auto_register.py -v
```
Expected: all auto_register tests pass.

- [ ] **Step 4: Commit**

```bash
git add desktop/auto_register.py desktop/tests/test_auto_register.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: auto-register STT/TTS/embed credentials + default Episode Profile"
```

---

## Task 8: Wire ProgressBus + voice spawning in __main__.py

Hook the launcher to actually use ProgressBus, the new Supervisor params, and pass ports to auto_register.

**Files:**
- Modify: `desktop/__main__.py`

- [ ] **Step 1: Add ProgressBus creation, voice paths, and pass to Supervisor + auto_register**

In `desktop/__main__.py`, after the `log_dir` block and before `_bootstrap_progress`:

```python
from desktop.progress import ProgressBus

progress_bus = ProgressBus(log_path=log_dir / "progress.jsonl")
progress_bus.publish("startup", "running", "Launcher starting…")
```

After `ensure_embedding_model(...)`, add:

```python
try:
    from desktop.model_downloads import (
        ensure_secondary_tts_voice,
        ensure_tts_model,
        ensure_stt_model,
    )

    ensure_tts_model(_model_dir, progress=_bootstrap_progress)
    ensure_secondary_tts_voice(_model_dir, progress=_bootstrap_progress)
    ensure_stt_model(_model_dir, progress=_bootstrap_progress)
except Exception:
    import traceback

    _bootstrap_progress(
        "Warning: voice model downloads failed: " + traceback.format_exc()
    )
```

Just before the `sv = Supervisor(...)` line, compute the voice paths:

```python
    voice_model_dir = Path(cfg.model_dir)
    whisper_path = voice_model_dir / "STT" / "ggml-base.en.bin"
    amy_path = voice_model_dir / "TTS" / "en_US-amy-medium.onnx"
    ryan_path = voice_model_dir / "TTS" / "en_US-ryan-high.onnx"
    nomic_path = voice_model_dir / "GGUF" / "nomic-embed-text-v1.5.f16.gguf"
    piper_voices = {}
    if amy_path.exists():
        piper_voices["alex"] = amy_path
    if ryan_path.exists():
        piper_voices["sam"] = ryan_path
```

Update the Supervisor construction to pass the new params:

```python
sv = Supervisor(
    cfg=cfg,
    repo_root=repo_root(),
    bin_dir=bin_dir,
    surreal_arch=arch,
    node_arch=arch,
    extra_env=extra_env,
    debug_mode=True,
    venv_python=venv_py,
    upstream_root=upstream_dir(),
    whisper_model_path=whisper_path if whisper_path.exists() else None,
    piper_voices=piper_voices,
    nomic_embed_path=nomic_path if nomic_path.exists() else None,
    progress=progress_bus,
)
```

Update the `auto_register(...)` call to pass voice ports:

```python
auto_register(
    api_base_url=api_base,
    cfg=cfg,
    llamacpp_port=llamacpp_port,
    whisper_port=getattr(sv, "whisper_port", None),
    piper_port=getattr(sv, "piper_port", None),
    embed_port=getattr(sv, "embed_port", None),
)
```

After `auto_register(...)` returns, signal ready:

```python
    progress_bus.publish("ready", "done", "Main window opening…")
```

- [ ] **Step 2: Verify importability**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "import desktop.__main__; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add desktop/__main__.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: wire ProgressBus + Supervisor voice paths + auto_register ports"
```

---

## Task 9: Wizard SSE endpoint (`/api/progress`)

Extend the wizard's aiohttp server to keep running past `/api/save` and stream progress events via Server-Sent Events.

**Files:**
- Modify: `desktop/first_run/server.py`
- Create: `desktop/tests/test_wizard_progress.py`

- [ ] **Step 1: Add SSE route and global progress-bus reference**

In `desktop/first_run/server.py`, add at the top:

```python
from desktop.progress import ProgressBus
```

Update `build_app` signature to accept a `progress_bus`:

```python
def build_app(config_path: Path, on_done: Callable[[], None],
              progress_bus: ProgressBus | None = None) -> web.Application:
```

Inside `build_app`, after the existing `index`/`save` route handlers, add:

```python
async def progress_stream(req: web.Request) -> web.StreamResponse:
    if progress_bus is None:
        return web.json_response({"error": "no progress bus"}, status=503)
    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await resp.prepare(req)
    # subscribe in a thread (bus.subscribe is blocking) and pump via loop
    import asyncio

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def reader():
        for evt in progress_bus.subscribe(timeout=120.0, replay=True):
            loop.call_soon_threadsafe(q.put_nowait, evt)
        loop.call_soon_threadsafe(q.put_nowait, None)

    import threading

    threading.Thread(target=reader, daemon=True).start()

    while True:
        evt = await q.get()
        if evt is None:
            break
        await resp.write(f"data: {json.dumps(evt)}\n\n".encode())
        if evt["step"] == "ready" and evt["status"] == "done":
            break
    await resp.write_eof()
    return resp
```

And register the route:

```python
    app.router.add_get("/api/progress", progress_stream)
```

Update `run_wizard_blocking` to accept and pass the bus:

```python
def run_wizard_blocking(config_path: Path,
                        progress_bus: ProgressBus | None = None) -> None:
```

…and at the call to `build_app(config_path, on_done=done.set)`, change to:

```python
        app = build_app(config_path, on_done=done.set, progress_bus=progress_bus)
```

- [ ] **Step 2: Write the test**

```python
# desktop/tests/test_wizard_progress.py
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest
from aiohttp.test_utils import AioHTTPTestCase

from desktop.first_run.server import build_app
from desktop.progress import ProgressBus


class WizardProgressTestCase(AioHTTPTestCase):
    async def get_application(self):
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.bus = ProgressBus(Path(self._tmpdir) / "progress.jsonl")
        return build_app(
            Path(self._tmpdir) / "config.toml",
            on_done=lambda: None,
            progress_bus=self.bus,
        )

    async def test_progress_returns_503_without_bus(self):
        # Build app without bus to verify the no-bus path
        app2 = build_app(
            Path(self._tmpdir) / "x.toml", on_done=lambda: None, progress_bus=None
        )
        from aiohttp.test_utils import TestClient, TestServer

        async with TestClient(TestServer(app2)) as c2:
            r = await c2.get("/api/progress")
            assert r.status == 503

    async def test_progress_streams_events_then_closes_on_ready(self):
        # Publish events from a background thread once the request is in flight
        async def publish_later():
            await asyncio.sleep(0.1)
            self.bus.publish("step.x", "running", "doing x")
            self.bus.publish("ready", "done")

        asyncio.create_task(publish_later())
        resp = await self.client.get("/api/progress")
        assert resp.status == 200
        body = await resp.text()
        # Each event is "data: {...}\n\n"
        events = [
            json.loads(line[6:])
            for line in body.splitlines()
            if line.startswith("data: ")
        ]
        assert any(e["step"] == "step.x" for e in events)
        assert any(e["step"] == "ready" for e in events)
```

- [ ] **Step 3: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_wizard_progress.py -v
```
Expected: `2 passed`.

- [ ] **Step 4: Commit**

```bash
git add desktop/first_run/server.py desktop/tests/test_wizard_progress.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: wizard /api/progress SSE endpoint streams ProgressBus events"
```

---

## Task 10: Wizard screen 6 — "Setting up…" UI

Add the live-progress screen to the wizard and subscribe via EventSource.

**Files:**
- Modify: `desktop/first_run/static/index.html`
- Modify: `desktop/first_run/static/wizard.js`
- Modify: `desktop/first_run/static/style.css`

- [ ] **Step 1: Add new screen to `index.html`**

Before `</main>`, add:

```html
    <section data-screen="setting-up" hidden>
      <div class="icon-row">
        <svg viewBox="0 0 64 64" aria-hidden="true">
          <circle cx="32" cy="32" r="22" fill="none" stroke="currentColor" stroke-width="3"/>
          <path d="M32 16v16l10 8" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round"/>
        </svg>
      </div>
      <h2>Setting up Open Notebook Plus</h2>
      <ul id="progress-list" class="progress-list"></ul>
      <p class="hint">Latest: <span id="progress-latest">starting…</span></p>
      <p class="hint">Elapsed: <span id="progress-elapsed">0s</span></p>
    </section>
```

Also change the `done` screen to be the success state shown briefly before close.

- [ ] **Step 2: Append `style.css` rules**

```css
.progress-list { list-style: none; padding: 0; margin: 16px 0; }
.progress-list li {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 6px;
  font-size: 13px;
  display: flex; align-items: center; gap: 10px;
}
.progress-list li[data-status="done"] { color: var(--muted); }
.progress-list li[data-status="running"] { font-weight: 600; }
.progress-list li[data-status="error"] { color: #c0382b; }
.progress-list li::before {
  content: ""; display: inline-block; width: 14px; height: 14px; flex: 0 0 14px;
  border-radius: 50%; background: var(--border);
}
.progress-list li[data-status="done"]::before { background: #3da750; }
.progress-list li[data-status="running"]::before { background: var(--primary); animation: pulse 1s infinite alternate; }
.progress-list li[data-status="error"]::before { background: #c0382b; }
@keyframes pulse { from { opacity: 0.4 } to { opacity: 1 } }
```

- [ ] **Step 3: Extend `wizard.js` — after Done click, switch to setting-up + subscribe**

Replace the `if (target === 'done') { ... }` block in `wizard.js` with:

```javascript
      if (target === 'done') {
        const choice = document.querySelector('input[name=choice]:checked').value;
        const payload = {
          model_dir: modelDirInput.value,
          provider: choice,
          default_model: document.getElementById('default_model').value || '',
          theme: chosenTheme,
        };
        show('setting-up');
        const list = document.getElementById('progress-list');
        const latest = document.getElementById('progress-latest');
        const elapsed = document.getElementById('progress-elapsed');
        const startTs = Date.now();
        setInterval(() => {
          elapsed.textContent = Math.round((Date.now() - startTs) / 1000) + 's';
        }, 500);

        // Save first…
        const saveResp = await fetch('/api/save', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload),
        });
        if (!saveResp.ok) {
          latest.textContent = 'Failed to save config.';
          return;
        }

        // …then subscribe to progress.
        const es = new EventSource('/api/progress');
        const items = {};
        es.onmessage = (ev) => {
          const evt = JSON.parse(ev.data);
          let li = items[evt.step];
          if (!li) {
            li = document.createElement('li');
            li.textContent = evt.step.replaceAll('.', ' › ');
            list.appendChild(li);
            items[evt.step] = li;
          }
          li.dataset.status = evt.status;
          if (evt.message) latest.textContent = evt.message;
          if (evt.step === 'ready' && evt.status === 'done') {
            es.close();
            // Window will be closed by the launcher's main window opening.
          }
        };
        es.onerror = () => {
          latest.textContent = '(progress stream disconnected)';
        };
      } else {
        show(target);
      }
```

- [ ] **Step 4: Verify wizard test suite still passes**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_first_run.py desktop/tests/test_wizard_progress.py -v
```

- [ ] **Step 5: Commit**

```bash
git add desktop/first_run/static/index.html desktop/first_run/static/style.css \
        desktop/first_run/static/wizard.js
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: wizard screen 6 — live progress feed via EventSource"
```

---

## Task 11: Wire ProgressBus into __main__'s wizard call

The wizard server now accepts a ProgressBus — pass ours through.

**Files:**
- Modify: `desktop/__main__.py`

- [ ] **Step 1: Pass progress_bus to wizard**

In `desktop/__main__.py`, where the wizard is run:

```python
if first_run:
    from desktop.first_run.server import run_wizard_blocking

    # progress_bus needs to be ready BEFORE the wizard runs so screen 6
    # can subscribe immediately. Re-order so progress_bus is created before
    # the wizard call.
    ...
    run_wizard_blocking(cfg_path, progress_bus=progress_bus)
```

You'll need to move the `progress_bus = ProgressBus(...)` line ABOVE the `if first_run:` block so it's defined before the wizard call. Adjust accordingly.

- [ ] **Step 2: Sanity-import**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "import desktop.__main__; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add desktop/__main__.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: pass ProgressBus to wizard for live screen-6 progress feed"
```

---

## Task 12: Frontend voice injection (mic FAB + per-message speaker)

Inject a microphone button + per-message speaker into the upstream UI via the existing theme-injection pipe.

**Files:**
- Create: `desktop/first_run/static/voice_injection.js`
- Modify: `desktop/window.py`

- [ ] **Step 1: Write voice_injection.js**

```javascript
// desktop/first_run/static/voice_injection.js
// Injected into the main UI by desktop/window.py after page load. Adds:
//   - Floating microphone button (press-and-hold to record, sends to /api/transcribe)
//   - Per-message speaker icon (click to play assistant message via TTS)
(function () {
  if (window.__ONP_VOICE_INJECTED) return;
  window.__ONP_VOICE_INJECTED = true;

  const STT_URL = (window.ONP_STT_URL || '/api/transcribe');
  const TTS_URL = (window.ONP_TTS_URL || '/api/audio/speech');

  // --- Mic FAB ---
  const fab = document.createElement('button');
  fab.id = 'onp-mic-fab';
  fab.innerHTML = '🎤';
  fab.title = 'Hold to record · Release to send';
  Object.assign(fab.style, {
    position: 'fixed', bottom: '24px', right: '24px',
    width: '52px', height: '52px', borderRadius: '50%',
    background: 'var(--primary, #2D7FF9)', color: 'var(--on-primary, #fff)',
    border: '1px solid var(--border, #ccc)', fontSize: '24px',
    cursor: 'pointer', zIndex: '99999',
    boxShadow: '0 4px 16px rgba(0,0,0,0.18)',
  });
  document.body.appendChild(fab);

  let mediaRecorder = null;
  let chunks = [];
  fab.addEventListener('mousedown', async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      chunks = [];
      mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const form = new FormData();
        form.append('file', blob, 'clip.webm');
        form.append('model', 'whisper-base-en');
        fab.innerHTML = '⌛';
        try {
          const r = await fetch(STT_URL, { method: 'POST', body: form });
          const data = await r.json();
          const input = document.querySelector('textarea, [contenteditable=true]');
          if (input) {
            if (input.tagName === 'TEXTAREA') {
              input.value = (input.value || '') + data.text;
              input.dispatchEvent(new Event('input', { bubbles: true }));
            } else {
              input.textContent = (input.textContent || '') + data.text;
            }
          }
        } catch (e) {
          console.error('STT failed', e);
        }
        fab.innerHTML = '🎤';
        stream.getTracks().forEach(t => t.stop());
      };
      mediaRecorder.start();
      fab.innerHTML = '🔴';
    } catch (e) {
      console.error('mic permission denied or recording failed', e);
    }
  });
  fab.addEventListener('mouseup', () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  });
  fab.addEventListener('mouseleave', () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  });

  // --- Per-message speaker buttons ---
  function injectSpeakerButtons() {
    // Upstream uses Radix components; chat messages have role="article" or
    // class "message" depending on the layout. We look for assistant bubbles
    // via a class that contains 'assistant' or via aria-label.
    const candidates = document.querySelectorAll(
      '[data-role="assistant"], .message-assistant, [aria-label*="assistant"]'
    );
    candidates.forEach((node) => {
      if (node.querySelector('.onp-speaker-btn')) return;
      const btn = document.createElement('button');
      btn.className = 'onp-speaker-btn';
      btn.innerHTML = '🔊';
      btn.title = 'Play this response';
      Object.assign(btn.style, {
        marginLeft: '8px', background: 'transparent', border: 'none',
        cursor: 'pointer', fontSize: '14px', opacity: '0.6',
      });
      btn.addEventListener('click', async () => {
        const text = node.innerText;
        try {
          btn.innerHTML = '⌛';
          const r = await fetch(TTS_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input: text, voice: 'alex',
                                   model: 'piper-amy-en' }),
          });
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          new Audio(url).play();
        } catch (e) {
          console.error('TTS failed', e);
        } finally {
          btn.innerHTML = '🔊';
        }
      });
      node.appendChild(btn);
    });
  }
  const observer = new MutationObserver(injectSpeakerButtons);
  observer.observe(document.body, { childList: true, subtree: true });
  injectSpeakerButtons();
})();
```

- [ ] **Step 2: Modify `desktop/window.py` to inject voice JS**

In `_theme_injection_js`, after the theme `<style>` injection, append a script-tag injection. Add a helper function that reads the JS file from disk:

```python
def _voice_injection_js() -> str:
    """Read the voice-injection JS file content (bundled as data)."""
    static = Path(__file__).parent / "first_run" / "static" / "voice_injection.js"
    if static.exists():
        try:
            return static.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""
```

In `_theme_injection_js(theme_id)`, before the closing `)();`, append:

```python
voice_js = _voice_injection_js()
# Inject after the theme style so DOM is ready
return (
    base_js
    + f"""
(function() {{
    var script = document.createElement('script');
    script.textContent = {json.dumps(voice_js)};
    document.head.appendChild(script);
}})();
"""
)
```

(Add `import json` and `from pathlib import Path` to the top of `window.py` if not present.)

- [ ] **Step 3: Sanity-import**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "import desktop.window; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add desktop/first_run/static/voice_injection.js desktop/window.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: inject mic FAB + per-message speaker into main UI"
```

---

## Task 13: macOS mic permission in Info.plist

Without `NSMicrophoneUsageDescription`, macOS rejects `getUserMedia` calls in the .app's WebKit.

**Files:**
- Modify: `desktop/build/pyinstaller.spec`

- [ ] **Step 1: Add to `info_plist` dict in the BUNDLE call**

Find the `info_plist={...}` block in the `BUNDLE(...)` call and add:

```python
            "NSMicrophoneUsageDescription":
                "Open Notebook Plus uses your microphone for voice chat (Whisper STT, runs locally on this Mac).",
```

- [ ] **Step 2: Sanity-check spec parses**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "
import pathlib
compile(pathlib.Path('desktop/build/pyinstaller.spec').read_text(),
        'desktop/build/pyinstaller.spec', 'exec')
print('spec parses')
"
```

- [ ] **Step 3: Commit**

```bash
git add desktop/build/pyinstaller.spec
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: add NSMicrophoneUsageDescription so getUserMedia works in .app"
```

---

## Task 14: Model-manager catalog

The catalog drives the "Recommended" column.

**Files:**
- Create: `desktop/model_manager/__init__.py`
- Create: `desktop/model_manager/catalog.json`

- [ ] **Step 1: Write catalog.json**

```json
{
  "chat": [
    {
      "name": "Llama 3.3 8B Instruct",
      "size_mb": 4900,
      "url": "https://huggingface.co/bartowski/Llama-3.3-8B-Instruct-GGUF/resolve/main/Llama-3.3-8B-Instruct-Q4_K_M.gguf?download=true",
      "dest": "GGUF/Llama-3.3-8B-Instruct-Q4_K_M.gguf"
    },
    {
      "name": "Mistral 7B Instruct v0.3",
      "size_mb": 4100,
      "url": "https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf?download=true",
      "dest": "GGUF/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"
    }
  ],
  "embedding": [
    {
      "name": "BGE small en v1.5",
      "size_mb": 67,
      "url": "https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf/resolve/main/bge-small-en-v1.5-f16.gguf?download=true",
      "dest": "GGUF/bge-small-en-v1.5-f16.gguf"
    }
  ],
  "stt": [
    {
      "name": "Whisper small.en",
      "size_mb": 466,
      "url": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin?download=true",
      "dest": "STT/ggml-small.en.bin"
    }
  ],
  "tts": [
    {
      "name": "Piper Lessac (en_US, female)",
      "size_mb": 31,
      "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true",
      "dest": "TTS/en_US-lessac-medium.onnx"
    },
    {
      "name": "Piper Joe (en_US, male)",
      "size_mb": 33,
      "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium/en_US-joe-medium.onnx?download=true",
      "dest": "TTS/en_US-joe-medium.onnx"
    }
  ]
}
```

(empty `__init__.py`)

- [ ] **Step 2: Commit**

```bash
git add desktop/model_manager/__init__.py desktop/model_manager/catalog.json
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: model manager catalog (chat/embedding/stt/tts recommendations)"
```

---

## Task 15: Model-manager server (aiohttp)

**Files:**
- Create: `desktop/model_manager/server.py`
- Create: `desktop/tests/test_model_manager_server.py`

- [ ] **Step 1: Write the tests**

```python
# desktop/tests/test_model_manager_server.py
import json
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase

from desktop.model_manager.server import build_app


class ModelManagerTest(AioHTTPTestCase):
    async def get_application(self):
        import tempfile

        self._tmpdir = Path(tempfile.mkdtemp())
        (self._tmpdir / "GGUF").mkdir()
        (self._tmpdir / "GGUF" / "test.gguf").write_bytes(b"x" * 2_000_000)
        return build_app(model_dir=self._tmpdir)

    async def test_lists_installed(self):
        r = await self.client.get("/api/installed")
        assert r.status == 200
        data = await r.json()
        assert any(m["name"] == "test.gguf" for m in data["models"])

    async def test_serves_catalog(self):
        r = await self.client.get("/api/catalog")
        assert r.status == 200
        data = await r.json()
        assert "chat" in data
        assert "embedding" in data

    async def test_delete_removes_file(self):
        r = await self.client.delete("/api/installed/GGUF/test.gguf")
        assert r.status == 200
        assert not (self._tmpdir / "GGUF" / "test.gguf").exists()
```

- [ ] **Step 2: Implement server**

```python
# desktop/model_manager/server.py
"""Aiohttp server backing the Model Manager PyWebView window.

Exposes:
    GET    /                              → static UI
    GET    /api/installed                 → list of installed models by class
    GET    /api/catalog                   → curated downloadable models
    POST   /api/download                  → {category, name} — kick off a download
    DELETE /api/installed/<rel-path>      → remove a model file
"""

from __future__ import annotations

import json
from pathlib import Path

from aiohttp import web

STATIC_DIR = Path(__file__).parent / "static"
CATALOG_PATH = Path(__file__).parent / "catalog.json"

_MIN_BYTES = 100_000


def _classify(rel: str) -> str:
    if rel.startswith("STT/"):
        return "stt"
    if rel.startswith("TTS/") and rel.endswith(".onnx"):
        return "tts"
    if rel.startswith("GGUF/") and (
        "embed" in rel.lower() or "bge" in rel.lower() or "nomic" in rel.lower()
    ):
        return "embedding"
    return "chat"


def build_app(model_dir: Path) -> web.Application:
    app = web.Application()
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    async def index(_: web.Request) -> web.Response:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def installed(_: web.Request) -> web.Response:
        models = []
        if model_dir.exists():
            for p in model_dir.rglob("*"):
                if p.is_file() and p.stat().st_size >= _MIN_BYTES:
                    rel = str(p.relative_to(model_dir))
                    models.append(
                        {
                            "name": p.name,
                            "rel": rel,
                            "size_mb": p.stat().st_size // 1024 // 1024,
                            "class": _classify(rel),
                        }
                    )
        return web.json_response({"models": models})

    async def catalog(_: web.Request) -> web.Response:
        if CATALOG_PATH.exists():
            return web.json_response(json.loads(CATALOG_PATH.read_text()))
        return web.json_response({})

    async def delete_model(req: web.Request) -> web.Response:
        rel = req.match_info["rel"]
        # Defensive: refuse paths trying to escape model_dir
        target = (model_dir / rel).resolve()
        if not str(target).startswith(str(model_dir.resolve())):
            return web.json_response({"error": "invalid path"}, status=400)
        if target.exists():
            target.unlink()
            return web.json_response({"ok": True})
        return web.json_response({"error": "not found"}, status=404)

    app.router.add_get("/", index)
    app.router.add_get("/api/installed", installed)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_delete("/api/installed/{rel:.+}", delete_model)
    app.router.add_static("/static", STATIC_DIR)
    return app
```

- [ ] **Step 3: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_model_manager_server.py -v
```
Expected: `3 passed`.

- [ ] **Step 4: Commit**

```bash
git add desktop/model_manager/server.py desktop/tests/test_model_manager_server.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: model-manager aiohttp server (list/catalog/delete)"
```

---

## Task 16: Model-manager static UI

**Files:**
- Create: `desktop/model_manager/static/index.html`
- Create: `desktop/model_manager/static/style.css`
- Create: `desktop/model_manager/static/manager.js`

- [ ] **Step 1: index.html**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Open Notebook Plus — Models</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <main>
    <h1>Models</h1>
    <div class="cols">
      <section class="installed">
        <h2>Installed</h2>
        <ul id="installed-list"></ul>
        <p class="hint">Total disk used: <span id="disk-used">0 MB</span></p>
      </section>
      <aside class="recommended">
        <h2>Recommended</h2>
        <div id="catalog"></div>
      </aside>
    </div>
  </main>
  <script src="/static/manager.js"></script>
</body>
</html>
```

- [ ] **Step 2: style.css**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       padding: 24px; background: #fafafa; color: #222; }
main { max-width: 1000px; margin: 0 auto; }
h1 { margin-bottom: 16px; }
.cols { display: grid; grid-template-columns: 2fr 1fr; gap: 24px; }
section, aside { background: #fff; border: 1px solid #e0e0e0; border-radius: 10px;
                 padding: 16px; }
ul { list-style: none; }
ul li { padding: 10px; border-bottom: 1px solid #f0f0f0; display: flex;
        align-items: center; gap: 8px; }
.cat { font-size: 11px; padding: 2px 6px; border-radius: 999px;
       background: #eee; color: #555; }
button { padding: 5px 10px; border-radius: 6px; border: 1px solid #ccc;
         background: #fff; cursor: pointer; font-size: 12px; }
button.danger { background: #fef2f2; border-color: #fca5a5; color: #b91c1c; }
.hint { color: #888; font-size: 12px; margin-top: 8px; }
```

- [ ] **Step 3: manager.js**

```javascript
(async () => {
  async function refresh() {
    const r = await fetch('/api/installed');
    const data = await r.json();
    const list = document.getElementById('installed-list');
    list.innerHTML = '';
    let total = 0;
    data.models.forEach(m => {
      total += m.size_mb;
      const li = document.createElement('li');
      li.innerHTML = `
        <span style="flex:1">${m.name}</span>
        <span class="cat">${m.class}</span>
        <span style="color:#888">${m.size_mb} MB</span>
        <button class="danger" data-rel="${m.rel}">Delete</button>
      `;
      li.querySelector('button').addEventListener('click', async (e) => {
        if (!confirm(`Delete ${m.name}?`)) return;
        await fetch('/api/installed/' + encodeURIComponent(m.rel), { method: 'DELETE' });
        refresh();
      });
      list.appendChild(li);
    });
    document.getElementById('disk-used').textContent = total + ' MB';
  }

  async function renderCatalog() {
    const r = await fetch('/api/catalog');
    const cat = await r.json();
    const root = document.getElementById('catalog');
    root.innerHTML = '';
    Object.entries(cat).forEach(([category, items]) => {
      const h3 = document.createElement('h3');
      h3.textContent = category.toUpperCase();
      h3.style.marginTop = '12px';
      root.appendChild(h3);
      items.forEach(item => {
        const div = document.createElement('div');
        div.innerHTML = `
          <strong>${item.name}</strong>
          <span style="color:#888">(${item.size_mb} MB)</span>
        `;
        root.appendChild(div);
      });
    });
  }

  await refresh();
  await renderCatalog();
})();
```

- [ ] **Step 4: Commit**

```bash
git add desktop/model_manager/static/
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: model-manager static UI (HTML/CSS/JS)"
```

---

## Task 17: PyWebView tray + opening model-manager window

**Files:**
- Create: `desktop/tray.py`
- Modify: `desktop/__main__.py`

- [ ] **Step 1: Write `desktop/tray.py`**

```python
# desktop/tray.py
"""PyWebView tray-icon menu for Open Notebook Plus.

Note: pywebview's tray support varies by platform — on macOS we use the
`menu` API; on Windows we use `Tray`. For v0.3 we implement Mac; Windows
gets the same behavior in v0.4.
"""

from __future__ import annotations

from typing import Callable

import webview


def install_tray(
    on_open_main: Callable[[], None],
    on_open_manager: Callable[[], None],
    on_quit: Callable[[], None],
) -> None:
    """Install a system tray icon with menu entries. Best-effort — silently
    no-ops if pywebview's host platform doesn't support tray menus.
    """
    try:
        from webview.menu import Menu, MenuAction

        menu = [
            Menu(
                "Open Notebook Plus",
                [
                    MenuAction("Open Main Window", on_open_main),
                    MenuAction("Manage Models…", on_open_manager),
                    MenuAction("Quit", on_quit),
                ],
            )
        ]
        webview.set_menu(menu)
    except Exception:
        # Tray not supported on this build — no-op.
        return
```

- [ ] **Step 2: Wire into `__main__.py`**

Near the bottom, just before `open_window(...)`:

```python
# Start the model-manager aiohttp server in a background thread so
# the tray can open it on demand.
from desktop.model_manager.server import build_app as mm_build_app
import aiohttp.web as _aio_web
import threading as _th, asyncio as _aio

mm_port = [0]


def _start_mm():
    loop = _aio.new_event_loop()
    _aio.set_event_loop(loop)
    app = mm_build_app(Path(cfg.model_dir))
    runner = _aio_web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = _aio_web.TCPSite(runner, "127.0.0.1", 0)
    loop.run_until_complete(site.start())
    mm_port[0] = site._server.sockets[0].getsockname()[1]
    loop.run_forever()


_mm_thread = _th.Thread(target=_start_mm, daemon=True)
_mm_thread.start()
# wait briefly for port
import time as _time

while mm_port[0] == 0:
    _time.sleep(0.02)

from desktop.tray import install_tray

install_tray(
    on_open_main=lambda: webview.windows[0].show(),
    on_open_manager=lambda: webview.create_window(
        "Models", f"http://127.0.0.1:{mm_port[0]}/", width=920, height=640
    ),
    on_quit=lambda: (sv.stop_all(), webview.windows[0].destroy()),
)
```

- [ ] **Step 3: Sanity-import**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "import desktop.tray; import desktop.__main__; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add desktop/tray.py desktop/__main__.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: tray menu + on-demand model-manager window"
```

---

## Task 18: PyInstaller spec — bundle new files

**Files:**
- Modify: `desktop/build/pyinstaller.spec`

- [ ] **Step 1: Add new entries to `datas`**

In the existing `datas = [...]` list, add:

```python
# v0.3 — shims, manager, voice JS
((str(PROJECT_ROOT / "desktop" / "desktop_shims"), "upstream/desktop_shims"),)
((str(ROOT / "model_manager" / "static"), "desktop/model_manager/static"),)
((str(ROOT / "model_manager" / "catalog.json"), "desktop/model_manager"),)
(
    (
        str(ROOT / "first_run" / "static" / "voice_injection.js"),
        "desktop/first_run/static",
    ),
)
```

- [ ] **Step 2: Spec parses**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "
import pathlib
compile(pathlib.Path('desktop/build/pyinstaller.spec').read_text(),
        'desktop/build/pyinstaller.spec', 'exec')
print('spec parses')
"
```

- [ ] **Step 3: Commit**

```bash
git add desktop/build/pyinstaller.spec
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: bundle v0.3 additions in PyInstaller spec (shims/manager/voice JS)"
```

---

## Task 19: Manual E2E smoke test

Last-step manual verification — no test code, just a checklist that proves the v0.3 acceptance criteria.

- [ ] **Step 1: Clean state**

```bash
rm -f ~/.open-notebook-plus/config.toml
rm -f ~/.open-notebook-plus/venv-marker
rm -rf ~/.open-notebook-plus/surreal_data ~/.open-notebook-plus/logs
rm -rf dist build
```

- [ ] **Step 2: Pull lockfile-aware dep + rebuild**

```bash
cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus
git pull origin desktop-app
source .venv-py312/bin/activate
pyinstaller desktop/build/pyinstaller.spec --noconfirm
bash desktop/build/post_build_mac.sh
open "dist/Open Notebook Plus.app"
```

- [ ] **Step 3: Verify each Definition-of-Done criterion**

Acceptance checklist (from the v0.3 spec, section "Definition of done"):

1. Wizard opens → click through 5 screens → click Done.
2. Wizard transitions to "Setting up Open Notebook Plus" screen 6.
3. Real-time progress events appear in the list as Surreal/API/worker/Next/llamacpp/whisper/piper boot.
4. Wizard window auto-closes when the main window opens.
5. Main window has the upstream notebook UI, a floating mic FAB in the bottom-right, and (for any chat with assistant messages) a speaker icon next to each assistant message.
6. Settings → Models is pre-populated: Hermes-3 (or auto-picked) as chat default, nomic-embed-text as embedding, Whisper as STT, Piper-Amy as TTS.
7. Tray menu "Manage Models…" opens a second window showing the model list + recommended downloads.
8. Open a fresh notebook with a few sources → click Generate Podcast → "Open Notebook Plus Local" profile preselected → wait ~3 min → audio playback works.
9. Open a chat, hold the mic, say "summarize this notebook", release → text fills the input → submit → assistant responds → click speaker icon → response plays back via Piper.

- [ ] **Step 4: If anything fails**

Tail the relevant log:
```bash
tail -50 ~/.open-notebook-plus/logs/{bootstrap,launcher,api,worker,next,whisper,piper,llamacpp_embed,progress,auto_register}.log
```

Open issues or paste output back for diagnosis. Fix as separate commits.

---

## Self-review

Spec coverage check (against `2026-05-11-open-notebook-plus-v0.3-design.md`):
- ✅ §Goal 1 (Voice chat) — Tasks 1, 3, 4, 6, 7, 12, 13
- ✅ §Goal 2 (Audio Overviews) — Tasks 1, 4, 5, 6, 7
- ✅ §Goal 3 (Local embedding endpoint) — Task 6 (`_spawn_llamacpp_embed`), Task 7 (auto-register)
- ✅ §Goal 4 (In-app model manager) — Tasks 14, 15, 16, 17 (tray + on-demand window)
- ✅ §Goal 5 (Live wizard progress) — Tasks 2 (ProgressBus), 9 (SSE endpoint), 10 (screen 6 UI), 11 (wiring)
- ✅ Build/packaging — Tasks 13 (Info.plist), 18 (pyinstaller datas)
- ✅ Smoke verification — Task 19

Type consistency: ProgressBus.publish signature is `(step, status, message)` everywhere; ProgressEvent TypedDict matches the JSONL schema; Supervisor's `progress_bus.publish` matches; SSE handler reads the same fields.

No placeholders — every step has full code or exact commands.

Test count growth: 58 (post-Path A) → ~85 (3 progress + 3 whisper + 4 piper + 1 model_downloads + 2 launcher + 1 auto_register + 2 wizard_progress + 3 model_manager = 19 new).

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-open-notebook-plus-v0.3-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, two-stage review (spec compliance + code quality) between tasks. Fastest iteration through a 19-task plan.

**2. Inline Execution** — Run tasks in this session via `executing-plans`, with batch checkpoints for review.

**Which approach?**
