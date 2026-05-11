"""Entry point — `python -m desktop` — see desktop/app.py for orchestration.

On first launch (after the wizard), bootstrap.ensure_venv() uses the bundled
uv binary and python-build-standalone interpreter to create
~/.open-notebook-plus/venv and install upstream deps (~30-60s). Subsequent
launches skip bootstrapping when requirements.lock hasn't changed.

The supervisor spawns FastAPI/worker/llama-cpp using the venv's Python
interpreter rather than the frozen launcher binary, so no internal dispatcher
tricks are needed.
"""
from __future__ import annotations

import sys

from desktop.app import run

if __name__ == "__main__":
    sys.exit(run())
