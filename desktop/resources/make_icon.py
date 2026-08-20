"""Generate Deeper Notebook app icons from the canonical Notebook Spark mark.

Run: uv run python desktop/resources/make_icon.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow not installed. Run: pip install Pillow==11.0.0", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]
CANONICAL_MARK = REPOSITORY_ROOT / "brand/deeper-notebook-mark.svg"
FRONTEND_FAVICON = REPOSITORY_ROOT / "frontend/src/app/favicon.ico"
ICONUTIL = Path("/usr/bin/iconutil")

SIZE = 1024
SCALE = SIZE // 256
RGBA = tuple[int, int, int, int]
PALETTE: dict[str, RGBA] = {
    "deep": (7, 27, 29, 255),
    "dark_teal": (15, 118, 110, 255),
    "teal": (45, 212, 191, 255),
    "cyan": (56, 189, 248, 255),
    "light": (204, 251, 241, 255),
}
ICO_SIZES = (16, 32, 48, 64, 128, 256)
ICONSET_FILES = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)


def _validate_canonical_mark() -> None:
    """Fail before rendering if the canonical accessible vector drifts."""
    root = ElementTree.parse(CANONICAL_MARK).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    title = root.find("svg:title", namespace)
    paths = root.findall("svg:path", namespace)
    expected_paths = {
        "M63 53h101c18 0 29 11 29 29v119H91c-16 0-28-12-28-28V53Z",
        "M91 53v148",
        "m157 82 8 23 23 8-23 8-8 23-8-23-23-8 23-8 8-23Z",
    }

    if (
        root.get("viewBox") != "0 0 256 256"
        or root.get("role") != "img"
        or root.get("aria-labelledby") != "title"
        or title is None
        or title.text != "Deeper Notebook"
        or {path.get("d") for path in paths} != expected_paths
    ):
        raise ValueError(f"Canonical Notebook Spark geometry drifted: {CANONICAL_MARK}")

    source = CANONICAL_MARK.read_text(encoding="utf-8").upper()
    missing_colors = {
        f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
        for color in PALETTE.values()
        if f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}" not in source
    }
    if missing_colors:
        raise ValueError(
            f"Canonical Notebook Spark palette is incomplete: {missing_colors}"
        )


def _point(x: float, y: float) -> tuple[float, float]:
    return x * SCALE, y * SCALE


def _cubic_points(
    start: tuple[float, float],
    control_1: tuple[float, float],
    control_2: tuple[float, float],
    end: tuple[float, float],
    *,
    steps: int = 24,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for step in range(1, steps + 1):
        t = step / steps
        inverse = 1 - t
        x = (
            inverse**3 * start[0]
            + 3 * inverse**2 * t * control_1[0]
            + 3 * inverse * t**2 * control_2[0]
            + t**3 * end[0]
        )
        y = (
            inverse**3 * start[1]
            + 3 * inverse**2 * t * control_1[1]
            + 3 * inverse * t**2 * control_2[1]
            + t**3 * end[1]
        )
        points.append((x, y))
    return points


def _core_gradient() -> Image.Image:
    start = _point(48, 36)
    end = _point(210, 220)
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    denominator = delta_x**2 + delta_y**2
    top = PALETTE["teal"]
    bottom = PALETTE["cyan"]
    image = Image.new("RGBA", (SIZE, SIZE), top)
    pixels = image.load()

    for y in range(SIZE):
        for x in range(SIZE):
            amount = ((x - start[0]) * delta_x + (y - start[1]) * delta_y) / denominator
            amount = min(1.0, max(0.0, amount))
            pixels[x, y] = (
                round(top[0] * (1 - amount) + bottom[0] * amount),
                round(top[1] * (1 - amount) + bottom[1] * amount),
                round(top[2] * (1 - amount) + bottom[2] * amount),
                255,
            )
    return image


def _notebook_outline() -> list[tuple[float, float]]:
    top_left = _point(63, 53)
    top_right = _point(164, 53)
    upper_curve_end = _point(193, 82)
    lower_right = _point(193, 201)
    lower_left = _point(91, 201)
    lower_curve_end = _point(63, 173)

    return [
        top_left,
        top_right,
        *_cubic_points(
            top_right,
            _point(182, 53),
            _point(193, 64),
            upper_curve_end,
        ),
        lower_right,
        lower_left,
        *_cubic_points(
            lower_left,
            _point(75, 201),
            _point(63, 189),
            lower_curve_end,
        ),
        top_left,
    ]


def _draw_notebook_spark(canvas: Image.Image) -> None:
    outline = _notebook_outline()
    draw = ImageDraw.Draw(canvas)
    draw.polygon(outline, fill=PALETTE["dark_teal"])

    stroke_mask = Image.new("L", canvas.size, 0)
    mask_draw = ImageDraw.Draw(stroke_mask)
    stroke_width = 12 * SCALE
    stroke_radius = stroke_width // 2
    mask_draw.line(
        outline,
        fill=255,
        width=stroke_width,
    )
    # Pillow's polyline joins can leave radial one-pixel seams on sampled
    # Bézier curves. SVG `stroke-linejoin="round"` is a union of round joins,
    # so explicitly union a stroke-radius disc at every sampled point.
    for x, y in outline:
        mask_draw.ellipse(
            (
                x - stroke_radius,
                y - stroke_radius,
                x + stroke_radius,
                y + stroke_radius,
            ),
            fill=255,
        )
    gradient_stroke = Image.composite(
        _core_gradient(),
        Image.new("RGBA", canvas.size, (0, 0, 0, 0)),
        stroke_mask,
    )
    canvas.alpha_composite(gradient_stroke)

    spine = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    spine_draw = ImageDraw.Draw(spine)
    spine_start = _point(91, 53)
    spine_end = _point(91, 201)
    spine_width = 10 * SCALE
    spine_radius = spine_width // 2
    spine_color = (*PALETTE["light"][:3], round(255 * 0.9))
    spine_draw.line(
        (spine_start, spine_end),
        fill=spine_color,
        width=spine_width,
    )
    for x, y in (spine_start, spine_end):
        spine_draw.ellipse(
            (x - spine_radius, y - spine_radius, x + spine_radius, y + spine_radius),
            fill=spine_color,
        )
    canvas.alpha_composite(spine)

    draw = ImageDraw.Draw(canvas)
    spark = [
        _point(157, 82),
        _point(165, 105),
        _point(188, 113),
        _point(165, 121),
        _point(157, 144),
        _point(149, 121),
        _point(126, 113),
        _point(149, 105),
    ]
    draw.polygon(spark, fill=PALETTE["light"])
    circle_radius = 10 * SCALE
    circle_x, circle_y = _point(157, 113)
    draw.ellipse(
        (
            circle_x - circle_radius,
            circle_y - circle_radius,
            circle_x + circle_radius,
            circle_y + circle_radius,
        ),
        fill=PALETTE["cyan"],
    )


def render_master() -> Image.Image:
    """Render the exact 256-unit canonical geometry at 4x resolution."""
    _validate_canonical_mark()
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).rounded_rectangle(
        (0, 0, SIZE - 1, SIZE - 1),
        radius=58 * SCALE,
        fill=PALETTE["deep"],
    )
    _draw_notebook_spark(canvas)
    return canvas


def render_frame(master: Image.Image, size: int) -> Image.Image:
    """Render one deterministic frame, pixel-hinting the 16px spark."""
    frame = master.resize((size, size), Image.Resampling.LANCZOS)
    if size != 16:
        return frame

    # At 16px, ordinary Lanczos reduction averages the four-point spark into
    # the dark-teal cover until none of the approved light survives. Keep the
    # canonical large geometry untouched and hint only the same 16px spark:
    # ten light arm pixels around its cyan center.
    draw = ImageDraw.Draw(frame)
    center_x, center_y = 10, 7
    draw.point(
        [
            (center_x, center_y - 2),
            (center_x - 1, center_y - 1),
            (center_x, center_y - 1),
            (center_x + 1, center_y - 1),
            (center_x - 2, center_y),
            (center_x + 2, center_y),
            (center_x - 1, center_y + 1),
            (center_x, center_y + 1),
            (center_x + 1, center_y + 1),
            (center_x, center_y + 2),
        ],
        fill=PALETTE["light"],
    )
    draw.point((center_x, center_y), fill=PALETTE["cyan"])
    return frame


def write_mac_icns(master: Image.Image, destination: Path) -> None:
    """Package the complete native ten-file iconset with macOS iconutil."""
    if sys.platform != "darwin":
        raise RuntimeError("macOS is required to generate the native ICNS iconset")
    if not ICONUTIL.is_file():
        raise RuntimeError(f"macOS iconutil is unavailable at {ICONUTIL}")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="deeper-notebook-",
        suffix=".iconset",
        dir=destination.parent,
    ) as iconset_directory:
        iconset = Path(iconset_directory)
        for filename, size in ICONSET_FILES:
            render_frame(master, size).save(iconset / filename)
        subprocess.run(
            [
                str(ICONUTIL),
                "-c",
                "icns",
                str(iconset),
                "-o",
                str(destination),
            ],
            check=True,
            capture_output=True,
            text=True,
        )


def _write_ico(image: Image.Image, destination: Path) -> None:
    frames = [render_frame(image, size) for size in ICO_SIZES]
    largest = frames[-1]
    largest.save(
        destination,
        format="ICO",
        sizes=[frame.size for frame in frames],
        append_images=frames[:-1],
    )


def write_win_ico(master: Image.Image, destination: Path) -> None:
    """Write the Windows icon with every required exact-size frame."""
    _write_ico(master, destination)


def write_frontend_favicon(master: Image.Image, destination: Path) -> None:
    """Write the frontend favicon from the canonical 256-pixel image."""
    favicon_master = render_frame(master, 256)
    _write_ico(favicon_master, destination)


def generate_assets(
    output_dir: Path,
    favicon_path: Path,
) -> dict[str, Path]:
    """Generate every brand artifact under caller-provided paths."""
    output_dir = Path(output_dir)
    favicon_path = Path(favicon_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    favicon_path.parent.mkdir(parents=True, exist_ok=True)

    paths = {
        "png": output_dir / "icon.png",
        "icns": output_dir / "icon.icns",
        "ico": output_dir / "icon.ico",
        "favicon": favicon_path,
    }
    if sys.platform != "darwin":
        paths.pop("icns")

    master = render_master()
    master.save(paths["png"])
    if "icns" in paths:
        write_mac_icns(master, paths["icns"])
    write_win_ico(master, paths["ico"])
    write_frontend_favicon(master, paths["favicon"])
    return paths


def main() -> None:
    print("Rendering Notebook Spark master 1024x1024 ...")
    generated = generate_assets(ROOT, FRONTEND_FAVICON)
    for label, path in generated.items():
        print(f"  {label:>7} -> {path}")


if __name__ == "__main__":
    main()
