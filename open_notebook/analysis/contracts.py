"""Closed, metadata-only contracts for local analysis execution.

These models describe an approval-gated execution request without carrying the
source bodies themselves. A future native sandbox receives copied inputs at
runtime; persistence retains only their stable identities and hashes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AnalysisRunState = Literal[
    "awaiting_approval",
    "approved",
    "running",
    "succeeded",
    "failed",
    "sandbox_unavailable",
    "cancelled",
]
AnalysisFailureCode = Literal[
    "sandbox_unavailable",
    "sandbox_error",
    "execution_failed",
    "output_rejected",
    "cancelled",
]

_SAFE_FAILURE_MESSAGES: dict[AnalysisFailureCode, str] = {
    "sandbox_unavailable": "Local analysis is unavailable on this platform.",
    "sandbox_error": "Local analysis could not start safely.",
    "execution_failed": "Local analysis did not complete.",
    "output_rejected": "Local analysis produced an unsafe output.",
    "cancelled": "Local analysis was cancelled.",
}
_TERMINAL_STATES: frozenset[AnalysisRunState] = frozenset(
    {"succeeded", "failed", "sandbox_unavailable", "cancelled"}
)
_TRANSITIONS: dict[AnalysisRunState, frozenset[AnalysisRunState]] = {
    "awaiting_approval": frozenset({"approved", "cancelled"}),
    "approved": frozenset({"running", "cancelled", "sandbox_unavailable"}),
    "running": frozenset(_TERMINAL_STATES),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "sandbox_unavailable": frozenset(),
    "cancelled": frozenset(),
}


def _validate_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("path must be a normalized relative path")
    return normalized


class SourceInputHash(BaseModel):
    """Identity and integrity metadata for one copied source input."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0, le=1_073_741_824)
    filename: str = Field(min_length=1, max_length=512)

    @field_validator("filename")
    @classmethod
    def relative_filename_only(cls, value: str) -> str:
        return _validate_relative_path(value)


class ScrubbedExecutionRequest(BaseModel):
    """Exact approved code plus source metadata, never environment or paths."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    code: str = Field(min_length=1, max_length=100_000)
    source_inputs: list[SourceInputHash] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_source_inputs(self) -> "ScrubbedExecutionRequest":
        source_ids = [source.source_id for source in self.source_inputs]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source inputs must have unique source ids")
        filenames = [source.filename for source in self.source_inputs]
        if len(filenames) != len(set(filenames)):
            raise ValueError("source inputs must have unique filenames")
        return self

    @property
    def sha256(self) -> str:
        """Bind approval and routing receipts to the exact approved request."""
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ResourceLimits(BaseModel):
    """Small immutable ceilings enforced by a future platform sandbox."""

    model_config = ConfigDict(extra="forbid")

    max_wall_seconds: int = Field(default=60, ge=1, le=300)
    max_cpu_seconds: int = Field(default=30, ge=1, le=300)
    max_memory_mib: int = Field(default=512, ge=64, le=4_096)
    max_output_bytes: int = Field(
        default=25 * 1024 * 1024, ge=1_024, le=100 * 1024 * 1024
    )
    max_stdout_stderr_bytes: int = Field(default=256 * 1024, ge=1_024, le=1_024 * 1024)
    max_processes: int = Field(default=1, ge=1, le=1)

    @model_validator(mode="after")
    def cpu_cannot_exceed_wall_time(self) -> "ResourceLimits":
        if self.max_cpu_seconds > self.max_wall_seconds:
            raise ValueError("CPU limit cannot exceed wall-time limit")
        return self


class ApprovalReceipt(BaseModel):
    """A local, idempotent acknowledgement of an exact code request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    approval_request_id: str = Field(min_length=1, max_length=256)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RouteReceipt(BaseModel):
    """Records why a backend was selected, including fail-closed selection."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    backend_id: str = Field(min_length=1, max_length=128)
    available: bool
    availability_checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason_code: str = Field(min_length=1, max_length=128)

    @classmethod
    def disabled(cls, request_sha256: str) -> "RouteReceipt":
        return cls(
            backend_id="disabled",
            available=False,
            request_sha256=request_sha256,
            reason_code="sandbox_unavailable",
        )


class AnalysisFailure(BaseModel):
    """A deliberately small error shape that cannot store provider/system text."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    code: AnalysisFailureCode
    message: str

    @model_validator(mode="after")
    def only_allow_safe_message(self) -> "AnalysisFailure":
        if self.message != _SAFE_FAILURE_MESSAGES[self.code]:
            raise ValueError("failure messages must use the approved safe text")
        return self

    @classmethod
    def for_code(cls, code: AnalysisFailureCode) -> "AnalysisFailure":
        return cls(code=code, message=_SAFE_FAILURE_MESSAGES[code])


class OutputEntry(BaseModel):
    """Metadata for a validated output file; never its bytes or contents."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    relative_path: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0, le=100 * 1024 * 1024)
    media_type: str = Field(min_length=1, max_length=128)

    @field_validator("relative_path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class OutputManifest(BaseModel):
    """Versioned manifest for outputs accepted by the later validation stage."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    outputs: list[OutputEntry] = Field(default_factory=list, max_length=1_000)

    @model_validator(mode="after")
    def unique_output_paths(self) -> "OutputManifest":
        paths = [entry.relative_path for entry in self.outputs]
        if len(paths) != len(set(paths)):
            raise ValueError("output paths must be unique")
        return self

    @property
    def total_bytes(self) -> int:
        return sum(entry.byte_size for entry in self.outputs)


class AnalysisRun(BaseModel):
    """Durable state for one approval-gated, locally bounded analysis run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str | None = None
    notebook_id: str | None = None
    objective: str = Field(min_length=1, max_length=4_000)
    state: AnalysisRunState = "awaiting_approval"
    execution_request: ScrubbedExecutionRequest
    resource_limits: ResourceLimits
    approval_receipt: ApprovalReceipt | None = None
    route_receipt: RouteReceipt | None = None
    output_manifest: OutputManifest | None = None
    failure: AnalysisFailure | None = None
    created: datetime | None = None
    updated: datetime | None = None

    @model_validator(mode="after")
    def validate_lifecycle_and_receipts(self) -> "AnalysisRun":
        if self.route_receipt is None:
            self.route_receipt = RouteReceipt.disabled(self.execution_request.sha256)
        elif self.route_receipt.request_sha256 != self.execution_request.sha256:
            raise ValueError("route receipt must bind the execution request hash")

        requires_approval = {"approved", "running", "succeeded", "failed"}
        if self.state in requires_approval and self.approval_receipt is None:
            raise ValueError("analysis state requires an approval receipt")
        if (
            self.approval_receipt is not None
            and self.approval_receipt.request_sha256 != self.execution_request.sha256
        ):
            raise ValueError("approval receipt must bind the execution request hash")
        if self.state == "succeeded" and self.output_manifest is None:
            raise ValueError("succeeded analysis requires an output manifest")
        if self.output_manifest is not None and self.state != "succeeded":
            raise ValueError("only succeeded analysis may expose output metadata")
        if self.failure is not None and self.state not in {
            "failed",
            "sandbox_unavailable",
            "cancelled",
        }:
            raise ValueError("failure records require a terminal failure state")
        if (
            self.state in {"failed", "sandbox_unavailable", "cancelled"}
            and self.failure is None
        ):
            raise ValueError("terminal failure state requires a sanitized failure")
        return self

    def transition_to(
        self, state: AnalysisRunState, **updates: object
    ) -> "AnalysisRun":
        """Reject skipped or replayed states before a repository write."""
        if state not in _TRANSITIONS[self.state]:
            raise ValueError(
                f"invalid analysis state transition: {self.state} -> {state}"
            )
        return AnalysisRun.model_validate(
            self.model_dump(mode="json") | {"state": state, **updates}
        )
