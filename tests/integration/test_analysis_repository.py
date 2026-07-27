"""Real-SurrealDB contracts for metadata-only analysis persistence."""

from __future__ import annotations

import pytest

from deeper_notebook.analysis.contracts import (
    AnalysisRun,
    ApprovalReceipt,
    OutputEntry,
    OutputManifest,
    ResourceLimits,
    ScrubbedExecutionRequest,
    SourceInputHash,
)
from deeper_notebook.analysis.repository import AnalysisRunRepository
from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import Notebook

pytestmark = pytest.mark.integration_surreal


async def test_repository_persists_hashes_and_output_metadata_without_source_content(
    clean_namespace,
):
    notebook = Notebook(name="Analysis", description="Analysis persistence test")
    await notebook.save()
    source_body = "private source body must never reach persistence"
    request = ScrubbedExecutionRequest(
        code="print('only generated code is retained')",
        source_inputs=[
            SourceInputHash(
                source_id="source:input",
                sha256="a" * 64,
                byte_size=len(source_body.encode("utf-8")),
                filename="input.txt",
            )
        ],
    )
    repository = AnalysisRunRepository()
    created = await repository.create(
        AnalysisRun(
            notebook_id=str(notebook.id),
            objective="Produce a metadata-only result",
            state="approved",
            execution_request=request,
            resource_limits=ResourceLimits(),
            approval_receipt=ApprovalReceipt(
                approval_request_id="approval:analysis-persistence",
                request_sha256=request.sha256,
            ),
        )
    )

    saved = await repository.save_result(
        created.model_copy(
            update={
                "state": "succeeded",
                "output_manifest": OutputManifest(
                    outputs=[
                        OutputEntry(
                            relative_path="result.csv",
                            sha256="b" * 64,
                            byte_size=18,
                            media_type="text/csv",
                        )
                    ]
                ),
            }
        )
    )

    rows = await repo_query(
        "SELECT execution_request, output_manifest FROM analysis_run WHERE id = $id",
        {"id": ensure_record_id(saved.id or "")},
    )
    assert rows[0]["execution_request"]["source_inputs"] == [
        {
            "source_id": "source:input",
            "sha256": "a" * 64,
            "byte_size": len(source_body.encode("utf-8")),
            "filename": "input.txt",
        }
    ]
    assert source_body not in str(rows[0])

    outputs = await repo_query(
        "SELECT relative_path, sha256, byte_size, media_type FROM analysis_output "
        "WHERE analysis_run_id = $run",
        {"run": ensure_record_id(saved.id or "")},
    )
    assert outputs == [
        {
            "relative_path": "result.csv",
            "sha256": "b" * 64,
            "byte_size": 18,
            "media_type": "text/csv",
        }
    ]
