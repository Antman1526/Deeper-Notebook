"""Atomic read-only protection for the complete notebook database cascade."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from surrealdb import RecordID, Surreal

from deeper_notebook.exceptions import DatabaseOperationError


class _FakeNote:
    def __init__(
        self,
        note_id: str,
        *,
        canonical_external: bool | None = None,
        external_state: str | None = None,
    ) -> None:
        self.id = note_id
        self.canonical_external = canonical_external
        self.external_state = external_state
        self.delete_called = False

    async def delete(self) -> bool:
        self.delete_called = True
        raise AssertionError("Notebook cascade must not call Note.delete()")


class _FakeSource:
    def __init__(self, source_id: str) -> None:
        self.id = source_id
        self.cleanup_calls = 0

    async def _cleanup_external_resources(self) -> None:
        self.cleanup_calls += 1


@pytest.fixture()
def make_notebook(monkeypatch):
    from deeper_notebook.domain import notebook as notebook_module

    def factory(
        notes: list[_FakeNote],
        *,
        transaction_result: Any = None,
        transaction_error: Exception | None = None,
        sources: list[Any] | None = None,
    ):
        calls: list[tuple[str, dict[str, Any]]] = []
        sources = sources or []

        async def fake_repo_query(
            query: str,
            params: dict[str, Any] | None = None,
        ) -> Any:
            calls.append((query, params or {}))
            if transaction_error is not None:
                raise transaction_error
            return transaction_result or [
                {
                    "deleted_notes": len(notes),
                    "deleted_sources": 0,
                    "unlinked_sources": 0,
                    "deleted_chat_session_ids": [],
                    "exclusive_source_ids": [],
                }
            ]

        async def get_notes(_self):
            return notes

        async def get_sources(_self):
            return sources

        monkeypatch.setattr(notebook_module, "repo_query", fake_repo_query)
        monkeypatch.setattr(notebook_module.Notebook, "get_notes", get_notes)
        monkeypatch.setattr(notebook_module.Notebook, "get_sources", get_sources)
        monkeypatch.setattr(notebook_module, "ensure_record_id", lambda value: value)

        notebook = notebook_module.Notebook(
            id="notebook:test-cascade",
            name="Cascade",
            description="Atomic cascade",
        )
        return notebook, calls

    return factory


def _transaction(calls: list[tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any]]:
    assert len(calls) == 1, f"expected one atomic database call, got {len(calls)}"
    query, params = calls[0]
    assert "BEGIN TRANSACTION" in query
    assert "COMMIT TRANSACTION" in query
    assert query.index("RETURN $result") < query.index("COMMIT TRANSACTION")
    return query, params


def _assert_guards_precede_destructive_sql(query: str) -> None:
    first_delete = query.index("DELETE ")
    assert query.index("notebook_note_set_changed") < first_delete
    assert query.index("external_note_read_only") < first_delete
    assert query.index("THROW") < first_delete
    assert first_delete < query.index("COMMIT TRANSACTION")


def test_success_uses_one_transaction_and_never_calls_per_note_delete(make_notebook):
    notes = [_FakeNote(f"note:{index}") for index in range(5)]
    notebook, calls = make_notebook(
        notes,
        transaction_result=[
            {
                "deleted_notes": 5,
                "deleted_sources": 1,
                "unlinked_sources": 2,
                "deleted_chat_session_ids": ["chat_session:a"],
                "exclusive_source_ids": ["source:exclusive"],
            }
        ],
    )

    result = asyncio.run(notebook.delete(delete_exclusive_sources=True))

    query, params = _transaction(calls)
    _assert_guards_precede_destructive_sql(query)
    for fragment in (
        "DELETE note WHERE id IN $current_note_ids",
        "DELETE artifact WHERE in IN $current_note_ids",
        "DELETE reference WHERE out = $notebook_id",
        "DELETE chat_session WHERE id IN $chat_session_ids",
        "DELETE $notebook_id",
    ):
        assert fragment in query
    assert params["expected_note_count"] == 5
    assert params["expected_note_ids"] == [note.id for note in notes]
    assert result["deleted_notes"] == 5
    assert result["deleted_sources"] == 1
    assert result["unlinked_sources"] == 2
    assert result["deleted_chat_session_ids"] == ["chat_session:a"]
    assert all(note.delete_called is False for note in notes)


@pytest.mark.parametrize(
    "notes",
    [
        [
            _FakeNote(
                f"note:external-{index}",
                canonical_external=False,
                external_state=None,
            )
            for index in range(30)
        ],
        [
            _FakeNote("note:normal"),
            _FakeNote(
                "note:external",
                canonical_external=False,
                external_state=None,
            ),
        ],
    ],
)
def test_persisted_external_note_rejection_ignores_hydrated_flags(
    make_notebook,
    notes,
):
    notebook, calls = make_notebook(
        notes,
        transaction_error=RuntimeError("external_note_read_only"),
    )

    from deeper_notebook.domain.notebook import ExternalNoteReadOnlyError

    with pytest.raises(ExternalNoteReadOnlyError, match="external_note_read_only"):
        asyncio.run(notebook.delete())

    query, params = _transaction(calls)
    _assert_guards_precede_destructive_sql(query)
    assert "canonical_external" in query
    assert "external_state" in query
    assert params["expected_note_count"] == len(notes)
    assert all(note.delete_called is False for note in notes)


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("notebook_note_set_changed"),
        RuntimeError("simulated transaction failure"),
    ],
)
def test_count_mismatch_or_transaction_failure_has_no_followup_destructive_call(
    make_notebook,
    error,
):
    notes = [_FakeNote("note:a"), _FakeNote("note:b")]
    notebook, calls = make_notebook(notes, transaction_error=error)

    with pytest.raises(DatabaseOperationError):
        asyncio.run(notebook.delete())

    query, _params = _transaction(calls)
    _assert_guards_precede_destructive_sql(query)
    assert "CANCEL TRANSACTION" not in query
    assert all(note.delete_called is False for note in notes)


def test_empty_notebook_still_commits_single_transaction(make_notebook):
    notebook, calls = make_notebook([])

    result = asyncio.run(notebook.delete())

    query, params = _transaction(calls)
    _assert_guards_precede_destructive_sql(query)
    assert params["expected_note_count"] == 0
    assert params["expected_note_ids"] == []
    assert result["deleted_notes"] == 0


def test_source_cleanup_runs_only_after_successful_commit(make_notebook):
    source = _FakeSource("source:exclusive")
    notebook, calls = make_notebook(
        [],
        sources=[source],
        transaction_result=[
            {
                "deleted_notes": 0,
                "deleted_sources": 1,
                "unlinked_sources": 0,
                "deleted_chat_session_ids": [],
                "exclusive_source_ids": ["source:exclusive"],
            }
        ],
    )

    asyncio.run(notebook.delete(delete_exclusive_sources=True))

    _transaction(calls)
    assert source.cleanup_calls == 1


def test_transaction_failure_never_runs_external_source_cleanup(make_notebook):
    source = _FakeSource("source:exclusive")
    notebook, calls = make_notebook(
        [],
        sources=[source],
        transaction_error=RuntimeError("simulated transaction failure"),
    )

    with pytest.raises(DatabaseOperationError):
        asyncio.run(notebook.delete(delete_exclusive_sources=True))

    _transaction(calls)
    assert source.cleanup_calls == 0


def _embedded_params(params: dict[str, Any]) -> dict[str, Any]:
    converted = dict(params)
    converted["notebook_id"] = RecordID("notebook", "test-cascade")
    converted["expected_note_ids"] = [
        RecordID("note", str(value).split(":", 1)[1])
        for value in params["expected_note_ids"]
    ]
    return converted


def test_embedded_surreal_success_returns_result_and_commits(make_notebook):
    notebook, calls = make_notebook(
        [_FakeNote("note:a")],
        transaction_result=[
            {
                "deleted_notes": 1,
                "deleted_sources": 1,
                "unlinked_sources": 0,
                "deleted_chat_session_ids": ["chat_session:a"],
                "exclusive_source_ids": ["source:exclusive"],
            }
        ],
    )
    asyncio.run(notebook.delete(delete_exclusive_sources=True))
    query, params = _transaction(calls)

    with Surreal("mem://") as db:
        db.use("cascade", "success")
        db.query(
            """
            CREATE notebook:`test-cascade`;
            CREATE notebook:other;
            CREATE note:a SET canonical_external = false;
            RELATE note:a->artifact->notebook:`test-cascade`;
            CREATE source:exclusive;
            RELATE source:exclusive->reference->notebook:`test-cascade`;
            CREATE source:shared;
            RELATE source:shared->reference->notebook:`test-cascade`;
            RELATE source:shared->reference->notebook:other;
            CREATE source_embedding:a SET source = source:exclusive;
            CREATE source_insight:a SET source = source:exclusive;
            CREATE chat_session:a;
            RELATE chat_session:a->refers_to->notebook:`test-cascade`;
            """
        )

        result = db.query(query, _embedded_params(params))

        assert isinstance(result, dict), result
        assert result["deleted_notes"] == 1
        assert result["deleted_sources"] == 1
        assert result["unlinked_sources"] == 1
        assert result["deleted_chat_session_ids"] == [RecordID("chat_session", "a")]
        assert db.query("SELECT VALUE id FROM notebook") == [
            RecordID("notebook", "other")
        ]
        assert db.query("SELECT VALUE id FROM note") == []
        assert db.query("SELECT VALUE id FROM artifact") == []
        assert db.query("SELECT VALUE id FROM source") == [RecordID("source", "shared")]
        assert db.query("SELECT VALUE id FROM source_embedding") == []
        assert db.query("SELECT VALUE id FROM source_insight") == []
        assert len(db.query("SELECT VALUE id FROM reference")) == 1
        assert db.query("SELECT VALUE id FROM chat_session") == []
        assert db.query("SELECT VALUE id FROM refers_to") == []


@pytest.mark.parametrize(
    ("external", "extra_note", "expected_error"),
    [
        (True, False, "external_note_read_only"),
        (False, True, "failed transaction"),
    ],
)
def test_embedded_surreal_guard_throw_rolls_back_every_delete(
    make_notebook,
    external,
    extra_note,
    expected_error,
):
    notebook, calls = make_notebook([_FakeNote("note:a")])
    asyncio.run(notebook.delete())
    query, params = _transaction(calls)

    with Surreal("mem://") as db:
        db.use("cascade", f"rollback-{external}-{extra_note}")
        db.query(
            """
            CREATE notebook:`test-cascade`;
            CREATE note:a SET canonical_external = $external;
            RELATE note:a->artifact->notebook:`test-cascade`;
            """,
            {"external": external},
        )
        if extra_note:
            db.query(
                """
                CREATE note:b SET canonical_external = false;
                RELATE note:b->artifact->notebook:`test-cascade`;
                """
            )

        result = db.query(query, _embedded_params(params))

        assert expected_error in result
        assert len(db.query("SELECT VALUE id FROM notebook")) == 1
        assert len(db.query("SELECT VALUE id FROM note")) == (2 if extra_note else 1)
        assert len(db.query("SELECT VALUE id FROM artifact")) == (
            2 if extra_note else 1
        )
