"""Download pinned SurrealDB + Node.js + uv + python-build-standalone runtimes into desktop/bin/ for the host platform."""
from __future__ import annotations

import platform
import shutil
import sys
import tarfile
import time
import tomllib
import urllib.request
import zipfile
from pathlib import Path

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


def host_arch() -> str:
    """Return the canonical key matching runtimes.toml URL rows."""
    sys_plat = sys.platform
    machine = platform.machine().lower()
    if sys_plat == "darwin":
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x86_64"
    if sys_plat == "win32":
        return "windows-x86_64"
    raise RuntimeError(f"Unsupported platform: {sys_plat}/{machine}")


def download(url: str, dest: Path, attempts: int = 4) -> None:
    """Download atomically, retrying truncated or interrupted transfers."""
    partial = dest.with_name(f"{dest.name}.part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        print(f"  downloading {url} (attempt {attempt}/{attempts})")
        partial.unlink(missing_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
                output.flush()

                expected = response.headers.get("Content-Length")
                if expected is not None and partial.stat().st_size != int(expected):
                    raise EOFError(
                        f"truncated download: expected {expected} bytes, "
                        f"received {partial.stat().st_size}"
                    )

            partial.replace(dest)
            return
        except Exception:
            partial.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            time.sleep(2 ** (attempt - 1))


def fetch_surreal(version: str, url: str, arch: str) -> None:
    BIN.mkdir(parents=True, exist_ok=True)
    if arch.startswith("windows"):
        out = BIN / f"surreal-{arch}.exe"
        download(url, out)
    else:
        archive = BIN / "surreal.tgz"
        target = BIN / f"surreal-{arch}"
        # Pre-clean the destination so the rename below can't FileExistsError.
        if target.exists():
            target.unlink()
        try:
            download(url, archive)
            with tarfile.open(archive) as t:
                t.extract("surreal", path=BIN, filter="data")
            (BIN / "surreal").rename(target)
            target.chmod(0o755)
        finally:
            if archive.exists():
                archive.unlink()
    print(f"  surreal v{version} -> {BIN}/surreal-{arch}")


def fetch_node(version: str, url: str, arch: str) -> None:
    out_dir = BIN / f"node-{arch}"
    if out_dir.exists():
        shutil.rmtree(out_dir)

    # Pre-clean any stale intermediate extraction directory left over from an
    # aborted prior run; otherwise the glob below could pick the wrong one.
    for stale in BIN.glob(f"node-v{version}-*"):
        if stale.is_dir():
            shutil.rmtree(stale)

    if arch.startswith("windows"):
        archive = BIN / "node.zip"
        try:
            download(url, archive)
            with zipfile.ZipFile(archive) as z:
                z.extractall(BIN)
            extracted = next(BIN.glob(f"node-v{version}-*"))
            extracted.rename(out_dir)
        finally:
            if archive.exists():
                archive.unlink()
    else:
        archive = BIN / "node.tar.gz"
        try:
            download(url, archive)
            with tarfile.open(archive) as t:
                t.extractall(BIN, filter="data")
            extracted = next(BIN.glob(f"node-v{version}-*"))
            extracted.rename(out_dir)
        finally:
            if archive.exists():
                archive.unlink()
    print(f"  node v{version} -> {out_dir}")


def fetch_uv(version: str, url: str, arch: str) -> None:
    """Extract the uv binary into desktop/bin/uv (or uv.exe on Windows)."""
    BIN.mkdir(parents=True, exist_ok=True)
    is_win = arch.startswith("windows")
    uv_name = "uv.exe" if is_win else "uv"
    target = BIN / uv_name

    if is_win:
        archive = BIN / "uv.zip"
        try:
            download(url, archive)
            with zipfile.ZipFile(archive) as z:
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
            download(url, archive)
            with tarfile.open(archive, "r:gz") as t:
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


def fetch_python_standalone(version: str, python_version: str, url: str, arch: str) -> None:
    """Download python-build-standalone tarball into desktop/bin/python-<arch>.tar.gz (or .zip).

    We intentionally do NOT extract the tarball here.  PyInstaller cannot
    correctly replicate python-build-standalone's internal symlinks when it
    walks an extracted directory tree.  Instead we ship the single archive
    file and extract it on first launch inside extract_python_runtime()
    (desktop/bootstrap.py).
    """
    BIN.mkdir(parents=True, exist_ok=True)
    is_win = arch.startswith("windows")

    # Clean up any previously-extracted directory so the .app build won't
    # accidentally bundle the broken extracted tree.
    out_dir = BIN / f"python-{arch}"
    if out_dir.exists():
        print(f"  removing stale extracted tree {out_dir}")
        shutil.rmtree(out_dir)

    # Destination tarball path.
    # v0.8.66 (audit H7) — python-build-standalone's `install_only` artifact is
    # a gzip TARBALL on EVERY platform, including windows-x86_64 (see
    # runtimes.toml: the Windows URL ends in `-install_only.tar.gz`). Saving it
    # as `.zip` was a lie about the bytes: bootstrap's extractor dispatches on
    # the suffix and called zipfile.ZipFile() on gzip-tar data → BadZipFile → a
    # deterministic Windows-only first-launch crash. Always use .tar.gz.
    ext = ".tar.gz"
    tarball = BIN / f"python-{arch}{ext}"

    download(url, tarball)

    size_mb = tarball.stat().st_size // 1024 // 1024
    print(f"  python-build-standalone {version} (Python {python_version}) -> {tarball} ({size_mb} MB)")


def main() -> int:
    arch = host_arch()
    cfg = tomllib.loads(RUNTIMES.read_text())
    print(f"Fetching runtimes for {arch}")
    fetch_surreal(cfg["surrealdb"]["version"], cfg["surrealdb"]["urls"][arch], arch)
    fetch_node(cfg["node"]["version"], cfg["node"]["urls"][arch], arch)
    fetch_uv(cfg["uv"]["version"], cfg["uv"]["urls"][arch], arch)
    fetch_python_standalone(
        cfg["python_standalone"]["version"],
        cfg["python_standalone"]["python_version"],
        cfg["python_standalone"]["urls"][arch],
        arch,
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
