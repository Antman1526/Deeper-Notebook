"""Unit tests for desktop/model_downloads.py."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desktop.model_downloads import (
    EMBEDDING_GGUF,
    _download_one,
    ensure_embedding_model,
    ensure_secondary_tts_voice,
)


# ---------------------------------------------------------------------------
# _download_one
# ---------------------------------------------------------------------------

def test_download_one_skips_existing_large_file(tmp_path):
    """_download_one skips the network call when the target already exists and
    is larger than 100 KB."""
    dest = tmp_path / "model.gguf"
    # Write 200 KB of dummy data to simulate an already-downloaded file.
    dest.write_bytes(b"x" * 200_001)

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    mock_urlopen.assert_not_called()
    assert result is True


def test_download_one_downloads_when_missing(tmp_path):
    """_download_one writes the file when it doesn't exist yet."""
    dest = tmp_path / "model.gguf"
    fake_content = b"fake gguf content " * 10_000  # ~180 KB

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: io.BytesIO(fake_content)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    assert result is True
    assert dest.exists()
    assert dest.read_bytes() == fake_content


def test_download_one_returns_false_on_network_error(tmp_path):
    """_download_one returns False (not raise) when the download fails."""
    dest = tmp_path / "model.gguf"

    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    assert result is False
    assert not dest.exists()


def test_download_one_cleans_up_tmp_on_error(tmp_path):
    """_download_one removes the .tmp file when the download raises mid-stream."""
    dest = tmp_path / "model.gguf"

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: (_ for _ in ()).throw(OSError("disk full"))
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _download_one("https://example.com/model.gguf", dest, "test model")

    assert result is False
    # Neither the final file nor the .tmp file should remain.
    assert not dest.exists()
    assert not dest.with_suffix(dest.suffix + ".tmp").exists()


def test_download_one_calls_progress(tmp_path):
    """_download_one calls the progress callback with status messages."""
    dest = tmp_path / "model.gguf"
    fake_content = b"x" * 200_001

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: io.BytesIO(fake_content)
    mock_resp.__exit__ = MagicMock(return_value=False)

    messages: list[str] = []

    with patch("urllib.request.urlopen", return_value=mock_resp):
        _download_one("https://example.com/model.gguf", dest, "my model",
                      progress=messages.append)

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

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: io.BytesIO(fake_content)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = ensure_embedding_model(tmp_path)

    assert result == expected
    assert expected.exists()


def test_ensure_embedding_model_returns_none_on_failure(tmp_path):
    """ensure_embedding_model returns None when the download fails."""
    with patch("urllib.request.urlopen", side_effect=OSError("no internet")):
        result = ensure_embedding_model(tmp_path)

    assert result is None


def test_ensure_embedding_model_skips_if_already_present(tmp_path):
    """ensure_embedding_model skips download when the file already exists.

    v0.6.29 — file size now needs to be within 80% of expected_size_mb
    (273 MB), since the threshold was lifted to detect partial downloads.
    Use a sparse 250 MB file to satisfy the new check without actually
    allocating the bytes (truncate, not write_bytes).
    """
    _, rel, _, expected_size_mb = EMBEDDING_GGUF
    dest = tmp_path / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Sparse file at ~96% of expected (no actual disk allocation on most filesystems)
    target_bytes = int(expected_size_mb * 1024 * 1024 * 0.96)
    with dest.open("wb") as f:
        f.truncate(target_bytes)

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = ensure_embedding_model(tmp_path)

    mock_urlopen.assert_not_called()
    assert result == dest


def test_ensure_secondary_tts_voice_skips_when_present(tmp_path, monkeypatch):
    """v0.6.29 — files need to be within 80% of expected size (78 MB onnx)."""
    from desktop.model_downloads import PIPER_RYAN_MODEL, PIPER_RYAN_CONFIG
    _, _, _, onnx_size_mb = PIPER_RYAN_MODEL
    _, _, _, cfg_size_mb = PIPER_RYAN_CONFIG

    (tmp_path / "TTS").mkdir()
    onnx = tmp_path / "TTS" / "en_US-ryan-high.onnx"
    cfg = tmp_path / "TTS" / "en_US-ryan-high.onnx.json"
    # Onnx is ~78 MB; allocate sparse file at 96% so we pass the 80% threshold
    with onnx.open("wb") as f:
        f.truncate(int(onnx_size_mb * 1024 * 1024 * 0.96))
    # Config is ~1 MB; write enough real bytes
    cfg.write_text("{" + " " * int(cfg_size_mb * 1024 * 1024 * 0.96))

    called = []
    monkeypatch.setattr(
        "desktop.model_downloads.urllib.request.urlopen",
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
    # A "partial" 50 MB file when we expected 280 MB. 50 < 0.8 * 280 = 224
    # so this MUST trigger a re-download.
    dest.write_bytes(b"x" * (50 * 1024 * 1024))

    fake_content = b"fresh content " * 1024
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: io.BytesIO(fake_content)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = _download_one(
            "https://example.com/model.gguf", dest, "test model",
            expected_size_mb=280,
        )

    mock_urlopen.assert_called_once()  # network call DID happen — old code skipped
    assert result is True
    # Old partial bytes replaced with fresh content
    assert dest.read_bytes() == fake_content


def test_download_one_skips_when_size_within_expected_tolerance(tmp_path):
    """A file within 20% of expected size is treated as already complete —
    no re-download. The tolerance accounts for the size estimates being
    approximate (e.g. piper voice .onnx is ~30 MB but HF compression can
    leave the on-disk size ~85% of that)."""
    dest = tmp_path / "model.gguf"
    # 270 MB on disk for a 280 MB expected — 96% of expected, well above 80%
    dest.write_bytes(b"x" * (270 * 1024 * 1024))

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = _download_one(
            "https://example.com/model.gguf", dest, "test model",
            expected_size_mb=280,
        )

    mock_urlopen.assert_not_called()  # skipped — file is good enough
    assert result is True


def test_download_one_passes_timeout_to_urlopen(tmp_path):
    """v0.6.29: urlopen now gets a timeout so a hung HuggingFace mirror
    can't stall the launcher forever."""
    dest = tmp_path / "model.gguf"
    fake_content = b"x"
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: io.BytesIO(fake_content)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        _download_one("https://example.com/x", dest, "test")

    # Inspect the call — timeout was passed
    _, kwargs = mock_urlopen.call_args
    assert kwargs.get("timeout") is not None
    assert kwargs["timeout"] > 0
