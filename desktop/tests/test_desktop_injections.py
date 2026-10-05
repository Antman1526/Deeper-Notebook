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
