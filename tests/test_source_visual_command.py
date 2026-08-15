from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

HASH = "a" * 64
ASSET_HASH = "b" * 64
NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


async def _wait_until(predicate, *, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition did not become true")
        await asyncio.sleep(0.005)


def _authority(source_id: str = "source:one", content: str = HASH):
    return SimpleNamespace(
        source_id=source_id,
        source_updated_at=NOW,
        normalized_source_type="upload",
        asset_url=None,
        controlled_file_path=f"/controlled/{source_id.replace(':', '-')}.pdf",
        source_file_sha256=None,
        full_text_sha256=None,
        content_sha256=content,
        extractor_version="source-visual-v1",
    )


class InMemoryQueueRepository:
    """Small durable-looking fake used to exercise queue boundaries."""

    def __init__(self):
        self.claims = {}
        self.operations = {}
        self.bound = []
        self.released = []
        self.recorded = []
        self._lock = asyncio.Lock()

    async def get_operation(self, source_id, request_id, operation):
        return self.operations.get((source_id, request_id, operation))

    async def acquire_claim(
        self,
        source_id=None,
        content_sha256=None,
        extractor_version=None,
        owner_token=None,
        **kwargs,
    ):
        from deeper_notebook.source_visuals.repository import (
            SourceVisualConflictError,
        )

        identity = (source_id, content_sha256, extractor_version)
        async with self._lock:
            current = self.claims.get(identity)
            if current and current["lease_until"] > NOW and current["owner_token"] != owner_token:
                raise SourceVisualConflictError("CLAIM_HELD")
            claim = SimpleNamespace(
                claim_id=hashlib.sha256(repr(identity).encode()).hexdigest(),
                source_id=source_id,
                content_sha256=content_sha256,
                extractor_version=extractor_version,
                owner_token=owner_token,
                lease_until=NOW + timedelta(seconds=90),
                command_id=current.get("command_id") if current else None,
            )
            self.claims[identity] = claim.__dict__.copy()
            return claim

    async def get_claim(self, source_id, content_sha256, extractor_version):
        identity = (source_id, content_sha256, extractor_version)
        row = self.claims.get(identity)
        return SimpleNamespace(**row) if row else None

    async def bind_command(
        self,
        source_id=None,
        content_sha256=None,
        extractor_version=None,
        owner_token=None,
        command_id=None,
        **kwargs,
    ):
        identity = (source_id, content_sha256, extractor_version)
        row = self.claims[identity]
        assert row["owner_token"] == owner_token
        row["command_id"] = str(command_id)
        self.bound.append((identity, owner_token, str(command_id)))
        return SimpleNamespace(**row)

    async def release_claim(
        self,
        source_id=None,
        content_sha256=None,
        extractor_version=None,
        owner_token=None,
        **kwargs,
    ):
        identity = (source_id, content_sha256, extractor_version)
        row = self.claims.get(identity)
        if row and row["owner_token"] == owner_token:
            self.released.append((identity, owner_token))
            self.claims.pop(identity, None)
        return SimpleNamespace(**(row or {}))

    async def record_operation(
        self,
        source_id=None,
        request_id=None,
        operation=None,
        **kwargs,
    ):
        from deeper_notebook.source_visuals.contracts import (
            SourceVisualOperationReceipt,
        )

        receipt = SourceVisualOperationReceipt(
            operation_id=hashlib.sha256(
                f"{source_id}\0{request_id}\0{operation}".encode()
            ).hexdigest(),
            source_id=source_id,
            request_id=request_id,
            source_updated_at=kwargs["source_updated_at"],
            content_sha256=kwargs["content_sha256"],
            operation=operation,
            command_id=kwargs.get("command_id"),
            outcome=kwargs.get("outcome", "queued"),
            error_code=kwargs.get("error_code"),
            created_at=NOW,
            updated_at=NOW,
        )
        key = (source_id, request_id, operation)
        self.operations[key] = receipt
        self.recorded.append(receipt)
        return receipt


@pytest.fixture
def queue_context(monkeypatch):
    import deeper_notebook.source_visuals.queue as queue

    source = SimpleNamespace(
        id="source:one",
        source_type="upload",
        updated=NOW,
        asset=SimpleNamespace(file_path="/controlled/one.pdf", url=None),
        full_text="unchanged source text",
    )
    repo = InMemoryQueueRepository()
    monkeypatch.setattr(queue, "SourceVisualRepository", lambda: repo)
    monkeypatch.setattr(queue, "Source", SimpleNamespace(get=lambda _id: source))
    monkeypatch.setattr(
        queue,
        "compute_source_visual_authority",
        lambda _source: _authority(_source.id),
    )
    return queue, repo, source


@pytest.mark.asyncio
async def test_two_independent_submitters_converge_on_one_claim_and_command(
    queue_context, monkeypatch
):
    queue, repo, source = queue_context
    submitted = []

    def submit(*args):
        submitted.append(args)
        return "command:visual-one"

    monkeypatch.setattr(queue, "submit_command", submit)

    first, second = await asyncio.gather(
        queue.submit_source_visual("source:one", "request-one", explicit=True),
        queue.submit_source_visual("source:one", "request-two", explicit=True),
    )

    assert len(submitted) == 1
    assert first.command_id == second.command_id == "command:visual-one"
    assert {first.outcome, second.outcome} <= {"queued", "replayed"}
    assert len(repo.bound) == 1
    assert set(repo.operations) == {
        ("source:one", "request-one", "refresh"),
        ("source:one", "request-two", "refresh"),
    }


@pytest.mark.asyncio
async def test_same_request_replays_without_submitting_again(queue_context, monkeypatch):
    queue, repo, _source = queue_context
    monkeypatch.setattr(queue, "submit_command", lambda *_args: pytest.fail("replay submitted"))
    existing = await repo.record_operation(
        "source:one",
        "request-one",
        "refresh",
        source_updated_at=NOW,
        content_sha256=HASH,
        command_id="command:prior",
        outcome="queued",
    )

    result = await queue.submit_source_visual("source:one", "request-one", explicit=True)

    assert result.outcome == "replayed"
    assert result.command_id == existing.command_id


@pytest.mark.asyncio
async def test_replay_after_winner_completion_never_submits_again(queue_context, monkeypatch):
    queue, repo, _source = queue_context
    submitted = []
    monkeypatch.setattr(
        queue,
        "submit_command",
        lambda *_args: submitted.append("submitted") or "command:winner",
    )

    winner = await queue.submit_source_visual("source:one", "request-one", explicit=True)
    identity, owner_token, _command_id = repo.bound[0]
    await repo.release_claim(*identity, owner_token=owner_token)

    replay = await queue.submit_source_visual("source:one", "request-one", explicit=True)

    assert winner.outcome == "queued"
    assert replay.outcome == "replayed"
    assert submitted == ["submitted"]


@pytest.mark.asyncio
async def test_expired_claim_takeover_rejects_a_late_old_submit(queue_context, monkeypatch):
    queue, repo, _source = queue_context
    old_started = threading.Event()
    old_finish = threading.Event()

    def submit(_app, _name, payload):
        if payload["request_id"] == "request-old":
            old_started.set()
            old_finish.wait(timeout=1)
            return "command:old"
        return "command:new"

    monkeypatch.setattr(queue, "submit_command", submit)
    monkeypatch.setattr(queue, "_QUEUE_TIMEOUT_SECONDS", 0.01)
    old = await queue.submit_source_visual("source:one", "request-old", explicit=True)
    assert old.outcome == "queued"
    assert old_started.is_set()

    identity = ("source:one", HASH, "source-visual-v1")
    repo.claims[identity]["lease_until"] = NOW - timedelta(seconds=1)
    new = await queue.submit_source_visual("source:one", "request-new", explicit=True)
    old_finish.set()
    await asyncio.sleep(0.03)

    assert new.command_id == "command:new"
    assert [entry[2] for entry in repo.bound] == ["command:new"]
    assert set(repo.operations) == {
        ("source:one", "request-old", "refresh"),
        ("source:one", "request-new", "refresh"),
    }


@pytest.mark.asyncio
async def test_conflicting_operation_payload_is_a_409_domain_error(queue_context):
    queue, repo, _source = queue_context
    from deeper_notebook.source_visuals.repository import SourceVisualConflictError

    await repo.record_operation(
        "source:one",
        "request-one",
        "refresh",
        source_updated_at=NOW,
        content_sha256="c" * 64,
        command_id="command:other",
        outcome="queued",
    )
    with pytest.raises(SourceVisualConflictError) as exc_info:
        await queue.submit_source_visual("source:one", "request-one", explicit=True)
    assert exc_info.value.code == "REQUEST_CONFLICT"
    assert getattr(exc_info.value, "status_code", 409) == 409


@pytest.mark.asyncio
async def test_submission_exception_retains_claim_and_queued_receipt(
    queue_context, monkeypatch
):
    queue, repo, _source = queue_context

    def fail_submit(*_args):
        raise TimeoutError("private path and source text must not escape")

    monkeypatch.setattr(queue, "submit_command", fail_submit)
    result = await queue.submit_source_visual("source:one", "request-one", explicit=True)

    assert result.outcome == "queued"
    assert result.command_id is None
    assert repo.released == []
    assert repo.recorded[-1].outcome == "queued"


@pytest.mark.asyncio
async def test_timeout_keeps_claim_until_late_submit_is_bound(queue_context, monkeypatch):
    queue, repo, _source = queue_context
    started = threading.Event()
    finish = threading.Event()

    def submit(*_args):
        started.set()
        finish.wait(timeout=1)
        return "command:late"

    monkeypatch.setattr(queue, "submit_command", submit)
    monkeypatch.setattr(queue, "_QUEUE_TIMEOUT_SECONDS", 0.01)
    result = await queue.submit_source_visual("source:one", "request-one", explicit=True)

    assert started.is_set()
    assert result.outcome == "queued"
    assert result.command_id is None
    assert repo.released == []
    assert repo.recorded[-1].outcome == "queued"

    finish.set()
    await _wait_until(lambda: bool(repo.bound))
    assert repo.bound[0][2] == "command:late"


@pytest.mark.asyncio
async def test_cancelling_caller_keeps_late_submit_owned_and_bound(queue_context, monkeypatch):
    queue, repo, _source = queue_context
    started = threading.Event()
    finish = threading.Event()

    def submit(*_args):
        started.set()
        finish.wait(timeout=1)
        return "command:late-cancelled"

    monkeypatch.setattr(queue, "submit_command", submit)
    pending = asyncio.create_task(
        queue.submit_source_visual("source:one", "request-one", explicit=True)
    )
    await _wait_until(started.is_set)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert repo.released == []

    finish.set()
    await _wait_until(lambda: bool(repo.bound))
    assert repo.bound[0][2] == "command:late-cancelled"


@pytest.mark.asyncio
async def test_bind_failure_after_command_creation_keeps_owner_and_queued_receipt(
    queue_context, monkeypatch
):
    queue, repo, _source = queue_context
    from deeper_notebook.source_visuals.repository import SourceVisualRepositoryError

    async def reject_bind(**_kwargs):
        raise SourceVisualRepositoryError("DATABASE_ERROR")

    monkeypatch.setattr(queue, "submit_command", lambda *_args: "command:created")
    monkeypatch.setattr(repo, "bind_command", reject_bind)
    result = await queue.submit_source_visual("source:one", "request-one", explicit=True)

    assert result.outcome == "queued"
    assert result.command_id is None
    assert repo.released == []
    assert repo.recorded[-1].outcome == "queued"


@pytest.mark.asyncio
async def test_submission_uses_legacy_app_strict_payload_and_thread_timeout(
    queue_context, monkeypatch
):
    queue, _repo, _source = queue_context
    captured = {}

    def submit(app, name, payload):
        captured.update(app=app, name=name, payload=payload)
        return "command:strict"

    monkeypatch.setattr(queue, "submit_command", submit)
    result = await queue.submit_source_visual("source:one", "request-one", explicit=True)

    from deeper_notebook.identity import LEGACY_COMMAND_APP

    assert result.command_id == "command:strict"
    assert captured["app"] == LEGACY_COMMAND_APP
    assert captured["name"] == "extract_source_visual"
    assert set(captured["payload"]) == {
        "source_id",
        "request_id",
        "expected_content_sha256",
        "extractor_version",
        "claim_owner_token",
    }
    assert len(captured["payload"]["claim_owner_token"]) == 64


def test_command_input_is_strict_and_owner_token_is_exactly_64_chars():
    from commands.source_visual_commands import ExtractSourceVisualInput

    valid = ExtractSourceVisualInput(
        source_id="source:one",
        request_id="request-one",
        expected_content_sha256=HASH,
        extractor_version="source-visual-v1",
        claim_owner_token="c" * 64,
    )
    assert valid.claim_owner_token == "c" * 64
    with pytest.raises(ValidationError):
        ExtractSourceVisualInput(
            **valid.model_dump(),
            unexpected="private",
        )
    with pytest.raises(ValidationError):
        ExtractSourceVisualInput(
            **{**valid.model_dump(), "claim_owner_token": "short"}
        )


def test_extract_command_is_registered_under_legacy_compatibility_app():
    from surreal_commands import registry

    import commands
    from deeper_notebook.identity import LEGACY_COMMAND_APP

    registered = registry.get_command(LEGACY_COMMAND_APP, "extract_source_visual")
    assert registered is not None
    assert "extract_source_visual_command" in commands.__all__


class InMemoryServiceRepository:
    def __init__(self):
        self.renewed = 0
        self.completed = 0
        self.released = 0

    async def renew_claim(self, *args, **kwargs):
        self.renewed += 1

    async def complete_claim(self, *args, **kwargs):
        self.completed += 1

    async def release_claim(self, *args, **kwargs):
        self.released += 1

    async def publish_ready(self, record, **kwargs):
        return record


class InMemoryServiceStore:
    def __init__(self):
        self.staged = []
        self.published = []
        self.removed = []
        self.cleaned = 0

    def stage(self, source_id, content_sha256, prepared):
        staged = SimpleNamespace(
            source_id=source_id,
            content_sha256=content_sha256,
            asset_sha256=prepared.asset_sha256,
            temp_name="stage-temp",
            byte_size=len(prepared.encoded_bytes),
            width=prepared.width,
            height=prepared.height,
            mime_type=prepared.mime_type,
        )
        self.staged.append(staged)
        return staged

    def publish(self, staged):
        self.published.append(staged)
        return SimpleNamespace(
            asset_relpath="aa/" + HASH + "/" + ASSET_HASH + ".webp",
            asset_sha256=staged.asset_sha256,
            byte_size=staged.byte_size,
            width=staged.width,
            height=staged.height,
            mime_type=staged.mime_type,
        )

    def reconcile_staged_files(self, **_kwargs):
        self.cleaned += 1
        return 0

    def tombstone(self, record):
        self.removed.append(("tombstone", record.asset_relpath))
        return SimpleNamespace(asset_relpath=record.asset_relpath)

    def remove_tombstone(self, tombstone):
        self.removed.append(("remove", tombstone.asset_relpath))


class InMemoryCleanup:
    def __init__(self):
        self.evictions = 0

    async def evict_to_budget(self, **_kwargs):
        self.evictions += 1
        return 0


@pytest.mark.asyncio
async def test_service_success_renews_publishes_completes_and_does_not_mutate_source(
    monkeypatch,
):
    import deeper_notebook.source_visuals.service as service
    from deeper_notebook.source_visuals.contracts import PreparedVisualAsset

    source = SimpleNamespace(
        id="source:one",
        source_type="upload",
        full_text="keep this source text",
        asset=SimpleNamespace(file_path="/controlled/one.pdf"),
        updated=NOW,
        title="Source one",
    )
    repo = InMemoryServiceRepository()
    store = InMemoryServiceStore()
    cleanup = InMemoryCleanup()
    monkeypatch.setattr(service, "Source", SimpleNamespace(get=lambda _id: source))
    monkeypatch.setattr(service, "SourceVisualRepository", lambda: repo)
    monkeypatch.setattr(service, "SourceVisualStore", lambda: store)
    monkeypatch.setattr(service, "SourceVisualCleanup", lambda *_args: cleanup)
    monkeypatch.setattr(service, "compute_source_visual_authority", lambda _s: _authority())
    monkeypatch.setattr(
        service,
        "extract_pdf_candidates",
        lambda _path: [
            SimpleNamespace(
                origin="embedded",
                locator={"page": 1},
                encoded_bytes=b"candidate",
                score=1.0,
                stable_key="pdf:1",
            )
        ],
    )
    monkeypatch.setattr(
        service,
        "select_candidate",
        lambda values: list(values)[0],
    )
    monkeypatch.setattr(
        service,
        "prepare_webp",
        lambda _value: PreparedVisualAsset(
            encoded_bytes=b"webp",
            asset_sha256=ASSET_HASH,
            width=10,
            height=10,
        ),
    )
    monkeypatch.setattr(service, "build_alt_text", lambda *_args: "Source one visual")

    before = source.full_text, source.asset.file_path
    result = await service.SourceVisualService(
        repository=repo, store=store, cleanup=cleanup
    ).execute(
        service.ExtractSourceVisualInput(
            source_id="source:one",
            request_id="request-one",
            expected_content_sha256=HASH,
            extractor_version="source-visual-v1",
            claim_owner_token="c" * 64,
        )
    )

    assert result.outcome == "ready"
    assert result.asset_sha256 == ASSET_HASH
    assert repo.renewed >= 3
    assert repo.completed == 1
    assert cleanup.evictions == 1
    assert (source.full_text, source.asset.file_path) == before


@pytest.mark.asyncio
async def test_service_typed_failure_releases_owner_and_cleans_temp(monkeypatch):
    import deeper_notebook.source_visuals.service as service
    from deeper_notebook.source_visuals.media import SourceVisualMediaError

    source = SimpleNamespace(
        id="source:one",
        source_type="upload",
        full_text="unchanged",
        asset=SimpleNamespace(file_path="/controlled/one.pdf"),
        updated=NOW,
    )
    repo = InMemoryServiceRepository()
    store = InMemoryServiceStore()
    cleanup = InMemoryCleanup()
    monkeypatch.setattr(service, "Source", SimpleNamespace(get=lambda _id: source))
    monkeypatch.setattr(service, "compute_source_visual_authority", lambda _s: _authority())
    monkeypatch.setattr(service, "extract_pdf_candidates", lambda _path: (_ for _ in ()).throw(SourceVisualMediaError("DECODE_FAILED")))

    result = await service.SourceVisualService(
        repository=repo, store=store, cleanup=cleanup
    ).execute(
        service.ExtractSourceVisualInput(
            source_id="source:one",
            request_id="request-one",
            expected_content_sha256=HASH,
            extractor_version="source-visual-v1",
            claim_owner_token="c" * 64,
        )
    )

    assert result.outcome == "failed"
    assert result.error_code == "decode_failed"
    assert repo.released == 1
    assert store.cleaned >= 1


@pytest.mark.asyncio
async def test_service_cancellation_is_bounded_and_releases_owner(monkeypatch):
    import deeper_notebook.source_visuals.service as service

    source = SimpleNamespace(
        id="source:one",
        source_type="upload",
        full_text="unchanged",
        asset=SimpleNamespace(file_path="/controlled/one.pdf"),
        updated=NOW,
    )
    repo = InMemoryServiceRepository()
    store = InMemoryServiceStore()
    monkeypatch.setattr(service, "Source", SimpleNamespace(get=lambda _id: source))
    monkeypatch.setattr(service, "compute_source_visual_authority", lambda _s: _authority())

    def cancelled(_path):
        raise asyncio.CancelledError

    monkeypatch.setattr(service, "extract_pdf_candidates", cancelled)
    result = await service.SourceVisualService(
        repository=repo, store=store, cleanup=InMemoryCleanup()
    ).execute(
        service.ExtractSourceVisualInput(
            source_id="source:one",
            request_id="request-one",
            expected_content_sha256=HASH,
            extractor_version="source-visual-v1",
            claim_owner_token="c" * 64,
        )
    )
    assert result.outcome == "failed"
    assert result.error_code == "cancelled"
    assert repo.released == 1


@pytest.mark.asyncio
async def test_service_per_fingerprint_serialization_and_global_two_job_limit(monkeypatch):
    import deeper_notebook.source_visuals.service as service
    from deeper_notebook.source_visuals.contracts import PreparedVisualAsset

    active = 0
    maximum = 0
    gate = asyncio.Event()
    sources = {
        f"source:{index}": SimpleNamespace(
            id=f"source:{index}",
            source_type="upload",
            full_text=f"text-{index}",
            asset=SimpleNamespace(file_path=f"/controlled/{index}.pdf"),
            updated=NOW,
            title=f"Source {index}",
        )
        for index in range(3)
    }

    class Repo(InMemoryServiceRepository):
        async def renew_claim(self, *args, **kwargs):
            await super().renew_claim(*args, **kwargs)

    def get_source(source_id):
        return sources[source_id]

    async def extract(_path):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await gate.wait()
        active -= 1
        return [SimpleNamespace(origin="embedded", locator={"page": 1}, encoded_bytes=b"x", score=1.0, stable_key="x")]

    monkeypatch.setattr(service, "Source", SimpleNamespace(get=get_source))
    monkeypatch.setattr(service, "compute_source_visual_authority", lambda s: _authority(s.id, HASH))
    monkeypatch.setattr(service, "extract_pdf_candidates", extract)
    monkeypatch.setattr(service, "select_candidate", lambda values: list(values)[0])
    monkeypatch.setattr(service, "prepare_webp", lambda _v: PreparedVisualAsset(encoded_bytes=b"w", asset_sha256=ASSET_HASH, width=1, height=1))
    monkeypatch.setattr(service, "build_alt_text", lambda *_args: "safe")
    service._GLOBAL_MEDIA_SEMAPHORE = asyncio.Semaphore(2)

    repo = Repo()
    store = InMemoryServiceStore()
    cleanup = InMemoryCleanup()
    tasks = [
        asyncio.create_task(
            service.SourceVisualService(repository=repo, store=store, cleanup=cleanup).execute(
                service.ExtractSourceVisualInput(
                    source_id=f"source:{index}",
                    request_id=f"request-{index}",
                    expected_content_sha256=HASH,
                    extractor_version="source-visual-v1",
                    claim_owner_token=(str(index) + "c" * 64)[:64],
                )
            )
        )
        for index in range(3)
    ]
    await asyncio.sleep(0)
    assert maximum <= 2
    gate.set()
    results = await asyncio.gather(*tasks)
    assert all(result.outcome == "ready" for result in results)
    assert maximum == 2


@pytest.mark.asyncio
async def test_service_renews_immediately_before_publication(monkeypatch):
    import deeper_notebook.source_visuals.service as service
    from deeper_notebook.source_visuals.contracts import PreparedVisualAsset

    events = []
    source = SimpleNamespace(
        id="source:one",
        source_type="upload",
        full_text="unchanged",
        asset=SimpleNamespace(file_path="/controlled/one.pdf"),
        updated=NOW,
        title="Source one",
    )

    class Repo(InMemoryServiceRepository):
        async def renew_claim(self, *args, **kwargs):
            events.append("renew")
            await super().renew_claim(*args, **kwargs)

    class Store(InMemoryServiceStore):
        def publish(self, staged):
            events.append("publish")
            return super().publish(staged)

    repo = Repo()
    store = Store()
    monkeypatch.setattr(service, "Source", SimpleNamespace(get=lambda _id: source))
    monkeypatch.setattr(service, "compute_source_visual_authority", lambda _s: _authority())
    monkeypatch.setattr(service, "extract_pdf_candidates", lambda _path: [SimpleNamespace(origin="embedded", locator={"page": 1}, encoded_bytes=b"x", score=1.0, stable_key="x")])
    monkeypatch.setattr(service, "select_candidate", lambda values: list(values)[0])
    monkeypatch.setattr(service, "prepare_webp", lambda _value: PreparedVisualAsset(encoded_bytes=b"w", asset_sha256=ASSET_HASH, width=1, height=1))
    monkeypatch.setattr(service, "build_alt_text", lambda *_args: "safe")

    result = await service.SourceVisualService(
        repository=repo, store=store, cleanup=InMemoryCleanup()
    ).execute(
        service.ExtractSourceVisualInput(
            source_id="source:one",
            request_id="request-one",
            expected_content_sha256=HASH,
            extractor_version="source-visual-v1",
            claim_owner_token="c" * 64,
        )
    )

    assert result.outcome == "ready"
    publish_index = events.index("publish")
    assert events[publish_index - 1] == "renew"


@pytest.mark.asyncio
async def test_service_cancellation_after_publish_removes_exact_uncommitted_asset(
    monkeypatch,
):
    import deeper_notebook.source_visuals.service as service
    from deeper_notebook.source_visuals.contracts import PreparedVisualAsset

    started = threading.Event()
    finish = threading.Event()
    source = SimpleNamespace(
        id="source:one",
        source_type="upload",
        full_text="unchanged",
        asset=SimpleNamespace(file_path="/controlled/one.pdf"),
        updated=NOW,
        title="Source one",
    )

    class Store(InMemoryServiceStore):
        def publish(self, staged):
            started.set()
            finish.wait(timeout=1)
            return super().publish(staged)

    repo = InMemoryServiceRepository()
    store = Store()
    monkeypatch.setattr(service, "Source", SimpleNamespace(get=lambda _id: source))
    monkeypatch.setattr(service, "compute_source_visual_authority", lambda _s: _authority())
    monkeypatch.setattr(service, "extract_pdf_candidates", lambda _path: [SimpleNamespace(origin="embedded", locator={"page": 1}, encoded_bytes=b"x", score=1.0, stable_key="x")])
    monkeypatch.setattr(service, "select_candidate", lambda values: list(values)[0])
    monkeypatch.setattr(service, "prepare_webp", lambda _value: PreparedVisualAsset(encoded_bytes=b"w", asset_sha256=ASSET_HASH, width=1, height=1))
    monkeypatch.setattr(service, "build_alt_text", lambda *_args: "safe")

    pending = asyncio.create_task(
        service.SourceVisualService(repository=repo, store=store, cleanup=InMemoryCleanup()).execute(
            service.ExtractSourceVisualInput(source_id="source:one", request_id="request-one", expected_content_sha256=HASH, extractor_version="source-visual-v1", claim_owner_token="c" * 64)
        )
    )
    await _wait_until(started.is_set)
    pending.cancel()
    threading.Timer(0.02, finish.set).start()
    result = await pending

    assert result.outcome == "failed"
    assert result.error_code == "cancelled"
    assert store.removed == [
        ("tombstone", "aa/" + HASH + "/" + ASSET_HASH + ".webp"),
        ("remove", "aa/" + HASH + "/" + ASSET_HASH + ".webp"),
    ]
    assert repo.released == 1


@pytest.mark.asyncio
async def test_service_lease_loss_before_publish_creates_no_canonical_or_row(monkeypatch):
    import deeper_notebook.source_visuals.service as service
    from deeper_notebook.source_visuals.contracts import PreparedVisualAsset
    from deeper_notebook.source_visuals.repository import SourceVisualConflictError

    source = SimpleNamespace(id="source:one", source_type="upload", full_text="unchanged", asset=SimpleNamespace(file_path="/controlled/one.pdf"), updated=NOW, title="Source one")

    class Repo(InMemoryServiceRepository):
        def __init__(self):
            super().__init__()
            self.ready_rows = []

        async def renew_claim(self, *args, **kwargs):
            await super().renew_claim(*args, **kwargs)
            if self.renewed == 3:
                raise SourceVisualConflictError("LEASE_EXPIRED")

        async def publish_ready(self, record, **kwargs):
            self.ready_rows.append(record)
            return record

    repo = Repo()
    store = InMemoryServiceStore()
    monkeypatch.setattr(service, "Source", SimpleNamespace(get=lambda _id: source))
    monkeypatch.setattr(service, "compute_source_visual_authority", lambda _s: _authority())
    monkeypatch.setattr(service, "extract_pdf_candidates", lambda _path: [SimpleNamespace(origin="embedded", locator={"page": 1}, encoded_bytes=b"x", score=1.0, stable_key="x")])
    monkeypatch.setattr(service, "select_candidate", lambda values: list(values)[0])
    monkeypatch.setattr(service, "prepare_webp", lambda _value: PreparedVisualAsset(encoded_bytes=b"w", asset_sha256=ASSET_HASH, width=1, height=1))
    monkeypatch.setattr(service, "build_alt_text", lambda *_args: "safe")

    with pytest.raises(SourceVisualConflictError):
        await service.SourceVisualService(repository=repo, store=store, cleanup=InMemoryCleanup()).execute(
            service.ExtractSourceVisualInput(source_id="source:one", request_id="request-one", expected_content_sha256=HASH, extractor_version="source-visual-v1", claim_owner_token="c" * 64)
        )
    assert store.published == []
    assert repo.ready_rows == []
    assert repo.released == 0


@pytest.mark.asyncio
async def test_service_publish_ready_lease_failure_removes_asset_and_reraises(
    monkeypatch,
):
    import deeper_notebook.source_visuals.service as service
    from deeper_notebook.source_visuals.contracts import PreparedVisualAsset
    from deeper_notebook.source_visuals.repository import SourceVisualConflictError

    source = SimpleNamespace(id="source:one", source_type="upload", full_text="unchanged", asset=SimpleNamespace(file_path="/controlled/one.pdf"), updated=NOW, title="Source one")

    class Repo(InMemoryServiceRepository):
        def __init__(self):
            super().__init__()
            self.ready_rows = []

        async def publish_ready(self, record, **kwargs):
            raise SourceVisualConflictError("LEASE_EXPIRED")

    repo = Repo()
    store = InMemoryServiceStore()
    monkeypatch.setattr(service, "Source", SimpleNamespace(get=lambda _id: source))
    monkeypatch.setattr(service, "compute_source_visual_authority", lambda _s: _authority())
    monkeypatch.setattr(service, "extract_pdf_candidates", lambda _path: [SimpleNamespace(origin="embedded", locator={"page": 1}, encoded_bytes=b"x", score=1.0, stable_key="x")])
    monkeypatch.setattr(service, "select_candidate", lambda values: list(values)[0])
    monkeypatch.setattr(service, "prepare_webp", lambda _value: PreparedVisualAsset(encoded_bytes=b"w", asset_sha256=ASSET_HASH, width=1, height=1))
    monkeypatch.setattr(service, "build_alt_text", lambda *_args: "safe")

    with pytest.raises(SourceVisualConflictError):
        await service.SourceVisualService(repository=repo, store=store, cleanup=InMemoryCleanup()).execute(
            service.ExtractSourceVisualInput(source_id="source:one", request_id="request-one", expected_content_sha256=HASH, extractor_version="source-visual-v1", claim_owner_token="c" * 64)
        )
    assert store.removed == [
        ("tombstone", "aa/" + HASH + "/" + ASSET_HASH + ".webp"),
        ("remove", "aa/" + HASH + "/" + ASSET_HASH + ".webp"),
    ]
    assert repo.ready_rows == []
    assert repo.released == 0


@pytest.mark.asyncio
async def test_command_wrapper_reraises_transient_and_returns_terminal_receipt(
    monkeypatch,
):
    import commands.source_visual_commands as command_module
    from deeper_notebook.source_visuals.media import SourceVisualMediaError
    from deeper_notebook.source_visuals.repository import SourceVisualRepositoryError

    input_data = command_module.ExtractSourceVisualInput(
        source_id="source:one",
        request_id="request-one",
        expected_content_sha256=HASH,
        extractor_version="source-visual-v1",
        claim_owner_token="c" * 64,
    )

    class TransientService:
        async def execute(self, _input):
            raise SourceVisualRepositoryError("DATABASE_ERROR")

    monkeypatch.setattr(command_module, "SourceVisualService", TransientService)
    with pytest.raises(SourceVisualRepositoryError):
        await command_module.extract_source_visual_command(input_data)

    class TerminalService:
        async def execute(self, _input):
            raise SourceVisualMediaError("DECODE_FAILED")

    monkeypatch.setattr(command_module, "SourceVisualService", TerminalService)
    result = await command_module.extract_source_visual_command(input_data)
    assert result.outcome == "failed"
    assert result.error_code == "decode_failed"
