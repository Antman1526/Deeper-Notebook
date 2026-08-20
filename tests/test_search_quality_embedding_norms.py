"""Task 5 — provider-output normalization measurement.

The search distance migration must be justified without calling an external
provider.  These fake provider vectors prove the two source-relevant paths
forward raw values: short ``generate_embedding`` and batched
``generate_embeddings``.  Long single-document pooling is deliberately
different and has its own normalization contract.
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deeper_notebook.utils.embedding import generate_embedding, generate_embeddings


def _l2_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


@pytest.mark.asyncio
async def test_short_and_batch_embedding_paths_preserve_raw_provider_norms() -> None:
    """Non-unit provider output reaches the source-relevant caller unchanged."""
    model = MagicMock()
    model.aembed = AsyncMock(
        side_effect=[
            [[3.0, 4.0]],
            [[0.0, 5.0], [6.0, 8.0]],
        ]
    )

    with patch(
        "deeper_notebook.ai.models.model_manager.get_embedding_model",
        new=AsyncMock(return_value=model),
    ):
        short = await generate_embedding("short source text")
        batch = await generate_embeddings(["source chunk one", "source chunk two"])

    assert short == [3.0, 4.0]
    assert batch == [[0.0, 5.0], [6.0, 8.0]]
    assert _l2_norm(short) == pytest.approx(5.0)
    assert [_l2_norm(vector) for vector in batch] == pytest.approx([5.0, 10.0])
