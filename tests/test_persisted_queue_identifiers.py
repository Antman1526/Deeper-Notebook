"""Exact contract for persisted surreal-commands identifiers."""

from __future__ import annotations

import ast
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, TypeVar

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "scripts" / "rebrand-allowlist.json"
InventoryEntry = TypeVar("InventoryEntry", bound=Mapping[str, object])


def _semantic_sort_key(entry: Mapping[str, object]) -> tuple[str, ...]:
    return (
        str(entry.get("kind") or ""),
        str(entry.get("path") or ""),
        str(entry.get("symbol") or ""),
        str(entry.get("callee") or ""),
        str(entry.get("invocation") or ""),
        str(entry.get("app") or ""),
        str(entry.get("command") or ""),
    )


def _sorted_inventory(
    entries: Iterable[InventoryEntry],
) -> list[InventoryEntry]:
    return sorted(entries, key=_semantic_sort_key)


def _expression(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node)


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ast.unparse(node.func)


def _keyword_or_positional(
    node: ast.Call,
    *,
    keywords: set[str],
    position: int,
) -> ast.expr | None:
    for keyword in node.keywords:
        if keyword.arg in keywords:
            return keyword.value
    if len(node.args) > position:
        return node.args[position]
    return None


def _registration_inventory() -> list[dict[str, str | None]]:
    registrations: list[dict[str, str | None]] = []
    for path in sorted((ROOT / "commands").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if _call_name(decorator) != "command":
                    continue
                app = _keyword_or_positional(
                    decorator,
                    keywords={"app"},
                    position=1,
                )
                if _expression(app) != "open_notebook":
                    continue
                command_name = _keyword_or_positional(
                    decorator,
                    keywords={"name"},
                    position=0,
                )
                registrations.append(
                    {
                        "kind": "registration",
                        "path": path.relative_to(ROOT).as_posix(),
                        "symbol": node.name,
                        "callee": "command",
                        "app": _expression(app),
                        "command": _expression(command_name),
                    }
                )
    return _sorted_inventory(registrations)


class _SubmissionVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.function_stack: list[str] = []
        self.entries: list[dict[str, str | None]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        callee = _call_name(node)
        invocation = callee
        submission = node

        if (
            callee == "to_thread"
            and node.args
            and isinstance(node.args[0], (ast.Name, ast.Attribute))
            and (
                node.args[0].id
                if isinstance(node.args[0], ast.Name)
                else node.args[0].attr
            )
            == "submit_command"
        ):
            callee = "submit_command"
            invocation = "to_thread"
            submission = ast.Call(
                func=node.args[0],
                args=node.args[1:],
                keywords=node.keywords,
            )
        elif callee not in {"submit_command", "submit_command_job"}:
            self.generic_visit(node)
            return

        app = _keyword_or_positional(
            submission,
            keywords={"app", "app_name", "module_name"},
            position=0,
        )
        command_name = _keyword_or_positional(
            submission,
            keywords={"command", "command_name"},
            position=1,
        )
        self.entries.append(
            {
                "kind": "submission",
                "path": self.path.relative_to(ROOT).as_posix(),
                "symbol": self.function_stack[-1] if self.function_stack else "<module>",
                "callee": callee,
                "invocation": invocation,
                "app": _expression(app),
                "command": _expression(command_name),
            }
        )
        self.generic_visit(node)


def _submission_inventory() -> list[dict[str, str | None]]:
    submissions: list[dict[str, str | None]] = []
    for path in sorted((ROOT / "api").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _SubmissionVisitor(path)
        visitor.visit(tree)
        submissions.extend(visitor.entries)
    return _sorted_inventory(submissions)


def _allowlisted_inventory() -> list[dict[str, Any]]:
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return _sorted_inventory(payload["persisted_queue_identifiers"])


def test_persisted_queue_identifier_allowlist_matches_exact_ast_inventory():
    actual = [*_registration_inventory(), *_submission_inventory()]

    assert actual == _allowlisted_inventory()


def test_all_fixed_queue_registrations_and_submissions_keep_legacy_app_id():
    actual = [*_registration_inventory(), *_submission_inventory()]
    fixed_apps = {
        entry["app"]
        for entry in actual
        if entry["app"] not in {"module_name", "request.app"}
    }

    assert fixed_apps == {"open_notebook"}
    assert len(_registration_inventory()) == 16
    assert len(_submission_inventory()) == 13


def test_inventory_comparison_ignores_json_member_order_but_not_semantics():
    registration = {
        "kind": "registration",
        "path": "commands/example.py",
        "symbol": "example_command",
        "callee": "command",
        "app": "open_notebook",
        "command": "example",
    }
    submission = {
        "kind": "submission",
        "path": "api/example.py",
        "symbol": "submit_example",
        "callee": "submit_command",
        "invocation": "to_thread",
        "app": "open_notebook",
        "command": "example",
    }
    reordered = [
        dict(reversed(tuple(registration.items()))),
        dict(reversed(tuple(submission.items()))),
    ]

    assert _sorted_inventory([registration, submission]) == _sorted_inventory(
        reordered
    )
    reordered[1]["app"] = "deeper_notebook"
    assert _sorted_inventory([registration, submission]) != _sorted_inventory(
        reordered
    )
