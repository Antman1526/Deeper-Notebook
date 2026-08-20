from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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
REQUIRED_ICNS_REPRESENTATIONS = {
    (16, 16, 2),
    (32, 32, 2),
    (128, 128, 1),
    (128, 128, 2),
    (256, 256, 1),
    (256, 256, 2),
    (512, 512, 1),
    (512, 512, 2),
}
REQUIRED_ICONSET_FILES = {
    "icon_16x16.png": (16, 16),
    "icon_16x16@2x.png": (32, 32),
    "icon_32x32.png": (32, 32),
    "icon_32x32@2x.png": (64, 64),
    "icon_128x128.png": (128, 128),
    "icon_128x128@2x.png": (256, 256),
    "icon_256x256.png": (256, 256),
    "icon_256x256@2x.png": (512, 512),
    "icon_512x512.png": (512, 512),
    "icon_512x512@2x.png": (1024, 1024),
}
ICONUTIL = shutil.which("iconutil")
CAN_EXTRACT_NATIVE_ICNS = sys.platform == "darwin" and ICONUTIL is not None
APPROVED_PALETTE = {
    "deep": (7, 27, 29, 255),
    "dark_teal": (15, 118, 110, 255),
    "teal": (45, 212, 191, 255),
    "cyan": (56, 189, 248, 255),
    "light": (204, 251, 241, 255),
}
COMMITTED_ARTIFACTS = {
    "png": REPOSITORY_ROOT / "desktop/resources/icon.png",
    "icns": REPOSITORY_ROOT / "desktop/resources/icon.icns",
    "ico": REPOSITORY_ROOT / "desktop/resources/icon.ico",
    "favicon": REPOSITORY_ROOT / "frontend/src/app/favicon.ico",
}


def _color_distance(
    actual: tuple[int, int, int, int],
    expected: tuple[int, int, int, int],
) -> int:
    return max(abs(actual[channel] - expected[channel]) for channel in range(4))


def _relative_luminance(color: tuple[int, int, int, int]) -> float:
    channels = []
    for value in color[:3]:
        channel = value / 255
        channels.append(
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> float:
    high, low = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (high + 0.05) / (low + 0.05)


def _assert_brand_content(image: Image.Image, *, require_transparency: bool) -> None:
    rgba = image.convert("RGBA")
    colors = set(rgba.getdata())
    if require_transparency:
        assert rgba.getchannel("A").getextrema() == (0, 255)
    # The diagonal teal-to-cyan outline has sub-pixel coverage at 16px, so its
    # teal endpoint is legitimately blended. Palette constants are pinned
    # separately; the tiny-frame content contract pins the four solid roles.
    expected_roles = (
        APPROVED_PALETTE
        if rgba.width > 16
        else {
            role: APPROVED_PALETTE[role]
            for role in ("deep", "dark_teal", "cyan", "light")
        }
    )
    for role, expected in expected_roles.items():
        assert any(_color_distance(color, expected) <= 18 for color in colors), (
            f"{rgba.size} frame is missing the {role} Research Core color"
        )


def _assert_spark_visible(image: Image.Image) -> None:
    rgba = image.convert("RGBA")
    size = rgba.width
    left = max(0, int(120 * size / 256))
    top = max(0, int(76 * size / 256))
    right = min(size, int(194 * size / 256) + 1)
    bottom = min(size, int(150 * size / 256) + 1)
    spark = rgba.crop((left, top, right, bottom))
    colors = list(spark.getdata())
    light_pixels = [
        color
        for color in colors
        if _color_distance(color, APPROVED_PALETTE["light"]) <= 18
    ]
    cyan_pixels = [
        color
        for color in colors
        if _color_distance(color, APPROVED_PALETTE["cyan"]) <= 18
    ]

    assert light_pixels, f"{size}px frame lost the light spark"
    assert cyan_pixels, f"{size}px frame lost the cyan spark core"
    if size == 16:
        assert len(light_pixels) >= 6
        assert (
            _contrast(
                APPROVED_PALETTE["light"],
                APPROVED_PALETTE["dark_teal"],
            )
            >= 4.5
        )


@pytest.fixture(scope="module")
def generated_assets(tmp_path_factory):
    first_root = tmp_path_factory.mktemp("generated-icons-first")
    second_root = tmp_path_factory.mktemp("generated-icons-second")
    first = make_icon.generate_assets(
        first_root / "desktop",
        first_root / "frontend/favicon.ico",
    )
    second = make_icon.generate_assets(
        second_root / "desktop",
        second_root / "frontend/favicon.ico",
    )
    return first, second


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


@pytest.mark.parametrize("artifact_name", ["ico", "favicon"])
def test_committed_16px_frames_keep_the_light_spark(artifact_name: str) -> None:
    with Image.open(COMMITTED_ARTIFACTS[artifact_name]) as icon:
        frame = icon.ico.getimage((16, 16)).copy()
    _assert_spark_visible(frame)


def test_generation_is_deterministic_and_matches_committed_artifacts(
    generated_assets,
) -> None:
    first, second = generated_assets

    expected_names = set(COMMITTED_ARTIFACTS)
    if not CAN_EXTRACT_NATIVE_ICNS:
        expected_names.remove("icns")
    assert set(first) == expected_names
    assert set(second) == expected_names
    for name in expected_names:
        committed = COMMITTED_ARTIFACTS[name]
        first_bytes = first[name].read_bytes()
        second_bytes = second[name].read_bytes()
        assert (
            hashlib.sha256(first_bytes).digest()
            == hashlib.sha256(second_bytes).digest()
        )
        assert first_bytes == committed.read_bytes()


@pytest.mark.parametrize("artifact_name", ["ico", "favicon"])
def test_every_required_ico_frame_contains_the_mark(
    generated_assets,
    artifact_name: str,
) -> None:
    generated, _ = generated_assets
    with Image.open(generated[artifact_name]) as icon:
        assert icon.ico.sizes() == REQUIRED_ICO_SIZES
        for size in sorted(REQUIRED_ICO_SIZES):
            frame = icon.ico.getimage(size)
            assert frame.size == size
            _assert_brand_content(frame, require_transparency=True)
            _assert_spark_visible(frame)


@pytest.mark.skipif(
    not CAN_EXTRACT_NATIVE_ICNS,
    reason="native ICNS generation requires macOS iconutil",
)
def test_every_generated_icns_representation_contains_the_mark(
    generated_assets,
) -> None:
    generated, _ = generated_assets
    with Image.open(generated["icns"]) as icon:
        representations = set(icon.info["sizes"])
        assert representations == REQUIRED_ICNS_REPRESENTATIONS
        for representation in sorted(representations):
            frame = icon.icns.getimage(representation)
            _assert_brand_content(frame, require_transparency=True)
            _assert_spark_visible(frame)


@pytest.mark.skipif(
    not CAN_EXTRACT_NATIVE_ICNS,
    reason="native ICNS iconset extraction requires macOS iconutil",
)
def test_native_icns_round_trip_contains_the_exact_ten_file_iconset(
    generated_assets,
    tmp_path,
) -> None:
    first, second = generated_assets
    artifacts = {
        "first": first["icns"],
        "second": second["icns"],
        "committed": COMMITTED_ARTIFACTS["icns"],
    }

    for label, artifact in artifacts.items():
        extracted = tmp_path / f"{label}.iconset"
        subprocess.run(
            [ICONUTIL, "-c", "iconset", str(artifact), "-o", str(extracted)],
            check=True,
            capture_output=True,
            text=True,
        )
        files = {}
        for path in extracted.iterdir():
            if path.is_file():
                with Image.open(path) as image:
                    files[path.name] = image.size
                    _assert_brand_content(image, require_transparency=True)
                    _assert_spark_visible(image)
        assert files == REQUIRED_ICONSET_FILES, label


def test_mac_icns_writer_rejects_non_macos_hosts(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(make_icon.sys, "platform", "linux")

    with pytest.raises(RuntimeError, match="macOS"):
        make_icon.write_mac_icns(
            make_icon.render_master(),
            tmp_path / "icon.icns",
        )


def test_mac_icns_writer_requires_iconutil(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(make_icon.sys, "platform", "darwin")
    monkeypatch.setattr(
        make_icon,
        "ICONUTIL",
        tmp_path / "missing-iconutil",
        raising=False,
    )

    with pytest.raises(RuntimeError, match="iconutil"):
        make_icon.write_mac_icns(
            make_icon.render_master(),
            tmp_path / "icon.icns",
        )


def test_non_macos_generation_skips_the_native_icns(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(make_icon.sys, "platform", "linux")

    generated = make_icon.generate_assets(
        tmp_path / "desktop",
        tmp_path / "frontend/favicon.ico",
    )

    assert generated.keys() == {"png", "ico", "favicon"}
    assert all(path.is_file() for path in generated.values())


def test_generated_png_contains_the_full_resolution_mark(generated_assets) -> None:
    generated, _ = generated_assets
    with Image.open(generated["png"]) as image:
        assert image.size == (1024, 1024)
        _assert_brand_content(image, require_transparency=True)
        _assert_spark_visible(image)
