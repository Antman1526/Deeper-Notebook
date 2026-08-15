"""Strict contracts for the Phase 2A source-derived visual boundary."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

HASH = "a" * 64
OTHER_HASH = "b" * 64
NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def test_source_visual_locator_requires_exactly_one_bounded_value():
    from deeper_notebook.source_visuals.contracts import SourceVisualLocator

    assert SourceVisualLocator(page=1).page == 1
    assert SourceVisualLocator(timestamp_ms=0).timestamp_ms == 0
    assert SourceVisualLocator(resource_id="image-1").resource_id == "image-1"

    for payload in ({}, {"page": 1, "timestamp_ms": 1}, {"resource_id": ""}):
        with pytest.raises(ValidationError):
            SourceVisualLocator(**payload)

    with pytest.raises(ValidationError):
        SourceVisualLocator(page=25)
    with pytest.raises(ValidationError):
        SourceVisualLocator(timestamp_ms=-1)
    with pytest.raises(ValidationError):
        SourceVisualLocator(page=1, unexpected=True)


def test_internal_source_visual_records_are_frozen_and_hash_strict():
    from deeper_notebook.source_visuals.contracts import (
        SourceVisualAuthority,
        SourceVisualLocator,
        SourceVisualRecord,
    )

    authority = SourceVisualAuthority(
        source_id="source:one",
        source_updated_at=NOW,
        normalized_source_type="pdf",
        asset_url=None,
        controlled_file_path=None,
        source_file_sha256=None,
        full_text_sha256=HASH,
        content_sha256=HASH,
        extractor_version="source-visual-v1",
    )
    assert authority.model_config["extra"] == "forbid"
    assert authority.model_config["frozen"] is True

    record = SourceVisualRecord(
        source_id="source:one",
        source_updated_at=NOW,
        source_file_sha256=None,
        content_sha256=HASH,
        asset_sha256=OTHER_HASH,
        asset_relpath="ab/" + HASH + "/" + OTHER_HASH + ".webp",
        origin="embedded",
        source_locator=SourceVisualLocator(page=1),
        extractor_version="source-visual-v1",
        alt_text="Source one embedded image",
        width=1280,
        height=720,
        created_at=NOW,
        updated_at=NOW,
    )
    assert record.mime_type == "image/webp"
    with pytest.raises(ValidationError):
        SourceVisualRecord(**{**record.model_dump(), "content_sha256": "A" * 64})
    with pytest.raises(ValidationError):
        SourceVisualRecord(
            source_id="source:one",
            source_updated_at=NOW,
            content_sha256="A" * 64,
            asset_sha256=OTHER_HASH,
            asset_relpath="asset.webp",
            origin="embedded",
            source_locator=SourceVisualLocator(page=1),
            extractor_version="source-visual-v1",
            alt_text="Image",
            width=1,
            height=1,
            created_at=NOW,
            updated_at=NOW,
        )


def test_claim_and_operation_contracts_bound_leases_and_outcomes():
    from deeper_notebook.source_visuals.contracts import (
        SourceVisualClaim,
        SourceVisualOperationReceipt,
    )

    claim = SourceVisualClaim(
        claim_id=HASH,
        source_id="source:one",
        content_sha256=HASH,
        extractor_version="source-visual-v1",
        owner_token=OTHER_HASH,
        lease_until=NOW,
        command_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    assert claim.command_id is None
    with pytest.raises(ValidationError):
        SourceVisualClaim(**{**claim.model_dump(), "owner_token": "not-a-hash"})
    with pytest.raises(ValidationError):
        SourceVisualClaim(**{**claim.model_dump(), "extra": True})

    receipt = SourceVisualOperationReceipt(
        operation_id=HASH,
        source_id="source:one",
        request_id="refresh-request",
        source_updated_at=NOW,
        content_sha256=HASH,
        operation="refresh",
        command_id="command:one",
        outcome="queued",
        error_code=None,
        created_at=NOW,
        updated_at=NOW,
    )
    assert receipt.outcome == "queued"
    for operation in ("create", "replace"):
        with pytest.raises(ValidationError):
            SourceVisualOperationReceipt(
                **{**receipt.model_dump(), "operation": operation}
            )
    for outcome in ("processing", "complete"):
        with pytest.raises(ValidationError):
            SourceVisualOperationReceipt(
                **{**receipt.model_dump(), "outcome": outcome}
            )


def test_prepared_asset_and_api_contracts_are_bounded_and_private():
    from api.schemas.source_visuals import (
        SourceVisualDeleteRequest,
        SourceVisualJobResponse,
        SourceVisualReceiptResponse,
        SourceVisualRefreshRequest,
        SourceVisualStatusResponse,
    )
    from deeper_notebook.source_visuals.contracts import (
        PreparedVisualAsset,
        SourceVisualLocator,
    )

    prepared = PreparedVisualAsset(
        encoded_bytes=b"webp",
        asset_sha256=HASH,
        width=4,
        height=4,
    )
    assert prepared.mime_type == "image/webp"
    with pytest.raises(ValidationError):
        PreparedVisualAsset(
            encoded_bytes=b"webp",
            asset_sha256=HASH.upper(),
            width=4,
            height=4,
        )

    refresh = SourceVisualRefreshRequest(request_id="r-1")
    delete = SourceVisualDeleteRequest(request_id="r-1")
    assert refresh.request_id == delete.request_id == "r-1"
    with pytest.raises(ValidationError):
        SourceVisualRefreshRequest(request_id="")
    with pytest.raises(ValidationError):
        SourceVisualDeleteRequest(request_id="x" * 257)

    receipt = SourceVisualReceiptResponse(
        source_id="source:one",
        content_sha256=HASH,
        asset_sha256=OTHER_HASH,
        origin="video_frame",
        source_locator=SourceVisualLocator(timestamp_ms=1000),
        alt_text="Source one video frame",
        width=640,
        height=360,
        asset_url="/api/sources/source%3Aone/visual?v=" + HASH,
        created_at=NOW,
        updated_at=NOW,
    )
    assert receipt.mime_type == "image/webp"
    assert "asset_relpath" not in receipt.model_dump()
    assert "source_file_sha256" not in receipt.model_dump()
    with pytest.raises(ValidationError):
        SourceVisualReceiptResponse(**{**receipt.model_dump(), "raw_path": "/tmp/a"})

    status = SourceVisualStatusResponse(
        state="failed",
        command_id=None,
        error_code="decode_failed",
        updated_at=NOW,
    )
    assert status.state == "failed"
    with pytest.raises(ValidationError):
        SourceVisualStatusResponse(
            state="failed",
            error_code="/tmp/private-source.txt",
            updated_at=NOW,
        )

    job = SourceVisualJobResponse(
        source_id="source:one",
        command_id="command:one",
        content_sha256=HASH,
        asset_sha256=OTHER_HASH,
        origin="embedded",
        width=10,
        height=10,
        duration_ms=250,
        outcome="replayed",
        error_code=None,
    )
    assert job.outcome == "replayed"
    with pytest.raises(ValidationError):
        SourceVisualJobResponse(**{**job.model_dump(), "source_text": "private"})
