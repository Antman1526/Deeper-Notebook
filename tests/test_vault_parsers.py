from __future__ import annotations

import hashlib
import os
import time
from datetime import date
from pathlib import Path

import pytest

from deeper_notebook.vault.contracts import ParsedDocument
from deeper_notebook.vault.parsers import (
    VaultParseError,
    detect_format,
    parse_document,
)

FIXTURES = Path(__file__).parent / "fixtures" / "vault"


def fixture_bytes(relative_path: str) -> bytes:
    return (FIXTURES / relative_path).read_bytes()


def fixture_hex_bytes(relative_path: str) -> bytes:
    return bytes.fromhex((FIXTURES / relative_path).read_text())


def test_obsidian_parser_preserves_links_blocks_and_frontmatter() -> None:
    raw = fixture_bytes("obsidian/complete.md")

    parsed = parse_document("complete.md", raw, format_mode="obsidian")

    assert isinstance(parsed, ParsedDocument)
    assert parsed.source_format == "obsidian"
    assert parsed.title == "Complete Research Note"
    assert parsed.properties["aliases"] == ["Complete note", "Reference"]
    assert parsed.properties["created"] == "2026-07-26"
    assert {link.target_text for link in parsed.links} >= {"Research", "Methods"}
    assert any(link.target_heading == "Evidence" for link in parsed.links)
    assert any(link.target_block == "claim-1" for link in parsed.links)
    assert any(block.stable_source_id == "claim-1" for block in parsed.blocks)
    assert any(block.block_kind == "callout" for block in parsed.blocks)
    assert any(block.block_kind == "footnote" for block in parsed.blocks)
    assert {embed.target_text for embed in parsed.embeds} >= {
        "attachments/chart.png",
        "attachments/diagram.png",
    }
    assert parsed.content_hash == hashlib.sha256(raw).hexdigest()


def test_logseq_parser_preserves_hierarchy_and_task_semantics() -> None:
    parsed = parse_document(
        "journals/2026_07_26.md",
        fixture_bytes("logseq/journal.md"),
        format_mode="logseq",
    )

    assert parsed.source_format == "logseq"
    assert parsed.title == "Research Journal"
    assert parsed.properties["category"] == "journal"
    assert parsed.blocks[1].parent_parser_id == parsed.blocks[0].parser_id
    assert parsed.blocks[0].stable_source_id == ("123e4567-e89b-12d3-a456-426614174000")
    assert [task.status for task in parsed.tasks] == [
        "todo",
        "doing",
        "done",
        "canceled",
    ]
    assert parsed.tasks[0].scheduled == date(2026, 7, 27)
    assert parsed.tasks[0].due == date(2026, 7, 30)
    assert parsed.tasks[0].priority == "A"
    assert parsed.tasks[0].recurrence == ".+1w"
    assert parsed.tasks[1].tags == ["analysis", "evidence"]
    assert parsed.tasks[2].completed == date(2026, 7, 26)
    assert any(link.link_kind == "block-ref" for link in parsed.links)
    assert any(embed.target_text == "Research Evidence" for embed in parsed.embeds)


def test_neutral_markdown_preserves_links_tags_attachments_and_unknown_syntax() -> None:
    raw = fixture_bytes("mixed/neutral.md")

    parsed = parse_document("notes/neutral.md", raw, format_mode="markdown")

    assert parsed.source_format == "markdown"
    assert parsed.title == "Neutral Markdown"
    assert parsed.tags == ["portable"]
    assert any(link.target_text == "docs/reference.md" for link in parsed.links)
    assert any(embed.target_text == "assets/chart.svg" for embed in parsed.embeds)
    assert any(block.block_kind == "callout" for block in parsed.blocks)
    assert ":unknown-directive[kept]" in parsed.markdown
    unknown = next(
        block for block in parsed.blocks if ":unknown-directive" in block.markdown
    )
    assert ":unknown-directive[kept]" in unknown.markdown


def test_tags_exclude_heading_fragments_inside_links() -> None:
    raw = b"[[Page#Heading]] [site](https://example.test/#fragment) #actual-tag\n"

    parsed = parse_document("tags.md", raw, format_mode="obsidian")

    assert parsed.tags == ["actual-tag"]


def test_logseq_embed_has_an_explicit_embed_link_edge() -> None:
    raw = b"- parent\n  {{embed [[Research#Evidence]]}}\n"

    parsed = parse_document("embed.md", raw, format_mode="logseq")

    assert any(
        link.link_kind == "embed"
        and link.target_text == "Research"
        and link.target_heading == "Evidence"
        for link in parsed.links
    )


def test_logseq_priority_marker_is_not_classified_as_a_tag() -> None:
    parsed = parse_document(
        "priority.md",
        b"- TODO Important [#A] #real-tag\n",
        format_mode="logseq",
    )

    assert parsed.tasks[0].priority == "A"
    assert parsed.tags == ["real-tag"]


def test_logseq_dotted_properties_and_inline_task_markers_are_preserved() -> None:
    raw = (
        b"- TODO Review SCHEDULED: <2026-08-01 Sat +1w> "
        b"DEADLINE: <2026-08-02 Sun>\n"
        b"  custom.property:: retained\n"
    )

    parsed = parse_document("properties.md", raw, format_mode="logseq")

    assert parsed.blocks[0].properties["custom.property"] == "retained"
    assert parsed.tasks[0].scheduled == date(2026, 8, 1)
    assert parsed.tasks[0].due == date(2026, 8, 2)
    assert parsed.tasks[0].recurrence == "+1w"


def test_logseq_block_embed_preserves_target_block() -> None:
    parsed = parse_document(
        "block-embed.md",
        b"- parent\n  {{embed ((123e4567-e89b-12d3-a456-426614174001))}}\n",
        format_mode="logseq",
    )

    assert any(
        embed.target_block == "123e4567-e89b-12d3-a456-426614174001"
        for embed in parsed.embeds
    )


def test_parse_is_read_only_and_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "complete.md"
    path.write_bytes(fixture_bytes("obsidian/complete.md"))
    before = path.read_bytes()

    first = parse_document(path.name, before, format_mode="obsidian")
    second = parse_document(path.name, path.read_bytes(), format_mode="obsidian")

    assert path.read_bytes() == before
    assert first == second


@pytest.mark.parametrize(
    ("relative_path", "format_mode", "expected"),
    [
        ("anything.md", "obsidian", "obsidian"),
        ("anything.md", "logseq", "logseq"),
        ("anything.md", "markdown", "markdown"),
        ("Obsidian Brain/Page.md", "mixed", "obsidian"),
        ("Obsidian Brain/nested/Page.md", "mixed", "obsidian"),
        ("Logseq Brain/pages/Page.md", "mixed", "logseq"),
        ("Logseq Brain/journals/2026_07_27.md", "mixed", "logseq"),
        ("Logseq Brain/assets/Page.md", "mixed", "markdown"),
        ("Other/Page.md", "mixed", "markdown"),
        (r"Obsidian Brain\Page.md", "mixed", "obsidian"),
        (".Obsidian Brain/Page.md", "mixed", "markdown"),
    ],
)
def test_format_detection_is_explicit_and_path_stable(
    relative_path: str, format_mode: str, expected: str
) -> None:
    assert detect_format(relative_path, format_mode) == expected


def test_typed_yaml_frontmatter_is_json_safe() -> None:
    raw = (
        b"---\n"
        b"text: value\nnumber: 12\nratio: 1.5\nenabled: true\n"
        b"empty: null\nday: 2026-07-27\n"
        b"items: [one, 2, false]\nnested: {child: value}\n"
        b"---\n# Title\n"
    )

    parsed = parse_document("typed.md", raw, format_mode="obsidian")

    assert parsed.properties == {
        "text": "value",
        "number": 12,
        "ratio": 1.5,
        "enabled": True,
        "empty": None,
        "day": "2026-07-27",
        "items": ["one", 2, False],
        "nested": {"child": "value"},
    }


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (
            fixture_bytes("edge/nonmapping-frontmatter.md"),
            "frontmatter_not_mapping",
        ),
        (fixture_bytes("edge/malformed-frontmatter.md"), "invalid_frontmatter"),
        (
            fixture_bytes("edge/malicious-frontmatter.md"),
            "invalid_frontmatter",
        ),
        (b"---\nvalue: .nan\n---\nbody\n", "frontmatter_not_json_safe"),
        (b"---\n? [complex, key]\n: value\n---\nbody\n", "invalid_frontmatter"),
        (
            b"---\nanchor: &node [1, 2]\nalias: *node\n---\nbody\n",
            "frontmatter_alias",
        ),
        (
            b"---\nrecursive: &node [*node]\n---\nbody\n",
            "frontmatter_alias",
        ),
    ],
)
def test_yaml_rejects_malformed_malicious_and_non_json_safe_values(
    raw: bytes, code: str
) -> None:
    with pytest.raises(VaultParseError) as raised:
        parse_document("unsafe.md", raw, format_mode="obsidian")

    assert raised.value.code == code
    assert "echo unsafe" not in str(raised.value)


def test_yaml_depth_is_bounded() -> None:
    with pytest.raises(VaultParseError) as raised:
        parse_document(
            "deep.md",
            fixture_bytes("edge/deep-frontmatter.md"),
            format_mode="obsidian",
        )

    assert raised.value.code == "frontmatter_too_deep"


def test_yaml_parser_recursion_is_converted_to_a_typed_depth_error() -> None:
    nested = ("[" * 1_000) + "0" + ("]" * 1_000)
    raw = f"---\nvalue: {nested}\n---\nbody\n".encode()

    with pytest.raises(VaultParseError) as raised:
        parse_document("recursive-depth.md", raw, format_mode="obsidian")

    assert raised.value.code == "frontmatter_too_deep"


def test_frontmatter_size_is_bounded_before_yaml_parse() -> None:
    raw = b"---\nkey: " + (b"x" * (256 * 1024)) + b"\n---\nbody\n"

    with pytest.raises(VaultParseError) as raised:
        parse_document("large-frontmatter.md", raw, format_mode="obsidian")

    assert raised.value.code == "frontmatter_too_large"


def test_markdown_size_default_and_explicit_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DN_VAULT_MAX_MARKDOWN_BYTES", raising=False)
    raw = fixture_bytes("edge/size-limit.md")

    with pytest.raises(VaultParseError) as raised:
        parse_document(
            "limit.md",
            raw,
            format_mode="markdown",
            max_markdown_bytes=len(raw) - 1,
        )

    assert raised.value.code == "file_too_large"


@pytest.mark.parametrize("invalid", ["", "nope", "0", "-1", "1.5"])
def test_invalid_or_nonpositive_size_environment_falls_back_safely(
    monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    monkeypatch.setenv("DN_VAULT_MAX_MARKDOWN_BYTES", invalid)

    parsed = parse_document("small.md", b"# Safe\n", format_mode="markdown")

    assert parsed.title == "Safe"


def test_positive_size_environment_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DN_VAULT_MAX_MARKDOWN_BYTES", "7")

    with pytest.raises(VaultParseError) as raised:
        parse_document("too-big.md", b"12345678", format_mode="markdown")

    assert raised.value.code == "file_too_large"


def test_only_utf8_and_utf8_bom_are_accepted() -> None:
    with pytest.raises(VaultParseError) as raised:
        parse_document("latin1.md", b"caf\xe9", format_mode="markdown")

    assert raised.value.code == "unsupported_encoding"

    raw = b"\xef\xbb\xbf# Caf\xc3\xa9\n"
    parsed = parse_document("bom.md", raw, format_mode="markdown")
    assert parsed.markdown == "# Caf\u00e9\n"
    assert parsed.encoding == "utf-8-sig"


@pytest.mark.parametrize(
    ("raw", "newline"),
    [
        (b"one", "none"),
        (b"one\ntwo\n", "lf"),
        (fixture_hex_bytes("edge/crlf.hex"), "crlf"),
        (fixture_hex_bytes("edge/mixed.hex"), "mixed"),
    ],
)
def test_newline_detection_preserves_source_style(raw: bytes, newline: str) -> None:
    parsed = parse_document("newline.md", raw, format_mode="markdown")
    assert parsed.newline == newline


@pytest.mark.parametrize(
    "raw",
    [
        "# Caf\u00e9\nSee [[R\u00e9sum\u00e9|CV]].\n".encode(),
        "# Caf\u00e9\r\nSee [[R\u00e9sum\u00e9|CV]].\r\n".encode(),
        "# Caf\u00e9\r\nSee [[R\u00e9sum\u00e9|CV]].\nFinal\r".encode(),
        fixture_hex_bytes("edge/bom-multibyte.hex"),
    ],
)
def test_all_source_spans_slice_exact_original_utf8_bytes(raw: bytes) -> None:
    parsed = parse_document("multibyte.md", raw, format_mode="obsidian")

    for block in parsed.blocks:
        assert raw[block.source_start : block.source_end].decode("utf-8") == (
            block.markdown
        )
    for link in parsed.links:
        source = raw[link.source_start : link.source_end].decode("utf-8")
        assert "R\u00e9sum\u00e9" in source


def test_parser_id_uses_the_approved_exact_formula() -> None:
    parsed = parse_document(
        "folder/id.md",
        b"# Heading\n\nParagraph.\n",
        format_mode="markdown",
    )
    block = parsed.blocks[0]
    expected = hashlib.sha256(
        (
            f"folder/id.md\0{block.parent_parser_id or ''}\0{block.position}"
            f"\0{block.block_kind}\0{block.markdown}"
        ).encode()
    ).hexdigest()[:24]

    assert block.parser_id == expected


def test_parser_errors_are_typed_and_do_not_leak_source_or_paths() -> None:
    secret = "SECRET_TOKEN_DO_NOT_EXPOSE"
    raw = f"---\nvalue: !!python/name:{secret}\n---\n".encode()

    with pytest.raises(VaultParseError) as raised:
        parse_document(
            f"{Path.home()}/private/{secret}.md",
            raw,
            format_mode="obsidian",
        )

    rendered = str(raised.value)
    assert secret not in rendered
    assert str(Path.home()) not in rendered
    assert raised.value.code == "invalid_frontmatter"


def test_worst_case_link_and_task_input_is_bounded() -> None:
    raw = ("[[" + ("x" * 200_000) + "\n").encode() + (
        ("- TODO " + ("#" * 5_000) + "\n") * 30
    ).encode()
    started = time.monotonic()

    parsed = parse_document(
        "adversarial.md",
        raw,
        format_mode="logseq",
        max_markdown_bytes=512_000,
    )

    assert time.monotonic() - started < 2.0
    assert parsed.blocks
    assert parsed.links == []


def test_parsing_never_changes_process_working_directory(tmp_path: Path) -> None:
    before = Path.cwd()
    os.chdir(tmp_path)
    try:
        parse_document("safe.md", b"# Safe\n", format_mode="markdown")
        assert Path.cwd() == tmp_path
    finally:
        os.chdir(before)
