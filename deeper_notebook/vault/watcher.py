"""Read-only, content-addressed watcher for approved external vaults."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Protocol

from deeper_notebook.vault.security import (
    ApprovedVaultRoot,
    SecureFileCandidate,
    VaultSecurityError,
    classify_vault_path,
    list_secure_candidates,
    secure_read,
)

ObservationState = Literal["pending", "ready", "retry", "missing"]
ParseState = Literal["pending", "parsed", "failed", "missing"]
EmbeddingState = Literal[
    "not_submitted", "pending", "embedded", "failed", "not_applicable"
]


@dataclass(frozen=True, slots=True)
class VaultFileObservation:
    vault_id: str
    relative_path: str
    state: ObservationState
    file_kind: str
    protected: bool
    content_hash: str | None
    byte_size: int | None
    modified_ns: int | None
    parse_state: ParseState
    embedding_state: EmbeddingState
    observed_at: float
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class VaultWorkItem:
    vault_id: str
    relative_path: str
    file_kind: Literal["markdown", "metadata"]
    protected: bool
    content: bytes
    content_hash: str
    byte_size: int
    modified_ns: int
    parse_state: ParseState = "pending"
    embedding_state: EmbeddingState = "not_submitted"


class VaultObservationRepository(Protocol):
    async def record_observation(
        self, observation: VaultFileObservation
    ) -> None: ...

    async def mark_missing(self, vault_id: str, relative_path: str) -> None: ...


@dataclass(frozen=True, slots=True)
class _StableObservation:
    device: int
    inode: int
    mode: int
    byte_size: int
    modified_ns: int
    first_seen_at: float

    @classmethod
    def from_candidate(
        cls, candidate: SecureFileCandidate, now: float
    ) -> "_StableObservation":
        return cls(
            device=candidate.device,
            inode=candidate.inode,
            mode=candidate.mode,
            byte_size=candidate.byte_size,
            modified_ns=candidate.modified_ns,
            first_seen_at=now,
        )

    def same_file_state(self, candidate: SecureFileCandidate) -> bool:
        return (
            self.device,
            self.inode,
            self.mode,
            self.byte_size,
            self.modified_ns,
        ) == (
            candidate.device,
            candidate.inode,
            candidate.mode,
            candidate.byte_size,
            candidate.modified_ns,
        )


class VaultWatcher:
    """Require two stable observations and coalesce work by path and hash."""

    def __init__(
        self,
        *,
        vault_id: str,
        approved_root: ApprovedVaultRoot,
        repository: VaultObservationRepository,
        stable_after_seconds: float = 2.0,
        known_paths: set[str] | None = None,
        max_file_bytes: int | None = None,
    ) -> None:
        if stable_after_seconds < 2.0:
            raise ValueError("vault stability window must be at least two seconds")
        self._vault_id = vault_id
        self._root = approved_root
        self._repository = repository
        self._stable_after_seconds = stable_after_seconds
        self._max_file_bytes = max_file_bytes
        self._observations: dict[str, _StableObservation] = {}
        self._known_paths = set(known_paths or ())
        self._missing_paths: set[str] = set()
        self._emitted: set[tuple[str, str]] = set()

    async def scan(
        self, *, now_monotonic: float | None = None
    ) -> list[VaultWorkItem]:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        candidates = list_secure_candidates(self._root)
        current_paths: set[str] = set()
        work: list[VaultWorkItem] = []

        for candidate in candidates:
            classification = classify_vault_path(candidate.relative_path)
            if not classification.indexable:
                continue
            relative = candidate.relative_path
            current_paths.add(relative)
            self._known_paths.add(relative)
            self._missing_paths.discard(relative)
            prior = self._observations.get(relative)
            if prior is None or not prior.same_file_state(candidate):
                self._observations[relative] = _StableObservation.from_candidate(
                    candidate, now
                )
                await self._record(
                    relative=relative,
                    state="pending",
                    file_kind=classification.kind,
                    protected=classification.protected,
                    content_hash=None,
                    byte_size=candidate.byte_size,
                    modified_ns=candidate.modified_ns,
                    observed_at=now,
                )
                continue
            if now - prior.first_seen_at < self._stable_after_seconds:
                await self._record(
                    relative=relative,
                    state="pending",
                    file_kind=classification.kind,
                    protected=classification.protected,
                    content_hash=None,
                    byte_size=candidate.byte_size,
                    modified_ns=candidate.modified_ns,
                    observed_at=now,
                )
                continue

            try:
                read = secure_read(
                    self._root,
                    relative,
                    max_bytes=self._max_file_bytes,
                )
            except VaultSecurityError as exc:
                self._observations.pop(relative, None)
                await self._record(
                    relative=relative,
                    state="retry",
                    file_kind=classification.kind,
                    protected=classification.protected,
                    content_hash=None,
                    byte_size=candidate.byte_size,
                    modified_ns=candidate.modified_ns,
                    observed_at=now,
                    error_code=exc.code,
                )
                continue

            if (
                read.device != candidate.device
                or read.inode != candidate.inode
                or read.mode != candidate.mode
                or read.byte_size != candidate.byte_size
                or read.modified_ns != candidate.modified_ns
            ):
                self._observations.pop(relative, None)
                await self._record(
                    relative=relative,
                    state="retry",
                    file_kind=classification.kind,
                    protected=classification.protected,
                    content_hash=None,
                    byte_size=read.byte_size,
                    modified_ns=read.modified_ns,
                    observed_at=now,
                    error_code="changed_during_read",
                )
                continue

            dedupe_key = (relative, read.sha256)
            if dedupe_key in self._emitted:
                continue
            self._emitted.add(dedupe_key)
            await self._record(
                relative=relative,
                state="ready",
                file_kind=classification.kind,
                protected=classification.protected,
                content_hash=read.sha256,
                byte_size=read.byte_size,
                modified_ns=read.modified_ns,
                observed_at=now,
            )
            work.append(
                VaultWorkItem(
                    vault_id=self._vault_id,
                    relative_path=relative,
                    file_kind=classification.kind,  # type: ignore[arg-type]
                    protected=classification.protected,
                    content=read.content,
                    content_hash=read.sha256,
                    byte_size=read.byte_size,
                    modified_ns=read.modified_ns,
                )
            )

        for relative in sorted(self._known_paths - current_paths):
            if relative in self._missing_paths:
                continue
            self._missing_paths.add(relative)
            self._observations.pop(relative, None)
            await self._repository.mark_missing(self._vault_id, relative)
            classification = classify_vault_path(relative)
            await self._record(
                relative=relative,
                state="missing",
                file_kind=classification.kind,
                protected=classification.protected,
                content_hash=None,
                byte_size=None,
                modified_ns=None,
                observed_at=now,
                parse_state="missing",
            )

        return work

    async def _record(
        self,
        *,
        relative: str,
        state: ObservationState,
        file_kind: str,
        protected: bool,
        content_hash: str | None,
        byte_size: int | None,
        modified_ns: int | None,
        observed_at: float,
        error_code: str | None = None,
        parse_state: ParseState = "pending",
    ) -> None:
        await self._repository.record_observation(
            VaultFileObservation(
                vault_id=self._vault_id,
                relative_path=relative,
                state=state,
                file_kind=file_kind,
                protected=protected,
                content_hash=content_hash,
                byte_size=byte_size,
                modified_ns=modified_ns,
                parse_state=parse_state,
                embedding_state="not_submitted",
                observed_at=observed_at,
                error_code=error_code,
            )
        )


__all__ = [
    "VaultFileObservation",
    "VaultObservationRepository",
    "VaultWatcher",
    "VaultWorkItem",
]
