from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from deeper_notebook.vault.security import approve_vault_root
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
