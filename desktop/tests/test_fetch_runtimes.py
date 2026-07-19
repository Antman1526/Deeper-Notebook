from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPT = Path(__file__).parents[1] / "build" / "fetch_runtimes.py"
SPEC = spec_from_file_location("fetch_runtimes", SCRIPT)
assert SPEC and SPEC.loader
fetch_runtimes = module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_runtimes)


class FakeResponse:
    def __init__(self, data: bytes, declared_size: int | None = None):
        self.data = data
        self.offset = 0
        self.headers = {
            "Content-Length": str(declared_size if declared_size is not None else len(data))
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        if self.offset >= len(self.data):
            return b""
        end = len(self.data) if size < 0 else self.offset + size
        chunk = self.data[self.offset:end]
        self.offset += len(chunk)
        return chunk


def test_download_retries_truncated_transfer_and_replaces_atomically(tmp_path):
    destination = tmp_path / "runtime.tgz"
    destination.write_bytes(b"known-good-old-file")
    responses = [FakeResponse(b"short", declared_size=10), FakeResponse(b"complete")]

    with patch.object(fetch_runtimes.urllib.request, "urlopen", side_effect=responses), patch.object(
        fetch_runtimes.time, "sleep"
    ) as sleep:
        fetch_runtimes.download("https://example.test/runtime.tgz", destination)

    assert destination.read_bytes() == b"complete"
    assert not destination.with_name("runtime.tgz.part").exists()
    sleep.assert_called_once_with(1)


def test_download_preserves_existing_file_after_all_attempts_fail(tmp_path):
    destination = tmp_path / "runtime.tgz"
    destination.write_bytes(b"known-good-old-file")

    with patch.object(
        fetch_runtimes.urllib.request,
        "urlopen",
        return_value=FakeResponse(b"short", declared_size=10),
    ), patch.object(fetch_runtimes.time, "sleep"):
        with pytest.raises(EOFError, match="truncated download"):
            fetch_runtimes.download("https://example.test/runtime.tgz", destination, attempts=2)

    assert destination.read_bytes() == b"known-good-old-file"
    assert not destination.with_name("runtime.tgz.part").exists()
