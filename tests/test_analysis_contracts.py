"""Closed contracts for fail-closed local analysis runs."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from open_notebook.analysis.backends.disabled import DisabledBackend
from open_notebook.analysis.contracts import (
    AnalysisRun,
    ApprovalReceipt,
    OutputEntry,
    OutputManifest,
    ResourceLimits,
    ScrubbedExecutionRequest,
    SourceInputHash,
)

SOURCE_HASH = "a" * 64


def _request(**overrides: object) -> ScrubbedExecutionRequest:
    data: dict[str, object] = {
        "code": "import csv\nprint('analysis')\n",
        "source_inputs": [
            SourceInputHash(
                source_id="source:contract",
                sha256=SOURCE_HASH,
                byte_size=24,
                filename="evidence.csv",
            )
        ],
    }
    data.update(overrides)
    return ScrubbedExecutionRequest(**data)


def _run(**overrides: object) -> AnalysisRun:
    data: dict[str, object] = {
        "notebook_id": "notebook:contract",
        "objective": "Count evidence rows",
        "execution_request": _request(),
        "resource_limits": ResourceLimits(),
    }
    data.update(overrides)
    return AnalysisRun(**data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "unsafe_shell"),
        (
            "execution_request",
            {"code": "print(1)", "source_inputs": []},
        ),
        (
            "execution_request",
            {
                "code": "print(1)",
                "source_inputs": [
                    {
                        "source_id": "source:x",
                        "sha256": "A" * 64,
                        "byte_size": 1,
                        "filename": "x.txt",
                    }
                ],
            },
        ),
        ("resource_limits", {"max_wall_seconds": 0}),
    ],
)
def test_analysis_run_rejects_values_outside_closed_contract(field, value):
    with pytest.raises(ValidationError):
        _run(**{field: value})


def test_run_cannot_include_source_content_or_unapproved_execution_state():
    with pytest.raises(ValidationError):
        _run(source_content="private source body")

    with pytest.raises(ValidationError, match="approval receipt"):
        _run(state="approved")


def test_approval_binds_the_exact_scrubbed_request_hash():
    request = _request()
    run = _run(
        state="approved",
        approval_receipt=ApprovalReceipt(
            approval_request_id="approval:one",
            request_sha256=request.sha256,
        ),
    )

    assert run.execution_request.sha256 == request.sha256
    assert run.route_receipt.backend_id == "disabled"
    assert run.route_receipt.available is False


def test_output_manifest_is_metadata_only_and_rejects_unsafe_paths():
    manifest = OutputManifest(
        outputs=[
            OutputEntry(
                relative_path="summary.csv",
                sha256="b" * 64,
                byte_size=12,
                media_type="text/csv",
            )
        ]
    )
    assert manifest.total_bytes == 12

    with pytest.raises(ValidationError):
        OutputEntry(
            relative_path="../escape.csv",
            sha256="b" * 64,
            byte_size=12,
            media_type="text/csv",
        )


async def test_disabled_backend_is_typed_and_never_starts_a_subprocess(monkeypatch):
    called = False

    async def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        raise AssertionError("disabled analysis must not start a process")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    backend = DisabledBackend()

    availability = await backend.availability()
    result = await backend.run(_request(), ResourceLimits())

    assert availability.available is False
    assert availability.reason_code == "sandbox_unavailable"
    assert result.state == "sandbox_unavailable"
    assert result.failure.code == "sandbox_unavailable"
    assert result.failure.message == "Local analysis is unavailable on this platform."
    assert called is False
