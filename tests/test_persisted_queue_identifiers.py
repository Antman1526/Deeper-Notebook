"""Exact behavioral contract for persisted surreal-commands identifiers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scripts.persisted_queue_inventory import (
    production_queue_inventory,
    production_queue_occurrence_inventory,
    semantic_sort_key,
)

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "scripts" / "rebrand-allowlist.json"


def _allowlisted_inventory() -> list[dict[str, str]]:
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return sorted(
        payload["persisted_queue_identifiers"],
        key=semantic_sort_key,
    )


def test_persisted_queue_identifier_allowlist_matches_exact_ast_inventory():
    assert production_queue_inventory(ROOT) == _allowlisted_inventory()


def test_production_queue_inventory_has_exact_shape_and_legacy_mappings():
    actual = production_queue_inventory(ROOT)

    assert Counter(entry["kind"] for entry in actual) == {
        "registration": 19,
        "submission": 21,
        "lookup": 2,
    }
    assert {
        entry["app"]
        for entry in actual
        if entry["kind"] in {"registration", "submission"}
        and entry["app"] not in {"module_name", "request.app"}
    } == {"open_notebook"}
    assert {
        (entry["callee"], entry["command_id"])
        for entry in actual
        if entry["kind"] == "lookup"
    } == {
        ("_is_command_registered", "open_notebook.embed_note"),
        ("get_command_by_id", "command_id"),
    }


def test_queue_compatibility_occurrences_come_only_from_ast_inventory():
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    allowlisted = {
        (
            entry["path"],
            entry["pattern"],
            entry["source"],
            entry["line"],
            entry["column"],
            entry["context_sha256"],
        )
        for entry in payload["entries"]
        if entry["category"] == "compatibility_alias"
        and entry["rationale"]["compatibility_contract"]
        == "persisted-queue-identifier-v1"
        and not entry["path"].startswith("tests/")
    }
    actual = {
        (
            entry["path"],
            entry["pattern"],
            entry["source"],
            entry["line"],
            entry["column"],
            entry["context_sha256"],
        )
        for entry in production_queue_occurrence_inventory(ROOT)
    }

    assert len(actual) == 39
    assert actual == allowlisted


def test_live_registry_matches_every_fixed_registration_after_imports():
    from surreal_commands.core.registry import CommandRegistry

    import commands  # noqa: F401
    import desktop.memory.memory_commands  # noqa: F401

    expected = {
        f"{entry['app']}.{entry['command']}"
        for entry in production_queue_inventory(ROOT)
        if entry["kind"] == "registration"
    }

    assert set(CommandRegistry()._commands) == expected


def test_inventory_sort_ignores_json_member_order_but_not_semantics():
    registration = {
        "kind": "registration",
        "path": "commands/example.py",
        "symbol": "example_command",
        "callee": "command",
        "app": "open_notebook",
        "command": "example",
    }
    reordered = dict(reversed(tuple(registration.items())))

    assert semantic_sort_key(registration) == semantic_sort_key(reordered)
    reordered["app"] = "deeper_notebook"
    assert semantic_sort_key(registration) != semantic_sort_key(reordered)
