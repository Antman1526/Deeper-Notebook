"""Disposable SurrealDB regressions for Study source readiness projection."""

from __future__ import annotations

import pytest

from deeper_notebook.study.plans import StudyPlanSourceLink
from deeper_notebook.study.source_service import StudySourceService

pytestmark = pytest.mark.integration_surreal


@pytest.mark.asyncio
async def test_optional_full_text_is_processing_not_unavailable_in_surreal_2(
    clean_namespace: dict[str, object],
) -> None:
    """A legacy source without full_text must remain a visible processing item."""

    from deeper_notebook.database.repository import repo_query

    await repo_query(
        "CREATE source:task5_missing CONTENT { title: 'Awaiting extraction', source_type: 'upload' };"
    )
    await repo_query(
        "CREATE source:task5_ready CONTENT { title: 'Extracted lecture', source_type: 'text', full_text: 'A nonblank transcript.' };"
    )

    readiness = await StudySourceService().readiness(
        (
            StudyPlanSourceLink(source_id="source:task5_missing"),
            StudyPlanSourceLink(source_id="source:task5_ready"),
        )
    )
    items = {item.source_id: item for item in readiness.items}

    assert readiness.ready is False
    assert items["source:task5_missing"].ready is False
    assert items["source:task5_missing"].reason == "processing"
    assert items["source:task5_ready"].ready is True
    assert items["source:task5_ready"].reason == "ready"
    assert all("full_text" not in item.model_dump() for item in readiness.items)
