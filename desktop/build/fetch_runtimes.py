"""Download pinned SurrealDB + Node.js runtimes into desktop/bin/ for the host platform."""
from __future__ import annotations

import platform
import shutil
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

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


def download(url: str, dest: Path) -> None:
    print(f"  downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f)


def fetch_surreal(version: str, url: str, arch: str) -> None:
    BIN.mkdir(parents=True, exist_ok=True)
    if arch.startswith("windows"):
        out = BIN / f"surreal-{arch}.exe"
        download(url, out)
    else:
        archive = BIN / "surreal.tgz"
        download(url, archive)
        with tarfile.open(archive) as t:
            t.extract("surreal", path=BIN)
        archive.unlink()
        (BIN / "surreal").rename(BIN / f"surreal-{arch}")
        (BIN / f"surreal-{arch}").chmod(0o755)
    print(f"  surreal v{version} → {BIN}/surreal-{arch}")


def fetch_node(version: str, url: str, arch: str) -> None:
    out_dir = BIN / f"node-{arch}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    if arch.startswith("windows"):
        archive = BIN / "node.zip"
        download(url, archive)
        with zipfile.ZipFile(archive) as z:
            z.extractall(BIN)
        # Node win zip extracts to node-vX.Y.Z-win-x64/
        extracted = next(BIN.glob(f"node-v{version}-*"))
        extracted.rename(out_dir)
        archive.unlink()
    else:
        archive = BIN / "node.tar.gz"
        download(url, archive)
        with tarfile.open(archive) as t:
            t.extractall(BIN)
        extracted = next(BIN.glob(f"node-v{version}-*"))
        extracted.rename(out_dir)
        archive.unlink()
    print(f"  node v{version} → {out_dir}")


def main() -> int:
    arch = host_arch()
    cfg = tomllib.loads(RUNTIMES.read_text())
    print(f"Fetching runtimes for {arch}")
    fetch_surreal(cfg["surrealdb"]["version"], cfg["surrealdb"]["urls"][arch], arch)
    fetch_node(cfg["node"]["version"], cfg["node"]["urls"][arch], arch)

    # Sanity check
    surreal = BIN / (f"surreal-{arch}.exe" if arch.startswith("windows") else f"surreal-{arch}")
    node_bin = BIN / f"node-{arch}" / ("node.exe" if arch.startswith("windows") else "bin/node")
    print(f"\nVerifying:")
    print(f"  surreal: {surreal} ({surreal.stat().st_size // 1024 // 1024} MB)")
    print(f"  node:    {node_bin} ({node_bin.stat().st_size // 1024 // 1024} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
