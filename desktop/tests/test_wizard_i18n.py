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
    # The exact-English lookup tables (backend literals) legitimately hold English.
    code = re.sub(r"const (?:FIXED_MESSAGE_KEYS|SAVE_ERROR_KEYS) = \{.*?\n  \};", "", code, flags=re.DOTALL)
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


# --- v0.8.130 follow-up: progress step labels, fixed launcher messages, save errors ---

DESKTOP = ROOT / "desktop"
_STEP_CALL = re.compile(
    r'(?:\b_progress|\b_try_spawn|\bprogress_bus\.publish|\.publish)\(\s*"([a-z_]+(?:\.[a-z_]+)*)"'
)
_STEP_TO_KIND_KEY = re.compile(r'^\s+"(supervisor\.[a-z_]+)":', re.MULTILINE)


def _launcher_step_codes() -> set[str]:
    codes: set[str] = set()
    for name in ("app.py", "launcher.py"):
        text = (DESKTOP / name).read_text(encoding="utf-8")
        codes.update(_STEP_CALL.findall(text))
        codes.update(_STEP_TO_KIND_KEY.findall(text))
    return codes


def test_launcher_step_codes_are_found():
    # Guards the collector itself: if a refactor changes how steps are emitted
    # and the regex goes blind, the test below would pass vacuously.
    codes = _launcher_step_codes()
    assert {"startup", "ready", "supervisor.surreal", "supervisor.llamacpp_chat"} <= codes
    assert len(codes) >= 15, sorted(codes)


def test_every_launcher_step_code_has_a_label_key(dictionary):
    # A step added to the launcher later fails here instead of silently
    # showing a raw "supervisor › something" in the wizard.
    missing = [c for c in sorted(_launcher_step_codes()) if f"step.{c}" not in dictionary["en-US"]]
    assert not missing, missing


def test_no_stale_step_label_keys(dictionary):
    codes = _launcher_step_codes()
    stale = [k for k in dictionary["en-US"] if k.startswith("step.") and k[5:] not in codes]
    assert not stale, stale


def _js_table(wizard_js: str, name: str) -> dict[str, str]:
    block = re.search(rf"const {name} = \{{(.*?)\n  \}};", wizard_js, re.DOTALL)
    assert block, f"{name} table not found in wizard.js"
    entries = dict(re.findall(r"'([^'\n]+)':\s*'([\w.]+)'", block.group(1)))
    assert entries, f"{name} table is empty"
    return entries


def _source_has_literal(files: list[Path], literal: str) -> bool:
    quoted = f'"{literal}"'
    return any(quoted in f.read_text(encoding="utf-8") for f in files)


def test_fixed_message_table_keys_exist_and_literals_match_backend(dictionary, wizard_js):
    table = _js_table(wizard_js, "FIXED_MESSAGE_KEYS")
    sources = [DESKTOP / "app.py", DESKTOP / "launcher.py"]
    for literal, key in table.items():
        assert key.startswith("msg."), key
        assert key in dictionary["en-US"], key
        # Exact, quoted, no f-string interpolation: a reworded backend sentence
        # must fail here rather than silently fall back to English.
        assert _source_has_literal(sources, literal), f"not verbatim in app.py/launcher.py: {literal!r}"


def test_save_error_table_keys_exist_and_literals_match_server(dictionary, wizard_js):
    table = _js_table(wizard_js, "SAVE_ERROR_KEYS")
    sources = [DESKTOP / "first_run/server.py"]
    for literal, key in table.items():
        assert key.startswith("error."), key
        assert key in dictionary["en-US"], key
        assert _source_has_literal(sources, literal), f"not verbatim in server.py: {literal!r}"


def test_every_save_handler_error_string_is_mapped(wizard_js):
    # Every fixed {"error": "..."} the /api/save handler returns must be mapped.
    server = (DESKTOP / "first_run/server.py").read_text(encoding="utf-8")
    start = server.index("async def save(")
    end = server.index("async def open_url(")
    fixed = re.findall(r'json_response\(\{"(?:error|detail)":\s*"([^"]+)"', server[start:end])
    assert fixed, "no fixed error strings found in the save handler"
    table = _js_table(wizard_js, "SAVE_ERROR_KEYS")
    assert set(fixed) <= set(table), sorted(set(fixed) - set(table))


def test_wizard_js_uses_the_lookup_tables(wizard_js):
    assert "'step.' + " in wizard_js
    assert "FIXED_MESSAGE_KEYS" in wizard_js and "SAVE_ERROR_KEYS" in wizard_js


# --- v0.8.130 round 3: launcher messages that carry live values (matched by pattern) ---
#
# Approach: wizard.js holds an ordered MESSAGE_PATTERNS table of
# { re: '<JS regex source>', key: 'msg.*' } with NAMED capture groups. The test
# parses that table, converts each regex to Python, renders the backend's real
# f-strings from the AST of app.py / launcher.py with sample values, and asserts
# every pattern still matches at least one of them. A reworded backend sentence
# therefore fails here instead of silently falling back to English.

import ast
import itertools

_SAMPLES: dict[str, list[str]] = {
    "gguf_dir": ["/Users/me/AI Models/gguf"],
    "nomic_path": ["/Users/me/AI_Models/nomic-embed-text-v1.5.f16.gguf"],
    "host": ["127.0.0.1"],
    "port": ["8123"],
    "url": ["http://127.0.0.1:8000/readyz"],
    "proc.returncode": ["1", "-9"],
    "timeout": ["30", "180.0"],
    "ctx.openchronicle_available": ["True", "False"],
}
# Backend messages that are not a string literal / f-string (a str(path) call):
# assert the source fragment is still there and the regex handles sample values.
_FRAGMENT_BACKED = {
    "msg.memoryCommandsRegistered": (
        'str(commands_dst / "memory_commands.py")',
        "app.py",
        ["/Users/me/commands/memory_commands.py", "C:\\Users\\me\\commands\\memory_commands.py"],
    ),
}
# Keys whose English template intentionally differs from the raw backend text
# (the raw text was developer-speak: "available=True", a bare path).
_ENGLISH_REPHRASED = {
    "msg.openchronicleFound",
    "msg.openchronicleNotFound",
    "msg.memoryCommandsRegistered",
}


def _js_unescape(raw: str) -> str:
    return re.sub(r"\\(.)", r"\1", raw)


def _message_patterns(wizard_js: str) -> list[tuple[str, str]]:
    block = re.search(r"const MESSAGE_PATTERNS = \[(.*?)\n  \];", wizard_js, re.DOTALL)
    assert block, "MESSAGE_PATTERNS table not found in wizard.js"
    entries = re.findall(
        r"\{\s*re:\s*'((?:[^'\\]|\\.)*)',\s*key:\s*'([\w.]+)'\s*\}", block.group(1)
    )
    assert entries, "MESSAGE_PATTERNS table is empty"
    return [(_js_unescape(raw), key) for raw, key in entries]


def _py_regex(js_source: str) -> re.Pattern[str]:
    return re.compile(js_source.replace("(?<", "(?P<").replace("(?P<=", "(?<=").replace("(?P<!", "(?<!"))


def _rendered_backend_strings() -> list[str]:
    out: list[str] = []
    for name in ("app.py", "launcher.py"):
        tree = ast.parse((DESKTOP / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
            elif isinstance(node, ast.JoinedStr):
                slots: list[list[str]] = []
                for part in node.values:
                    if isinstance(part, ast.Constant):
                        slots.append([str(part.value)])
                    else:
                        expr = ast.unparse(part.value) if isinstance(part, ast.FormattedValue) else "?"
                        slots.append(_SAMPLES.get(expr, ["SAMPLE"]))
                for combo in itertools.product(*slots):
                    out.append("".join(combo))
    return out


def test_message_patterns_match_the_real_backend_sentences(dictionary, wizard_js):
    backend = _rendered_backend_strings()
    sample_values = {v for vals in _SAMPLES.values() for v in vals}
    for js_source, key in _message_patterns(wizard_js):
        assert key.startswith("msg.") and key in dictionary["en-US"], key
        pattern = _py_regex(js_source)
        if key in _FRAGMENT_BACKED:
            fragment, filename, samples = _FRAGMENT_BACKED[key]
            assert fragment in (DESKTOP / filename).read_text(encoding="utf-8"), key
            for sample in samples:
                match = pattern.search(sample)
                assert match, f"{key}: {js_source!r} does not match {sample!r}"
                assert match.group("path") == sample
            continue
        hits = [(s, pattern.search(s)) for s in backend]
        hits = [(s, m) for s, m in hits if m]
        assert hits, f"{key}: no backend sentence matches {js_source!r} (backend reworded?)"
        for s, m in hits:
            assert set(m.groupdict().values()) <= sample_values, (key, s, m.groupdict())
            if key not in _ENGLISH_REPHRASED:
                # English users must see exactly what the backend sent.
                rendered = _PLACEHOLDER.sub(
                    lambda p: m.group(p.group(1)), dictionary["en-US"][key]
                )
                assert rendered == s, (key, rendered, s)


def test_message_pattern_placeholders_equal_capture_groups(dictionary, wizard_js):
    for js_source, key in _message_patterns(wizard_js):
        groups = set(_py_regex(js_source).groupindex)
        for locale in LOCALES:
            assert set(_PLACEHOLDER.findall(dictionary[locale][key])) == groups, f"{locale}:{key}"


def test_message_pattern_table_is_ordered_and_specific(wizard_js):
    # First match wins, so no pattern may be a bare catch-all.
    for js_source, _key in _message_patterns(wizard_js):
        assert js_source.startswith("^") and js_source.endswith("$"), js_source
        assert js_source not in {"^.*$", "^.+$"}


def test_wizard_js_uses_message_patterns(wizard_js):
    assert "MESSAGE_PATTERNS" in wizard_js and "new RegExp" in wizard_js


# --- Italian speech terms follow the app's own wording (frontend it-IT) ---

def test_italian_speech_labels_use_the_apps_own_terms(dictionary):
    it = dictionary["it-IT"]
    assert it["step.supervisor.whisper"] == "Riconoscimento vocale"
    assert it["step.supervisor.piper"] == "Sintesi vocale"
    assert "Da voce a testo" not in json.dumps(it, ensure_ascii=False)
    assert "Da testo a voce" not in json.dumps(it, ensure_ascii=False)
