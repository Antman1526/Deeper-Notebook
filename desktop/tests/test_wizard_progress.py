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
        # Build a separate app without a bus to verify the no-bus path
        import tempfile

        tmp2 = tempfile.mkdtemp()
        app2 = build_app(Path(tmp2) / "x.toml", on_done=lambda: None, progress_bus=None)
        from aiohttp.test_utils import TestClient, TestServer

        async with TestClient(TestServer(app2)) as c2:
            r = await c2.get("/api/progress")
            assert r.status == 503

    async def test_progress_streams_events_then_closes_on_ready(self):
        # Publish events from a background task once the request is in flight
        async def publish_later():
            await asyncio.sleep(0.1)
            self.bus.publish("step.x", "running", "doing x")
            self.bus.publish("ready", "done")

        asyncio.create_task(publish_later())
        resp = await self.client.get("/api/progress")
        assert resp.status == 200
        body = await resp.text()
        events = [
            json.loads(line[6:])
            for line in body.splitlines()
            if line.startswith("data: ")
        ]
        assert any(e["step"] == "step.x" for e in events)
        assert any(e["step"] == "ready" for e in events)
