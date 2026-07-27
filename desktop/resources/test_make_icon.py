from __future__ import annotations

import importlib.util
from pathlib import Path

from PIL import Image, ImageDraw

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKE_ICON_PATH = REPOSITORY_ROOT / "desktop/resources/make_icon.py"
MAKE_ICON_SPEC = importlib.util.spec_from_file_location("make_icon", MAKE_ICON_PATH)
assert MAKE_ICON_SPEC and MAKE_ICON_SPEC.loader
make_icon = importlib.util.module_from_spec(MAKE_ICON_SPEC)
MAKE_ICON_SPEC.loader.exec_module(make_icon)

REQUIRED_ICO_SIZES = {
    (16, 16),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
}
APPROVED_PALETTE = {
    "deep": (7, 27, 29, 255),
    "dark_teal": (15, 118, 110, 255),
    "teal": (45, 212, 191, 255),
    "cyan": (56, 189, 248, 255),
    "light": (204, 251, 241, 255),
}


def _largest_rgba(path: Path) -> Image.Image:
    image = Image.open(path)
    if image.format == "ICO":
        image = image.ico.getimage((256, 256))
    return image.convert("RGBA")


def _contains_near_color(
    colors: set[tuple[int, int, int, int]],
    target: tuple[int, int, int, int],
    tolerance: int = 18,
) -> bool:
    return any(
        color[3] == target[3]
        and max(abs(color[channel] - target[channel]) for channel in range(3))
        <= tolerance
        for color in colors
    )


def test_icon_generator_declares_the_approved_palette() -> None:
    assert make_icon.PALETTE == APPROVED_PALETTE


def test_master_renders_notebook_spark_geometry_on_transparent_corners() -> None:
    master = make_icon.render_master()

    assert master.size == (1024, 1024)
    assert master.mode == "RGBA"
    assert master.getpixel((0, 0))[3] == 0
    assert master.getpixel((512, 80)) == APPROVED_PALETTE["deep"]
    assert master.getpixel((480, 680)) == APPROVED_PALETTE["dark_teal"]
    assert master.getpixel((628, 360)) == APPROVED_PALETTE["light"]
    assert master.getpixel((628, 452)) == APPROVED_PALETTE["cyan"]


def test_gradient_outline_has_no_background_seams_at_rounded_joins() -> None:
    master = make_icon.render_master()
    outline = make_icon._notebook_outline()
    join_mask = Image.new("L", master.size, 0)
    join_draw = ImageDraw.Draw(join_mask)
    inset_radius = (12 * make_icon.SCALE // 2) - 2

    for x, y in outline:
        join_draw.ellipse(
            (
                x - inset_radius,
                y - inset_radius,
                x + inset_radius,
                y + inset_radius,
            ),
            fill=255,
        )

    background_colors = {
        APPROVED_PALETTE["deep"],
        (0, 0, 0, 255),
    }
    seams = sum(
        1
        for pixel, covered in zip(master.getdata(), join_mask.getdata(), strict=True)
        if covered and pixel in background_colors
    )
    assert seams == 0


def test_generator_exposes_frontend_favicon_writer() -> None:
    assert callable(make_icon.write_frontend_favicon)


def test_generated_icons_contain_the_brand_and_required_representations() -> None:
    artifacts = [
        REPOSITORY_ROOT / "desktop/resources/icon.png",
        REPOSITORY_ROOT / "desktop/resources/icon.icns",
        REPOSITORY_ROOT / "desktop/resources/icon.ico",
        REPOSITORY_ROOT / "frontend/src/app/favicon.ico",
    ]

    for artifact in artifacts:
        assert artifact.is_file()
        assert artifact.stat().st_size > 0
        image = _largest_rgba(artifact)
        assert max(image.size) >= 256
        colors = set(image.getdata())
        for role, expected in APPROVED_PALETTE.items():
            assert _contains_near_color(colors, expected), (
                f"{artifact} is missing the {role} Research Core color"
            )

    with Image.open(REPOSITORY_ROOT / "desktop/resources/icon.ico") as icon:
        assert icon.ico.sizes() == REQUIRED_ICO_SIZES

    with Image.open(REPOSITORY_ROOT / "frontend/src/app/favicon.ico") as favicon:
        assert (256, 256) in favicon.ico.sizes()
