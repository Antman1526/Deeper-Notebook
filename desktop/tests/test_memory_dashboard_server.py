from aiohttp.test_utils import AioHTTPTestCase

from desktop.memory_dashboard.server import build_app


class MemoryDashboardTest(AioHTTPTestCase):
    async def get_application(self):
        # Point at a guaranteed-unreachable port — proxy attempts return 502
        # but route resolution itself still works.
        return build_app(memory_retriever_url="http://127.0.0.1:65535")

    async def test_root_serves_html_or_fallback(self):
        async with self.client.get("/") as r:
            assert r.status == 200

    async def test_api_theme_returns_a_theme(self):
        async with self.client.get("/api/theme") as r:
            assert r.status == 200
            body = await r.json()
            assert "theme" in body
            assert isinstance(body["theme"], str)


def test_save_capture_state_is_atomic(tmp_path, monkeypatch):
    """v0.6.27 regression: capture_state.json must be written via tmp+replace
    so a crash mid-write can't corrupt it. Previously a half-written file
    blew away the user's muted_apps list on next load (JSON decode error
    → silent fallback to empty defaults)."""
    from desktop.memory_dashboard import server as srv

    # Redirect path to tmp_path
    monkeypatch.setattr(
        srv, "_capture_state_path", lambda: tmp_path / "capture_state.json"
    )
    p = tmp_path / "capture_state.json"
    tmp_sibling = p.with_suffix(p.suffix + ".tmp")

    srv._save_capture_state(
        {"last_seen": "2025-01-01T00:00:00Z", "muted_apps": ["Slack", "VSCode"]}
    )

    # File present, .tmp NOT left behind
    assert p.exists()
    assert not tmp_sibling.exists(), f"leftover .tmp file: {tmp_sibling}"

    # Round-trip
    state = srv._load_capture_state()
    assert state["last_seen"] == "2025-01-01T00:00:00Z"
    assert state["muted_apps"] == ["Slack", "VSCode"]


def test_save_capture_state_preserves_old_file_on_replace_failure(
    tmp_path, monkeypatch
):
    """If os.replace itself raises (e.g. cross-device link error in a
    weird mount setup), the ORIGINAL capture_state.json must remain
    intact — its data is more valuable than the new write."""
    import os as _os

    from desktop.memory_dashboard import server as srv

    monkeypatch.setattr(
        srv, "_capture_state_path", lambda: tmp_path / "capture_state.json"
    )

    # Seed an existing valid file
    srv._save_capture_state({"last_seen": "old", "muted_apps": ["A"]})
    assert (tmp_path / "capture_state.json").read_text()  # not empty

    # Now make os.replace blow up — old file stays intact
    monkeypatch.setattr(
        _os,
        "replace",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("simulated replace failure")),
    )

    srv._save_capture_state({"last_seen": "new", "muted_apps": ["B"]})

    # Old data still there (since replace never landed the new content)
    state = srv._load_capture_state()
    assert state["last_seen"] == "old"
    assert state["muted_apps"] == ["A"]

    # And no .tmp leftover (cleaned up by the except branch)
    tmp_sibling = (tmp_path / "capture_state.json").with_suffix(".json.tmp")
    assert not tmp_sibling.exists()


def test_save_capture_state_handles_corrupted_existing_file(tmp_path, monkeypatch):
    """If the existing file is corrupted JSON (e.g. left over from a
    pre-v0.6.27 mid-write crash), _load_capture_state returns the empty
    default — and a subsequent save overwrites it atomically with valid
    content."""
    from desktop.memory_dashboard import server as srv

    monkeypatch.setattr(
        srv, "_capture_state_path", lambda: tmp_path / "capture_state.json"
    )
    p = tmp_path / "capture_state.json"
    p.write_text("{ this is not json")  # corrupted

    # Load returns defaults without raising
    state = srv._load_capture_state()
    assert state == {"last_seen": "", "muted_apps": []}

    # Save fixes the file
    srv._save_capture_state({"last_seen": "ts1", "muted_apps": ["Slack"]})
    state2 = srv._load_capture_state()
    assert state2["last_seen"] == "ts1"
    assert state2["muted_apps"] == ["Slack"]
