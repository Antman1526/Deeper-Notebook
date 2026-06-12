"""Generate Open Notebook Plus app icon (1024x1024 PNG + Mac .icns + Win .ico).

Run: python desktop/resources/make_icon.py
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    print("Pillow not installed. Run: pip install Pillow==11.0.0", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
SIZE = 1024
PRIMARY = (45, 127, 249, 255)      # #2D7FF9
ACCENT = (90, 177, 255, 255)        # #5AB1FF
WHITE = (255, 255, 255, 255)
PAGE_GREY = (216, 229, 245, 255)
TEXT_GREY = (180, 195, 215, 255)


def vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGBA", (size, size), top)
    pixels = img.load()
    for y in range(size):
        t = y / size
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(size):
            pixels[x, y] = (r, g, b, 255)
    return img


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    return mask


def draw_book(canvas: Image.Image) -> None:
    """Draw an open book centered on the canvas."""
    d = ImageDraw.Draw(canvas)
    cx, cy = SIZE // 2, SIZE // 2 + 40

    # Spine shadow
    spine_w = 12
    d.rectangle((cx - spine_w // 2, cy - 280, cx + spine_w // 2, cy + 240),
                fill=(0, 0, 80, 60))

    # Right page (slight tilt)
    right_page = [
        (cx + 4,   cy - 250),
        (cx + 360, cy - 230),
        (cx + 360, cy + 240),
        (cx + 4,   cy + 240),
    ]
    d.polygon(right_page, fill=WHITE, outline=PAGE_GREY)
    # Left page
    left_page = [
        (cx - 4,   cy - 250),
        (cx - 360, cy - 230),
        (cx - 360, cy + 240),
        (cx - 4,   cy + 240),
    ]
    d.polygon(left_page, fill=WHITE, outline=PAGE_GREY)

    # Right page text lines
    line_x_start = cx + 60
    line_x_end = cx + 320
    for i, y_off in enumerate((-120, -40, 40, 120)):
        end = line_x_end - (i % 2) * 60
        d.rectangle((line_x_start, cy + y_off - 8, end, cy + y_off + 8),
                    fill=TEXT_GREY)

    # Left page: AI sparkle (4-point star)
    sx, sy = cx - 180, cy - 30
    sparkle_r = 90
    points = []
    for i in range(8):
        angle = math.pi / 2 + i * math.pi / 4
        r = sparkle_r if i % 2 == 0 else sparkle_r // 3
        points.append((sx + r * math.cos(angle), sy - r * math.sin(angle)))
    d.polygon(points, fill=ACCENT)
    # Tiny secondary sparkles
    for (dx, dy, sz) in ((90, -90, 22), (130, 60, 16), (80, 110, 14)):
        s2_pts = []
        for i in range(8):
            angle = math.pi / 2 + i * math.pi / 4
            r = sz if i % 2 == 0 else sz // 3
            s2_pts.append((sx + dx + r * math.cos(angle), sy + dy - r * math.sin(angle)))
        d.polygon(s2_pts, fill=ACCENT)


def render_master() -> Image.Image:
    bg = vertical_gradient(SIZE, ACCENT, PRIMARY)
    mask = rounded_mask(SIZE, radius=180)
    # Apply mask: rounded square
    rounded = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    rounded.paste(bg, (0, 0), mask)
    draw_book(rounded)
    # Soft inner shadow on edge
    edge_shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    es_d = ImageDraw.Draw(edge_shadow)
    es_d.rounded_rectangle((6, 6, SIZE - 6, SIZE - 6), radius=178,
                           outline=(0, 0, 80, 100), width=8)
    edge_shadow = edge_shadow.filter(ImageFilter.GaussianBlur(8))
    rounded = Image.alpha_composite(rounded, edge_shadow)
    return rounded


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


def main() -> None:
    print("Rendering master 1024x1024 ...")
    master = render_master()
    master_png = ROOT / "icon.png"
    master.save(master_png)
    print(f"  -> {master_png}")
    if sys.platform == "darwin":
        print("Generating Mac .icns ...")
        write_mac_icns(master)
        print(f"  -> {ROOT}/icon.icns")
    print("Generating Windows .ico ...")
    write_win_ico(master)
    print(f"  -> {ROOT}/icon.ico")


if __name__ == "__main__":
    main()
