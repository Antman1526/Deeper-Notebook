"""First-run wizard i18n contract.

v0.8.130 — the wizard shipped hardcoded English while the app itself has 14
locales. These tests pin the dictionary shape (identical keys, placeholders and
markup per locale) and that every key the page/script asks for really exists,
so a typo shows up here instead of as a raw key on a first-run screen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "desktop/first_run/static"

LOCALES = [
    "en-US", "de-DE", "es-ES", "ca-ES", "fr-FR", "it-IT", "pt-BR",
    "pl-PL", "ru-RU", "tr-TR", "ja-JP", "zh-CN", "zh-TW", "bn-IN",
]
THEME_KEYS = [
    "theme.dark",
    "theme.high-contrast-dark",
    "theme.high-contrast-light",
    "theme.light-blue",
    "theme.paper",
    "theme.system",
]
# The six generic theme names are translated in the main app. Where a locale
# there keeps the English word for "Dark" the wizard may too.
FRONTEND_THEME_NAME_KEYS = {
    "theme.dark": "themeNameDark",
    "theme.high-contrast-dark": "themeNameHighContrastDark",
    "theme.high-contrast-light": "themeNameHighContrastLight",
    "theme.light-blue": "themeNameLightBlue",
    "theme.paper": "themeNamePaper",
    "theme.system": "themeNameSystem",
}

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_TAG = re.compile(r"<[^>]+>")


@pytest.fixture(scope="module")
def dictionary() -> dict[str, dict[str, str]]:
    source = (STATIC / "wizard-i18n.js").read_text(encoding="utf-8")
    prefix = "window.DN_WIZARD_I18N = "
    start = source.index(prefix) + len(prefix)
    # Strict JSON on purpose: no JS parser needed, and no trailing commas.
    value, _end = json.JSONDecoder().raw_decode(source[start:])
    return value


@pytest.fixture(scope="module")
def index_html() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def wizard_js() -> str:
    return (STATIC / "wizard.js").read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_all_fourteen_locales_present(dictionary):
    assert set(dictionary) == set(LOCALES)


def test_every_locale_has_identical_key_set(dictionary):
    expected = set(dictionary["en-US"])
    for locale in LOCALES:
        keys = set(dictionary[locale])
        assert keys == expected, (
            f"{locale}: missing={sorted(expected - keys)} extra={sorted(keys - expected)}"
        )


def test_no_empty_values(dictionary):
    for locale in LOCALES:
        for key, value in dictionary[locale].items():
            assert isinstance(value, str) and value.strip(), f"{locale}:{key} is empty"


def test_placeholders_match_english(dictionary):
    for locale in LOCALES:
        for key, value in dictionary[locale].items():
            assert sorted(_PLACEHOLDER.findall(value)) == sorted(
                _PLACEHOLDER.findall(dictionary["en-US"][key])
            ), f"{locale}:{key} placeholder mismatch"


def test_html_tags_match_english(dictionary):
    # Markup-bearing values are injected with innerHTML; the tag sequence
    # (attributes included, so hrefs cannot drift) must equal the English one.
    for locale in LOCALES:
        for key, value in dictionary[locale].items():
            assert _TAG.findall(value) == _TAG.findall(dictionary["en-US"][key]), (
                f"{locale}:{key} markup mismatch"
            )


_I18N_ATTR = re.compile(r'data-i18n(?:-html)?="([^"]+)"')
_I18N_ATTR_PAIRS = re.compile(r'data-i18n-attr="([^"]+)"')


def _html_keys(index_html: str) -> set[str]:
    keys = set(_I18N_ATTR.findall(index_html))
    for pairs in _I18N_ATTR_PAIRS.findall(index_html):
        for pair in pairs.split(","):
            attr, _, key = pair.partition(":")
            assert attr.strip() and key.strip(), f"malformed data-i18n-attr {pairs!r}"
            keys.add(key.strip())
    return keys


def test_index_html_keys_exist(dictionary, index_html):
    keys = _html_keys(index_html)
    assert keys, "index.html uses no i18n keys"
    assert keys <= set(dictionary["en-US"]), sorted(keys - set(dictionary["en-US"]))


def test_index_html_english_fallback_matches_dictionary(dictionary, index_html):
    # The English text left in the HTML is the no-JS fallback; it must stay
    # identical to the en-US dictionary so en-US users see no change.
    pattern = re.compile(
        r'<(\w+)\b[^>]*\bdata-i18n(?:-html)?="([^"]+)"[^>]*>(.*?)</\1>', re.DOTALL
    )
    found = 0
    for _tag, key, inner in pattern.findall(index_html):
        found += 1
        assert _norm(inner) == _norm(dictionary["en-US"][key]), key
    assert found >= 20


def test_wizard_js_literal_keys_exist(dictionary, wizard_js):
    keys = set(re.findall(r"dnWizardT\(\s*(['\"])([^'\"]+)\1\s*[,)]", wizard_js))
    keys = {key for _quote, key in keys}
    assert keys, "wizard.js calls dnWizardT with no literal keys"
    assert keys <= set(dictionary["en-US"]), sorted(keys - set(dictionary["en-US"]))


def test_wizard_js_has_no_leftover_english_ui_strings(wizard_js):
    # Comments may quote the old English (the v0.5.10 note does); only code counts.
    code = "\n".join(
        line for line in wizard_js.splitlines() if not line.lstrip().startswith("//")
    )
    for phrase in (
        "Saving config",
        "Failed to save config",
        "Retrying",
        "Failed again",
        "starting…",
        "progress stream disconnected",
        "'Retry'",
    ):
        assert phrase not in code, phrase


def test_index_loads_i18n_before_wizard(index_html):
    i18n = index_html.index('src="/static/wizard-i18n.js"')
    wizard = index_html.index('src="/static/wizard.js"')
    assert i18n < wizard


def test_generic_theme_keys_exist_everywhere(dictionary):
    for locale in LOCALES:
        for key in THEME_KEYS:
            assert key in dictionary[locale], f"{locale}:{key}"


def _frontend_theme_names(locale: str) -> dict[str, str]:
    source = (ROOT / f"frontend/src/lib/locales/{locale}/index.ts").read_text(encoding="utf-8")
    names = {}
    for wizard_key, ts_key in FRONTEND_THEME_NAME_KEYS.items():
        match = re.search(rf'\b{ts_key}:\s*"((?:[^"\\]|\\.)*)"', source)
        assert match, f"{locale}: {ts_key} not found in frontend locale"
        names[wizard_key] = match.group(1)
    return names


def test_theme_names_agree_with_frontend_locales(dictionary):
    # The wizard and the main app must name the same theme the same way.
    for locale in LOCALES:
        frontend = _frontend_theme_names(locale)
        for key in THEME_KEYS:
            assert dictionary[locale][key] == frontend[key], f"{locale}:{key}"


def test_non_english_dark_theme_is_translated_unless_frontend_keeps_english(dictionary):
    english = dictionary["en-US"]["theme.dark"]
    for locale in LOCALES:
        if locale == "en-US":
            continue
        if _frontend_theme_names(locale)["theme.dark"] == english:
            continue
        assert dictionary[locale]["theme.dark"] != english, locale


def test_non_english_locales_are_actually_translated(dictionary):
    # Guard against a locale that was copy-pasted from English: most values
    # must differ. Proper-noun-only values (none today) would be the exception.
    english = dictionary["en-US"]
    for locale in LOCALES:
        if locale == "en-US":
            continue
        same = [k for k, v in dictionary[locale].items() if v == english[k]]
        assert len(same) <= 3, f"{locale} leaves English values: {same}"
