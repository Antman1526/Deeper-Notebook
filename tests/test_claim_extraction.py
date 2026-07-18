"""Deterministic material-claim extraction tests."""

from open_notebook.evaluation.claims import extract_material_claims


def test_extracts_declarative_claims_and_attaches_citation_markers() -> None:
    response = """# Findings

    The launch completed on 12 March 2026 [S1].
    Run `rm -rf cache` before retrying.
    Is the launch ready?
    I think the interface is beautiful.
    The release includes an offline mode [S2].
    """

    claims = extract_material_claims(response)

    assert [claim.text for claim in claims] == [
        "The launch completed on 12 March 2026.",
        "The release includes an offline mode.",
    ]
    assert [claim.citation_markers for claim in claims] == [("[S1]",), ("[S2]",)]


def test_preserves_unicode_codepoint_offsets() -> None:
    response = "Cafe \u2615 ships with accessibility fixes [source:release]."

    claim = extract_material_claims(response)[0]

    assert response[claim.start : claim.end] == claim.text_with_markers
    assert claim.text == "Cafe \u2615 ships with accessibility fixes."


def test_ignores_headings_commands_questions_and_subjective_language() -> None:
    response = """## Summary
    - Deploy the package now.
    Why did the import fail?
    This may be the best workflow.
    It feels surprisingly polished.
    The import retries three times [S1].
    """

    claims = extract_material_claims(response)

    assert [claim.text for claim in claims] == ["The import retries three times."]
