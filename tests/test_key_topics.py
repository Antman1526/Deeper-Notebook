"""v0.8.91 — tests for opt-in source key-topics extraction (parse + default-off)."""

from deeper_notebook.domain.content_settings import ContentSettings
from deeper_notebook.domain.transformation import parse_topics


def test_parse_topics_handles_empty():
    assert parse_topics(None) == []
    assert parse_topics("") == []
    assert parse_topics("   \n  \n") == []


def test_parse_topics_strips_bullets_and_numbers():
    text = (
        "- Machine learning\n* Neural networks\n• Backprop\n1. Optimizers\n2) Datasets"
    )
    assert parse_topics(text) == [
        "Machine learning",
        "Neural networks",
        "Backprop",
        "Optimizers",
        "Datasets",
    ]


def test_parse_topics_strips_markdown_and_dedupes():
    text = "- **Vector search**\n- vector search\n- `Embeddings`"
    # Case-insensitive de-dupe keeps the first; emphasis/backticks stripped.
    assert parse_topics(text) == ["Vector search", "Embeddings"]


def test_parse_topics_drops_overlong_lines_and_caps():
    long_line = "x" * 80  # over the per-topic length cap → dropped
    many = "\n".join(f"Topic {i}" for i in range(20))
    out = parse_topics(f"- {long_line}\n{many}")
    assert long_line not in out
    assert len(out) <= 8


def test_auto_extract_topics_defaults_off():
    field = ContentSettings.model_fields["auto_extract_topics_on_ingest"]
    assert field.default is False
