"""v0.8.130 — the controls the desktop shell injects into the app match its design.

The Memory link was a bordered box with a brain emoji, found through an English
aria-label (so it never appeared in other languages); the microphone button was an
emoji on a circle using a colour token the app does not define.
"""

import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "first_run" / "static"
MEMORY = (STATIC / "memory_injection.js").read_text(encoding="utf-8")
VOICE = (STATIC / "voice_injection.js").read_text(encoding="utf-8")

LOCALES = {
    "en", "de", "es", "ca", "fr", "it", "pt", "pl", "ru", "tr", "ja", "zh-CN", "zh-TW", "bn",
}


def _no_comments(source: str) -> str:
    return "\n".join(line for line in source.splitlines() if not line.strip().startswith("//"))


def test_no_emoji_glyphs_are_used_as_icons():
    for name, source in (("memory", MEMORY), ("voice", VOICE)):
        found = re.findall("[\U0001F300-\U0001FAFF☀-➿]", _no_comments(source))
        assert not found, f"{name}_injection.js still draws {found}"


def test_memory_link_is_a_rail_link_found_without_english_text():
    assert "dn-rail-link" in MEMORY
    # Anchored on the Settings link's href, not on a translated aria-label.
    assert 'href="/settings"' in MEMORY
    assert "<svg" in MEMORY


def test_memory_label_is_translated_for_every_app_language():
    match = re.search(r"var MEMORY_LABELS = (\{.*?\});", MEMORY, re.S)
    assert match, "MEMORY_LABELS must be a JSON object literal"
    labels = json.loads(match.group(1))
    assert set(labels) == LOCALES
    assert labels["en"] == "Memory"
    assert all(value.strip() for value in labels.values())
    assert len({labels[k] for k in ("de", "fr", "ru", "ja", "zh-CN")}) == 5


def test_microphone_button_uses_the_app_theme_tokens():
    code = _no_comments(VOICE)
    assert "--on-primary" not in code, "the app defines --primary-foreground, not --on-primary"
    assert "var(--primary-foreground" in code
    assert "var(--destructive" in code, "recording is shown in the theme's destructive colour"
    assert "borderRadius: '50%'" not in code, "controls are rounded rectangles in this design"


# --- v0.8.130 round 3: voice control strings are translated --------------------

VOICE_KEYS_EN = {
    "mic.title": "Hold to record · Release to send",
    "speaker.play": "Play this response",
    "speaker.stop": "Stop playback",
    "toast.transcribed": "Transcribed: “{text}”",
    "toast.networkError": "Network error",
    "toast.sttFailed": "STT failed: {error}",
    "toast.micDenied": "Microphone permission denied",
    "toast.ttsFailed": "TTS failed: {error}",
    "toast.voiceReady": "Voice ready",
    "toast.close": "Close notification",
}


def _voice_strings() -> dict:
    marker = "var VOICE_STRINGS = "
    start = VOICE.index(marker) + len(marker)
    value, _end = json.JSONDecoder().raw_decode(VOICE[start:])
    return value, start, _end


def test_voice_strings_is_strict_json_with_all_app_languages():
    table, _s, _e = _voice_strings()
    assert set(table) == LOCALES
    assert table["en"] == VOICE_KEYS_EN
    for lang, strings in table.items():
        assert set(strings) == set(VOICE_KEYS_EN), lang
        assert all(isinstance(v, str) and v.strip() for v in strings.values()), lang


def test_voice_strings_placeholders_match_english():
    table, _s, _e = _voice_strings()
    placeholder = re.compile(r"\{(\w+)\}")
    for lang, strings in table.items():
        for key, value in strings.items():
            assert sorted(placeholder.findall(value)) == sorted(
                placeholder.findall(table["en"][key])
            ), f"{lang}:{key}"


def test_voice_strings_are_translated_not_copied():
    table, _s, _e = _voice_strings()
    for lang, strings in table.items():
        if lang == "en":
            continue
        assert strings["mic.title"] != table["en"]["mic.title"], lang
        assert strings["speaker.play"] != table["en"]["speaker.play"], lang


def test_voice_italian_uses_the_apps_speech_terms():
    table, _s, _e = _voice_strings()
    assert "Riconoscimento vocale" in table["it"]["toast.sttFailed"]
    assert "Sintesi vocale" in table["it"]["toast.ttsFailed"]


def test_voice_injection_has_no_hardcoded_english_outside_the_table():
    _table, start, end = _voice_strings()
    code = _no_comments(VOICE[: start] + VOICE[start + end :])
    for english in (
        "Hold to record",
        "Play this response",
        "Stop playback",
        "Transcribed:",
        "Network error",
        "STT failed",
        "Microphone permission denied",
        "TTS failed",
        "Voice ready",
        "Close notification",
    ):
        assert english not in code, english


def test_voice_helper_resolves_language_at_call_time_and_labels_buttons():
    code = _no_comments(VOICE)
    assert "function vt(" in code
    assert "document.documentElement.lang" in code
    # Both buttons get an accessible name, not just a tooltip.
    assert "el.setAttribute('aria-label', text)" in code  # setLabel: mic + speaker
    assert "closeBtn.setAttribute('aria-label', vt(" in code
    assert "setLabel(fab" in code and "setLabel(btn" in code
