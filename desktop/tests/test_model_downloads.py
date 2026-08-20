"""Unit tests for desktop/model_downloads.py.

v0.7.188 — Rewritten to mock `httpx.stream` instead of
`urllib.request.urlopen`. The underlying download function was
migrated from urllib to httpx.stream to enable resumable downloads
(Range header) and bounded per-chunk read timeouts. Behavioural
semantics being asserted (skip-if-present, fail-gracefully,
min_bytes override) are unchanged.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from desktop.model_downloads import (
    EMBEDDING_GGUF,
    _download_one,
    ensure_embedding_model,
    ensure_secondary_tts_voice,
)

# ---------------------------------------------------------------------------
# httpx.stream mock helper
# ---------------------------------------------------------------------------


class _FakeStreamResponse:
    """Minimal stand-in for httpx.Response under `httpx.stream(...)`.

    Used as the context-manager target of `with httpx.stream(...) as resp`.
    Exposes the subset of the Response API `_download_one` calls:
      - status_code
      - raise_for_status()
      - iter_bytes(chunk_size)
    """

    def __init__(
        self,
        content: bytes = b"",
        status_code: int = 200,
        chunk_size: int = 1024 * 1024,
    ):
        self._content = content
        self.status_code = status_code
        self._chunk_size = chunk_size

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=None,
                response=None,  # type: ignore[arg-type]
            )

    def iter_bytes(self, chunk_size: int | None = None):
        cs = chunk_size or self._chunk_size
        for i in range(0, len(self._content), cs):
            yield self._content[i : i + cs]


def _patch_stream(content: bytes = b"", status_code: int = 200):
    """Convenience: patch `httpx.stream` in the module-under-test to
    return our fake response."""
    return patch(
        "desktop.model_downloads.httpx.stream",
        return_value=_FakeStreamResponse(content, status_code),
    )


# ---------------------------------------------------------------------------
# _download_one — skip-if-already-present
# ---------------------------------------------------------------------------


def test_download_one_skips_existing_large_file(tmp_path):
    """_download_one skips the network call when the target already exists and
    is larger than 100 KB."""
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"x" * 200_001)

    with patch("desktop.model_downloads.httpx.stream") as mock_stream:
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    mock_stream.assert_not_called()
    assert result is True


def test_download_one_downloads_when_missing(tmp_path):
    """_download_one writes the file when it doesn't exist yet."""
    dest = tmp_path / "model.gguf"
    fake_content = b"fake gguf content " * 10_000  # ~180 KB

    with _patch_stream(fake_content):
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    assert result is True
    assert dest.exists()
    assert dest.read_bytes() == fake_content


def test_download_one_returns_false_on_network_error(tmp_path):
    """_download_one returns False (not raise) when the download fails."""
    dest = tmp_path / "model.gguf"

    with patch(
        "desktop.model_downloads.httpx.stream",
        side_effect=httpx.ConnectError("connection refused"),
    ):
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    assert result is False
    assert not dest.exists()


def test_download_one_preserves_tmp_on_error_for_resume(tmp_path):
    """v0.7.188 — Was `test_download_one_cleans_up_tmp_on_error`. The new
    contract is the OPPOSITE: on failure, the .tmp file is PRESERVED so
    the next launch can resume via Range: bytes=<offset>-. The partial-
    validity check at the top of _download_one (min_bytes / 80% rule)
    deletes the FINAL `dest` if it's corrupted; the `.tmp` lives across
    failures by design.
    """
    dest = tmp_path / "model.gguf"

    # Simulate failure AFTER some bytes were written to .tmp by having
    # the iterator raise mid-stream.
    class _FailingResponse(_FakeStreamResponse):
        def iter_bytes(self, chunk_size: int | None = None):
            yield b"partial data " * 100  # ~1300 bytes written
            raise httpx.ReadTimeout("idle stall")

    with patch(
        "desktop.model_downloads.httpx.stream",
        return_value=_FailingResponse(b""),
    ):
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    assert result is False
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    # The .tmp file MUST survive so the next launch can resume.
    assert tmp.exists(), (
        "v0.7.188 regression: .tmp file deleted on download failure. "
        "Resume support is broken — next launch will restart from byte 0."
    )
    assert tmp.read_bytes() == b"partial data " * 100


def test_download_one_resumes_from_existing_tmp(tmp_path):
    """v0.7.188 — When a .tmp file exists from a prior interrupted
    download, the next call must send `Range: bytes=<offset>-` and
    APPEND to the .tmp (not overwrite). This is the whole point
    of the v0.7.188 resume support."""
    dest = tmp_path / "model.gguf"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    # Pre-existing .tmp from a "previous interrupted launch".
    existing_partial = b"first half of the model " * 1000  # ~24 KB
    tmp.write_bytes(existing_partial)

    # The server returns the REMAINDER (206 Partial Content). Our fake
    # just streams what we hand it; we hand it the second half.
    second_half = b"second half of the model " * 1000  # ~25 KB

    with patch(
        "desktop.model_downloads.httpx.stream",
        return_value=_FakeStreamResponse(second_half, status_code=206),
    ) as mock_stream:
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    assert result is True
    # The final file = partial + remainder, concatenated.
    assert dest.read_bytes() == existing_partial + second_half
    # And the call included a Range header.
    call_kwargs = mock_stream.call_args.kwargs
    headers = call_kwargs.get("headers", {})
    assert headers.get("Range", "").startswith("bytes="), (
        "v0.7.188 regression: resume call didn't send a Range header. "
        "Server will return the full file and we'll restart from byte 0."
    )


def test_download_one_restarts_from_zero_when_server_ignores_range(tmp_path):
    """v0.7.188 — Some CDNs don't support Range. If we asked for a Range
    but the server replied 200 (full content) instead of 206 (partial),
    we MUST restart from byte 0 — appending would duplicate the prefix
    and corrupt the file."""
    dest = tmp_path / "model.gguf"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(b"old partial that the server is going to replace")

    full_content = b"complete fresh file content " * 2000  # bigger than partial

    with patch(
        "desktop.model_downloads.httpx.stream",
        # status 200 — server ignored our Range header.
        return_value=_FakeStreamResponse(full_content, status_code=200),
    ):
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    assert result is True
    # File content = ONLY the fresh download. Pre-existing partial
    # must have been overwritten (not concatenated).
    assert dest.read_bytes() == full_content


def test_download_one_calls_progress(tmp_path):
    """_download_one calls the progress callback with status messages."""
    dest = tmp_path / "model.gguf"
    fake_content = b"x" * 200_001
    messages: list[str] = []

    with _patch_stream(fake_content):
        _download_one(
            "https://example.com/model.gguf",
            dest,
            "my model",
            progress=messages.append,
        )

    assert any("Downloading" in m for m in messages)
    assert any("Downloaded" in m for m in messages)


# ---------------------------------------------------------------------------
# ensure_embedding_model
# ---------------------------------------------------------------------------


def test_ensure_embedding_model_returns_expected_path(tmp_path):
    """ensure_embedding_model returns model_dir/GGUF/nomic-embed-text-v1.5.f16.gguf."""
    _, rel, _, _ = EMBEDDING_GGUF
    expected = tmp_path / rel
    fake_content = b"y" * 200_001

    with _patch_stream(fake_content):
        result = ensure_embedding_model(tmp_path)

    assert result == expected
    assert expected.exists()


def test_ensure_embedding_model_returns_none_on_failure(tmp_path):
    """ensure_embedding_model returns None when the download fails."""
    with patch(
        "desktop.model_downloads.httpx.stream",
        side_effect=httpx.ConnectError("no internet"),
    ):
        result = ensure_embedding_model(tmp_path)

    assert result is None


def test_ensure_embedding_model_skips_if_already_present(tmp_path):
    """ensure_embedding_model skips download when the file already exists.

    File size needs to be within 80% of expected_size_mb (273 MB).
    Use a sparse 250 MB file to satisfy the new check without actually
    allocating the bytes (truncate, not write_bytes).
    """
    _, rel, _, expected_size_mb = EMBEDDING_GGUF
    dest = tmp_path / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    target_bytes = int(expected_size_mb * 1024 * 1024 * 0.96)
    with dest.open("wb") as f:
        f.truncate(target_bytes)

    with patch("desktop.model_downloads.httpx.stream") as mock_stream:
        result = ensure_embedding_model(tmp_path)

    mock_stream.assert_not_called()
    assert result == dest


def test_ensure_secondary_tts_voice_skips_when_present(tmp_path, monkeypatch):
    """v0.6.29 — files need to be within 80% of expected size (78 MB onnx)."""
    from desktop.model_downloads import PIPER_RYAN_CONFIG, PIPER_RYAN_MODEL

    _, _, _, onnx_size_mb = PIPER_RYAN_MODEL
    _, _, _, cfg_size_mb = PIPER_RYAN_CONFIG

    (tmp_path / "TTS").mkdir()
    onnx = tmp_path / "TTS" / "en_US-ryan-high.onnx"
    cfg = tmp_path / "TTS" / "en_US-ryan-high.onnx.json"
    with onnx.open("wb") as f:
        f.truncate(int(onnx_size_mb * 1024 * 1024 * 0.96))
    cfg.write_text("{" + " " * int(cfg_size_mb * 1024 * 1024 * 0.96))

    called = []
    monkeypatch.setattr(
        "desktop.model_downloads.httpx.stream",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not download")),
    )
    result = ensure_secondary_tts_voice(tmp_path, progress=lambda m: called.append(m))
    assert result == (onnx, cfg)


def test_download_one_re_downloads_when_partial_file_exists(tmp_path):
    """v0.6.29 regression: a previous launch interrupted at 120 MB of a
    280 MB embedding model left a partial .gguf. The old code saw
    size > 100 KB and skipped re-download — llama-cpp then crashed
    loading the truncated GGUF header. The fix uses expected_size_mb
    (with 20% lower-bound tolerance) so partial files are detected and
    re-fetched."""
    dest = tmp_path / "model.gguf"
    # A "partial" 50 MB file when we expected 280 MB. 50 < 0.8 * 280 = 224.
    dest.write_bytes(b"x" * (50 * 1024 * 1024))

    fake_content = b"fresh content " * 1024

    with _patch_stream(fake_content) as mock_stream:
        result = _download_one(
            "https://example.com/model.gguf",
            dest,
            "test model",
            expected_size_mb=280,
        )

    mock_stream.assert_called_once()  # network call DID happen — old code skipped
    assert result is True
    assert dest.read_bytes() == fake_content


def test_download_one_skips_when_size_within_expected_tolerance(tmp_path):
    """A file within 20% of expected size is treated as already complete —
    no re-download. The tolerance accounts for the size estimates being
    approximate."""
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"x" * (270 * 1024 * 1024))

    with patch("desktop.model_downloads.httpx.stream") as mock_stream:
        result = _download_one(
            "https://example.com/model.gguf",
            dest,
            "test model",
            expected_size_mb=280,
        )

    mock_stream.assert_not_called()
    assert result is True


def test_download_one_passes_timeout_to_httpx(tmp_path):
    """v0.7.188 — httpx.stream gets an explicit Timeout config so a hung
    HuggingFace mirror can't stall the launcher forever. Replaces the
    earlier v0.6.29 test that asserted the urllib `timeout=` kwarg."""
    dest = tmp_path / "model.gguf"

    with patch(
        "desktop.model_downloads.httpx.stream",
        return_value=_FakeStreamResponse(b"x"),
    ) as mock_stream:
        _download_one("https://example.com/x", dest, "test")

    _, kwargs = mock_stream.call_args
    timeout = kwargs.get("timeout")
    assert timeout is not None, (
        "v0.7.188 regression: httpx.stream call lost its timeout kwarg. "
        "A flaky mirror can stall the launcher forever."
    )
    # Should be an httpx.Timeout instance with per-stage budgets.
    assert isinstance(timeout, httpx.Timeout)


# ---------------------------------------------------------------------------
# v0.7.150 — min_bytes override for small files (Piper config JSONs)
# ---------------------------------------------------------------------------


def test_download_one_min_bytes_override_accepts_small_real_file(tmp_path):
    """v0.7.150 regression.

    Piper `.onnx.json` voice configs are ~5 KB. The MB-based threshold
    (expected_size_mb=1 → 838860 bytes) was incorrectly flagging the real
    files as too small, triggering re-download on every launch.
    """
    dest = tmp_path / "voice.onnx.json"
    dest.write_bytes(b"x" * 4882)

    with patch("desktop.model_downloads.httpx.stream") as mock_stream:
        result = _download_one(
            "https://example.com/voice.onnx.json",
            dest,
            "voice cfg",
            min_bytes=2048,
        )

    mock_stream.assert_not_called(), "must skip download — file already valid"
    assert result is True


def test_download_one_min_bytes_override_rejects_tiny_html_error_page(tmp_path):
    """min_bytes still filters out obviously-broken downloads — e.g. when
    HuggingFace returns a tiny HTML 503 page instead of the JSON. The 2 KB
    floor is below real Piper configs (~5 KB) but well above an error page.
    """
    dest = tmp_path / "voice.onnx.json"
    dest.write_bytes(b"<html>503 Service Unavailable</html>")

    fresh_content = b"{" + b" " * 5000  # 5001 bytes — passes the 2 KB floor

    with _patch_stream(fresh_content):
        result = _download_one(
            "https://example.com/voice.onnx.json",
            dest,
            "voice cfg",
            min_bytes=2048,
        )

    # The old partial was rejected, fresh download succeeded.
    assert result is True
    assert dest.read_bytes() == fresh_content


# ---------------------------------------------------------------------------
# v0.8.67p — ensure_stt_model fetches the faster-whisper CTranslate2 model
# ---------------------------------------------------------------------------


def test_ensure_stt_model_downloads_faster_whisper_not_ggml(tmp_path):
    """The whisper shim uses faster-whisper, so ensure_stt_model must fetch the
    CTranslate2 model files (Systran/faster-whisper-base.en), NOT the legacy
    whisper.cpp ggml .bin, and return the model dir when all files succeed."""
    from desktop.model_downloads import (
        FASTER_WHISPER_STT_DIR,
        FASTER_WHISPER_STT_FILES,
        ensure_stt_model,
    )

    calls = []

    def fake_dl(url, dest, label, progress=None, expected_size_mb=0, min_bytes=0):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x" * 1024)
        return True

    with patch("desktop.model_downloads._download_one", side_effect=fake_dl):
        result = ensure_stt_model(tmp_path)

    assert result == tmp_path / FASTER_WHISPER_STT_DIR
    assert len(calls) == len(FASTER_WHISPER_STT_FILES)
    assert all("Systran/faster-whisper-base.en" in u for u in calls)
    assert all("ggml" not in u for u in calls)


def test_ensure_stt_model_returns_none_if_any_file_fails(tmp_path):
    """If any file fails, return None so the launcher falls back to the bare
    'base.en' HF download — an INCOMPLETE local dir would break the shim."""
    from desktop.model_downloads import ensure_stt_model

    def fake_dl(url, dest, label, progress=None, expected_size_mb=0, min_bytes=0):
        return "model.bin" not in url  # the big file "fails"

    with patch("desktop.model_downloads._download_one", side_effect=fake_dl):
        result = ensure_stt_model(tmp_path)

    assert result is None
