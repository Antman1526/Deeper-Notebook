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
