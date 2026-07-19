from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parents[1] / "resources"
REPO_ROOT = Path(__file__).parents[2]
REPOSITORY_ASSETS = (
    ROOT / "icon.png",
    ROOT / "icon.icns",
    ROOT / "icon.ico",
    REPO_ROOT / "frontend/src/app/favicon.ico",
)


def asset_hashes(paths: tuple[Path, ...]) -> dict[Path, bytes]:
    return {path: hashlib.sha256(path.read_bytes()).digest() for path in paths}


def test_master_icon_is_transparent_rgba():
    image = Image.open(ROOT / "icon.png")
    assert image.mode == "RGBA"
    assert image.size == (1024, 1024)
    assert image.getchannel("A").getextrema() == (0, 255)
    assert all(
        image.getpixel(point)[3] == 0
        for point in ((0, 0), (1023, 0), (0, 1023), (1023, 1023))
    )


def test_generator_preserves_master_and_writes_ico_sets(tmp_path: Path):
    repository_before = asset_hashes(REPOSITORY_ASSETS)
    resources = tmp_path / "desktop" / "resources"
    frontend = tmp_path / "frontend" / "src" / "app"
    resources.mkdir(parents=True)
    frontend.mkdir(parents=True)
    shutil.copy2(ROOT / "make_icon.py", resources / "make_icon.py")
    shutil.copy2(ROOT / "icon.png", resources / "icon.png")

    master = resources / "icon.png"
    before = hashlib.sha256(master.read_bytes()).digest()
    subprocess.run([sys.executable, str(resources / "make_icon.py")], check=True)
    assert hashlib.sha256(master.read_bytes()).digest() == before

    with Image.open(resources / "icon.ico") as icon:
        assert icon.ico.sizes() == {
            (16, 16), (32, 32), (48, 48),
            (64, 64), (128, 128), (256, 256),
        }
    with Image.open(frontend / "favicon.ico") as favicon:
        assert favicon.ico.sizes() == {(16, 16), (32, 32), (48, 48)}

    assert asset_hashes(REPOSITORY_ASSETS) == repository_before
