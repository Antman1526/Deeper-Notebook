"""Production-wide AST inventory for persisted surreal-commands identifiers."""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Mapping
from pathlib import Path


def semantic_sort_key(entry: Mapping[str, object]) -> tuple[str, ...]:
    return (
        str(entry.get("kind") or ""),
        str(entry.get("path") or ""),
        str(entry.get("symbol") or ""),
        str(entry.get("callee") or ""),
        str(entry.get("invocation") or ""),
        str(entry.get("app") or ""),
        str(entry.get("command") or ""),
        str(entry.get("command_id") or ""),
    )


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


def production_python_paths(root: Path) -> list[Path]:
    """Return every tracked production Python file, excluding tests and shims."""
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return [
        root / relative
        for relative in tracked
        if not (
            relative.startswith("tests/")
            or "/tests/" in relative
            or relative.startswith("open_" "notebook/")
            or relative.startswith("desktop/bin/")
        )
    ]


class _QueueInventoryVisitor(ast.NodeVisitor):
    def __init__(self, root: Path, path: Path) -> None:
        self.root = root
        self.path = path
        self.function_stack: list[str] = []
        self.entries: list[dict[str, str]] = []

    @property
    def symbol(self) -> str:
        return self.function_stack[-1] if self.function_stack else "<module>"

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(self.root).as_posix()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if _call_name(decorator) != "command":
                continue
            app = _expression(
                _keyword_or_positional(
                    decorator,
                    keywords={"app"},
                    position=1,
                )
            )
            command_name = _expression(
                _keyword_or_positional(
                    decorator,
                    keywords={"name"},
                    position=0,
                )
            )
            if app is None or command_name is None:
                raise ValueError(
                    "persisted command registrations require explicit app "
                    f"and command names: {self.relative_path}:{node.lineno}"
                )
            self.entries.append(
                {
                    "kind": "registration",
                    "path": self.relative_path,
                    "symbol": node.name,
                    "callee": "command",
                    "app": app,
                    "command": command_name,
                }
            )
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        callee = _call_name(node)
        invocation = callee
        queue_call = node
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
            queue_call = ast.Call(
                func=node.args[0],
                args=node.args[1:],
                keywords=node.keywords,
            )
        if callee in {"submit_command", "submit_command_job"}:
            app = _expression(
                _keyword_or_positional(
                    queue_call,
                    keywords={"app", "app_name", "module_name"},
                    position=0,
                )
            )
            command_name = _expression(
                _keyword_or_positional(
                    queue_call,
                    keywords={"command", "command_name"},
                    position=1,
                )
            )
            if app is None or command_name is None:
                raise ValueError(
                    "persisted command submissions require explicit app "
                    f"and command expressions: {self.relative_path}:{node.lineno}"
                )
            self.entries.append(
                {
                    "kind": "submission",
                    "path": self.relative_path,
                    "symbol": self.symbol,
                    "callee": callee,
                    "invocation": invocation,
                    "app": app,
                    "command": command_name,
                }
            )
        elif callee in {"_is_command_registered", "get_command_by_id"}:
            command_id = _expression(
                _keyword_or_positional(
                    node,
                    keywords={"command_id"},
                    position=0,
                )
            )
            if command_id is None:
                raise ValueError(
                    "persisted command lookups require an explicit identifier "
                    f"expression: {self.relative_path}:{node.lineno}"
                )
            self.entries.append(
                {
                    "kind": "lookup",
                    "path": self.relative_path,
                    "symbol": self.symbol,
                    "callee": callee,
                    "command_id": command_id,
                }
            )
        self.generic_visit(node)


def production_queue_inventory(root: Path) -> list[dict[str, str]]:
    """Inventory every production registration, submission, and lookup."""
    inventory: list[dict[str, str]] = []
    for path in production_python_paths(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _QueueInventoryVisitor(root, path)
        visitor.visit(tree)
        inventory.extend(visitor.entries)
    return sorted(inventory, key=semantic_sort_key)
