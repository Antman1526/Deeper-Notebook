"""v0.8.88 — tests for opt-in source auto-summary (preview + default-off)."""

from api.routers.sources import _summary_preview
from deeper_notebook.domain.content_settings import ContentSettings


def test_summary_preview_handles_empty():
    assert _summary_preview(None) is None
    assert _summary_preview("") is None
    assert _summary_preview("   ") is None


def test_summary_preview_passthrough_and_collapse():
    assert _summary_preview("short summary") == "short summary"
    # Collapses arbitrary whitespace runs to single spaces.
    assert _summary_preview("a\n\n  b\tc") == "a b c"


def test_summary_preview_truncates_long_text():
    preview = _summary_preview("word " * 100)
    assert len(preview) <= 140
    assert preview.endswith("…")


def test_auto_summarize_defaults_off():
    # Opt-in: the ingest hook must NOT summarize unless the user enables it.
    field = ContentSettings.model_fields["auto_summarize_on_ingest"]
    assert field.default is False
