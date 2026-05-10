import json
from pathlib import Path

import pytest
from aiohttp.test_utils import AioHTTPTestCase

from desktop.first_run.server import build_app


class WizardTestCase(AioHTTPTestCase):
    cfg_path: Path

    async def get_application(self):
        return build_app(self.cfg_path, on_done=lambda: None)

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.cfg_path = Path(self._tmpdir) / "config.toml"
        super().setUp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().tearDown()

    async def test_get_index_returns_html(self):
        resp = await self.client.get("/")
        assert resp.status == 200
        assert "text/html" in resp.headers["Content-Type"]
        body = await resp.text()
        assert "open-notebook-Plus" in body

    async def test_post_save_writes_config(self):
        payload = {"model_dir": str(self.cfg_path.parent / "AI"),
                   "provider": "llamacpp", "default_model": "x.gguf"}
        resp = await self.client.post("/api/save", data=json.dumps(payload),
                                      headers={"Content-Type": "application/json"})
        assert resp.status == 200
        assert self.cfg_path.exists()
        text = self.cfg_path.read_text()
        assert "provider = " in text and "llamacpp" in text
        assert "default_model = " in text and "x.gguf" in text

    async def test_post_save_rejects_invalid_provider(self):
        payload = {"model_dir": "/tmp", "provider": "bogus", "default_model": ""}
        resp = await self.client.post("/api/save", data=json.dumps(payload),
                                      headers={"Content-Type": "application/json"})
        assert resp.status == 400


@pytest.mark.asyncio
async def test_build_app_returns_aiohttp_application(tmp_path):
    from aiohttp import web
    app = build_app(tmp_path / "config.toml", on_done=lambda: None)
    assert isinstance(app, web.Application)
