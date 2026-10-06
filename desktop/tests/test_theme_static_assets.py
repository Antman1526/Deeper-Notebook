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


def test_first_run_wizard_starts_in_the_indigo_default():
    # v0.8.130 — decision of 2026-09-30: indigo is the one brand. The wizard
    # opened, and preselected, teal Research Core Dark.
    from desktop.config import DEFAULT_THEME

    static = ROOT / "desktop/first_run/static"
    assert f'data-theme="{DEFAULT_THEME}"' in (static / "index.html").read_text()
    wizard = (static / "wizard.js").read_text()
    assert f"let chosenTheme = '{DEFAULT_THEME}';" in wizard
    assert "research-core-dark" not in wizard


def test_first_run_catalog_features_the_indigo_pair_first():
    source = (ROOT / "desktop/first_run/static/theme-catalog.generated.js").read_text()
    catalog = json.loads(source.removeprefix("window.DN_THEME_CATALOG = ").removesuffix(";\n"))
    assert [entry["id"] for entry in catalog[:2]] == ["gemini-forward-light", "gemini-forward-dark"]
    assert {entry["group"] for entry in catalog[:2]} == {"featured"}
