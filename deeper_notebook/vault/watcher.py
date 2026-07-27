"""Read-only, content-addressed watcher for approved external vaults."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
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

ObservationState = Literal["pending", "ready", "retry"]
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

    async def mark_missing(self, vault_id: str, relative_path: str) -> None:
        """Atomically transition to missing and append its receipt once.

        Implementations MUST be idempotent. Repeating this call for an already
        missing path must not append another transition receipt.
        """
        ...


@dataclass(frozen=True, slots=True)
class _StableObservation:
    device: int
    inode: int
    mode: int
    byte_size: int
    modified_ns: int
    changed_ns: int
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
            changed_ns=candidate.changed_ns,
            first_seen_at=now,
        )

    def same_file_state(self, candidate: SecureFileCandidate) -> bool:
        return (
            self.device,
            self.inode,
            self.mode,
            self.byte_size,
            self.modified_ns,
            self.changed_ns,
        ) == (
            candidate.device,
            candidate.inode,
            candidate.mode,
            candidate.byte_size,
            candidate.modified_ns,
            candidate.changed_ns,
        )


class VaultWatcher:
    """Require stable reads and coalesce by last committed projection hash.

    ``known_projected_hashes`` contains only hashes whose complete projection
    transaction committed successfully. A merely ready or queued observation
    must never be supplied as a projected hash seed.
    """

    def __init__(
        self,
        *,
        vault_id: str,
        approved_root: ApprovedVaultRoot,
        repository: VaultObservationRepository,
        stable_after_seconds: float = 2.0,
        known_paths: set[str] | None = None,
        known_projected_hashes: Mapping[str, str | None] | None = None,
        max_file_bytes: int | None = None,
    ) -> None:
        if stable_after_seconds < 2.0:
            raise ValueError("vault stability window must be at least two seconds")
        self._vault_id = vault_id
        self._root = approved_root
        self._repository = repository
        self._stable_after_seconds = stable_after_seconds
        self._max_file_bytes = max_file_bytes
        self._scan_lock = asyncio.Lock()
        self._observations: dict[str, _StableObservation] = {}
        self._known_paths = {
            self._validated_seed_path(relative) for relative in (known_paths or ())
        }
        self._projected_hashes: dict[str, str] = {}
        self._queued_hashes: dict[str, str] = {}
        for relative, content_hash in (known_projected_hashes or {}).items():
            validated = self._validated_seed_path(relative)
            self._known_paths.add(validated)
            if content_hash is not None:
                self._projected_hashes[validated] = self._validated_hash(content_hash)
        self._missing_paths: set[str] = set()

    async def scan(
        self, *, now_monotonic: float | None = None
    ) -> list[VaultWorkItem]:
        async with self._scan_lock:
            return await self._scan_locked(now_monotonic=now_monotonic)

    async def acknowledge_projected(
        self, relative_path: str, content_hash: str
    ) -> bool:
        """Acknowledge the exact queued hash after its projection commits."""

        relative = self._validated_seed_path(relative_path)
        validated_hash = self._validated_hash(content_hash)
        async with self._scan_lock:
            if self._queued_hashes.get(relative) != validated_hash:
                return self._projected_hashes.get(relative) == validated_hash
            self._projected_hashes[relative] = validated_hash
            self._queued_hashes.pop(relative, None)
            return True

    async def release_queued(self, relative_path: str, content_hash: str) -> bool:
        """Release the exact queued hash so a failed consumer can retry it."""

        relative = self._validated_seed_path(relative_path)
        validated_hash = self._validated_hash(content_hash)
        async with self._scan_lock:
            if self._queued_hashes.get(relative) != validated_hash:
                return False
            self._queued_hashes.pop(relative, None)
            return True

    async def _scan_locked(
        self, *, now_monotonic: float | None
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
            prior = self._observations.get(relative)
            if prior is None or not prior.same_file_state(candidate):
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
                self._observations[relative] = _StableObservation.from_candidate(
                    candidate, now
                )
                self._known_paths.add(relative)
                self._missing_paths.discard(relative)
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
                self._known_paths.add(relative)
                self._missing_paths.discard(relative)
                continue

            try:
                read = secure_read(
                    self._root,
                    relative,
                    max_bytes=self._max_file_bytes,
                )
            except VaultSecurityError as exc:
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
                self._observations.pop(relative, None)
                self._known_paths.add(relative)
                self._missing_paths.discard(relative)
                continue

            if (
                read.device != candidate.device
                or read.inode != candidate.inode
                or read.mode != candidate.mode
                or read.byte_size != candidate.byte_size
                or read.modified_ns != candidate.modified_ns
                or read.changed_ns != candidate.changed_ns
            ):
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
                self._observations.pop(relative, None)
                self._known_paths.add(relative)
                self._missing_paths.discard(relative)
                continue

            if (
                self._projected_hashes.get(relative) == read.sha256
                or self._queued_hashes.get(relative) == read.sha256
            ):
                continue
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
            self._queued_hashes[relative] = read.sha256
            self._known_paths.add(relative)
            self._missing_paths.discard(relative)
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
            await self._repository.mark_missing(self._vault_id, relative)
            self._missing_paths.add(relative)
            self._observations.pop(relative, None)
            self._projected_hashes.pop(relative, None)
            self._queued_hashes.pop(relative, None)

        return work

    @staticmethod
    def _validated_seed_path(relative: str) -> str:
        classification = classify_vault_path(relative)
        if not classification.indexable:
            raise ValueError("seed paths must identify indexable vault files")
        return relative

    @staticmethod
    def _validated_hash(content_hash: str) -> str:
        if (
            not isinstance(content_hash, str)
            or len(content_hash) != 64
            or any(
                character not in "0123456789abcdef" for character in content_hash
            )
        ):
            raise ValueError("content hashes must be lowercase SHA-256")
        return content_hash

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
