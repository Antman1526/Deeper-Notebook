"""v0.8.114 — search results must come back sorted, in both search legs.

THE DEFECT

SurrealDB 2.6.5 silently ignores `ORDER BY` on a statement that also carries
`GROUP BY`. Both search functions ended with exactly that shape:

    select ... math::max(similarity) as similarity from $all_results
    group by id, parent_id, title ORDER BY similarity DESC LIMIT $match_count

So `LIMIT` sliced an UNORDERED set. The "top N" was an arbitrary N of everything
that matched, in meaningless order. Measured against the live corpus before the
fix:

    fn::vector_search  ->  0.835, 1.0, 0.723, 0.709, 0.710, …
    fn::text_search    -> -0.5265, -1.0535, -0.5388, -0.4265, -0.152, …

`fn::vector_search` returned nothing at all for unrelated reasons (see
`test_v0_8_114_knn_operator_arity.py`), so its ordering defect was invisible
until that was fixed. `fn::text_search` has been returning arbitrary results
since migration 1.

WHY IT MATTERS MORE THAN "SLIGHTLY WRONG ORDER"

Two reasons. The obvious one is that `LIMIT` on an unsorted set does not return
the best matches — it returns whichever N the engine happened to emit.

The subtler one is hybrid search. v0.8.113 fuses the legs with Reciprocal Rank
Fusion, which scores a document purely by its RANK inside each leg. A leg in
arbitrary order feeds meaningless ranks into the fusion, so one broken leg
degrades the combined result too.

WHAT THIS TEST DOES

Reads the migration text and asserts neither effective search function ends with
the broken shape. Static on purpose: the integration tests that prove ordering
against a real database only run with `SURREAL_INTEGRATION=1`, and this defect
class survived for dozens of migrations precisely because nothing unconditional
looked for it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = (
    Path(__file__).resolve().parents[1] / "deeper_notebook" / "database" / "migrations"
)

SEARCH_FUNCTIONS = ("fn::vector_search", "fn::text_search")


def _forward_migrations() -> list[tuple[int, Path]]:
    """Numbered forward migrations, ascending; down migrations excluded.

    Down migrations deliberately restore the broken shape, because their job is
    to reproduce the previous state rather than improve on it.
    """
    found = [
        (int(path.stem), path)
        for path in MIGRATIONS.glob("*.surrealql")
        if path.stem.isdigit()
    ]
    return sorted(found)


def _effective_definition(function_name: str) -> str:
    """The body a freshly migrated database ends up with for `function_name`.

    Several migrations redefine each function; the highest-numbered one wins,
    since migrations apply in order and each does REMOVE-then-DEFINE.
    """
    for _number, path in reversed(_forward_migrations()):
        text = path.read_text(encoding="utf-8")
        marker = f"DEFINE FUNCTION IF NOT EXISTS {function_name}"
        if marker in text:
            body = text[text.index(marker) :]
            # A migration may define several functions; stop at the next one.
            following = body.find("DEFINE FUNCTION", 1)
            return body if following == -1 else body[:following]
    raise AssertionError(f"no forward migration defines {function_name}")


def _strip_comments(body: str) -> str:
    return "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("--")
    )


@pytest.mark.parametrize("function_name", SEARCH_FUNCTIONS)
def test_a_forward_migration_defines_the_function(function_name):
    """Guards the guard: a rename must fail loudly rather than silently pass."""
    assert function_name in _effective_definition(function_name)


@pytest.mark.parametrize("function_name", SEARCH_FUNCTIONS)
def test_order_by_is_not_on_the_same_statement_as_group_by(function_name):
    """The regression: `GROUP BY … ORDER BY` on one statement drops the sort."""
    code = _strip_comments(_effective_definition(function_name))

    # Normalize whitespace so a line break between the clauses cannot hide it.
    flattened = re.sub(r"\s+", " ", code)
    # The broken shape is GROUP BY <fields> ORDER BY with no intervening close
    # paren — a closing paren means the ORDER BY belongs to an enclosing SELECT,
    # which is exactly the fix.
    offenders = re.findall(r"group by[^()]*?order by", flattened, re.IGNORECASE)

    assert not offenders, (
        f"{function_name} sorts on the same statement as GROUP BY: {offenders!r}. "
        "SurrealDB 2.6.5 ignores that ORDER BY, so LIMIT returns an arbitrary "
        "slice. Wrap the grouped SELECT in a subquery and sort outside it."
    )


@pytest.mark.parametrize("function_name", SEARCH_FUNCTIONS)
def test_the_function_still_sorts_and_limits_somewhere(function_name):
    """Removing the broken ORDER BY entirely would satisfy the test above.

    That would be a worse outcome than the bug, so the sort and the limit both
    have to still be present.
    """
    code = _strip_comments(_effective_definition(function_name))

    assert re.search(r"order by", code, re.IGNORECASE), "the sort was removed"
    assert re.search(r"limit\s+\$match_count", code, re.IGNORECASE), (
        "the caller's match_count limit was removed"
    )
