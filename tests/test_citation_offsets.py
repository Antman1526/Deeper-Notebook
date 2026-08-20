"""v0.8.78 — tests for citation passage location (improvement roadmap, Batch 2)."""

from deeper_notebook.utils.citation_offsets import locate_passage

TEXT = (
    "Introduction. This document covers many topics.\n\n"
    "Deep learning is a subset of machine learning that uses multi-layer "
    "neural networks to learn representations from data.\n\n"
    "Retrieval-augmented generation combines a retriever with a generator so "
    "the model can ground its answers in external documents.\n\n"
    "Conclusion. Thank you for reading."
)


def test_locates_the_matching_passage():
    m = locate_passage(TEXT, "How do neural networks learn representations?")
    assert m is not None
    # The matched window should contain the deep-learning sentence.
    assert "neural networks" in m["snippet"]
    assert "representations" in m["snippet"]
    # Offsets point at real text and don't split words.
    assert TEXT[m["start"] : m["end"]].strip() == m["snippet"]
    assert m["start"] == 0 or TEXT[m["start"] - 1].isspace()
    assert m["end"] == len(TEXT) or TEXT[m["end"]].isspace()


def test_discriminates_between_passages():
    # Sentence-sized window so adjacent blocks don't bleed into the match.
    rag = locate_passage(
        TEXT,
        "retrieval augmented generation retriever grounding documents",
        window=140,
        stride=60,
    )
    dl = locate_passage(
        TEXT,
        "deep learning neural networks representations",
        window=140,
        stride=60,
    )
    assert rag is not None and (
        "retriever" in rag["snippet"] or "generation" in rag["snippet"]
    )
    assert dl is not None and "neural networks" in dl["snippet"]
    # The two queries land on clearly different regions of the document.
    assert abs(rag["start"] - dl["start"]) > 80


def test_returns_none_when_no_decent_match():
    assert locate_passage(TEXT, "quarterly revenue forecast spreadsheet pivot") is None


def test_returns_none_on_empty_inputs():
    assert locate_passage("", "anything") is None
    assert locate_passage(TEXT, "") is None
    # A query of only stopwords carries no locating signal.
    assert locate_passage(TEXT, "the of and to is") is None


def test_offsets_are_within_bounds():
    m = locate_passage(TEXT, "deep learning neural networks data")
    assert m is not None
    assert 0 <= m["start"] < m["end"] <= len(TEXT)
