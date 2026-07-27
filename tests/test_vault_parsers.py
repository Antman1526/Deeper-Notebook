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


def test_logseq_supports_common_workflow_markers() -> None:
    raw = (
        b"- NOW Active\n"
        b"- LATER Planned\n"
        b"- WAITING Delegated\n"
        b"- CANCELLED Duplicate spelling\n"
    )

    parsed = parse_document("markers.md", raw, format_mode="logseq")

    assert [task.status for task in parsed.tasks] == [
        "doing",
        "todo",
        "todo",
        "canceled",
    ]
    assert [block.task_state for block in parsed.blocks] == [
        "doing",
        "todo",
        "todo",
        "canceled",
    ]


def test_logseq_multiline_code_span_does_not_project_inner_syntax() -> None:
    raw = (
        b"- TODO Keep real task ``literal starts\n"
        b"  [[Hidden Link]] #hidden-tag``\n"
        b"- NOW [[Visible Link]] #visible-tag\n"
    )

    parsed = parse_document("logseq-code.md", raw, format_mode="logseq")

    assert [task.status for task in parsed.tasks] == ["todo", "doing"]
    assert [
        link.target_text for link in parsed.links if link.link_kind == "wikilink"
    ] == ["Visible Link"]
    assert parsed.tags == ["visible-tag"]


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


def test_yaml_scalar_anchor_without_alias_is_accepted() -> None:
    parsed = parse_document(
        "anchor.md",
        b"---\nvalue: &stable anchored\n---\nbody\n",
        format_mode="obsidian",
    )

    assert parsed.properties["value"] == "anchored"


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
        (
            b"---\nfirst: &value secret\nsecond: *value\n---\nbody\n",
            "frontmatter_alias",
        ),
        (
            b"---\nfirst: &value 42\nsecond: *value\n---\nbody\n",
            "frontmatter_alias",
        ),
        (
            b"---\nfirst: &value 2026-07-27\nsecond: *value\n---\nbody\n",
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


def test_literal_regions_and_escaped_syntax_do_not_create_semantics() -> None:
    raw = (
        b"# Real heading\n\n"
        b"`[[Inline Code]] #inline-code`\n\n"
        b"``Code with ` and [[Multi\n"
        b"Line]] #multiline-code``\n\n"
        b"\\[[Escaped Wiki]] \\#escaped-tag\n"
        b"\\# Escaped heading\n"
        b"\\- [ ] Escaped task\n\n"
        b"```markdown\n"
        b"[[Fenced Code]] #fenced-code\n"
        b"- [ ] Fenced task\n"
        b"# Fenced heading\n"
        b"```\n\n"
        b"    [[Indented Code]] #indented-code\n"
        b"    - [ ] Indented task\n\n"
        b"<pre>[[Raw HTML]] #raw-html</pre>\n\n"
        b"<!DOCTYPE [[Declaration]]>\n"
        b"<?processor [[Instruction]]?>\n"
        b"<![CDATA[[[CData]]]]>\n\n"
        b"[[Real Link]] #real-tag\n"
    )

    parsed = parse_document("literals.md", raw, format_mode="obsidian")

    assert [
        link.target_text for link in parsed.links if link.link_kind == "wikilink"
    ] == ["Real Link"]
    assert parsed.tags == ["real-tag"]
    assert parsed.tasks == []
    assert [
        block.plain_text for block in parsed.blocks if block.block_kind == "heading"
    ] == ["Real heading"]
    assert "[[Fenced Code]]" in parsed.markdown
    assert any(
        block.block_kind == "code" and "[[Fenced Code]]" in block.markdown
        for block in parsed.blocks
    )


def test_escaped_image_and_link_destinations_are_not_nested_semantics() -> None:
    raw = (
        b"\\![[Escaped Image]] \\[[Escaped Link]]\n"
        b'[label](target-[[not-a-wikilink]].md "#not-a-tag")\n'
        b"![alt](asset-[[not-a-wikilink]].png)\n"
    )

    parsed = parse_document("escaped.md", raw, format_mode="obsidian")

    assert not any(
        link.target_text in {"Escaped Image", "Escaped Link", "not-a-wikilink"}
        for link in parsed.links
    )
    assert {link.target_text for link in parsed.links} == {
        "target-[[not-a-wikilink]].md",
        "asset-[[not-a-wikilink]].png",
    }
    assert parsed.tags == []


def test_markdown_links_support_bounded_nested_labels_targets_and_titles() -> None:
    raw = (
        b'[outer [nested]](folder/a_(b).md "Title (#not-a-tag)")\n'
        b"[escaped](folder/a_\\).md)\n"
    )

    parsed = parse_document("markdown-links.md", raw, format_mode="markdown")

    assert [link.target_text for link in parsed.links] == [
        "folder/a_(b).md",
        "folder/a_\\).md",
    ]
    assert parsed.links[0].alias == "outer [nested]"
    assert parsed.tags == []


def test_neutral_markdown_uses_semantic_block_boundaries_and_exact_spans() -> None:
    raw = (
        b"# Heading\n\n"
        b"First paragraph line\n"
        b"continues on line two.\n\n"
        b"> Quoted line one\n"
        b"> quoted line two\n\n"
        b"- parent item\n"
        b"  continuation\n"
        b"  - nested item\n\n"
        b"```text\n"
        b"literal\n"
        b"```\n"
    )

    parsed = parse_document("blocks.md", raw, format_mode="markdown")

    paragraph = next(
        block for block in parsed.blocks if block.markdown.startswith("First paragraph")
    )
    assert (
        paragraph.markdown == b"First paragraph line\ncontinues on line two.\n".decode()
    )
    assert raw[paragraph.source_start : paragraph.source_end] == (
        paragraph.markdown.encode()
    )
    quote = next(block for block in parsed.blocks if block.block_kind == "blockquote")
    nested = [
        block
        for block in parsed.blocks
        if block.block_kind == "list-item" and "nested item" in block.markdown
    ]
    assert quote.parent_parser_id is not None
    assert nested and nested[-1].parent_parser_id is not None
    code = next(
        block
        for block in parsed.blocks
        if block.block_kind == "code" and "literal" in block.markdown
    )
    assert code.markdown == "```text\nliteral\n```\n"
    for block in parsed.blocks:
        expected = hashlib.sha256(
            (
                f"blocks.md\0{block.parent_parser_id or ''}\0{block.position}"
                f"\0{block.block_kind}\0{block.markdown}"
            ).encode()
        ).hexdigest()[:24]
        assert block.parser_id == expected
        assert raw[block.source_start : block.source_end] == block.markdown.encode()
    for index, block in enumerate(parsed.blocks):
        for other in parsed.blocks[index + 1 :]:
            assert (
                block.source_end <= other.source_start
                or other.source_end <= block.source_start
            )


def test_multiline_semantic_spans_remain_exact_with_bom_crlf_and_multibyte() -> None:
    raw = (
        b"\xef\xbb\xbf# Caf\xc3\xa9\r\n\r\n"
        b"R\xc3\xa9sum\xc3\xa9 line one\r\n"
        b"continues [[M\xc3\xa9thode]].\r\n"
    )

    parsed = parse_document("bom-crlf.md", raw, format_mode="obsidian")

    paragraph = next(
        block
        for block in parsed.blocks
        if block.markdown.startswith("R\u00e9sum\u00e9")
    )
    assert paragraph.markdown == (
        "R\u00e9sum\u00e9 line one\r\ncontinues [[M\u00e9thode]].\r\n"
    )
    assert raw[paragraph.source_start : paragraph.source_end].decode() == (
        paragraph.markdown
    )
    link = next(link for link in parsed.links if link.target_text == "M\u00e9thode")
    assert raw[link.source_start : link.source_end].decode() == "[[M\u00e9thode]]"


def test_dense_unmatched_wikilinks_scale_linearly() -> None:
    timings: list[float] = []
    for size in (100_000, 500_000, 1_000_000):
        raw = (b"[[" * ((size - 1) // 2)) + b"\n"
        started = time.monotonic()
        parsed = parse_document(
            f"dense-{size}.md",
            raw,
            format_mode="obsidian",
            max_markdown_bytes=2_000_000,
        )
        timings.append(time.monotonic() - started)
        assert parsed.links == []

    assert timings[-1] < 4.0
    assert timings[-1] <= max(0.05, timings[0]) * 20


def test_near_default_limit_dense_unmatched_wikilinks_remain_bounded() -> None:
    raw = (b"[[" * ((9 * 1024 * 1024) // 2)) + b"\n"
    started = time.monotonic()

    parsed = parse_document("dense-9m.md", raw, format_mode="obsidian")

    assert parsed.links == []
    assert time.monotonic() - started < 8.0


def test_many_semantic_blocks_scale_without_rebuilding_line_maps() -> None:
    timings: list[float] = []
    for count in (1_000, 5_000):
        raw = (
            "\n\n".join(f"paragraph {index}" for index in range(count)) + "\n"
        ).encode()
        started = time.monotonic()
        parsed = parse_document("many-blocks.md", raw, format_mode="markdown")
        timings.append(time.monotonic() - started)
        assert len(parsed.blocks) == count

    assert timings[-1] <= max(0.1, timings[0]) * 10


def test_parsing_never_changes_process_working_directory(tmp_path: Path) -> None:
    before = Path.cwd()
    os.chdir(tmp_path)
    try:
        parse_document("safe.md", b"# Safe\n", format_mode="markdown")
        assert Path.cwd() == tmp_path
    finally:
        os.chdir(before)
