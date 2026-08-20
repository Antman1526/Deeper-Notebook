"""v0.8.114 — the KNN operator in `fn::vector_search` must match the index type.

WHAT SHIPPED BROKEN

Migration 21 added HNSW indexes and rewrote `fn::vector_search` to use the KNN
operator, but wrote the ONE-argument form:

    WHERE embedding <|100|> $query

In SurrealDB `<|K|>` targets an MTREE index and `<|K,EF|>` targets HNSW. No
MTREE index exists on any of these tables, so the predicate matched nothing and
semantic search returned zero results for every query — with HTTP 200 and no
error anywhere. Measured on a live database holding 320 embedded chunks, same
query vector:

    <|100|>      ->    0 rows
    <|100,100|>  ->  100 rows
    cosine only  ->  320 rows

WHY A STATIC TEST AND NOT ONLY AN INTEGRATION TEST

The real-database regression test lives in
`tests/integration/test_vector_search_returns_results.py`, and it is the
stronger test — it runs the actual query planner. But everything under
`tests/integration/` is skipped unless `SURREAL_INTEGRATION=1`, which is not
set in a normal run. A defect that survived because nothing exercised it
deserves a guard that runs unconditionally, so this one reads the migration
text and needs no database at all.

WHAT THIS CANNOT CATCH

Reading SQL is not running it. This proves the operator arity matches the index
type; it cannot prove the query returns the right documents. That is the
integration test's job, and neither replaces the other.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPOSITORY_ROOT / "deeper_notebook" / "database" / "migrations"

# `<|K|>` targets MTREE; `<|K,EF|>` targets HNSW.
# The operand may be a Python f-string expression (for example, `{_MAX_FACTS}`),
# so this cannot be limited to numeric literals.
_ONE_ARG_KNN = re.compile(r"<\|\s*[^,|]+\s*\|>")
_TWO_ARG_KNN = re.compile(r"<\|\s*\d+\s*,\s*\d+\s*\|>")


def _forward_migrations() -> list[tuple[int, Path]]:
    """Numbered forward migrations, ascending. Down migrations are excluded.

    A down migration's job is to restore the previous state exactly, including
    when that state was wrong, so `49_down.surrealql` deliberately contains the
    one-argument form and must not be linted against the current schema.
    """
    found: list[tuple[int, Path]] = []
    for path in MIGRATIONS.glob("*.surrealql"):
        if path.stem.endswith("_down"):
            continue
        if path.stem.isdigit():
            found.append((int(path.stem), path))
    return sorted(found)


def _effective_vector_search_body() -> str:
    """The `fn::vector_search` body a freshly migrated database ends up with.

    Several migrations redefine this function; the highest-numbered one wins,
    because migrations apply in order and each does REMOVE-then-DEFINE.
    """
    for number, path in reversed(_forward_migrations()):
        text = path.read_text(encoding="utf-8")
        marker = text.find("DEFINE FUNCTION")
        if marker != -1 and "fn::vector_search" in text[marker:]:
            return text[marker:]
    raise AssertionError("no forward migration defines fn::vector_search")


def test_a_forward_migration_defines_vector_search():
    """Guards the guard: if the function is renamed, fail loudly, not silently."""
    assert "fn::vector_search" in _effective_vector_search_body()


def test_no_vector_index_is_mtree():
    """The premise of this whole file. If an MTREE index is ever added, the
    one-argument operator becomes legitimate and these assertions must be
    revisited rather than mechanically satisfied."""
    for _number, path in _forward_migrations():
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.strip().startswith("--"):
                continue
            assert "MTREE" not in line.upper(), (
                f"{path.name} defines an MTREE index. Vector search assumes HNSW "
                "everywhere; see this file's docstring before changing it."
            )


def test_effective_vector_search_uses_the_hnsw_operator_form():
    """The regression itself: one-argument KNN against HNSW matches nothing."""
    body = _effective_vector_search_body()
    # Strip comments so prose describing the bug does not trip its own guard.
    code = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("--")
    )

    leftover = _ONE_ARG_KNN.findall(_TWO_ARG_KNN.sub("", code))

    assert not leftover, (
        f"fn::vector_search uses the MTREE form of the KNN operator {leftover!r} "
        "while every vector index is HNSW. This matches zero rows and returns "
        "an empty result set with no error. Use <|K,EF|>."
    )


def test_every_knn_predicate_in_the_function_is_two_arg():
    """All three legs — source_embedding, source_insight, note — not just one.

    Migration 21 got all three wrong identically, so a test asserting only that
    *some* two-argument operator is present would have passed on a partial fix.
    """
    body = _effective_vector_search_body()
    code = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("--")
    )

    assert len(_TWO_ARG_KNN.findall(code)) == 3, (
        "expected one KNN predicate per searched table (source_embedding, "
        "source_insight, note)"
    )


def _production_python_code() -> list[tuple[Path, str]]:
    """Return tracked production Python source, excluding tests and comments.

    Query strings may be f-strings, so matching only digit literals would miss
    a one-argument predicate whose K is a Python constant. `ast.unparse()`
    strips explanatory comments. Git's tracked-file inventory prevents ignored
    build trees, sibling worktrees, and developer-local Python files from
    changing this repository contract.
    """
    tracked = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "ls-files", "-z", "--", "*.py"],
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    sources: list[tuple[Path, str]] = []
    for encoded_path in tracked:
        if not encoded_path:
            continue
        relative_path = Path(encoded_path.decode("utf-8"))
        if "tests" in relative_path.parts:
            continue
        path = REPOSITORY_ROOT / relative_path
        sources.append(
            (
                path,
                ast.unparse(ast.parse(path.read_text(encoding="utf-8-sig"))),
            )
        )
    return sources


def test_no_production_python_query_uses_one_argument_knn():
    """All production KNN query predicates must match the HNSW index arity."""
    offenders = [
        f"{path.relative_to(REPOSITORY_ROOT)}: {match.group(0)}"
        for path, source in _production_python_code()
        for match in _ONE_ARG_KNN.finditer(source)
    ]

    assert not offenders, (
        "one-argument KNN predicates target MTREE and silently return no rows "
        f"against this repository's HNSW indexes: {offenders!r}. Use <|K,EF|>."
    )
