"""v0.7.143 — Next.js rewrites patcher tests.

The real user bug this fixes: browser showed "API config endpoint
returned status 500" with attempted URL `http://127.0.0.1:53018/api/config`.

The API was actually fine — Next.js was the broken piece. Next.js's
standalone build bakes the rewrite destination at BUILD time
(default `localhost:5055` from next.config.ts:33). The launcher
allocates DYNAMIC ports per session. So every `/api/*` request the
frontend made got proxied to a port that didn't exist.

This file pins:

  1. The patcher reads pristine `.orig` backups, not the live files
     (so re-patching doesn't compound previous edits).
  2. It writes to the same path the standalone server reads from
     (or to a writable copy if the source is read-only).
  3. It refuses to claim success when no `localhost:5055` strings
     were found (suggests next.config.ts was refactored — caller
     should investigate, not silently launch broken).
  4. `restore_originals` is a clean round-trip back to the baked
     state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Sample manifest contents matching what Next.js standalone bakes.
# We don't need real Next output — just files with the magic string.
SAMPLE_SERVER_JS = """
// next.config.ts evaluated at build time
const rewrites = [{
  source: "/api/:path*",
  destination: "http://localhost:5055/api/:path*"
}];
"""

SAMPLE_REQUIRED_SERVER_FILES = """{
  "version": 1,
  "config": {
    "rewrites": {
      "afterFiles": [
        { "source": "/api/:path*", "destination": "http://localhost:5055/api/:path*" }
      ]
    }
  }
}"""

SAMPLE_ROUTES_MANIFEST = """{
  "version": 3,
  "rewrites": {
    "afterFiles": [
      { "source": "/api/:path*", "destination": "http://localhost:5055/api/:path*" }
    ]
  }
}"""


def _build_fake_frontend(root: Path) -> None:
    """Materialize a minimal frontend dir structure with the three
    files the patcher knows about."""
    (root / ".next").mkdir(parents=True, exist_ok=True)
    (root / "server.js").write_text(SAMPLE_SERVER_JS)
    (root / ".next" / "required-server-files.json").write_text(
        SAMPLE_REQUIRED_SERVER_FILES
    )
    (root / ".next" / "routes-manifest.json").write_text(SAMPLE_ROUTES_MANIFEST)


# ---------------------------------------------------------------------- #
# patch_rewrites_for_api_port — happy path
# ---------------------------------------------------------------------- #


class TestPatchRewritesHappyPath:
    def test_substitutes_localhost_port_in_all_three_files(self, tmp_path):
        from desktop.next_rewrites_patcher import patch_rewrites_for_api_port
        _build_fake_frontend(tmp_path)
        # Use a non-default port; default port 5055 short-circuits.
        result = patch_rewrites_for_api_port(tmp_path, 54321)
        assert result == tmp_path  # tmp_path is writable, no copy needed
        for rel in ("server.js", ".next/required-server-files.json",
                    ".next/routes-manifest.json"):
            content = (tmp_path / rel).read_text()
            assert "localhost:54321" in content, (
                f"{rel} should contain replacement; got {content!r}"
            )
            assert "localhost:5055" not in content, (
                f"{rel} still contains pristine port — patch didn't fully apply"
            )

    def test_creates_orig_backups_on_first_patch(self, tmp_path):
        from desktop.next_rewrites_patcher import patch_rewrites_for_api_port
        _build_fake_frontend(tmp_path)
        patch_rewrites_for_api_port(tmp_path, 12345)
        for rel in ("server.js", ".next/required-server-files.json",
                    ".next/routes-manifest.json"):
            orig_path = tmp_path / (rel + ".orig")
            assert orig_path.exists(), (
                f"{orig_path} missing — patch should create .orig backup"
            )
            # The .orig should contain the pristine localhost:5055
            assert "localhost:5055" in orig_path.read_text()

    def test_repeated_patches_dont_compound(self, tmp_path):
        """Round-trip: every patch reads from .orig, so patching multiple
        times with different ports always works from the pristine baseline."""
        from desktop.next_rewrites_patcher import patch_rewrites_for_api_port
        _build_fake_frontend(tmp_path)
        patch_rewrites_for_api_port(tmp_path, 11111)
        patch_rewrites_for_api_port(tmp_path, 22222)
        patch_rewrites_for_api_port(tmp_path, 33333)
        # Final state: only the LAST port should be in the live files
        for rel in ("server.js", ".next/required-server-files.json",
                    ".next/routes-manifest.json"):
            content = (tmp_path / rel).read_text()
            assert "localhost:33333" in content
            assert "localhost:11111" not in content
            assert "localhost:22222" not in content
            assert "localhost:5055" not in content

    def test_default_port_short_circuits_no_file_io(self, tmp_path):
        """If api_port=5055 (the build-time default), patching is a
        no-op — saves filesystem work for dev environments."""
        from desktop.next_rewrites_patcher import patch_rewrites_for_api_port
        _build_fake_frontend(tmp_path)
        before_mtime = (tmp_path / "server.js").stat().st_mtime
        result = patch_rewrites_for_api_port(tmp_path, 5055)
        assert result == tmp_path
        after_mtime = (tmp_path / "server.js").stat().st_mtime
        assert before_mtime == after_mtime, (
            "Default port should not touch the file"
        )
        # And no .orig should have been created either
        assert not (tmp_path / "server.js.orig").exists()


# ---------------------------------------------------------------------- #
# Error / edge cases
# ---------------------------------------------------------------------- #


class TestPatchRewritesErrors:
    def test_raises_when_no_files_contain_target_string(self, tmp_path):
        """If next.config.ts gets refactored to use a different default,
        the build will no longer have `localhost:5055` baked in. The
        patcher must NOT silently claim success — that would mean
        launching a Next.js that can't reach the API."""
        from desktop.next_rewrites_patcher import (
            PatchError,
            patch_rewrites_for_api_port,
        )
        # Build the files but with a DIFFERENT URL that doesn't match
        # the build-time default.
        (tmp_path / ".next").mkdir(parents=True, exist_ok=True)
        (tmp_path / "server.js").write_text("destination: 'http://example.com/api'")
        (tmp_path / ".next" / "required-server-files.json").write_text(
            '{"rewrites": "no localhost"}'
        )
        (tmp_path / ".next" / "routes-manifest.json").write_text(
            '{"version": 3}'
        )
        with pytest.raises(PatchError, match="next.config.ts"):
            patch_rewrites_for_api_port(tmp_path, 9999)

    def test_missing_target_files_dont_crash_when_some_succeed(self, tmp_path):
        """Resilience: if some files are missing (e.g., user has an
        older bundle without the full manifest set), patch what we
        can and warn about the rest."""
        from desktop.next_rewrites_patcher import patch_rewrites_for_api_port
        # Only create one of the three target files
        (tmp_path / "server.js").write_text(SAMPLE_SERVER_JS)
        # .next/ dir + the other files are missing
        result = patch_rewrites_for_api_port(tmp_path, 7777)
        # Should succeed because at least one file was patched
        assert result == tmp_path
        assert "localhost:7777" in (tmp_path / "server.js").read_text()


# ---------------------------------------------------------------------- #
# restore_originals — clean round-trip back to pristine
# ---------------------------------------------------------------------- #


class TestRestoreOriginals:
    def test_restore_brings_back_pristine(self, tmp_path):
        from desktop.next_rewrites_patcher import (
            patch_rewrites_for_api_port,
            restore_originals,
        )
        _build_fake_frontend(tmp_path)
        patch_rewrites_for_api_port(tmp_path, 88888)
        # Files are now patched
        assert "localhost:88888" in (tmp_path / "server.js").read_text()
        # Restore
        restored = restore_originals(tmp_path)
        assert restored == 3
        # Files match the pristine baseline again
        for rel in ("server.js", ".next/required-server-files.json",
                    ".next/routes-manifest.json"):
            content = (tmp_path / rel).read_text()
            assert "localhost:5055" in content
            assert "localhost:88888" not in content

    def test_restore_with_no_orig_files_is_safe(self, tmp_path):
        """If patching never ran, restore should be a clean no-op
        (returns 0) rather than crashing on missing .orig files."""
        from desktop.next_rewrites_patcher import restore_originals
        _build_fake_frontend(tmp_path)
        # No .orig files exist yet
        restored = restore_originals(tmp_path)
        assert restored == 0


# ---------------------------------------------------------------------- #
# Writability detection
# ---------------------------------------------------------------------- #


class TestWritabilityDetection:
    def test_writable_dir_detected(self, tmp_path):
        from desktop.next_rewrites_patcher import _is_writable
        assert _is_writable(tmp_path) is True

    def test_readonly_dir_falls_back_to_copy(self, tmp_path, monkeypatch):
        """If the bundle is read-only (e.g., installed under
        /Applications by another user), patcher copies to
        ~/.deeper-notebook/frontend-runtime/ and patches there."""
        import desktop.next_rewrites_patcher as patcher

        # Build the source bundle
        src = tmp_path / "bundle"
        _build_fake_frontend(src)
        # ACLs on Windows do not treat POSIX chmod as a reliable way to make
        # a directory unwritable, so force the patcher's write-probe outcome.
        monkeypatch.setattr(patcher, "_is_writable", lambda _path: False)
        # Use a fake HOME pointing into our tmp_path so the writable copy
        # doesn't pollute the real ~/.deeper-notebook/.
        monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
        result = patcher.patch_rewrites_for_api_port(src, 55555)
        expected = (
            tmp_path
            / "fake-home"
            / ".deeper-notebook"
            / patcher.WRITABLE_COPY_NAME
        )
        assert result == expected
        # The writable copy should have the patched content
        patched_server = result / "server.js"
        assert patched_server.exists()
        assert "localhost:55555" in patched_server.read_text()


# ---------------------------------------------------------------------- #
# Idempotency end-to-end
# ---------------------------------------------------------------------- #


def test_patch_returns_path_for_launcher_to_use_as_cwd(tmp_path):
    """The launcher uses the returned path as Next.js's cwd. Confirm
    the return value is always a valid directory containing
    server.js."""
    from desktop.next_rewrites_patcher import patch_rewrites_for_api_port
    _build_fake_frontend(tmp_path)
    result = patch_rewrites_for_api_port(tmp_path, 60000)
    assert result.is_dir()
    assert (result / "server.js").exists()
