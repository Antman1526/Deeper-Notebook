import json
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase

from desktop.model_manager import server
from desktop.model_manager.server import build_app


def test_build_app_accepts_config_path_without_resolving_data_root(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.toml"
    config_path.write_text("theme='dracula'")

    def unexpected_resolution():
        raise AssertionError("injected config must avoid data-root resolution")

    monkeypatch.setattr(server, "active_data_root", unexpected_resolution)

    app = build_app(model_dir=tmp_path / "models", config_path=config_path)

    assert app[server.CONFIG_PATH_KEY] == config_path


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


class PathTraversalTest(AioHTTPTestCase):
    """v0.6.31 — defense against path-traversal in DELETE /api/installed/{rel}.

    The old check used str.startswith on resolved paths, which has a
    well-known prefix-without-separator bug: a model_dir of
    "/Users/foo/models" passes "/Users/foo/models_evil/secret.gguf"
    because "/Users/foo/models_evil/..." literally starts with
    "/Users/foo/models". Use Path.is_relative_to instead."""

    async def get_application(self):
        import tempfile

        self._root = Path(tempfile.mkdtemp())
        # Two sibling dirs — model_dir and a "sensitive" dir next to it.
        self._model_dir = self._root / "models"
        self._sensitive_dir = self._root / "models_evil"
        self._model_dir.mkdir()
        self._sensitive_dir.mkdir()
        # A file outside model_dir that should NEVER be deletable
        self._victim = self._sensitive_dir / "should_not_be_deleted.gguf"
        self._victim.write_bytes(b"sensitive data")
        # A real file inside model_dir
        (self._model_dir / "GGUF").mkdir()
        (self._model_dir / "GGUF" / "real.gguf").write_bytes(b"x" * 2_000_000)
        return build_app(model_dir=self._model_dir)

    async def test_dotdot_traversal_rejected(self):
        """A `rel` with ../ that resolves outside model_dir must be rejected."""
        # Try: GGUF/../../models_evil/should_not_be_deleted.gguf
        r = await self.client.delete(
            "/api/installed/GGUF/..%2F..%2Fmodels_evil%2Fshould_not_be_deleted.gguf"
        )
        # Either rejected explicitly or 404 (because the dotdot escapes), but
        # the victim file MUST still exist.
        assert self._victim.exists(), (
            "victim file outside model_dir was deleted by dotdot traversal"
        )
        assert r.status in (400, 404)

    async def test_sibling_prefix_traversal_rejected(self):
        """The actual v0.6.31 bug. model_dir is `.../models`. A path that
        resolves to `.../models_evil/x` used to pass startswith but not
        is_relative_to. This test isn't easy to trigger directly through
        the URL (the request path is interpreted by aiohttp), so we exercise
        the underlying behavior via raw resolve below."""
        # The aiohttp route won't accept a literal `..` in the URL segment,
        # so this test directly exercises the resolved-path logic.
        from pathlib import Path as _P

        bad = (
            (self._model_dir / "..").resolve()
            / "models_evil"
            / "should_not_be_deleted.gguf"
        )
        root = self._model_dir.resolve()
        assert not bad.is_relative_to(root), (
            "Path.is_relative_to should reject /Users/.../models_evil/... "
            "as not being a child of /Users/.../models"
        )
        # str-startswith is what the OLD code did, and would have INCORRECTLY
        # passed this path. Verify so we know the test guards a real bug.
        assert str(bad).startswith(str(root)), (
            "this assertion documents that the OLD str.startswith check "
            "would have FALSELY accepted this path"
        )

    async def test_real_inside_file_still_deletes(self):
        """Sanity: hardened check still allows legitimate deletes."""
        r = await self.client.delete("/api/installed/GGUF/real.gguf")
        assert r.status == 200
        assert not (self._model_dir / "GGUF" / "real.gguf").exists()


class SymlinkTraversalTest(AioHTTPTestCase):
    """v0.6.31 — symlinks pointing outside model_dir are caught by resolve(),
    but ensure the explicit guard also catches them as a belt-and-suspenders."""

    async def get_application(self):
        import os
        import tempfile

        self._root = Path(tempfile.mkdtemp())
        self._model_dir = self._root / "models"
        self._model_dir.mkdir()
        self._victim = self._root / "victim.gguf"
        self._victim.write_bytes(b"sensitive")
        # Symlink inside model_dir → victim outside
        self._link = self._model_dir / "evil-link.gguf"
        os.symlink(str(self._victim), str(self._link))
        return build_app(model_dir=self._model_dir)

    async def test_symlink_pointing_outside_rejected(self):
        r = await self.client.delete("/api/installed/evil-link.gguf")
        # The symlink target is outside model_dir → 400 or 404 either way
        assert r.status in (400, 404)
        # And the victim file is untouched
        assert self._victim.exists()
