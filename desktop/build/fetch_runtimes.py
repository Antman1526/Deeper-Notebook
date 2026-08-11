"""Download pinned SurrealDB + Node.js + uv + python-build-standalone runtimes into desktop/bin/ for the host platform."""
from __future__ import annotations

import hashlib
import hmac
import platform
import secrets
import shutil
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from desktop.build.archive_validation import (
    validate_tar_members,
    validate_zip_members,
)

# v0.8.68 — force UTF-8 stdout/stderr. On Windows the default console codec is
# cp1252, which raised UnicodeEncodeError on the "->" status arrows below and
# crashed the whole runtime fetch in CI even though every download succeeded.
# Reconfiguring here fixes any non-ASCII output regardless of console codepage.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass  # not a reconfigurable TextIOWrapper (e.g. already wrapped) — non-fatal

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "desktop" / "bin"
RUNTIMES = ROOT / "desktop" / "build" / "runtimes.toml"
# Bound socket inactivity while retaining support for large runtime archives.
# This is deliberately an inactivity timeout, not a total download deadline.
DOWNLOAD_SOCKET_TIMEOUT_SECONDS = 60.0


def host_arch() -> str:
    """Return the canonical key matching runtimes.toml URL rows."""
    sys_plat = sys.platform
    machine = platform.machine().lower()
    if sys_plat == "darwin":
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x86_64"
    if sys_plat == "win32":
        return "windows-x86_64"
    raise RuntimeError(f"Unsupported platform: {sys_plat}/{machine}")


def _validate_https_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError(f"Runtime URL must be an absolute HTTPS URL: {url!r}")
    if parsed.username or parsed.password:
        raise ValueError("Runtime URL must not contain embedded credentials")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_download(path: Path, expected_sha256: str) -> None:
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("Runtime SHA-256 must be a 64-character hexadecimal digest")
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise ValueError("Runtime SHA-256 must be hexadecimal") from exc
    actual = _sha256_file(path)
    if not hmac.compare_digest(actual, expected_sha256.lower()):
        raise ValueError(
            f"Runtime SHA-256 mismatch for {path.name}: expected {expected_sha256.lower()}, "
            f"got {actual}"
        )


def download(url: str, dest: Path, expected_sha256: str | None = None) -> None:
    """Download and verify one task-owned runtime asset before it is used."""
    _validate_https_url(url)
    if expected_sha256 is None:
        raise ValueError("A pinned runtime SHA-256 is required")
    print(f"  downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.with_name(f".{dest.name}.{secrets.token_hex(8)}.part")
    try:
        with urllib.request.urlopen(  # nosec B310 - HTTPS validated above
            url, timeout=DOWNLOAD_SOCKET_TIMEOUT_SECONDS
        ) as r, staging.open("wb") as f:
            shutil.copyfileobj(r, f)
        _verify_download(staging, expected_sha256)
        staging.replace(dest)
    except Exception:
        # Only the unique staging path is owned by this attempt. Preserve a
        # previously verified destination if a replacement download fails.
        staging.unlink(missing_ok=True)
        raise


# Focused aliases keep the guard discoverable to desktop tests and callers
# without coupling them to the helper module's internal naming.
_validate_tar_members = validate_tar_members
_validate_zip_members = validate_zip_members


def _node_root(version: str, arch: str) -> str:
    suffix = {
        "darwin-arm64": "darwin-arm64",
        "darwin-x86_64": "darwin-x64",
        "windows-x86_64": "win-x64",
    }.get(arch)
    if suffix is None:
        raise ValueError(f"Unsupported Node runtime architecture: {arch}")
    return f"node-v{version}-{suffix}"


def _uv_root(arch: str) -> str:
    return {
        "darwin-arm64": "uv-aarch64-apple-darwin",
        "darwin-x86_64": "uv-x86_64-apple-darwin",
        "windows-x86_64": "uv-x86_64-pc-windows-msvc",
    }[arch]


def fetch_surreal(
    version: str, url: str, arch: str, expected_sha256: str | None = None,
) -> None:
    BIN.mkdir(parents=True, exist_ok=True)
    if arch.startswith("windows"):
        out = BIN / f"surreal-{arch}.exe"
        download(url, out, expected_sha256)
    else:
        archive = BIN / "surreal.tgz"
        target = BIN / f"surreal-{arch}"
        try:
            download(url, archive, expected_sha256)
            with tarfile.open(archive) as t:
                _validate_tar_members(
                    t, expected_root="surreal", exact_members={"surreal"}
                )
                # Only replace the prior binary after the new archive has
                # passed both digest and layout validation.
                target.unlink(missing_ok=True)
                (BIN / "surreal").unlink(missing_ok=True)
                t.extract("surreal", path=BIN, filter="data")  # nosec B202 - validated above
            (BIN / "surreal").rename(target)
            target.chmod(0o755)
        finally:
            if archive.exists():
                archive.unlink()
    print(f"  surreal v{version} -> {BIN}/surreal-{arch}")


def fetch_node(
    version: str, url: str, arch: str, expected_sha256: str | None = None,
) -> None:
    out_dir = BIN / f"node-{arch}"

    if arch.startswith("windows"):
        archive = BIN / "node.zip"
        try:
            download(url, archive, expected_sha256)
            with zipfile.ZipFile(archive) as z:
                _validate_zip_members(z.infolist(), expected_root=_node_root(version, arch))
                if out_dir.exists():
                    shutil.rmtree(out_dir)
                for stale in BIN.glob(f"node-v{version}-*"):
                    if stale.is_dir():
                        shutil.rmtree(stale)
                z.extractall(BIN)  # nosec B202 - validated above
            extracted = next(BIN.glob(f"node-v{version}-*"))
            extracted.rename(out_dir)
        finally:
            if archive.exists():
                archive.unlink()
    else:
        archive = BIN / "node.tar.gz"
        try:
            download(url, archive, expected_sha256)
            with tarfile.open(archive) as t:
                _validate_tar_members(t, expected_root=_node_root(version, arch))
                if out_dir.exists():
                    shutil.rmtree(out_dir)
                for stale in BIN.glob(f"node-v{version}-*"):
                    if stale.is_dir():
                        shutil.rmtree(stale)
                t.extractall(BIN, filter="data")  # nosec B202 - validated above
            extracted = next(BIN.glob(f"node-v{version}-*"))
            extracted.rename(out_dir)
        finally:
            if archive.exists():
                archive.unlink()
    print(f"  node v{version} -> {out_dir}")


def fetch_uv(
    version: str, url: str, arch: str, expected_sha256: str | None = None,
) -> None:
    """Extract the uv binary into desktop/bin/uv (or uv.exe on Windows)."""
    BIN.mkdir(parents=True, exist_ok=True)
    is_win = arch.startswith("windows")
    uv_name = "uv.exe" if is_win else "uv"
    target = BIN / uv_name

    if is_win:
        archive = BIN / "uv.zip"
        try:
            download(url, archive, expected_sha256)
            with zipfile.ZipFile(archive) as z:
                root = _uv_root(arch)
                _validate_zip_members(
                    z.infolist(),
                    expected_root=root,
                    required_members={f"{root}/uv.exe"},
                )
                # The zip contains uv.exe at the top level or inside a dir.
                # Find and extract it.
                names = z.namelist()
                exe_name = next(n for n in names if n.endswith("uv.exe"))
                with z.open(exe_name) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        finally:
            if archive.exists():
                archive.unlink()
    else:
        archive = BIN / "uv.tar.gz"
        try:
            download(url, archive, expected_sha256)
            with tarfile.open(archive, "r:gz") as t:
                root = _uv_root(arch)
                _validate_tar_members(
                    t,
                    expected_root=root,
                    required_members={f"{root}/uv"},
                )
                # The tarball contains uv-aarch64-apple-darwin/uv (or similar).
                # Find the member named */uv (not uvx).
                uv_member = next(
                    m for m in t.getmembers()
                    if m.name.endswith("/uv") or m.name == "uv"
                )
                uv_member.name = uv_name  # flatten to just "uv"
                t.extract(uv_member, path=BIN, filter="data")
        finally:
            if archive.exists():
                archive.unlink()
    target.chmod(0o755)
    print(f"  uv v{version} -> {target}")


def fetch_python_standalone(
    version: str,
    python_version: str,
    url: str,
    arch: str,
    expected_sha256: str | None = None,
) -> None:
    """Download python-build-standalone tarball into desktop/bin/python-<arch>.tar.gz (or .zip).

    We intentionally do NOT extract the tarball here.  PyInstaller cannot
    correctly replicate python-build-standalone's internal symlinks when it
    walks an extracted directory tree.  Instead we ship the single archive
    file and extract it on first launch inside extract_python_runtime()
    (desktop/bootstrap.py).
    """
    BIN.mkdir(parents=True, exist_ok=True)
    out_dir = BIN / f"python-{arch}"

    # Destination tarball path.
    # v0.8.66 (audit H7) — python-build-standalone's `install_only` artifact is
    # a gzip TARBALL on EVERY platform, including windows-x86_64 (see
    # runtimes.toml: the Windows URL ends in `-install_only.tar.gz`). Saving it
    # as `.zip` was a lie about the bytes: bootstrap's extractor dispatches on
    # the suffix and called zipfile.ZipFile() on gzip-tar data → BadZipFile → a
    # deterministic Windows-only first-launch crash. Always use .tar.gz.
    ext = ".tar.gz"
    tarball = BIN / f"python-{arch}{ext}"

    download(url, tarball, expected_sha256)

    # A verified replacement is now available; remove only the prior
    # task-owned extracted tree so packaging cannot bundle a stale copy.
    if out_dir.exists():
        print(f"  removing stale extracted tree {out_dir}")
        shutil.rmtree(out_dir)

    size_mb = tarball.stat().st_size // 1024 // 1024
    print(f"  python-build-standalone {version} (Python {python_version}) -> {tarball} ({size_mb} MB)")


def main() -> int:
    arch = host_arch()
    cfg = tomllib.loads(RUNTIMES.read_text())
    print(f"Fetching runtimes for {arch}")
    fetch_surreal(
        cfg["surrealdb"]["version"],
        cfg["surrealdb"]["urls"][arch],
        arch,
        cfg["surrealdb"]["sha256"][arch],
    )
    fetch_node(
        cfg["node"]["version"],
        cfg["node"]["urls"][arch],
        arch,
        cfg["node"]["sha256"][arch],
    )
    fetch_uv(
        cfg["uv"]["version"],
        cfg["uv"]["urls"][arch],
        arch,
        cfg["uv"]["sha256"][arch],
    )
    fetch_python_standalone(
        cfg["python_standalone"]["version"],
        cfg["python_standalone"]["python_version"],
        cfg["python_standalone"]["urls"][arch],
        arch,
        cfg["python_standalone"]["sha256"][arch],
    )

    # Sanity check
    is_win = arch.startswith("windows")
    surreal = BIN / (f"surreal-{arch}.exe" if is_win else f"surreal-{arch}")
    node_bin = BIN / f"node-{arch}" / ("node.exe" if is_win else "bin/node")
    uv_bin = BIN / ("uv.exe" if is_win else "uv")
    # v0.8.67r — python-build-standalone uses .tar.gz on all platforms
    py_ext = ".tar.gz"
    py_tarball = BIN / f"python-{arch}{py_ext}"
    print(f"\nVerifying:")
    print(f"  surreal: {surreal} ({surreal.stat().st_size // 1024 // 1024} MB)")
    print(f"  node:    {node_bin} ({node_bin.stat().st_size // 1024 // 1024} MB)")
    print(f"  uv:      {uv_bin} ({uv_bin.stat().st_size // 1024 // 1024} MB)")
    print(f"  python:  {py_tarball} ({py_tarball.stat().st_size // 1024 // 1024} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
