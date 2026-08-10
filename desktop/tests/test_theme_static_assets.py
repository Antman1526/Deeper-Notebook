import json
from pathlib import Path

from desktop.window import _THEMES
from scripts.render_theme_static_assets import render_assets

ROOT = Path(__file__).resolve().parents[2]


def test_generated_theme_assets_are_current():
    assert render_assets(check=True) == 0


def test_first_run_catalog_contains_every_runtime_theme():
    source = (ROOT / "desktop/first_run/static/theme-catalog.generated.js").read_text()
    prefix = "window.DN_THEME_CATALOG = "
    assert source.startswith(prefix)
    catalog = json.loads(source.removeprefix(prefix).removesuffix(";\n"))
    assert {entry["id"] for entry in catalog} == set(_THEMES)
