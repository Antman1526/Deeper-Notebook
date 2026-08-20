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
        assert "Deeper Notebook" in body
        assert "Open Notebook Plus" not in body
        assert 'value="mlx"' in body

    async def test_post_save_writes_config(self):
        payload = {
            "model_dir": str(self.cfg_path.parent / "AI"),
            "provider": "llamacpp",
            "default_model": "x.gguf",
        }
        resp = await self.client.post(
            "/api/save",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        assert self.cfg_path.exists()
        text = self.cfg_path.read_text()
        assert "provider = " in text and "llamacpp" in text
        assert "default_model = " in text and "x.gguf" in text

    async def test_post_save_accepts_mlx_provider(self):
        payload = {
            "model_dir": str(self.cfg_path.parent / "AI"),
            "provider": "mlx",
            "default_model": "MLX/mlx-community__North-Mini-Code-1.0-6bit",
        }
        resp = await self.client.post(
            "/api/save",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        text = self.cfg_path.read_text()
        assert "provider = " in text and "mlx" in text
        assert "MLX/mlx-community__North-Mini-Code-1.0-6bit" in text

    async def test_post_save_rejects_invalid_provider(self):
        payload = {"model_dir": "/tmp", "provider": "bogus", "default_model": ""}
        resp = await self.client.post(
            "/api/save",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400


@pytest.mark.asyncio
async def test_build_app_returns_aiohttp_application(tmp_path):
    from aiohttp import web

    app = build_app(tmp_path / "config.toml", on_done=lambda: None)
    assert isinstance(app, web.Application)


class DismissOpenChronicleTestCase(AioHTTPTestCase):
    """v0.6.28 regression: dismiss-openchronicle handler used to manually
    enumerate every Config field when rebuilding the dataclass — so any
    NEW field added to Config would silently revert to its default the
    next time the user dismissed the reminder. The fix uses
    dataclasses.replace, which preserves every field automatically.

    This test pre-populates a config with a non-default theme + provider
    combo, hits the dismiss endpoint, and asserts the OTHER fields are
    still intact afterwards.
    """

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

    async def test_dismiss_preserves_all_other_config_fields(self):
        # Seed a config with non-default values
        from desktop.config import Config

        original = Config(
            model_dir=Path(self._tmpdir) / "models",
            provider="ollama",
            default_model="qwen-7b",
            surreal_user="root",
            surreal_password="x" * 32,
            theme="dracula",
            openchronicle_choice="prompt",
            encryption_key="Y" * 43,
        )
        original.save(self.cfg_path)

        resp = await self.client.post(
            "/api/config/dismiss_openchronicle_reminder",
            data="{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200

        # Reload + check: openchronicle_choice flipped to "skip", everything
        # else preserved exactly.
        from desktop.config import load_or_create

        reloaded = load_or_create(self.cfg_path)
        assert reloaded.openchronicle_choice == "skip"  # what we changed
        # The crucial assertions — everything else preserved
        assert reloaded.theme == "dracula"
        assert reloaded.provider == "ollama"
        assert reloaded.default_model == "qwen-7b"
        assert reloaded.surreal_password == "x" * 32
        assert reloaded.encryption_key == "Y" * 43
        assert reloaded.surreal_user == "root"
