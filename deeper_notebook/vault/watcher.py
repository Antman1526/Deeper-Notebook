"""Read-only, content-addressed watcher for approved external vaults."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, Protocol

from deeper_notebook.vault.security import (
    ApprovedVaultRoot,
    SecureFileCandidate,
    VaultSecurityError,
    classify_vault_path,
    list_secure_candidates_bounded,
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


@dataclass(frozen=True, slots=True)
class VaultHandoffResult:
    accepted: bool
    corrective_work: tuple[VaultWorkItem, ...] = ()
    missing_corrected: bool = False


class VaultObservationRepository(Protocol):
    async def record_observation(self, observation: VaultFileObservation) -> None: ...

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


@dataclass(frozen=True, slots=True)
class _CurrentObserved:
    generation: int
    work: VaultWorkItem | None
    missing: bool


@dataclass(frozen=True, slots=True)
class _InFlight:
    content_hash: str
    generation: int


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
        excluded_relative_prefixes: tuple[str, ...] = (),
        max_file_bytes: int | None = None,
        filesystem_timeout_seconds: float = 15.0,
    ) -> None:
        if stable_after_seconds < 2.0:
            raise ValueError("vault stability window must be at least two seconds")
        self._vault_id = vault_id
        self._root = approved_root
        self._repository = repository
        self._stable_after_seconds = stable_after_seconds
        self._max_file_bytes = max_file_bytes
        if filesystem_timeout_seconds <= 0:
            raise ValueError("filesystem timeout must be positive")
        self._filesystem_timeout_seconds = filesystem_timeout_seconds
        self._excluded_relative_prefixes = tuple(
            self._validated_excluded_prefix(prefix)
            for prefix in excluded_relative_prefixes
        )
        self._scan_lock = asyncio.Lock()
        self._observations: dict[str, _StableObservation] = {}
        self._current_observed: dict[str, _CurrentObserved] = {}
        self._known_paths = {
            self._validated_seed_path(relative) for relative in (known_paths or ())
        }
        self._projected_hashes: dict[str, str] = {}
        self._in_flight: dict[str, _InFlight] = {}
        for relative, content_hash in (known_projected_hashes or {}).items():
            validated = self._validated_seed_path(relative)
            self._known_paths.add(validated)
            if content_hash is not None:
                self._projected_hashes[validated] = self._validated_hash(content_hash)
        self._missing_paths: set[str] = set()

    async def scan(self, *, now_monotonic: float | None = None) -> list[VaultWorkItem]:
        async with self._scan_lock:
            return await self._scan_locked(now_monotonic=now_monotonic)

    async def acknowledge_projected(
        self, relative_path: str, content_hash: str
    ) -> VaultHandoffResult:
        """Acknowledge the exact queued hash after its projection commits."""

        relative = self._validated_seed_path(relative_path)
        validated_hash = self._validated_hash(content_hash)
        async with self._scan_lock:
            in_flight = self._in_flight.get(relative)
            if in_flight is None:
                if self._projected_hashes.get(relative) != validated_hash:
                    return VaultHandoffResult(accepted=False)
                corrective = await self._corrective_scan_with_handoff_rollback()
                return VaultHandoffResult(
                    accepted=True, corrective_work=tuple(corrective)
                )
            if in_flight.content_hash != validated_hash:
                return VaultHandoffResult(accepted=False)

            current = self._current_observed.get(relative)
            if current is not None and current.missing:
                await self._repository.mark_missing(self._vault_id, relative)
                self._in_flight.pop(relative, None)
                self._projected_hashes.pop(relative, None)
                return VaultHandoffResult(
                    accepted=True,
                    missing_corrected=True,
                )

            projected_before = dict(self._projected_hashes)
            in_flight_before = dict(self._in_flight)
            self._projected_hashes[relative] = validated_hash
            self._in_flight.pop(relative, None)
            corrective = await self._corrective_scan_with_handoff_rollback(
                projected_before=projected_before,
                in_flight_before=in_flight_before,
            )
            return VaultHandoffResult(accepted=True, corrective_work=tuple(corrective))

    async def release_queued(
        self, relative_path: str, content_hash: str
    ) -> VaultHandoffResult:
        """Release the exact queued hash so a failed consumer can retry it."""

        relative = self._validated_seed_path(relative_path)
        validated_hash = self._validated_hash(content_hash)
        async with self._scan_lock:
            in_flight = self._in_flight.get(relative)
            if in_flight is None or in_flight.content_hash != validated_hash:
                return VaultHandoffResult(accepted=False)
            projected_before = dict(self._projected_hashes)
            in_flight_before = dict(self._in_flight)
            self._in_flight.pop(relative, None)
            corrective = await self._corrective_scan_with_handoff_rollback(
                projected_before=projected_before,
                in_flight_before=in_flight_before,
            )
            return VaultHandoffResult(accepted=True, corrective_work=tuple(corrective))

    async def _corrective_scan_with_handoff_rollback(
        self,
        *,
        projected_before: dict[str, str] | None = None,
        in_flight_before: dict[str, _InFlight] | None = None,
    ) -> list[VaultWorkItem]:
        """Run a corrective scan without losing handoff state on interruption."""

        projected_snapshot = (
            dict(self._projected_hashes)
            if projected_before is None
            else projected_before
        )
        in_flight_snapshot = (
            dict(self._in_flight) if in_flight_before is None else in_flight_before
        )
        try:
            return await self._scan_locked(now_monotonic=None)
        except BaseException:
            self._projected_hashes = projected_snapshot
            self._in_flight = in_flight_snapshot
            raise

    async def _scan_locked(self, *, now_monotonic: float | None) -> list[VaultWorkItem]:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        candidates = list_secure_candidates_bounded(
            self._root,
            timeout_seconds=self._filesystem_timeout_seconds,
        )
        current_paths: set[str] = set()
        work: list[VaultWorkItem] = []

        for candidate in candidates:
            if self._is_excluded(candidate.relative_path):
                continue
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
                self._remember_unknown_present(relative)
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

            work_item = VaultWorkItem(
                vault_id=self._vault_id,
                relative_path=relative,
                file_kind=classification.kind,  # type: ignore[arg-type]
                protected=classification.protected,
                content=read.content,
                content_hash=read.sha256,
                byte_size=read.byte_size,
                modified_ns=read.modified_ns,
            )
            current = self._current_observed.get(relative)
            current_hash = (
                current.work.content_hash
                if current is not None and current.work is not None
                else None
            )
            in_flight = self._in_flight.get(relative)
            if in_flight is not None:
                if current_hash != read.sha256:
                    await self._record(
                        relative=relative,
                        state="pending",
                        file_kind=classification.kind,
                        protected=classification.protected,
                        content_hash=read.sha256,
                        byte_size=read.byte_size,
                        modified_ns=read.modified_ns,
                        observed_at=now,
                    )
                    self._remember_current(relative, work_item)
                continue
            if self._projected_hashes.get(relative) == read.sha256:
                if current_hash != read.sha256:
                    await self._record(
                        relative=relative,
                        state="pending",
                        file_kind=classification.kind,
                        protected=classification.protected,
                        content_hash=read.sha256,
                        byte_size=read.byte_size,
                        modified_ns=read.modified_ns,
                        observed_at=now,
                    )
                    self._remember_current(relative, work_item)
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
            generation = self._remember_current(relative, work_item)
            self._in_flight[relative] = _InFlight(
                content_hash=read.sha256,
                generation=generation,
            )
            self._known_paths.add(relative)
            self._missing_paths.discard(relative)
            work.append(work_item)

        for relative in sorted(self._known_paths - current_paths):
            if relative in self._missing_paths:
                continue
            await self._repository.mark_missing(self._vault_id, relative)
            self._missing_paths.add(relative)
            self._observations.pop(relative, None)
            self._projected_hashes.pop(relative, None)
            self._remember_missing(relative)

        return work

    def _next_generation(self, relative: str) -> int:
        current = self._current_observed.get(relative)
        return 1 if current is None else current.generation + 1

    def _remember_current(self, relative: str, work: VaultWorkItem) -> int:
        generation = self._next_generation(relative)
        self._current_observed[relative] = _CurrentObserved(
            generation=generation,
            work=work,
            missing=False,
        )
        return generation

    def _remember_unknown_present(self, relative: str) -> None:
        self._current_observed[relative] = _CurrentObserved(
            generation=self._next_generation(relative),
            work=None,
            missing=False,
        )

    def _remember_missing(self, relative: str) -> None:
        self._current_observed[relative] = _CurrentObserved(
            generation=self._next_generation(relative),
            work=None,
            missing=True,
        )

    @staticmethod
    def _validated_seed_path(relative: str) -> str:
        classification = classify_vault_path(relative)
        if not classification.indexable:
            raise ValueError("seed paths must identify indexable vault files")
        return relative

    @staticmethod
    def _validated_excluded_prefix(prefix: str) -> str:
        """Accept only canonical, root-relative directory prefixes."""
        if (
            not isinstance(prefix, str)
            or not prefix
            or "\\" in prefix
            or prefix.startswith("/")
            or "\x00" in prefix
        ):
            raise ValueError("excluded prefixes must be canonical relative paths")
        parts = prefix.split("/")
        path = PurePosixPath(*parts)
        if any(part in {"", ".", ".."} for part in parts) or path.as_posix() != prefix:
            raise ValueError("excluded prefixes must be canonical relative paths")
        return prefix

    def _is_excluded(self, relative: str) -> bool:
        return any(
            relative == prefix or relative.startswith(prefix + "/")
            for prefix in self._excluded_relative_prefixes
        )

    @staticmethod
    def _validated_hash(content_hash: str) -> str:
        if (
            not isinstance(content_hash, str)
            or len(content_hash) != 64
            or any(character not in "0123456789abcdef" for character in content_hash)
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
    "VaultHandoffResult",
    "VaultObservationRepository",
    "VaultWatcher",
    "VaultWorkItem",
]
