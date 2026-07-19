"""Generate platform icon derivatives from the approved 1024x1024 PNG master.

Run: python desktop/resources/make_icon.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed. Run: pip install Pillow==11.0.0", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
SIZE = 1024
MASTER_PATH = ROOT / "icon.png"
FAVICON_PATH = ROOT.parents[1] / "frontend" / "src" / "app" / "favicon.ico"


def load_master() -> Image.Image:
    master = Image.open(MASTER_PATH).convert("RGBA")
    if master.size != (SIZE, SIZE):
        raise ValueError(f"icon.png must be {SIZE}x{SIZE}; got {master.size}")
    if master.getchannel("A").getextrema()[0] != 0:
        raise ValueError("icon.png must contain transparent background pixels")
    return master


def write_mac_icns(master: Image.Image) -> None:
    """Use macOS sips/iconutil to make .icns from a master PNG."""
    iconset = ROOT / "Open Notebook Plus.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for sz, name in sizes:
        master.resize((sz, sz), Image.LANCZOS).save(iconset / name)
    out = ROOT / "icon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
                   check=True)
    shutil.rmtree(iconset)


def write_win_ico(master: Image.Image) -> None:
    """Use Pillow to write a multi-size .ico."""
    sizes = [(s, s) for s in (16, 32, 48, 64, 128, 256)]
    master.save(ROOT / "icon.ico", format="ICO", sizes=sizes)


def write_favicon(master: Image.Image) -> None:
    FAVICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    master.save(
        FAVICON_PATH,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )


def main() -> None:
    print("Loading approved master 1024x1024 ...")
    master = load_master()
    if sys.platform == "darwin":
        print("Generating Mac .icns ...")
        write_mac_icns(master)
        print(f"  -> {ROOT}/icon.icns")
    print("Generating Windows .ico ...")
    write_win_ico(master)
    print(f"  -> {ROOT}/icon.ico")
    print("Generating frontend favicon ...")
    write_favicon(master)
    print(f"  -> {FAVICON_PATH}")


if __name__ == "__main__":
    main()
