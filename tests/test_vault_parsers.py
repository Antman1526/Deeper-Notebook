from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import subprocess
import sys
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
from deeper_notebook.vault.parsers.common import SourceRegion
from deeper_notebook.vault.parsers.markdown import ByteOffsetMapper, ScanContext

FIXTURES = Path(__file__).parent / "fixtures" / "vault"

PARSER_RUNTIME_LIMIT_SECONDS = (
    16.0 if sys.platform == "darwin" and platform.machine() == "x86_64" else 8.0
)
PARSER_SUBPROCESS_TIMEOUT_SECONDS = PARSER_RUNTIME_LIMIT_SECONDS + 12.0

RSS_SAMPLER_CODE = """
import ctypes
import os
import sys

def current_rss():
    if sys.platform.startswith("linux"):
        with open("/proc/self/statm", encoding="ascii") as statm:
            resident_pages = int(statm.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    if sys.platform == "win32":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_bool
        process = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        ):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return counters.WorkingSetSize
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
"""


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


def test_logseq_fence_requires_a_valid_commonmark_closer() -> None:
    raw = (
        b"- parent\n"
        b"  ```python\n"
        b"  [[Hidden One]] #hidden-one\n"
        b"  ```not-a-close\n"
        b"  [[Hidden Two]] #hidden-two\n"
        b"  ````   \n"
        b"- NOW [[Visible]] #visible\n"
    )

    parsed = parse_document("fences.md", raw, format_mode="logseq")

    assert [task.status for task in parsed.tasks] == ["doing"]
    assert [
        link.target_text for link in parsed.links if link.link_kind == "wikilink"
    ] == ["Visible"]
    assert parsed.tags == ["visible"]


def test_logseq_fence_openers_and_eof_are_fail_closed() -> None:
    raw = (
        b"- parent\n"
        b"  ```bad`info\n"
        b"  [[Visible Before Fence]]\n"
        b"  ~~~ tilde info\n"
        b"  [[Hidden At EOF]] #hidden\n"
    )

    parsed = parse_document("fence-eof.md", raw, format_mode="logseq")

    assert [
        link.target_text for link in parsed.links if link.link_kind == "wikilink"
    ] == ["Visible Before Fence"]
    assert parsed.tags == []


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


def test_inline_html_declarations_comments_and_tags_are_literal() -> None:
    raw = (
        b"Text <!DOCTYPE [[DocType]] #doctype> "
        b"<?processor [[Instruction]] #pi?> "
        b"<![CDATA[[[CData]] #cdata]]> "
        b"<!-- [[Comment]] #comment --> "
        b'<span title="[[Attribute]] #attribute">visible</span> '
        b"[[Real]] #real\n"
    )

    parsed = parse_document("inline-html.md", raw, format_mode="obsidian")

    assert [
        link.target_text for link in parsed.links if link.link_kind == "wikilink"
    ] == ["Real"]
    assert parsed.tags == ["real"]


def test_unmatched_raw_html_scales_linearly() -> None:
    timings: list[float] = []
    for size in (50_000, 100_000, 150_000):
        raw = (b"<pre>" * (size // 5)) + b"\n"
        started = time.monotonic()
        parsed = parse_document(
            f"html-{size}.md",
            raw,
            format_mode="markdown",
        )
        timings.append(time.monotonic() - started)
        assert parsed.links == []

    assert timings[-1] < 2.0
    assert timings[-1] <= max(0.03, timings[0]) * 6


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


def test_markdown_links_with_code_labels_project_only_the_outer_link() -> None:
    raw = (
        b"[`[[hidden]] #hidden`](target.md)\n"
        b'[pre ``code [[hidden-two]]`` post](other.md "title")\n'
    )

    parsed = parse_document("code-labels.md", raw, format_mode="markdown")

    assert [link.target_text for link in parsed.links] == [
        "target.md",
        "other.md",
    ]
    assert parsed.tags == []


@pytest.mark.parametrize(
    "raw",
    [
        b"[[Outer [[Inner]] tail]]\n",
        b"[[Page [alias](nested.md)]]\n",
        b"[[Outer [[Inner]] tail [label](nested.md)]]\n",
    ],
)
def test_nested_invalid_link_syntax_is_preserved_without_partial_edges(
    raw: bytes,
) -> None:
    parsed = parse_document("invalid-overlap.md", raw, format_mode="obsidian")

    assert parsed.markdown.encode() == raw
    assert parsed.links == []


@pytest.mark.parametrize("target_length", [4095, 4096])
def test_wikilink_target_boundary_accepts_values_at_or_below_limit(
    target_length: int,
) -> None:
    target = "x" * target_length
    raw = f"[[{target}]] and [[Good]]\n".encode()

    parsed = parse_document("wiki-boundary.md", raw, format_mode="obsidian")

    assert [link.target_text for link in parsed.links] == [target, "Good"]


def test_oversized_wikilink_protects_its_full_invalid_outer_construct() -> None:
    raw = (
        b"[["
        + (b"x" * 4097)
        + b" [[Inner]] [label](nested.md) #leaked]] and [[Good]] #good\n"
    )

    parsed = parse_document("oversized-wiki.md", raw, format_mode="obsidian")

    assert [
        link.target_text for link in parsed.links if link.link_kind == "wikilink"
    ] == ["Good"]
    assert not any(link.target_text == "nested.md" for link in parsed.links)
    assert parsed.tags == ["good"]


@pytest.mark.parametrize("separator", [b"\n", b"\r", b"\r\n"])
def test_unclosed_oversized_wikilink_is_protected_through_line_end(
    separator: bytes,
) -> None:
    raw = (
        b"[["
        + (b"x" * 4097)
        + b" [label](nested.md) #leaked"
        + separator
        + b"[[Good]] #good"
    )

    parsed = parse_document("oversized-line.md", raw, format_mode="obsidian")

    assert [
        link.target_text for link in parsed.links if link.link_kind == "wikilink"
    ] == ["Good"]
    assert not any(link.target_text == "nested.md" for link in parsed.links)
    assert parsed.tags == ["good"]


def test_unclosed_oversized_wikilink_is_protected_through_eof() -> None:
    raw = b"[[" + (b"x" * 4097) + b" [label](nested.md) #leaked"

    parsed = parse_document("oversized-eof.md", raw, format_mode="obsidian")

    assert parsed.links == []
    assert parsed.tags == []


def test_oversized_multibyte_wikilink_resumes_with_exact_byte_spans() -> None:
    raw = (
        "[[" + ("\u00e9" * 4097) + " [label](nested.md) #leaked]] [[Good]] #good\n"
    ).encode()

    parsed = parse_document("oversized-multibyte.md", raw, format_mode="obsidian")

    assert [link.target_text for link in parsed.links] == ["Good", "good"]
    for link in parsed.links:
        projected = raw[link.source_start : link.source_end].decode()
        assert link.target_text in projected


@pytest.mark.parametrize("label_length", [1023, 1024])
def test_markdown_label_boundary_accepts_values_at_or_below_limit(
    label_length: int,
) -> None:
    label = "x" * label_length
    raw = f"[{label}](outer.md) and [[Good]]\n".encode()

    parsed = parse_document("label-boundary.md", raw, format_mode="markdown")

    assert [link.target_text for link in parsed.links] == ["outer.md", "Good"]
    assert parsed.links[0].alias == label


@pytest.mark.parametrize("target_length", [4095, 4096])
def test_markdown_target_boundary_accepts_values_at_or_below_limit(
    target_length: int,
) -> None:
    target = "x" * target_length
    raw = f"[outer]({target}) and [[Good]]\n".encode()

    parsed = parse_document("target-boundary.md", raw, format_mode="markdown")

    assert [link.target_text for link in parsed.links] == [target, "Good"]


@pytest.mark.parametrize("character", ["x", "\u00e9"])
def test_oversized_markdown_label_protects_full_outer_construct(
    character: str,
) -> None:
    raw = (
        "["
        + (character * 1025)
        + " [[Nested]] [inner](nested.md) #leaked]"
        + '(outer-[[target]].md "#title") and [[Good]] #good\n'
    ).encode()

    parsed = parse_document("oversized-label.md", raw, format_mode="markdown")

    assert [link.target_text for link in parsed.links] == ["Good", "good"]


@pytest.mark.parametrize("character", ["x", "\u00e9"])
def test_oversized_markdown_target_protects_full_outer_construct(
    character: str,
) -> None:
    raw = (
        "[outer]("
        + (character * 4097)
        + " [[Nested]] [inner](nested.md) #leaked)"
        + " and [[Good]] #good\n"
    ).encode()

    parsed = parse_document("oversized-target.md", raw, format_mode="markdown")

    assert [link.target_text for link in parsed.links] == ["Good", "good"]


@pytest.mark.parametrize("kind", ["label", "target"])
@pytest.mark.parametrize("ending", ["newline", "eof"])
def test_unclosed_oversized_markdown_construct_is_protected_to_boundary(
    kind: str,
    ending: str,
) -> None:
    if kind == "label":
        invalid = "[" + ("x" * 1025) + " [inner](nested.md) #leaked"
    else:
        invalid = "[outer](" + ("x" * 4097) + " [[Nested]] #leaked"
    suffix = "\n[[Good]] #good" if ending == "newline" else ""
    raw = (invalid + suffix).encode()

    parsed = parse_document(
        f"oversized-{kind}-{ending}.md",
        raw,
        format_mode="markdown",
    )

    expected = ["Good", "good"] if ending == "newline" else []
    assert [link.target_text for link in parsed.links] == expected


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


def test_logseq_task_tag_association_scales_linearly() -> None:
    timings: list[float] = []
    for count in (1_000, 5_000, 10_000):
        raw = "".join(
            f"- TODO Task {index} #tag-{index}\n" for index in range(count)
        ).encode()
        started = time.monotonic()
        parsed = parse_document(
            f"tasks-{count}.md",
            raw,
            format_mode="logseq",
        )
        timings.append(time.monotonic() - started)
        assert len(parsed.tasks) == count
        assert parsed.tasks[-1].tags == [f"tag-{count - 1}"]

    assert timings[-1] < 4.0
    assert timings[-1] <= max(0.08, timings[0]) * 15


def test_logseq_task_metadata_ignores_code_and_html_literals() -> None:
    raw = (
        b"- TODO Task `SCHEDULED: <2026-08-01> [#A] +1w #hidden`\n"
        b"  <code>DEADLINE: <2026-08-02> [#B] +2w #hidden-html</code>\n"
        b"  SCHEDULED: <2026-08-03 Mon +3w>\n"
        b"  DEADLINE: <2026-08-04 Tue>\n"
        b"  priority:: C\n"
        b"  tags:: visible-property\n"
        b"  #visible-tag\n"
    )

    parsed = parse_document("task-metadata.md", raw, format_mode="logseq")
    task = parsed.tasks[0]

    assert task.scheduled == date(2026, 8, 3)
    assert task.due == date(2026, 8, 4)
    assert task.priority == "C"
    assert task.recurrence == "+3w"
    assert task.tags == ["visible-property", "visible-tag"]


def test_near_default_limit_dense_unmatched_wikilinks_remain_bounded() -> None:
    raw = (b"[[" * ((9 * 1024 * 1024) // 2)) + b"\n"
    started = time.monotonic()

    parsed = parse_document("dense-9m.md", raw, format_mode="obsidian")

    assert parsed.links == []
    assert time.monotonic() - started < PARSER_RUNTIME_LIMIT_SECONDS


def test_projection_budget_rejects_excessive_structure_before_tokenization() -> None:
    raw = b"paragraph\n\n" * 60_000

    with pytest.raises(VaultParseError) as raised:
        parse_document(
            "too-structured.md",
            raw,
            format_mode="markdown",
        )

    assert raised.value.code == "projection_too_large"
    assert "paragraph" not in str(raised.value)


def test_projection_budget_rejects_excessive_inline_outputs_incrementally() -> None:
    raw = b"#tag " * 100_001

    with pytest.raises(VaultParseError) as raised:
        parse_document("too-many-tags.md", raw, format_mode="markdown")

    assert raised.value.code == "projection_too_large"
    assert "tag" not in str(raised.value)


def test_projection_line_budget_counts_cr_only_and_unterminated_lines() -> None:
    raw = (b"\r" * 100_000) + b"unterminated"

    with pytest.raises(VaultParseError) as raised:
        parse_document("cr-only.md", raw, format_mode="markdown")

    assert raised.value.code == "projection_too_large"


def test_projection_budget_subprocess_rss_and_time_are_bounded() -> None:
    code = (
        RSS_SAMPLER_CODE
        + """
import json
import threading
import time
from deeper_notebook.vault.parsers import VaultParseError, parse_document

baseline_rss = current_rss()
unit = b"# Heading\\n[[Target]] #tag\\n\\n"
raw = (unit * ((9 * 1024 * 1024 // len(unit)) + 1))[: 9 * 1024 * 1024]
peak_rss = [baseline_rss]
stop_sampling = threading.Event()
def sample_rss():
    while not stop_sampling.wait(0.001):
        peak_rss[0] = max(peak_rss[0], current_rss())
monitor = threading.Thread(target=sample_rss, daemon=True)
monitor.start()
started = time.monotonic()
try:
    parse_document("hostile.md", raw, format_mode="obsidian")
except VaultParseError as exc:
    elapsed = time.monotonic() - started
    stop_sampling.set()
    monitor.join()
    peak_rss[0] = max(peak_rss[0], current_rss())
    result = {
        "code": exc.code,
        "elapsed": elapsed,
        "rss_growth": max(0, peak_rss[0] - baseline_rss),
    }
    print(json.dumps(result))
else:
    stop_sampling.set()
    monitor.join()
    raise SystemExit("projection unexpectedly succeeded")
"""
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result["code"] == "projection_too_large"
    assert result["elapsed"] < 5.0
    assert result["rss_growth"] < 350 * 1024 * 1024


def test_one_mebibyte_useful_wikilink_document_is_accepted() -> None:
    count = 95_000
    raw = b"[[Target]] " * count

    parsed = parse_document("useful-wiki.md", raw, format_mode="obsidian")

    assert len(raw) == 1_045_000
    assert len(parsed.links) == count


def test_exact_wikilink_output_boundary_is_accepted() -> None:
    raw = b"[[x]] " * 100_000

    parsed = parse_document("exact-link-limit.md", raw, format_mode="obsidian")

    assert len(parsed.links) == 100_000


@pytest.mark.parametrize(
    "kind",
    [
        "wikilinks",
        "wikilinks-9m",
        "markdown",
        "code",
        "html",
        "invalid",
        "mixed",
    ],
)
def test_single_line_transient_bombs_fail_with_bounded_rss(kind: str) -> None:
    code = (
        RSS_SAMPLER_CODE
        + """
import json
import sys
import threading
import time
from deeper_notebook.vault.parsers import VaultParseError, parse_document

kind = sys.argv[1]
baseline_rss = current_rss()
raw = {
    "wikilinks": b"[[Target]] " * 300_000,
    "wikilinks-9m": (
        (b"[[Target]] " * ((9 * 1024 * 1024 // 11) + 1))[: 9 * 1024 * 1024]
    ),
    "markdown": b"[label](target.md) " * 180_000,
    "code": b"`x` " * 200_000,
    "html": b"<i></i> " * 100_000,
    "invalid": b"[[Outer [label](nested.md)]] " * 160_000,
    "mixed": b"[[Target]] [label](target.md) " * 75_001,
}[kind]
peak_rss = [baseline_rss]
stop_sampling = threading.Event()
def sample_rss():
    while not stop_sampling.wait(0.001):
        peak_rss[0] = max(peak_rss[0], current_rss())
monitor = threading.Thread(target=sample_rss, daemon=True)
monitor.start()
started = time.monotonic()
try:
    parse_document(f"{kind}.md", raw, format_mode="obsidian")
except VaultParseError as exc:
    elapsed = time.monotonic() - started
    stop_sampling.set()
    monitor.join()
    peak_rss[0] = max(peak_rss[0], current_rss())
    result = {
        "code": exc.code,
        "elapsed": elapsed,
        "rss_growth": max(0, peak_rss[0] - baseline_rss),
    }
    print(json.dumps(result))
else:
    stop_sampling.set()
    monitor.join()
    raise SystemExit("transient bomb unexpectedly succeeded")
"""
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, kind],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=PARSER_SUBPROCESS_TIMEOUT_SECONDS,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result["code"] == "projection_too_large"
    assert result["elapsed"] < PARSER_RUNTIME_LIMIT_SECONDS
    assert result["rss_growth"] < 150 * 1024 * 1024


def test_multibyte_single_line_offset_mapping_has_bounded_rss() -> None:
    code = (
        RSS_SAMPLER_CODE
        + """
import json
import threading
import time
from deeper_notebook.vault.parsers import parse_document

baseline_rss = current_rss()
raw = ("é" * 4_000_000).encode()
peak_rss = [baseline_rss]
stop_sampling = threading.Event()
def sample_rss():
    while not stop_sampling.wait(0.001):
        peak_rss[0] = max(peak_rss[0], current_rss())
monitor = threading.Thread(target=sample_rss, daemon=True)
monitor.start()
started = time.monotonic()
parsed = parse_document("multibyte.md", raw, format_mode="markdown")
elapsed = time.monotonic() - started
stop_sampling.set()
monitor.join()
peak_rss[0] = max(peak_rss[0], current_rss())
print(json.dumps({
    "blocks": len(parsed.blocks),
    "elapsed": elapsed,
    "rss_growth": max(0, peak_rss[0] - baseline_rss),
}))
"""
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=PARSER_SUBPROCESS_TIMEOUT_SECONDS,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result["blocks"] == 1
    assert result["elapsed"] < PARSER_RUNTIME_LIMIT_SECONDS
    assert result["rss_growth"] < 150 * 1024 * 1024


def test_escape_map_fast_path_preserves_unescaped_semantics() -> None:
    scan = ScanContext.from_text("plain text without escapes")

    assert scan.escaped == bytearray(len(scan.text))
    assert not any(scan.is_escaped(index) for index in range(len(scan.text)))


def test_multibyte_offset_map_is_lazy_until_a_span_is_projected() -> None:
    source = SourceRegion(
        source_start=7,
        source_end=13,
        markdown="ééé",
        content="ééé",
    )

    mapper = ByteOffsetMapper.from_source(source)

    assert mapper.offsets is None
    assert mapper.span(1, 3) == (9, 13)
    assert mapper.offsets is not None


def test_parser_scanners_do_not_stage_unbounded_transient_lists() -> None:
    parser_source = (
        Path(__file__).parents[1]
        / "deeper_notebook"
        / "vault"
        / "parsers"
        / "markdown.py"
    ).read_text()
    tree = ast.parse(parser_source)
    scanner_names = {
        "_iter_code_spans",
        "_iter_html_spans",
        "_iter_wikilinks",
        "_iter_markdown_links",
    }
    scanners = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in scanner_names
    ]

    assert {node.name for node in scanners} == scanner_names
    for scanner in scanners:
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            for node in ast.walk(scanner)
        )

    accumulator = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ParseAccumulator"
    )
    permitted_output_appenders = {
        "blocks": "add_block",
        "links": "add_link",
        "tasks": "add_task",
        "embeds": "add_embed",
    }
    for method in (
        node for node in accumulator.body if isinstance(node, ast.FunctionDef)
    ):
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "self"
                and node.func.value.attr in permitted_output_appenders
            ):
                assert method.name == permitted_output_appenders[node.func.value.attr]


def test_large_useful_logseq_document_stays_within_projection_budget() -> None:
    count = 40_000
    raw = "".join(f"- TODO Useful task {index}\n" for index in range(count)).encode()

    parsed = parse_document("useful-large.md", raw, format_mode="logseq")

    assert len(parsed.blocks) == count
    assert len(parsed.tasks) == count


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
