"""v0.8.99 — startup instrumentation is granular and can never fail a launch.

`core_ready` was a single bucket covering the whole of `Supervisor.start_all()`.
A fresh install measured 114,328 ms there with no way to attribute it: database,
API, worker, Next server, or a multi-GB GGUF mmap all looked identical. The
Supervisor now emits a milestone as each dependency comes up.

Two properties matter and are pinned here:

1. the milestone names are stable, ordered, and measured from start_all()'s
   entry — otherwise the numbers cannot be compared across launches;
2. a recorder that raises must NOT propagate. Instrumentation that can break a
   boot is worse than no instrumentation.
"""

from __future__ import annotations

from desktop.launcher import Supervisor

# v0.8.99 — `api_spawned` and `api_ready` are deliberately SEPARATE. The first
# fires when uvicorn's process exists (~200 ms); the second after the /readyz
# wait, which measured 20,208 ms on a warm launch and is the single dominant
# startup cost. A combined mark hid that entirely and blamed the worker.
EXPECTED_STAGES = (
    "database_up",
    "api_spawned",
    "api_ready",
    "worker_up",
    "frontend_up",
    "sidecars_up",
)


def _bare_supervisor(stage_recorder=None) -> Supervisor:
    """A Supervisor instance without running __init__ (which needs a Config)."""
    supervisor = Supervisor.__new__(Supervisor)
    supervisor._stage_recorder = stage_recorder
    supervisor._start_all_began_at = None
    return supervisor


def test_no_recorder_is_a_silent_no_op() -> None:
    supervisor = _bare_supervisor(None)
    supervisor._start_all_began_at = 0.0
    supervisor._record_stage("database_up")  # must not raise


def test_stage_before_start_all_is_ignored() -> None:
    """Without an entry timestamp there is nothing to measure from."""
    recorded: list[tuple[str, int]] = []
    supervisor = _bare_supervisor(lambda s, ms: recorded.append((s, ms)))
    supervisor._record_stage("database_up")
    assert recorded == []


def test_stages_are_recorded_with_a_non_negative_elapsed() -> None:
    import time

    recorded: list[tuple[str, int]] = []
    supervisor = _bare_supervisor(lambda s, ms: recorded.append((s, ms)))
    supervisor._start_all_began_at = time.monotonic()
    for stage in EXPECTED_STAGES:
        supervisor._record_stage(stage)

    assert [name for name, _ in recorded] == list(EXPECTED_STAGES)
    assert all(isinstance(ms, int) and ms >= 0 for _, ms in recorded)
    # Measured from one origin, so elapsed values are non-decreasing.
    elapsed = [ms for _, ms in recorded]
    assert elapsed == sorted(elapsed)


def test_a_raising_recorder_never_breaks_the_launch() -> None:
    """The whole point: a bad sink must not be able to abort start_all()."""
    import time

    def _explode(stage: str, elapsed_ms: int) -> None:
        raise RuntimeError("receipt store is on fire")

    supervisor = _bare_supervisor(_explode)
    supervisor._start_all_began_at = time.monotonic()
    supervisor._record_stage("database_up")  # must swallow


def test_start_all_marks_every_expected_stage_in_source() -> None:
    """Guards against a boundary being dropped during a refactor."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1] / "launcher.py"
    ).read_text(encoding="utf-8")
    for stage in EXPECTED_STAGES:
        assert f'self._record_stage("{stage}")' in source, f"missing mark: {stage}"


def test_app_builds_a_recorder_from_the_receipt_store() -> None:
    from desktop.app import _supervisor_stage_recorder

    class _Ctx:
        startup_receipts = None

    assert _supervisor_stage_recorder(_Ctx()) is None

    recorded: list[tuple[str, int]] = []

    class _Store:
        def record(self, stage, elapsed_ms):
            recorded.append((stage, elapsed_ms))

    class _CtxWithStore:
        startup_receipts = _Store()

    recorder = _supervisor_stage_recorder(_CtxWithStore())
    assert recorder is not None
    recorder("database_up", 1234)
    assert recorded == [("database_up", 1234)]
