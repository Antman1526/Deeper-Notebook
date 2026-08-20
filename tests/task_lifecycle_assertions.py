"""AST assertions for lifespan-managed background tasks."""

from __future__ import annotations

import ast


class _ExecutableAssignmentVisitor(ast.NodeVisitor):
    """Collect assignments without entering nested lexical scopes."""

    def __init__(self) -> None:
        self.assignments: list[ast.Assign] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        self.assignments.append(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def assert_lifespan_tracked_task(
    source: str, *, task_name: str, coroutine_name: str
) -> None:
    """Require a lifespan-local tracked task running the named coroutine."""
    tree = ast.parse(source)
    lifespans = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan"
    ]
    assert len(lifespans) == 1, "api/main.py must define exactly one lifespan handler"

    visitor = _ExecutableAssignmentVisitor()
    for statement in lifespans[0].body:
        visitor.visit(statement)
    assignments = [
        node
        for node in visitor.assignments
        if any(
            isinstance(target, ast.Name) and target.id == task_name
            for target in node.targets
        )
    ]
    assert assignments, f"lifespan must assign the {task_name} task locally"

    for assignment in assignments:
        tracked = assignment.value
        if not (
            isinstance(tracked, ast.Call)
            and isinstance(tracked.func, ast.Name)
            and tracked.func.id == "_track_task"
            and len(tracked.args) == 1
        ):
            continue
        created = tracked.args[0]
        if not (
            isinstance(created, ast.Call)
            and isinstance(created.func, ast.Attribute)
            and isinstance(created.func.value, ast.Name)
            and created.func.value.id == "asyncio"
            and created.func.attr == "create_task"
            and created.args
        ):
            continue
        coroutine = created.args[0]
        if (
            isinstance(coroutine, ast.Call)
            and isinstance(coroutine.func, ast.Name)
            and coroutine.func.id == coroutine_name
        ):
            return

    raise AssertionError(
        f"{task_name} must wrap asyncio.create_task({coroutine_name}(...)) "
        "with _track_task"
    )
