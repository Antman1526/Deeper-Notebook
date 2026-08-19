"""Production-wide AST inventory for persisted surreal-commands identifiers."""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

_WHITESPACE_RUN = re.compile(r"\s+")


def _occurrence_digest(pattern: str, context: str, column: int) -> str:
    """Mirror of rebrand_audit.occurrence_digest — keep the two in lockstep."""
    ordinal = 0
    cursor = context.find(pattern)
    while cursor != -1 and cursor < column - 1:
        ordinal += 1
        cursor = context.find(pattern, cursor + len(pattern))
    normalized = _WHITESPACE_RUN.sub(" ", context).strip()
    return hashlib.sha256(f"{ordinal}\x00{normalized}".encode("utf-8")).hexdigest()


LEGACY_QUEUE_APP = "open_notebook"


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
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    tracked = result.stdout.splitlines()
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
        self.identifier_nodes: list[ast.expr] = []

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
            app_node = _keyword_or_positional(
                decorator,
                keywords={"app"},
                position=1,
            )
            app = _expression(app_node)
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
            assert app_node is not None
            self.identifier_nodes.append(app_node)
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
            app_node = _keyword_or_positional(
                queue_call,
                keywords={"app", "app_name", "module_name"},
                position=0,
            )
            app = _expression(app_node)
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
            assert app_node is not None
            self.identifier_nodes.append(app_node)
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
            command_id_node = _keyword_or_positional(
                node,
                keywords={"command_id"},
                position=0,
            )
            command_id = _expression(command_id_node)
            if command_id is None:
                raise ValueError(
                    "persisted command lookups require an explicit identifier "
                    f"expression: {self.relative_path}:{node.lineno}"
                )
            assert command_id_node is not None
            self.identifier_nodes.append(command_id_node)
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


def _node_legacy_occurrences(
    *,
    relative_path: str,
    source_lines: list[str],
    node: ast.expr,
) -> list[dict[str, object]]:
    """Return scanner-identical legacy tokens contained by one queue argument."""
    if node.end_lineno is None or node.end_col_offset is None:
        raise ValueError(
            f"queue identifier lacks a closed source range: {relative_path}"
        )
    occurrences: list[dict[str, object]] = []
    for line_number in range(node.lineno, node.end_lineno + 1):
        line = source_lines[line_number - 1]
        start = node.col_offset if line_number == node.lineno else 0
        end = (
            node.end_col_offset
            if line_number == node.end_lineno
            else len(line)
        )
        cursor = line.find(LEGACY_QUEUE_APP, start, end)
        while cursor >= 0:
            occurrences.append(
                {
                    "path": relative_path,
                    "pattern": LEGACY_QUEUE_APP,
                    "source": "content",
                    "line": line_number,
                    "column": cursor + 1,
                    # Must stay byte-identical to
                    # rebrand_audit.occurrence_digest: normalized content with
                    # the intra-line ordinal folded in. Duplicated rather than
                    # imported because rebrand_audit imports THIS module; when
                    # only one side normalized, 30 compatibility entries
                    # resolved to a null contract and load_allowlist aborted.
                    "context_sha256": _occurrence_digest(
                        LEGACY_QUEUE_APP, line, cursor + 1
                    ),
                }
            )
            cursor = line.find(
                LEGACY_QUEUE_APP,
                cursor + len(LEGACY_QUEUE_APP),
                end,
            )
    return occurrences


def production_queue_occurrence_inventory(
    root: Path,
) -> list[dict[str, object]]:
    """Emit exact scanner identities owned by queue registration semantics."""
    occurrences: list[dict[str, object]] = []
    for path in production_python_paths(root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        visitor = _QueueInventoryVisitor(root, path)
        visitor.visit(tree)
        for node in visitor.identifier_nodes:
            occurrences.extend(
                _node_legacy_occurrences(
                    relative_path=visitor.relative_path,
                    source_lines=source.splitlines(),
                    node=node,
                )
            )
    return sorted(
        occurrences,
        key=lambda entry: (
            str(entry["path"]),
            int(entry["line"]),
            int(entry["column"]),
            str(entry["pattern"]),
        ),
    )
