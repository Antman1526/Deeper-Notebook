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
    """ensure_embedding_model skips download when the file already exists."""
    _, rel, _, _ = EMBEDDING_GGUF
    dest = tmp_path / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"z" * 200_001)

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = ensure_embedding_model(tmp_path)

    mock_urlopen.assert_not_called()
    assert result == dest
