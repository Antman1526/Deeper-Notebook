"""Exact contract for persisted surreal-commands identifiers."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "scripts" / "rebrand-allowlist.json"


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
    return sorted(registrations, key=lambda entry: tuple(entry.values()))


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
    return sorted(submissions, key=lambda entry: tuple(entry.values()))


def _allowlisted_inventory() -> list[dict[str, Any]]:
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return sorted(
        payload["persisted_queue_identifiers"],
        key=lambda entry: tuple(entry.values()),
    )


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
