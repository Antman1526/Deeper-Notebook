from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_notebook.vault.security import VaultSecurityError, approve_vault_root
from deeper_notebook.vault.watcher import (
    VaultFileObservation,
    VaultWatcher,
)


class MemoryObservationRepository:
    def __init__(self) -> None:
        self.observations: list[VaultFileObservation] = []
        self.missing: list[tuple[str, str]] = []

    async def record_observation(self, observation: VaultFileObservation) -> None:
        self.observations.append(observation)

    async def mark_missing(self, vault_id: str, relative_path: str) -> None:
        self.missing.append((vault_id, relative_path))


class FailingObservationRepository(MemoryObservationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.fail_record_state: str | None = None
        self.cancel_record_state: str | None = None
        self.fail_mark_missing = False
        self.cancel_mark_missing = False

    async def record_observation(self, observation: VaultFileObservation) -> None:
        if observation.state == self.cancel_record_state:
            self.cancel_record_state = None
            raise asyncio.CancelledError
        if observation.state == self.fail_record_state:
            self.fail_record_state = None
            raise RuntimeError("repository unavailable")
        await super().record_observation(observation)

    async def mark_missing(self, vault_id: str, relative_path: str) -> None:
        if self.cancel_mark_missing:
            self.cancel_mark_missing = False
            raise asyncio.CancelledError
        if self.fail_mark_missing:
            self.fail_mark_missing = False
            raise RuntimeError("repository unavailable")
        await super().mark_missing(vault_id, relative_path)


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    root = tmp_path / "approved-vault"
    root.mkdir()
    return root


@pytest.mark.asyncio
async def test_two_identical_observations_two_seconds_apart_produce_ready_work(
    vault_root: Path,
) -> None:
    (vault_root / "note.md").write_text("body")
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test",
            approved_root=approved,
            repository=repository,
            stable_after_seconds=2.0,
        )
        assert await watcher.scan(now_monotonic=10.0) == []
        assert await watcher.scan(now_monotonic=11.999) == []
        work = await watcher.scan(now_monotonic=12.0)

    assert len(work) == 1
    assert work[0].relative_path == "note.md"
    assert work[0].content == b"body"
    assert work[0].parse_state == "pending"
    assert work[0].embedding_state == "not_submitted"
    assert repository.observations[-1].state == "ready"


@pytest.mark.asyncio
async def test_changed_observation_restarts_stability_window(
    vault_root: Path,
) -> None:
    path = vault_root / "note.md"
    path.write_text("one")
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        path.write_text("two and changed")
        assert await watcher.scan(now_monotonic=3.0) == []
        work = await watcher.scan(now_monotonic=5.0)
    assert [item.content for item in work] == [b"two and changed"]


@pytest.mark.asyncio
async def test_event_storm_coalesces_same_path_and_hash(vault_root: Path) -> None:
    (vault_root / "note.md").write_text("body")
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        first = await watcher.scan(now_monotonic=3.0)
        repeats = [
            await watcher.scan(now_monotonic=4.0),
            await watcher.scan(now_monotonic=5.0),
            await watcher.scan(now_monotonic=6.0),
        ]
    assert len(first) == 1
    assert repeats == [[], [], []]
    ready = [item for item in repository.observations if item.state == "ready"]
    assert len(ready) == 1


@pytest.mark.asyncio
async def test_current_hash_dedupe_allows_a_to_b_to_a(vault_root: Path) -> None:
    path = vault_root / "note.md"
    path.write_bytes(b"A")
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        first = await watcher.scan(now_monotonic=3.0)
        path.write_bytes(b"B")
        await watcher.scan(now_monotonic=4.0)
        second = await watcher.scan(now_monotonic=6.0)
        path.write_bytes(b"A")
        await watcher.scan(now_monotonic=7.0)
        third = await watcher.scan(now_monotonic=9.0)

    assert [item.content for item in first + second + third] == [b"A", b"B", b"A"]


@pytest.mark.asyncio
async def test_restart_seeded_current_hash_dedupes_without_ready_work(
    vault_root: Path,
) -> None:
    content = b"body"
    (vault_root / "note.md").write_bytes(content)
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test",
            approved_root=approved,
            repository=repository,
            known_content_hashes={
                "note.md": hashlib.sha256(content).hexdigest(),
            },
        )
        await watcher.scan(now_monotonic=1.0)
        assert await watcher.scan(now_monotonic=3.0) == []
    assert not any(item.state == "ready" for item in repository.observations)


@pytest.mark.asyncio
async def test_deletion_marks_missing_without_deleting_projection(
    vault_root: Path,
) -> None:
    path = vault_root / "note.md"
    path.write_text("body")
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        await watcher.scan(now_monotonic=3.0)
        path.unlink()
        assert await watcher.scan(now_monotonic=4.0) == []
        assert await watcher.scan(now_monotonic=5.0) == []

    assert repository.missing == [("vault:test", "note.md")]
    assert repository.observations[-1].state == "missing"


@pytest.mark.asyncio
async def test_missing_then_same_content_reappearance_emits_again(
    vault_root: Path,
) -> None:
    path = vault_root / "note.md"
    path.write_bytes(b"body")
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        assert len(await watcher.scan(now_monotonic=3.0)) == 1
        path.unlink()
        await watcher.scan(now_monotonic=4.0)
        path.write_bytes(b"body")
        await watcher.scan(now_monotonic=5.0)
        work = await watcher.scan(now_monotonic=7.0)
    assert [item.content for item in work] == [b"body"]


@pytest.mark.asyncio
async def test_control_connector_temporary_and_non_page_files_are_skipped(
    vault_root: Path,
) -> None:
    fixtures = {
        ".obsidian/workspace.json": b"{}",
        ".git/config": b"x",
        "logseq/config.edn": b"x",
        "brain-engine/generated.md": b"x",
        "note.md.tmp": b"x",
        "image.png": b"x",
        "board.canvas": b"{}",
        "sources/paper.md": b"paper",
    }
    for relative, content in fixtures.items():
        path = vault_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    repository = MemoryObservationRepository()

    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        work = await watcher.scan(now_monotonic=3.0)

    assert {item.relative_path for item in work} == {
        "board.canvas",
        "sources/paper.md",
    }
    paper = next(item for item in work if item.relative_path == "sources/paper.md")
    assert paper.protected is True


@pytest.mark.asyncio
async def test_scan_is_read_only_after_fixture_setup(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = vault_root / "note.md"
    path.write_bytes(b"immutable")
    before = path.read_bytes()
    forbidden_calls: list[str] = []

    def forbidden(name: str):
        def fail(*args: object, **kwargs: object) -> None:
            forbidden_calls.append(name)
            raise AssertionError(f"source mutation attempted: {name}")

        return fail

    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        for name in (
            "write_text",
            "write_bytes",
            "replace",
            "unlink",
            "rename",
            "mkdir",
            "chmod",
        ):
            monkeypatch.setattr(Path, name, forbidden(name))
        for name in ("unlink", "remove", "rename", "replace", "mkdir", "chmod"):
            monkeypatch.setattr(
                "deeper_notebook.vault.security.os." + name, forbidden("os." + name)
            )
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        await watcher.scan(now_monotonic=3.0)

    assert forbidden_calls == []
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_changed_during_secure_read_is_retryable_not_ready(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (vault_root / "note.md").write_text("body")
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)

        def changed(*args: object, **kwargs: object):
            from deeper_notebook.vault.security import VaultSecurityError

            raise VaultSecurityError("changed_during_read")

        monkeypatch.setattr("deeper_notebook.vault.watcher.secure_read", changed)
        assert await watcher.scan(now_monotonic=3.0) == []
    assert repository.observations[-1].state == "retry"
    assert repository.observations[-1].error_code == "changed_during_read"


@pytest.mark.asyncio
async def test_ready_repository_failure_and_cancellation_do_not_poison_dedupe(
    vault_root: Path,
) -> None:
    (vault_root / "note.md").write_bytes(b"body")
    repository = FailingObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        repository.fail_record_state = "ready"
        with pytest.raises(RuntimeError):
            await watcher.scan(now_monotonic=3.0)
        repository.cancel_record_state = "ready"
        with pytest.raises(asyncio.CancelledError):
            await watcher.scan(now_monotonic=4.0)
        work = await watcher.scan(now_monotonic=5.0)
    assert [item.content for item in work] == [b"body"]
    assert sum(item.state == "ready" for item in repository.observations) == 1


@pytest.mark.asyncio
async def test_missing_repository_failures_retry_without_poisoning_state(
    vault_root: Path,
) -> None:
    path = vault_root / "note.md"
    path.write_bytes(b"body")
    repository = FailingObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        await watcher.scan(now_monotonic=3.0)
        path.unlink()
        repository.fail_mark_missing = True
        with pytest.raises(RuntimeError):
            await watcher.scan(now_monotonic=4.0)
        repository.fail_record_state = "missing"
        with pytest.raises(RuntimeError):
            await watcher.scan(now_monotonic=5.0)
        await watcher.scan(now_monotonic=6.0)
        path.write_bytes(b"body")
        await watcher.scan(now_monotonic=7.0)
        work = await watcher.scan(now_monotonic=9.0)
    assert [item.content for item in work] == [b"body"]
    assert repository.missing == [
        ("vault:test", "note.md"),
        ("vault:test", "note.md"),
    ]


@pytest.mark.asyncio
async def test_missing_repository_cancellations_retry_without_poisoning_state(
    vault_root: Path,
) -> None:
    path = vault_root / "note.md"
    path.write_bytes(b"body")
    repository = FailingObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        await watcher.scan(now_monotonic=3.0)
        path.unlink()
        repository.cancel_mark_missing = True
        with pytest.raises(asyncio.CancelledError):
            await watcher.scan(now_monotonic=4.0)
        repository.cancel_record_state = "missing"
        with pytest.raises(asyncio.CancelledError):
            await watcher.scan(now_monotonic=5.0)
        await watcher.scan(now_monotonic=6.0)
        path.write_bytes(b"body")
        await watcher.scan(now_monotonic=7.0)
        work = await watcher.scan(now_monotonic=9.0)
    assert [item.content for item in work] == [b"body"]


@pytest.mark.asyncio
async def test_concurrent_scans_are_serialized_pending_before_ready(
    vault_root: Path,
) -> None:
    (vault_root / "note.md").write_bytes(b"body")
    repository = MemoryObservationRepository()
    first_record_started = asyncio.Event()
    release_first_record = asyncio.Event()
    original_record = repository.record_observation

    async def blocking_record(observation: VaultFileObservation) -> None:
        if not first_record_started.is_set():
            first_record_started.set()
            await release_first_record.wait()
        await original_record(observation)

    repository.record_observation = blocking_record  # type: ignore[method-assign]
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        first_scan = asyncio.create_task(watcher.scan(now_monotonic=1.0))
        await first_record_started.wait()
        second_scan = asyncio.create_task(watcher.scan(now_monotonic=3.0))
        await asyncio.sleep(0)
        assert repository.observations == []
        release_first_record.set()
        assert await first_scan == []
        ready = await second_scan
    assert len(ready) == 1
    assert [item.state for item in repository.observations] == ["pending", "ready"]


@pytest.mark.asyncio
async def test_ctime_change_with_restored_size_and_mtime_restarts_stability(
    vault_root: Path,
) -> None:
    path = vault_root / "note.md"
    path.write_bytes(b"A")
    original_mtime = path.stat().st_mtime_ns
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test", approved_root=approved, repository=repository
        )
        await watcher.scan(now_monotonic=1.0)
        path.write_bytes(b"B")
        os.utime(path, ns=(original_mtime, original_mtime))
        assert await watcher.scan(now_monotonic=3.0) == []
        work = await watcher.scan(now_monotonic=5.0)
    assert [item.content for item in work] == [b"B"]


@pytest.mark.parametrize(
    "invalid", ["../bad.md", "/bad.md", r"a\\bad.md", "a\x00b.md", "a//b.md", "a/./b.md", "./b.md"]
)
def test_constructor_rejects_noncanonical_seed_paths(
    vault_root: Path, invalid: str
) -> None:
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        with pytest.raises(ValueError):
            VaultWatcher(
                vault_id="vault:test",
                approved_root=approved,
                repository=repository,
                known_paths={invalid},
            )
        with pytest.raises(ValueError):
            VaultWatcher(
                vault_id="vault:test",
                approved_root=approved,
                repository=repository,
                known_content_hashes={invalid: None},
            )
    assert repository.observations == []
    assert repository.missing == []


@pytest.mark.asyncio
async def test_incomplete_subtree_listing_does_not_mark_known_paths_missing(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subtree = vault_root / "subtree"
    subtree.mkdir()
    (subtree / "note.md").write_bytes(b"body")
    repository = MemoryObservationRepository()
    real_open = os.open
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test",
            approved_root=approved,
            repository=repository,
            known_paths={"known.md"},
        )

        def denied(path: str | bytes, flags: int, *args: object, **kwargs: object) -> int:
            if path == "subtree" and kwargs.get("dir_fd") == approved._fd:
                raise PermissionError
            return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(os, "open", denied)
        with pytest.raises(VaultSecurityError) as caught:
            await watcher.scan(now_monotonic=1.0)
        assert caught.value.code == "unreadable"
    assert repository.missing == []
    assert repository.observations == []


@pytest.mark.asyncio
async def test_disappearing_subtree_aborts_scan_without_missing_mutation(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subtree = vault_root / "subtree"
    subtree.mkdir()
    (subtree / "note.md").write_bytes(b"body")
    moved = vault_root / "moved"
    repository = MemoryObservationRepository()
    real_open = os.open
    disappeared = False
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test",
            approved_root=approved,
            repository=repository,
            known_paths={"known.md"},
        )

        def disappearing(
            path: str | bytes, flags: int, *args: object, **kwargs: object
        ) -> int:
            nonlocal disappeared
            if (
                path == "subtree"
                and kwargs.get("dir_fd") == approved._fd
                and not disappeared
            ):
                disappeared = True
                subtree.rename(moved)
                raise FileNotFoundError
            return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(os, "open", disappearing)
        with pytest.raises(VaultSecurityError) as caught:
            await watcher.scan(now_monotonic=1.0)
        assert caught.value.code == "unreadable"
    assert repository.missing == []
    assert repository.observations == []


@pytest.mark.asyncio
async def test_oversize_candidate_is_retryable_and_never_emitted(
    vault_root: Path,
) -> None:
    (vault_root / "large.md").write_bytes(b"12345")
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test",
            approved_root=approved,
            repository=repository,
            max_file_bytes=4,
        )
        await watcher.scan(now_monotonic=1.0)
        assert await watcher.scan(now_monotonic=3.0) == []
    assert repository.observations[-1].state == "retry"
    assert repository.observations[-1].error_code == "file_too_large"


@pytest.mark.asyncio
async def test_restart_can_seed_known_paths_for_missing_detection(
    vault_root: Path,
) -> None:
    repository = MemoryObservationRepository()
    with approve_vault_root(vault_root) as approved:
        watcher = VaultWatcher(
            vault_id="vault:test",
            approved_root=approved,
            repository=repository,
            known_paths={"gone.md"},
        )
        await watcher.scan(now_monotonic=1.0)
    assert repository.missing == [("vault:test", "gone.md")]


def test_observation_cannot_mix_parse_and_embedding_state() -> None:
    observation = VaultFileObservation(
        vault_id="vault:test",
        relative_path="note.md",
        state="ready",
        file_kind="markdown",
        protected=False,
        content_hash="a" * 64,
        byte_size=1,
        modified_ns=1,
        parse_state="pending",
        embedding_state="not_submitted",
        observed_at=1.0,
    )
    updated = replace(observation, embedding_state="failed")
    assert updated.parse_state == "pending"
    assert updated.embedding_state == "failed"
