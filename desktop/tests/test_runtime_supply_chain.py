"""RED regressions for runtime download integrity and archive boundaries."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from desktop import bootstrap
from desktop.build import archive_validation, fetch_runtimes


def test_direct_runtime_fetch_resolves_repo_from_script_path_without_network(
    tmp_path: Path,
):
    """Direct execution must import the package before entering the fetch path."""
    # Keep this subprocess off the real platform path so ``main`` exits before
    # any runtime URL is read or opened.  This is an exact script invocation,
    # from a cwd that is not the repository, with no network access required.
    (tmp_path / "sitecustomize.py").write_text(
        "import sys\n"
        "sys.platform = 'task19-import-probe'\n",
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[2] / "desktop" / "build" / "fetch_runtimes.py"
    env = os.environ.copy()
    env.update({"PYTHONNOUSERSITE": "1", "PYTHONPATH": str(tmp_path)})

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Unsupported platform: task19-import-probe" in completed.stderr
    assert "ModuleNotFoundError: No module named 'desktop'" not in completed.stderr


def _tar_bytes(entries: list[tuple[str, bytes, str | None]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content, linkname in entries:
            info = tarfile.TarInfo(name=name)
            if linkname is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = linkname
            else:
                info.size = len(content)
            archive.addfile(info, io.BytesIO(content) if linkname is None else None)
    return buffer.getvalue()


def test_runtime_manifest_has_https_urls_and_sha256_for_every_supported_asset():
    config = tomllib.loads(fetch_runtimes.RUNTIMES.read_text(encoding="utf-8"))
    for runtime_name, runtime in config.items():
        urls = runtime["urls"]
        digests = runtime["sha256"]
        assert set(urls) == set(digests), runtime_name
        for arch, url in urls.items():
            fetch_runtimes._validate_https_url(url)
            assert len(digests[arch]) == 64
            int(digests[arch], 16)


def test_download_rejects_non_https_before_urlopen(tmp_path: Path):
    with patch.object(fetch_runtimes.urllib.request, "urlopen") as urlopen:
        with pytest.raises(ValueError, match="HTTPS"):
            fetch_runtimes.download("http://example.invalid/runtime", tmp_path / "x", "0" * 64)
    urlopen.assert_not_called()


def test_download_digest_mismatch_removes_only_owned_download(tmp_path: Path):
    from io import BytesIO

    class _Response:
        def __init__(self):
            self._body = BytesIO(b"synthetic-runtime")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return self._body.read(_size)

    destination = tmp_path / "runtime.tgz"
    with patch.object(fetch_runtimes.urllib.request, "urlopen", return_value=_Response()) as urlopen:
        with pytest.raises(ValueError, match="SHA-256"):
            fetch_runtimes.download(
                "https://example.invalid/runtime.tgz",
                destination,
                hashlib.sha256(b"different").hexdigest(),
            )
    urlopen.assert_called_once_with(
        "https://example.invalid/runtime.tgz",
        timeout=fetch_runtimes.DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    )
    assert not destination.exists()


def test_download_digest_mismatch_preserves_previous_verified_destination(tmp_path: Path):
    from io import BytesIO

    class _Response:
        def __enter__(self):
            self._body = BytesIO(b"tampered-runtime")
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _size=-1):
            return self._body.read(_size)

    destination = tmp_path / "runtime.exe"
    destination.write_bytes(b"previously-verified")
    with patch.object(fetch_runtimes.urllib.request, "urlopen", return_value=_Response()):
        with pytest.raises(ValueError, match="SHA-256"):
            fetch_runtimes.download(
                "https://example.invalid/runtime.exe",
                destination,
                hashlib.sha256(b"different").hexdigest(),
            )
    assert destination.read_bytes() == b"previously-verified"


def test_node_extract_failure_preserves_previous_verified_runtime(
    tmp_path: Path, monkeypatch,
):
    runtime_bin = tmp_path / "bin"
    prior_node = runtime_bin / "node-darwin-arm64" / "bin" / "node"
    prior_node.parent.mkdir(parents=True)
    prior_node.write_bytes(b"previously-verified-node")

    archive_bytes = _tar_bytes(
        [("node-v20.18.0-darwin-arm64/bin/node", b"replacement-node", None)]
    )

    def fake_download(_url: str, destination: Path, _expected: str | None):
        destination.write_bytes(archive_bytes)

    def fail_extract(*_args, **_kwargs):
        raise OSError("synthetic extraction failure")

    monkeypatch.setattr(fetch_runtimes, "BIN", runtime_bin)
    monkeypatch.setattr(fetch_runtimes, "download", fake_download)
    monkeypatch.setattr(tarfile.TarFile, "extractall", fail_extract)

    with pytest.raises(OSError, match="synthetic extraction failure"):
        fetch_runtimes.fetch_node(
            "20.18.0",
            "https://example.invalid/node.tar.gz",
            "darwin-arm64",
            "0" * 64,
        )

    assert prior_node.read_bytes() == b"previously-verified-node"


def test_surreal_extract_failure_preserves_previous_verified_runtime(
    tmp_path: Path, monkeypatch,
):
    runtime_bin = tmp_path / "bin"
    runtime_bin.mkdir()
    target = runtime_bin / "surreal-darwin-arm64"
    target.write_bytes(b"previously-verified-surreal")
    archive_bytes = _tar_bytes([("surreal", b"replacement-surreal", None)])

    def fake_download(_url: str, destination: Path, _expected: str | None):
        destination.write_bytes(archive_bytes)

    def fail_extract(*_args, **_kwargs):
        raise OSError("synthetic extraction failure")

    monkeypatch.setattr(fetch_runtimes, "BIN", runtime_bin)
    monkeypatch.setattr(fetch_runtimes, "download", fake_download)
    monkeypatch.setattr(tarfile.TarFile, "extract", fail_extract)

    with pytest.raises(OSError, match="synthetic extraction failure"):
        fetch_runtimes.fetch_surreal(
            "2.1.0",
            "https://example.invalid/surreal.tar.gz",
            "darwin-arm64",
            "0" * 64,
        )

    assert target.read_bytes() == b"previously-verified-surreal"


def test_uv_extract_failure_preserves_previous_verified_runtime(
    tmp_path: Path, monkeypatch,
):
    runtime_bin = tmp_path / "bin"
    runtime_bin.mkdir()
    target = runtime_bin / "uv"
    target.write_bytes(b"previously-verified-uv")
    archive_bytes = _tar_bytes(
        [("uv-aarch64-apple-darwin/uv", b"replacement-uv", None)]
    )

    def fake_download(_url: str, destination: Path, _expected: str | None):
        destination.write_bytes(archive_bytes)

    def partial_then_fail(_archive, member, path, **_kwargs):
        (Path(path) / member.name).write_bytes(b"partial")
        raise OSError("synthetic extraction failure")

    monkeypatch.setattr(fetch_runtimes, "BIN", runtime_bin)
    monkeypatch.setattr(fetch_runtimes, "download", fake_download)
    monkeypatch.setattr(tarfile.TarFile, "extract", partial_then_fail)

    with pytest.raises(OSError, match="synthetic extraction failure"):
        fetch_runtimes.fetch_uv(
            "0.8.15",
            "https://example.invalid/uv.tar.gz",
            "darwin-arm64",
            "0" * 64,
        )

    assert target.read_bytes() == b"previously-verified-uv"


@pytest.mark.parametrize(
    ("name", "linkname"),
    [
        ("../escape", None),
        ("/absolute", None),
        ("python/bin/python", "../../outside"),
    ],
)
def test_tar_validator_rejects_traversal_absolute_and_escaping_links(name, linkname):
    payload = _tar_bytes([(name, b"x", linkname)])
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        with pytest.raises(ValueError):
            fetch_runtimes._validate_tar_members(
                archive.getmembers(), expected_root="python"
            )


def test_tar_validator_rejects_duplicate_targets_and_devices():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        first = tarfile.TarInfo(name="python/bin/python3")
        first.size = 1
        archive.addfile(first, io.BytesIO(b"x"))
        duplicate = tarfile.TarInfo(name="python/bin/./python3")
        duplicate.size = 1
        archive.addfile(duplicate, io.BytesIO(b"y"))
    with tarfile.open(fileobj=io.BytesIO(buffer.getvalue()), mode="r:gz") as archive:
        with pytest.raises(ValueError, match="duplicate"):
            fetch_runtimes._validate_tar_members(
                archive.getmembers(), expected_root="python"
            )

    class _Unknown:
        name = "python/unknown"
        linkname = ""

        @staticmethod
        def isdev():
            return False

        @staticmethod
        def islnk():
            return False

        @staticmethod
        def issym():
            return False

        @staticmethod
        def isfile():
            return False

        @staticmethod
        def isdir():
            return False

    with pytest.raises(ValueError, match="unsupported"):
        fetch_runtimes._validate_tar_members([_Unknown()], expected_root="python")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        device = tarfile.TarInfo(name="python/dev/null")
        device.type = tarfile.CHRTYPE
        device.devmajor = 1
        device.devminor = 3
        archive.addfile(device)
    with tarfile.open(fileobj=io.BytesIO(buffer.getvalue()), mode="r:gz") as archive:
        with pytest.raises(ValueError, match="device"):
            fetch_runtimes._validate_tar_members(
                archive.getmembers(), expected_root="python"
            )


def test_archive_validator_enforces_finite_member_and_size_budgets(monkeypatch):
    class _Member:
        name = "python/file"
        size = 1

        @staticmethod
        def isdev():
            return False

        @staticmethod
        def islnk():
            return False

        @staticmethod
        def issym():
            return False

        @staticmethod
        def isfile():
            return True

    monkeypatch.setattr(archive_validation, "_MAX_ARCHIVE_MEMBERS", 1)
    with pytest.raises(ValueError, match="too many members"):
        archive_validation.validate_tar_members(
            [_Member(), _Member()], expected_root="python"
        )

    monkeypatch.setattr(archive_validation, "_MAX_ARCHIVE_MEMBERS", 50_000)
    monkeypatch.setattr(archive_validation, "_MAX_DECLARED_BYTES", 0)
    with pytest.raises(ValueError, match="file bytes"):
        archive_validation.validate_tar_members([_Member()], expected_root="python")


def test_zip_validator_rejects_traversal_duplicate_and_symlink_members():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("python/python.exe", b"MZ")
        archive.writestr("../escape", b"bad")
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        with pytest.raises(ValueError):
            fetch_runtimes._validate_zip_members(
                archive.infolist(), expected_root="python"
            )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("python/python.exe", b"MZ")
        archive.writestr("python/./python.exe", b"duplicate")
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        with pytest.raises(ValueError, match="duplicate"):
            fetch_runtimes._validate_zip_members(
                archive.infolist(), expected_root="python"
            )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("python/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "../../outside")
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        with pytest.raises(ValueError, match="link"):
            fetch_runtimes._validate_zip_members(
                archive.infolist(), expected_root="python"
            )


def test_bootstrap_validates_before_writing_escape_member(tmp_path: Path, monkeypatch):
    tarball = tmp_path / "python.tar.gz"
    tarball.write_bytes(
        _tar_bytes(
            [
                ("python/bin/python3", b"fake", None),
                ("../outside", b"must-not-write", None),
            ]
        )
    )
    monkeypatch.setattr(sys, "platform", "darwin")
    destination = tmp_path / "home"
    with pytest.raises(ValueError):
        bootstrap.extract_python_runtime(tarball, destination)
    assert not (tmp_path / "outside").exists()


def test_bootstrap_preserves_contained_relative_symlink(tmp_path: Path, monkeypatch):
    tarball = tmp_path / "python.tar.gz"
    tarball.write_bytes(
        _tar_bytes(
            [
                ("python/bin/python3.12", b"fake", None),
                ("python/bin/python3", b"", "python3.12"),
            ]
        )
    )
    monkeypatch.setattr(sys, "platform", "darwin")
    result = bootstrap.extract_python_runtime(tarball, tmp_path / "home")
    assert result.is_symlink()
    assert result.readlink() == Path("python3.12")


def test_tar_validator_accepts_node_symlinks_and_uv_layouts():
    node_payload = _tar_bytes(
        [
            ("node-v20.18.0-darwin-arm64/bin/node", b"node", None),
            (
                "node-v20.18.0-darwin-arm64/bin/npm",
                b"",
                "../lib/node_modules/npm/bin/npm-cli.js",
            ),
            (
                "node-v20.18.0-darwin-arm64/lib/node_modules/npm/bin/npm-cli.js",
                b"cli",
                None,
            ),
        ]
    )
    with tarfile.open(fileobj=io.BytesIO(node_payload), mode="r:gz") as archive:
        archive_validation.validate_tar_members(
            archive,
            expected_root="node-v20.18.0-darwin-arm64",
        )

    uv_payload = _tar_bytes(
        [("uv-aarch64-apple-darwin/uv", b"uv", None)]
    )
    with tarfile.open(fileobj=io.BytesIO(uv_payload), mode="r:gz") as archive:
        archive_validation.validate_tar_members(
            archive,
            expected_root="uv-aarch64-apple-darwin",
            required_members={"uv-aarch64-apple-darwin/uv"},
        )
