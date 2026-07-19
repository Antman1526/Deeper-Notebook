from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parents[1] / "resources"


def test_master_icon_is_transparent_rgba():
    image = Image.open(ROOT / "icon.png")
    assert image.mode == "RGBA"
    assert image.size == (1024, 1024)
    assert image.getchannel("A").getextrema() == (0, 255)
    assert all(
        image.getpixel(point)[3] == 0
        for point in ((0, 0), (1023, 0), (0, 1023), (1023, 1023))
    )


def test_generator_preserves_master_and_writes_ico_sets():
    master = ROOT / "icon.png"
    before = hashlib.sha256(master.read_bytes()).digest()
    subprocess.run([sys.executable, str(ROOT / "make_icon.py")], check=True)
    assert hashlib.sha256(master.read_bytes()).digest() == before

    with Image.open(ROOT / "icon.ico") as icon:
        assert icon.ico.sizes() == {
            (16, 16), (32, 32), (48, 48),
            (64, 64), (128, 128), (256, 256),
        }
    with Image.open(Path(__file__).parents[2] / "frontend/src/app/favicon.ico") as favicon:
        assert favicon.ico.sizes() == {(16, 16), (32, 32), (48, 48)}
