"""v0.7.135 — AST meta-test for the HTTPException re-raise pattern
(Area for Review #3).

Background — the recurring bug this prevents:

    @router.get("/things/{id}")
    async def get_thing(id: str):
        try:
            thing = await fetch(id)            # raises HTTPException(404) on miss
            return await process(thing)        # raises ValueError on bad shape
        except Exception as e:
            raise HTTPException(500, detail=str(e))  # ← clobbers the 404 to 500

The intent is "anything unexpected becomes 500", but `except Exception`
also catches the explicit HTTPException(404) that `fetch()` raises —
so the 404 turns into a generic 500 with a misleading error message.

The codebase has FIXED this pattern in many places (search for
"v0.7.108 — re-raise typed HTTPExceptions"). This meta-test
mechanically enforces the convention so future routes can't
regress.

The rule:
  In any function under api/routers/*.py, any try/except chain that
  contains BOTH (a) an `except Exception` clause whose body raises
  HTTPException AND (b) calls inside the `try:` that could plausibly
  raise HTTPException — MUST first have an `except HTTPException:
  raise` (or equivalent) clause to let typed exceptions propagate.

We approximate (b) by treating any function-body try block as
"could raise HTTPException" if its `except Exception` re-raises as
HTTPException. That's a slight over-approximation but matches the
codebase's defensive convention exactly.

Whitelist: append `# noqa: HTTP_RAISE` to the `except Exception:`
line for a deliberate exemption. (Used by genuinely-leaf handlers
that don't call anything that raises typed exceptions.)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Paths to walk. We restrict to `api/routers/` because the convention
# is about HTTP response semantics; service / domain / util modules
# don't return HTTP responses and shouldn't be subject to this rule.
_ROUTERS_DIR = Path(__file__).resolve().parent.parent / "api" / "routers"

# Skip files unrelated to HTTP-status-shaping (no router decorators).
_SKIP_BASENAMES: set[str] = {"__init__.py"}


def _is_exception_name(node: ast.expr | None, name: str) -> bool:
    """Is this `ast.Name` referring to the exception class `name`?

    Handles bare `Exception` and the dotted `builtins.Exception`
    form. Tuples (`except (Foo, Exception)`) are accepted if any
    element matches.
    """
    if node is None:
        # Bare `except:` clause — node is None. Treated as catching
        # everything just like `except Exception`.
        return name == "Exception" or name == "BaseException"
    if isinstance(node, ast.Name):
        return node.id == name
    if isinstance(node, ast.Tuple):
        return any(_is_exception_name(elt, name) for elt in node.elts)
    if isinstance(node, ast.Attribute):
        return node.attr == name
    return False


def _exception_clause_raises_httpexception(handler: ast.ExceptHandler) -> bool:
    """Does the body of `except Exception:` raise HTTPException?

    The codebase pattern looks like:
        except Exception as e:
            logger.error(...)
            raise HTTPException(status_code=500, detail=...)

    We walk every node in the body and check for any `raise
    HTTPException(...)` call.
    """
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc
            # `raise HTTPException(...)` form: exc is a Call.
            if isinstance(exc, ast.Call):
                func = exc.func
                if isinstance(func, ast.Name) and func.id == "HTTPException":
                    return True
                if isinstance(func, ast.Attribute) and func.attr == "HTTPException":
                    return True
            # `raise some_var` form where some_var is HTTPException:
            # can't detect statically. Conservative: skip.
    return False


def _has_noqa_http_raise(handler: ast.ExceptHandler, source_lines: list[str]) -> bool:
    """Does the `except Exception:` line carry `# noqa: HTTP_RAISE`?

    The handler's line is 1-indexed; source_lines is 0-indexed.
    """
    line_idx = handler.lineno - 1
    if 0 <= line_idx < len(source_lines):
        return "# noqa: HTTP_RAISE" in source_lines[line_idx]
    return False


def _try_block_has_httpexception_before_generic(node: ast.Try) -> bool:
    """Does this try/except chain have an `except HTTPException:`
    clause BEFORE any `except Exception:` clause?

    Returns True if the protection is in place (test should NOT flag).
    Order matters: Python matches except clauses top-to-bottom, so
    `except HTTPException` must come first.

    Counts a `raise` inside the HTTPException handler as the
    "re-raise" pattern. A handler that just logs and swallows the
    HTTPException without re-raising would also be a bug but is
    much rarer; we flag those too by requiring the body contain a
    bare `raise` statement.
    """
    saw_httpexception = False
    for handler in node.handlers:
        if _is_exception_name(handler.type, "HTTPException"):
            # Body should contain `raise` (no arg = re-raise).
            for child in ast.walk(handler):
                if isinstance(child, ast.Raise) and child.exc is None:
                    saw_httpexception = True
                    break
            # If the body re-raises with an arg (raise HTTPException(...))
            # that's also acceptable — the intent is to preserve the
            # original status code, and a re-raise-with-arg using the
            # captured `e` qualifies. We'd need to inspect the
            # captured-name binding for full rigor; skipping that
            # level of analysis here.
            if not saw_httpexception:
                # Body of `except HTTPException` doesn't re-raise.
                # That's a different kind of bug but out of scope for
                # this enforcement — flag as not-protected so the
                # test catches "wrote the right handler but forgot
                # to actually re-raise".
                continue

        if _is_exception_name(handler.type, "Exception") and not saw_httpexception:
            return False
    return True


def _scan_function(
    func: ast.AsyncFunctionDef | ast.FunctionDef,
    source_lines: list[str],
) -> list[tuple[int, str]]:
    """Find all violations inside one function body.

    Returns a list of (line_number, message) tuples.
    """
    violations: list[tuple[int, str]] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Try):
            continue

        # Find any `except Exception` (or bare `except:`) clause whose
        # body raises HTTPException — that's the bug pattern.
        has_generic_raising_httpexc = False
        for handler in node.handlers:
            if _is_exception_name(handler.type, "Exception"):
                if _exception_clause_raises_httpexception(handler):
                    if not _has_noqa_http_raise(handler, source_lines):
                        has_generic_raising_httpexc = True
                        break

        if not has_generic_raising_httpexc:
            continue

        # If we're here, the try has a generic catch that converts
        # everything to 500. Verify the HTTPException re-raise
        # precedes it.
        if not _try_block_has_httpexception_before_generic(node):
            violations.append((
                node.lineno,
                f"{func.name}() try/except at line {node.lineno} converts "
                "any Exception to HTTPException(500) but lacks an `except "
                "HTTPException: raise` clause earlier — typed 4xx/5xx "
                "exceptions raised inside the try will be clobbered to 500. "
                "Add `except HTTPException:\\n    raise` before the generic "
                "`except Exception` clause, or annotate the line with "
                "`# noqa: HTTP_RAISE` if the catch is intentional.",
            ))
    return violations


def _scan_file(file_path: Path) -> list[tuple[int, str]]:
    source = file_path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=str(file_path))
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            violations.extend(_scan_function(node, source_lines))
    return violations


@pytest.mark.parametrize(
    "router_file",
    sorted(p for p in _ROUTERS_DIR.glob("*.py") if p.name not in _SKIP_BASENAMES),
    ids=lambda p: p.name,
)
def test_router_httpexception_reraise_enforced(router_file: Path):
    """Mechanically enforce the HTTPException re-raise convention.

    Every router file is parsed independently so the failure
    message identifies the exact router with the issue. Add
    `# noqa: HTTP_RAISE` to a specific `except Exception:` line
    to whitelist a deliberate exemption.
    """
    violations = _scan_file(router_file)
    if violations:
        lines = "\n".join(
            f"  {router_file.name}:{ln}: {msg}"
            for ln, msg in violations
        )
        pytest.fail(
            f"\n{lines}\n\nThe `except HTTPException: raise` convention "
            "exists to prevent typed 4xx/5xx exceptions from being "
            "clobbered to 500 by the generic `except Exception` catch. "
            "See the docstring of tests/test_v0_7_135_meta.py for the "
            "pattern and the whitelist mechanism."
        )


# Smoke test the AST walker itself so a future refactor of the
# helper logic doesn't silently disable the enforcement.


def test_walker_detects_synthetic_violation(tmp_path: Path):
    """Construct a known-buggy file in tmp_path and prove the walker
    flags it. Catches regressions where the AST analysis breaks but
    every router happens to pass."""
    src = """
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/x")
async def buggy():
    try:
        await something()
    except Exception as e:
        raise HTTPException(500, detail=str(e))
"""
    f = tmp_path / "fake_router.py"
    f.write_text(src)
    violations = _scan_file(f)
    assert len(violations) == 1
    assert "buggy" in violations[0][1]


def test_walker_accepts_correct_pattern(tmp_path: Path):
    src = """
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/x")
async def correct():
    try:
        await something()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=str(e))
"""
    f = tmp_path / "ok_router.py"
    f.write_text(src)
    violations = _scan_file(f)
    assert violations == []


def test_walker_respects_noqa_whitelist(tmp_path: Path):
    src = """
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/x")
async def intentional():
    try:
        await something()
    except Exception as e:  # noqa: HTTP_RAISE
        raise HTTPException(500, detail=str(e))
"""
    f = tmp_path / "noqa_router.py"
    f.write_text(src)
    violations = _scan_file(f)
    assert violations == []


def test_walker_ignores_handlers_that_dont_raise_httpexception(tmp_path: Path):
    """Helper functions that just log and return don't trigger the
    rule — they're not converting to HTTPException(500)."""
    src = """
from fastapi import APIRouter

router = APIRouter()

def helper():
    try:
        do_work()
    except Exception as e:
        # Just logs and returns — no HTTPException involved.
        print(e)
        return None
"""
    f = tmp_path / "helper.py"
    f.write_text(src)
    violations = _scan_file(f)
    assert violations == []
