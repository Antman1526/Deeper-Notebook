"""v0.7.133 — four deferred-item improvements landed in a single batch:

  * #16  Note.save() — registry introspection replaces string-match exception
  * #2   Memory recall — DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC outer wall
  * #11  Source.delete() — race-window post-sweep
  * #4   Notebook.delete() — legacy bulk-SQL threshold (now retired)

All tests are hermetic — no SurrealDB, no surreal-commands worker.
DB-touching tests mock repo_query at the boundary.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------- #
# #16 — _is_command_registered + Note.save behavior
# ---------------------------------------------------------------------- #


class TestIsCommandRegistered:
    """v0.7.133 — Replaces the v0.7.129 string-match `if "Command not
    found" in str(exc)` with a direct registry.get_command_by_id()
    lookup. These tests pin the helper's edge cases."""

    def test_registered_command_returns_true(self):
        from deeper_notebook.domain import notebook as nb_mod

        fake_registry = MagicMock()
        fake_registry.get_command_by_id.return_value = MagicMock()  # truthy
        with patch.dict(
            "sys.modules",
            {"surreal_commands": MagicMock(registry=fake_registry)},
        ):
            assert nb_mod._is_command_registered("deeper_notebook.embed_note") is True

    def test_unregistered_command_returns_false(self):
        from deeper_notebook.domain import notebook as nb_mod

        fake_registry = MagicMock()
        fake_registry.get_command_by_id.return_value = None
        with patch.dict(
            "sys.modules",
            {"surreal_commands": MagicMock(registry=fake_registry)},
        ):
            assert nb_mod._is_command_registered("deeper_notebook.embed_note") is False

    def test_registry_import_failure_returns_false(self):
        """Defensive: if the registry attribute disappears in a future
        surreal_commands version, fail-closed (treat as not registered,
        skip the submit). Better than crashing."""
        from deeper_notebook.domain import notebook as nb_mod

        class _Borked:
            registry = property(lambda self: (_ for _ in ()).throw(AttributeError))

        with patch.dict("sys.modules", {"surreal_commands": _Borked()}):
            assert nb_mod._is_command_registered("any.command") is False


class TestNoteSaveUsesRegistry:
    """v0.7.133 — Note.save() now checks the registry before calling
    submit_command. Confirms the cleaner control flow."""

    @pytest.mark.asyncio
    async def test_save_skips_submit_when_command_not_registered(self):
        from deeper_notebook.domain.notebook import Note

        note = Note(title="N", content="content", note_type="human")

        # Mock super().save() to set id
        async def _fake_super_save(self):
            self.id = "note:fake"

        with (
            patch("deeper_notebook.domain.notebook.ObjectModel.save", _fake_super_save),
            patch(
                "deeper_notebook.domain.notebook._is_command_registered",
                return_value=False,
            ),
            patch(
                "deeper_notebook.domain.notebook.submit_command",
            ) as submit_mock,
        ):
            result = await note.save()
            assert result is None
            # submit_command must NOT have been called — the pre-check
            # short-circuits cleanly.
            submit_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_calls_submit_when_registered(self):
        from deeper_notebook.domain.notebook import Note

        note = Note(title="N", content="content", note_type="human")

        async def _fake_super_save(self):
            self.id = "note:fake"

        with (
            patch("deeper_notebook.domain.notebook.ObjectModel.save", _fake_super_save),
            patch(
                "deeper_notebook.domain.notebook._is_command_registered",
                return_value=True,
            ),
            patch(
                "deeper_notebook.domain.notebook.submit_command",
                return_value="command:xyz",
            ) as submit_mock,
        ):
            result = await note.save()
            assert result == "command:xyz"
            submit_mock.assert_called_once()


# ---------------------------------------------------------------------- #
# #2 — Memory recall outer budget
# ---------------------------------------------------------------------- #


class TestMemoryRecallBudget:
    """v0.7.133 — DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC wraps the whole
    recall_memory orchestration in a single asyncio.wait_for."""

    def test_default_budget_when_env_unset(self, monkeypatch):
        from deeper_notebook.utils.memory_recall import _recall_budget_sec

        monkeypatch.delenv("DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC", raising=False)
        assert _recall_budget_sec() == 12.0

    def test_env_override_parsed(self, monkeypatch):
        from deeper_notebook.utils.memory_recall import _recall_budget_sec

        monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC", "30")
        assert _recall_budget_sec() == 30.0

    def test_garbage_env_falls_back_to_default(self, monkeypatch):
        from deeper_notebook.utils.memory_recall import _recall_budget_sec

        monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC", "not-a-float")
        assert _recall_budget_sec() == 12.0

    def test_zero_or_negative_falls_back_to_default(self, monkeypatch):
        from deeper_notebook.utils.memory_recall import _recall_budget_sec

        for v in ("0", "-5", "-0.1"):
            monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC", v)
            assert _recall_budget_sec() == 12.0, f"Expected fallback for {v!r}"

    @pytest.mark.asyncio
    async def test_recall_within_budget_returns_normally(self, monkeypatch):
        from deeper_notebook.utils import memory_recall as mr_mod

        monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC", "5")

        async def fast_inner(query):
            return {"facts": [{"text": "ok"}], "preferences": []}

        with patch(
            "deeper_notebook.utils.memory_recall._recall_memory_inner",
            new=fast_inner,
        ):
            result = await mr_mod.recall_memory("anything")
            assert result == {"facts": [{"text": "ok"}], "preferences": []}

    @pytest.mark.asyncio
    async def test_recall_exceeding_budget_returns_empty(self, monkeypatch):
        """When the inner orchestration takes longer than the budget,
        the outer wait_for fires and we return an empty memory dict."""
        from deeper_notebook.utils import memory_recall as mr_mod

        monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC", "0.2")

        async def slow_inner(query):
            await asyncio.sleep(5)
            return {"facts": [{"text": "would have been here"}]}

        with patch(
            "deeper_notebook.utils.memory_recall._recall_memory_inner",
            new=slow_inner,
        ):
            result = await mr_mod.recall_memory("anything")
            # v0.8.49 — empty dict now carries the `episodes` key too so
            # the recall-dict shape is stable across all return paths.
            assert result == {"facts": [], "preferences": [], "episodes": []}


# ---------------------------------------------------------------------- #
# #11 — Source.delete race-window post-sweep
# ---------------------------------------------------------------------- #


class TestSourceDeletePostSweep:
    """v0.7.133 — After super().delete() the source row is gone, but
    the worker may have written fresh source_embedding rows between
    our cancel and that point. The new post-sweep DELETEs those by
    source_id match."""

    @pytest.mark.asyncio
    async def test_post_sweep_runs_after_super_delete(self):
        from deeper_notebook.domain.notebook import (
            Source,
            _wait_for_source_search_index_maintenance,
        )

        src = Source(title="t", full_text="x")
        src.id = "source:fake"

        # Track the order of repo_query calls so we can prove the
        # post-sweep happens AFTER super().delete().
        call_log = []

        async def fake_repo_query(query, vars=None):
            call_log.append(query)
            return []

        async def fake_super_delete(self):
            call_log.append("__SUPER_DELETE__")
            return True

        with (
            patch(
                "deeper_notebook.domain.notebook.repo_query",
                new=fake_repo_query,
            ),
            patch(
                "deeper_notebook.domain.notebook._mark_source_search_rebuild_pending",
                new=AsyncMock(return_value="test-marker"),
            ),
            patch(
                "deeper_notebook.domain.base.ObjectModel.delete",
                new=fake_super_delete,
            ),
            patch(
                "deeper_notebook.config.UPLOADS_FOLDER",
                "/tmp/fake-uploads",
            ),
        ):
            await src.delete()
            await _wait_for_source_search_index_maintenance()

        # Locate the position of __SUPER_DELETE__ in the call log.
        super_idx = call_log.index("__SUPER_DELETE__")

        # The pre-sweep should run BEFORE super delete; the post-sweep
        # AFTER. Pre-sweep includes 3 queries (embedding, insight,
        # reference); post-sweep includes 2 (embedding, insight).
        pre = call_log[:super_idx]
        post = call_log[super_idx + 1 :]

        # Pre-sweep: source_embedding + source_insight + reference
        assert any("source_embedding" in q for q in pre)
        assert any("source_insight" in q for q in pre)
        assert any("reference" in q for q in pre)

        # Post-sweep: source_embedding + source_insight (no reference,
        # see comment in delete()).
        assert any("source_embedding" in q for q in post)
        assert any("source_insight" in q for q in post)
        assert not any("reference" in q for q in post), (
            "Post-sweep should NOT re-delete reference edges"
        )

    @pytest.mark.asyncio
    async def test_post_sweep_failure_does_not_break_delete(self):
        """If the post-sweep query raises (transient DB hiccup), the
        delete still returns successfully — the orphan rows are present
        but unreachable since the source row is already gone."""
        from deeper_notebook.domain.notebook import (
            Source,
            _wait_for_source_search_index_maintenance,
        )

        src = Source(title="t", full_text="x")
        src.id = "source:fake"

        call_count = [0]

        async def flaky_repo_query(query, vars=None):
            call_count[0] += 1
            # Pre-sweep succeeds; post-sweep raises.
            if call_count[0] > 3:
                raise RuntimeError("transient DB error")
            return []

        async def fake_super_delete(self):
            return True

        with (
            patch(
                "deeper_notebook.domain.notebook.repo_query",
                new=flaky_repo_query,
            ),
            patch(
                "deeper_notebook.domain.notebook._mark_source_search_rebuild_pending",
                new=AsyncMock(return_value="test-marker"),
            ),
            patch(
                "deeper_notebook.domain.base.ObjectModel.delete",
                new=fake_super_delete,
            ),
            patch(
                "deeper_notebook.config.UPLOADS_FOLDER",
                "/tmp/fake-uploads",
            ),
        ):
            # Must not raise.
            result = await src.delete()
            assert result is True
            await _wait_for_source_search_index_maintenance()


# ---------------------------------------------------------------------- #
# #4 — Notebook delete atomic cascade supersedes partial bulk paths
# ---------------------------------------------------------------------- #


class TestNotebookBulkDelete:
    """The old partial/best-effort bulk path must stay retired."""

    def test_threshold_and_partial_bulk_helpers_are_absent(self):
        from deeper_notebook.domain import notebook as notebook_module

        assert not hasattr(notebook_module, "_notebook_delete_bulk_threshold")
        assert not hasattr(notebook_module.Notebook, "_bulk_delete_notes")

    def test_notebook_delete_uses_one_transaction_instead_of_gather(self):
        import inspect

        from deeper_notebook.domain.notebook import Notebook

        source = inspect.getsource(Notebook.delete)
        assert "BEGIN TRANSACTION" in source
        assert "COMMIT TRANSACTION" in source
        assert "asyncio.gather" not in source
