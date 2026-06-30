import asyncio
import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional, Tuple, Union

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator
from surreal_commands import submit_command

# v0.7.133 — Notebook delete bulk-SQL threshold (Area for Review #4).
_DEFAULT_NOTEBOOK_DELETE_BULK_THRESHOLD = 25


def _notebook_delete_bulk_threshold() -> int:
    """Return the note-count threshold above which `Notebook.delete()`
    switches from per-note gather to bulk-SQL. Configurable via
    `ONP_NOTEBOOK_DELETE_BULK_THRESHOLD`. Defaults to 25.

    Rationale for the default: with ONP_DB_POOL_SIZE=4 (default), 25
    concurrent per-note DELETEs serialize into ~6-7 round-trip batches.
    Bulk does it in 3 statements total, so the breakeven is somewhere
    in the 10-25 range depending on pool latency. 25 is the safer
    default — bigger speedup with no observability loss on small
    notebooks where the per-note log lines actually help.

    Set to 1 (or 0) to force bulk on every delete; set to a huge
    number to force the per-note path. Useful for debugging.
    """
    raw = (os.environ.get("ONP_NOTEBOOK_DELETE_BULK_THRESHOLD") or "").strip()
    if not raw:
        return _DEFAULT_NOTEBOOK_DELETE_BULK_THRESHOLD
    try:
        val = int(raw)
        if val < 0:
            logger.warning(
                "ONP_NOTEBOOK_DELETE_BULK_THRESHOLD={} negative; using default {}",
                raw, _DEFAULT_NOTEBOOK_DELETE_BULK_THRESHOLD,
            )
            return _DEFAULT_NOTEBOOK_DELETE_BULK_THRESHOLD
        return val
    except ValueError:
        logger.warning(
            "ONP_NOTEBOOK_DELETE_BULK_THRESHOLD={!r} not an int; using "
            "default {}", raw, _DEFAULT_NOTEBOOK_DELETE_BULK_THRESHOLD,
        )
        return _DEFAULT_NOTEBOOK_DELETE_BULK_THRESHOLD


def _is_command_registered(command_id: str) -> bool:
    """v0.7.133 — Check whether a surreal-commands command is in the
    process registry. Replaces the previous string-match against the
    `ValueError: Command not found` message that submit_command()
    raises when the registry is empty.

    Returns True if the command is registered (submit will succeed at
    the registry-check stage), False otherwise. Lazy-import the
    registry so an absent surreal_commands install doesn't break
    module load. Wrapped in a try/except because the registry API
    surface could change between minor versions and we want this
    pre-check to fail-closed (treat as "not registered, log + skip")
    rather than break Note.save.

    Why a pre-check beats catching the ValueError after the fact:
      - No string-content brittleness — surreal_commands could rename
        the exception message and this still works.
      - We never have to distinguish "registry miss" ValueError from
        a real argument-validation ValueError inside the command
        handler. The pre-check answers exactly the question we care
        about.
      - Faster: skips the cross-process DB roundtrip submit_command
        does before discovering the registry is empty.
    """
    try:
        from surreal_commands import registry
        return registry.get_command_by_id(command_id) is not None
    except Exception:
        # Registry API change, attribute missing, or surreal_commands
        # absent. Fail-closed.
        return False
from surrealdb import RecordID

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.base import ObjectModel
from open_notebook.exceptions import DatabaseOperationError, InvalidInputError


class Notebook(ObjectModel):
    table_name: ClassVar[str] = "notebook"
    name: str
    description: str
    archived: Optional[bool] = False

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise InvalidInputError("Notebook name cannot be empty")
        return v

    async def get_sources(self) -> list["Source"]:
        try:
            srcs = await repo_query(
                """
                select * omit source.full_text from (
                select in as source from reference where out=$id
                fetch source
            ) order by source.updated desc
            """,
                {"id": ensure_record_id(self.id)},
            )
            return [Source(**src["source"]) for src in srcs] if srcs else []
        except Exception as e:
            logger.error(f"Error fetching sources for notebook {self.id}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(e)

    async def get_notes(self) -> list["Note"]:
        try:
            srcs = await repo_query(
                """
            select * omit note.content, note.embedding from (
                select in as note from artifact where out=$id
                fetch note
            ) order by note.updated desc
            """,
                {"id": ensure_record_id(self.id)},
            )
            return [Note(**src["note"]) for src in srcs] if srcs else []
        except Exception as e:
            logger.error(f"Error fetching notes for notebook {self.id}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(e)

    async def get_graph(self) -> dict[str, Any]:
        """v0.8.83 — mind-map graph (improvement roadmap, Batch 3).

        Returns the notebook as a hub node with its sources and notes as
        connected nodes, grounded in the existing ``reference``
        (source→notebook) and ``artifact`` (note→notebook) edges — no schema
        change. Node ids are the record ids so the frontend can deep-link to
        each item; labels are trimmed to keep the payload small.
        """
        sources = await self.get_sources()
        notes = await self.get_notes()

        def _label(text: Optional[str], fallback: str) -> str:
            cleaned = (text or "").strip() or fallback
            return cleaned if len(cleaned) <= 80 else cleaned[:79] + "…"

        nodes: list[dict[str, Any]] = [
            {"id": str(self.id), "type": "notebook", "label": _label(self.name, "Notebook")}
        ]
        edges: list[dict[str, Any]] = []
        for s in sources:
            nodes.append(
                {"id": str(s.id), "type": "source", "label": _label(s.title, "Untitled source")}
            )
            edges.append({"source": str(self.id), "target": str(s.id), "kind": "reference"})
        for n in notes:
            nodes.append(
                {"id": str(n.id), "type": "note", "label": _label(n.title, "Untitled note")}
            )
            edges.append({"source": str(self.id), "target": str(n.id), "kind": "artifact"})
        return {"nodes": nodes, "edges": edges}

    async def get_chat_sessions(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list["ChatSession"]:
        """Fetch all chat sessions for this notebook, newest-first.

        v0.7.169 — Optional `limit` / `offset` pagination. Previously
        this returned EVERY chat session attached to the notebook with
        no bound — a power user with hundreds of long-running chats
        paid for the full table fan-out PLUS the per-session LangGraph
        checkpoint read (v0.7.161 made those concurrent, but the
        underlying session list itself was still unbounded). Now
        the router can pass `limit=` to cap the response and keep the
        right-rail Chat list snappy.

        Defaults stay None for backward compatibility — callers that
        don't ask for pagination keep the pre-v0.7.169 unbounded
        behavior.
        """
        try:
            # v0.7.169 — Inject `LIMIT $limit START $offset` only when
            # the caller asked. Validate the inputs aggressively
            # (positive int / non-negative int respectively) BEFORE
            # interpolating into the query — SurrealQL accepts integer
            # literals via direct interpolation, but it doesn't sanitize
            # them the way a SQL driver would. Mirror the v0.7.159
            # `ObjectModel.get_all` validation pattern.
            if limit is not None:
                if not isinstance(limit, int) or limit <= 0 or isinstance(limit, bool):
                    raise InvalidInputError(
                        f"limit must be a positive int, got {limit!r}"
                    )
            if offset is not None:
                if not isinstance(offset, int) or offset < 0 or isinstance(offset, bool):
                    raise InvalidInputError(
                        f"offset must be a non-negative int, got {offset!r}"
                    )
            tail = ""
            if limit is not None:
                tail = f" LIMIT {limit}"
            if offset is not None:
                tail += f" START {offset}"
            srcs = await repo_query(
                f"""
                select * from (
                    select
                    <- chat_session as chat_session
                    from refers_to
                    where out=$id
                    fetch chat_session
                )
                order by chat_session.updated desc{tail}
            """,
                {"id": ensure_record_id(self.id)},
            )
            return (
                [ChatSession(**src["chat_session"][0]) for src in srcs] if srcs else []
            )
        except InvalidInputError:
            # v0.7.169 — Let typed input errors propagate to the
            # global exception handler (mapped to HTTP 400) rather
            # than getting clobbered to 500 by the generic except below.
            raise
        except Exception as e:
            logger.error(
                f"Error fetching chat sessions for notebook {self.id}: {str(e)}"
            )
            logger.exception(e)
            raise DatabaseOperationError(e)

    async def get_delete_preview(self) -> dict[str, Any]:
        """
        Get counts of items that would be affected by deleting this notebook.

        Returns a dict with:
        - note_count: Number of notes that will be deleted
        - exclusive_source_count: Sources only in this notebook (can be deleted)
        - shared_source_count: Sources in other notebooks (will be unlinked only)
        """
        try:
            notebook_id = ensure_record_id(self.id)

            # Count notes
            note_result = await repo_query(
                "SELECT count() as count FROM artifact WHERE out = $notebook_id GROUP ALL",
                {"notebook_id": notebook_id},
            )
            note_count = note_result[0]["count"] if note_result else 0

            # Get sources with count of references to OTHER notebooks
            # If assigned_others = 0, source is exclusive to this notebook
            # If assigned_others > 0, source is shared with other notebooks
            source_counts = await repo_query(
                """
                SELECT
                    id,
                    count(->reference[WHERE out != $notebook_id].out) as assigned_others
                FROM (SELECT VALUE <-reference.in AS sources FROM $notebook_id)[0]
                """,
                {"notebook_id": notebook_id},
            )

            exclusive_count = 0
            shared_count = 0
            for src in source_counts:
                if src.get("assigned_others", 0) == 0:
                    exclusive_count += 1
                else:
                    shared_count += 1

            return {
                "note_count": note_count,
                "exclusive_source_count": exclusive_count,
                "shared_source_count": shared_count,
            }
        except Exception as e:
            logger.error(f"Error getting delete preview for notebook {self.id}: {e}")
            logger.exception(e)
            raise DatabaseOperationError(e)

    async def delete(self, delete_exclusive_sources: bool = False) -> dict[str, int]:
        """
        Delete notebook with cascade deletion of notes and optional source deletion.

        Args:
            delete_exclusive_sources: If True, also delete sources that belong
                                     only to this notebook. Default is False.

        Returns:
            Dict with counts: deleted_notes, deleted_sources, unlinked_sources
        """
        if self.id is None:
            raise InvalidInputError("Cannot delete notebook without an ID")

        try:
            notebook_id = ensure_record_id(self.id)
            deleted_notes = 0
            deleted_sources = 0
            unlinked_sources = 0

            # 1. Get and delete all notes linked to this notebook.
            #
            # v0.7.107 — parallelize per-note deletes. For v0.7.89
            # multi-page notebooks with N notes, the old sequential loop
            # was N+1 round-trips serialized; with asyncio.gather they
            # interleave concurrently against the connection pool.
            # Each note.delete() still runs its own cascade (artifact
            # edges + note_embedding rows, per v0.7.76), so we retain
            # the per-note observability without the sequential wait.
            # return_exceptions=True keeps one failed note from
            # cancelling the others — a partial cleanup is still
            # better than aborting halfway and leaving orphan rows.
            #
            # v0.7.133 — Bulk-SQL path for notebooks above the
            # ONP_NOTEBOOK_DELETE_BULK_THRESHOLD (default 25) note
            # threshold (Area for Review #4). Even with gather, the
            # per-note path is N concurrent DELETEs hitting a
            # connection pool of size 4 (ONP_DB_POOL_SIZE default) —
            # they queue up. For a 100-note notebook that's 100 ÷ 4 =
            # ~25 round-trip-batches serialized, plus per-call overhead.
            # The bulk path does 3 SurrealQL statements regardless of N.
            #
            # Trade-off: bulk loses the per-note observability log line
            # ("note X failed to delete"). For small notebooks that's a
            # diagnostic loss not worth the speedup; for large notebooks
            # the speedup is huge AND a per-note log per failure was
            # always noise. Threshold is tunable.
            import asyncio as _asyncio_for_delete  # local alias avoids name shadowing
            notes = await self.get_notes()
            if notes:
                bulk_threshold = _notebook_delete_bulk_threshold()
                if len(notes) > bulk_threshold:
                    deleted_notes = await self._bulk_delete_notes(notes)
                else:
                    results = await _asyncio_for_delete.gather(
                        *(note.delete() for note in notes),
                        return_exceptions=True,
                    )
                    for note, result in zip(notes, results):
                        if isinstance(result, BaseException):
                            logger.warning(
                                "Notebook delete: note {} failed to delete: {}",
                                note.id, result,
                            )
                            # Skip counting failed deletes; the top-level
                            # `DELETE artifact WHERE out=$notebook_id`
                            # below will at least unlink the orphan.
                            continue
                        deleted_notes += 1
            logger.info(f"Deleted {deleted_notes} notes for notebook {self.id}")

            # Delete artifact relationships
            await repo_query(
                "DELETE artifact WHERE out = $notebook_id",
                {"notebook_id": notebook_id},
            )

            # 2. Handle sources
            if delete_exclusive_sources:
                # Find sources with count of references to OTHER notebooks
                # If assigned_others = 0, source is exclusive to this notebook
                source_counts = await repo_query(
                    """
                    SELECT
                        id,
                        count(->reference[WHERE out != $notebook_id].out) as assigned_others
                    FROM (SELECT VALUE <-reference.in AS sources FROM $notebook_id)[0]
                    """,
                    {"notebook_id": notebook_id},
                )

                for src in source_counts:
                    source_id = src.get("id")
                    if source_id and src.get("assigned_others", 0) == 0:
                        # Exclusive source - delete it
                        try:
                            source = await Source.get(str(source_id))
                            await source.delete()
                            deleted_sources += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete exclusive source {source_id}: {e}"
                            )
                    else:
                        unlinked_sources += 1
            else:
                # Just count sources that will be unlinked
                source_result = await repo_query(
                    "SELECT count() as count FROM reference WHERE out = $notebook_id GROUP ALL",
                    {"notebook_id": notebook_id},
                )
                unlinked_sources = source_result[0]["count"] if source_result else 0

            # Delete reference relationships (unlink all sources)
            await repo_query(
                "DELETE reference WHERE out = $notebook_id",
                {"notebook_id": notebook_id},
            )
            logger.info(
                f"Unlinked {unlinked_sources} sources, deleted {deleted_sources} "
                f"exclusive sources for notebook {self.id}"
            )

            # v0.7.61 — cascade-delete chat sessions linked via the
            # refers_to edge. Without this, chat_session records survive
            # with a dangling notebook reference: they show up in any
            # "all sessions" listing and any attempt to open them
            # returns a 404 indefinitely because the parent notebook is
            # gone. The associated LangGraph SQLite checkpoint blobs are
            # left behind (they're keyed by session id, no FK to clean
            # up automatically) but become unreachable; we accept that
            # as orphaned storage rather than complicate the cascade
            # further.
            #
            # Order matters: delete the edge first so the session record
            # delete can't race a parallel "open session" call.
            chat_session_ids = await repo_query(
                "SELECT VALUE in FROM refers_to WHERE out = $notebook_id",
                {"notebook_id": notebook_id},
            )
            await repo_query(
                "DELETE refers_to WHERE out = $notebook_id",
                {"notebook_id": notebook_id},
            )
            # v0.8.48 — stringify the cascade-deleted session ids so the
            # caller (the notebooks API router) can clean up each one's
            # LangGraph checkpoint thread. The domain layer must NOT import
            # the chat graph / checkpointer (layering), so we surface the
            # ids and let the API layer — which already owns the
            # checkpointer in the single-session delete path
            # (api/routers/chat.py v0.7.171) — do the cleanup. Without
            # this, notebook deletes leaked checkpoint blobs forever:
            # `prune_old_checkpoints` only trims the OLDEST snapshots
            # WITHIN a thread that exceeds the per-thread retention (50),
            # so a deleted session's <50-checkpoint thread is never
            # touched. The thread_id IS the str() form of the session id.
            deleted_chat_session_ids = (
                [str(cid) for cid in chat_session_ids] if chat_session_ids else []
            )
            if chat_session_ids:
                # v0.7.184 — Was `DELETE $ids` with the ids list bound
                # as the entire post-DELETE expression. That isn't valid
                # SurrealQL: DELETE wants a table reference / record-id
                # expression / WHERE clause, NOT an array bound straight
                # to the verb position. The query silently no-op'd (or
                # errored, depending on driver version), so cascade
                # delete leaked every chat_session row that ever pointed
                # at a deleted notebook. Backend audit finding #1.
                # The correct form binds the id list to a WHERE-IN.
                await repo_query(
                    "DELETE chat_session WHERE id IN $ids",
                    {"ids": chat_session_ids},
                )
                logger.info(
                    f"Deleted {len(chat_session_ids)} chat session(s) for "
                    f"notebook {self.id}"
                )

            # 3. Delete the notebook record itself
            await super().delete()
            logger.info(f"Deleted notebook {self.id}")

            return {
                "deleted_notes": deleted_notes,
                "deleted_sources": deleted_sources,
                "unlinked_sources": unlinked_sources,
                # v0.8.48 — surface the cascade-deleted session ids for
                # caller-side checkpoint cleanup (see above).
                "deleted_chat_session_ids": deleted_chat_session_ids,
            }

        except Exception as e:
            logger.error(f"Error deleting notebook {self.id}: {e}")
            logger.exception(e)
            raise DatabaseOperationError(f"Failed to delete notebook: {e}")

    async def _bulk_delete_notes(self, notes: list["Note"]) -> int:
        """v0.7.133 — Bulk-SQL cascade-delete for notes in this notebook.

        Two statements, regardless of N notes (v0.8.66 — was three; the
        `note_embedding` step was dropped, see D-1 below). Rows are deleted
        FIRST so a partial failure can't strand searchable orphan note rows:
          1. DELETE note     WHERE id IN $note_ids             (rows; embedding
                                                                is a column on
                                                                the row)
          2. DELETE artifact WHERE in IN $note_ids             (edges)

        Trade-offs vs the per-note gather path:
          + 3 round-trips total instead of ~N/pool_size batches.
          + No per-note connection-pool contention.
          - Lose per-note "note X failed to delete" log line — if a
            single statement fails, the entire batch fails.
          - Bypasses any per-note logic Note.delete() might add in
            future. Currently Note.delete() does exactly the same
            DELETE statements we're issuing here, just per-note.
            Worth a code review if Note.delete() ever grows
            per-note side effects (e.g., file cleanup).

        Returns the count of notes successfully deleted (i.e. that
        existed before this call). Best-effort: any failure logs and
        returns 0 — the surrounding `Notebook.delete()` then proceeds
        with edge cleanup (DELETE artifact WHERE out=$notebook_id),
        which at minimum unlinks the orphans.
        """
        note_ids = [ensure_record_id(n.id) for n in notes if n.id]
        if not note_ids:
            return 0
        try:
            # v0.8.66 (audit D-1 + D-5):
            #  • D-1 — removed the dead `DELETE note_embedding` step.
            #    `note_embedding` is a PHANTOM table (no migration defines it);
            #    note embeddings live in the `note.embedding` column and are
            #    removed when the row is deleted. The statement was a no-op and
            #    the comment misled maintainers into thinking the table existed.
            #  • D-5 — delete the note ROWS *before* the artifact edges, so a
            #    partial failure can't leave searchable note rows whose edges
            #    were already removed (orphans). If the edge delete then fails,
            #    the leftover edges are swept by the notebook-level
            #    `DELETE artifact WHERE out=$notebook_id` cleanup in delete().
            await repo_query(
                "DELETE note WHERE id IN $note_ids",
                {"note_ids": note_ids},
            )
            await repo_query(
                "DELETE artifact WHERE in IN $note_ids",
                {"note_ids": note_ids},
            )
            logger.info(
                "Bulk-deleted {} notes for notebook {}",
                len(note_ids), self.id,
            )
            return len(note_ids)
        except Exception as e:
            logger.warning(
                "Bulk delete of {} notes failed for notebook {}: {}. "
                "Outer Notebook.delete() will still unlink artifact "
                "edges (DELETE artifact WHERE out=$notebook_id).",
                len(note_ids), self.id, e,
            )
            return 0


class Asset(BaseModel):
    file_path: Optional[str] = None
    url: Optional[str] = None


class SourceEmbedding(ObjectModel):
    table_name: ClassVar[str] = "source_embedding"
    content: str

    async def get_source(self) -> "Source":
        try:
            src = await repo_query(
                """
            select source.* from $id fetch source
            """,
                {"id": ensure_record_id(self.id)},
            )
            return Source(**src[0]["source"])
        except Exception as e:
            logger.error(f"Error fetching source for embedding {self.id}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(e)


class SourceInsight(ObjectModel):
    table_name: ClassVar[str] = "source_insight"
    insight_type: str
    content: str

    async def get_source(self) -> "Source":
        try:
            src = await repo_query(
                """
            select source.* from $id fetch source
            """,
                {"id": ensure_record_id(self.id)},
            )
            return Source(**src[0]["source"])
        except Exception as e:
            logger.error(f"Error fetching source for insight {self.id}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(e)

    async def save_as_note(self, notebook_id: Optional[str] = None) -> Any:
        source = await self.get_source()
        note = Note(
            title=f"{self.insight_type} from source {source.title}",
            content=self.content,
        )
        await note.save()
        if notebook_id:
            await note.add_to_notebook(notebook_id)
        return note


class Source(ObjectModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    table_name: ClassVar[str] = "source"
    asset: Optional[Asset] = None
    title: Optional[str] = None
    topics: Optional[list[str]] = Field(default_factory=list)
    provenance: Optional[dict[str, Any]] = Field(default_factory=dict)
    source_type: Optional[
        Literal["link", "upload", "text", "web_import", "deep_research_report"]
    ] = None
    full_text: Optional[str] = None
    command: Optional[str | RecordID] = Field(
        default=None, description="Link to surreal-commands processing job"
    )

    @field_validator("command", mode="before")
    @classmethod
    def parse_command(cls, value):
        """Parse command field to ensure RecordID format"""
        if isinstance(value, str) and value:
            return ensure_record_id(value)
        return value

    # v0.8.66 (audit D-6) — the per-Source `parse_id` validator was hoisted to
    # ObjectModel base (`_coerce_id_to_str`) so all models coerce id uniformly.

    async def get_status(self) -> Optional[str]:
        """Get the processing status of the associated command"""
        if not self.command:
            return None

        try:
            from surreal_commands import get_command_status

            status = await get_command_status(str(self.command))
            return status.status if status else "unknown"
        except Exception as e:
            logger.warning(f"Failed to get command status for {self.command}: {e}")
            return "unknown"

    async def get_processing_progress(self) -> Optional[dict[str, Any]]:
        """Get detailed processing information for the associated command"""
        if not self.command:
            return None

        try:
            from surreal_commands import get_command_status

            status_result = await get_command_status(str(self.command))
            if not status_result:
                return None

            # Extract execution metadata if available
            result = getattr(status_result, "result", None)
            execution_metadata = (
                result.get("execution_metadata", {}) if isinstance(result, dict) else {}
            )

            return {
                "status": status_result.status,
                "started_at": execution_metadata.get("started_at"),
                "completed_at": execution_metadata.get("completed_at"),
                "error": getattr(status_result, "error_message", None),
                "progress": getattr(status_result, "progress", None),
                "result": result,
            }
        except Exception as e:
            logger.warning(f"Failed to get command progress for {self.command}: {e}")
            return None

    async def get_context(
        self, context_size: Literal["short", "long"] = "short"
    ) -> dict[str, Any]:
        insights_list = await self.get_insights()
        insights = [insight.model_dump() for insight in insights_list]
        if context_size == "long":
            return dict(
                id=self.id,
                title=self.title,
                insights=insights,
                full_text=self.full_text,
            )
        else:
            return dict(id=self.id, title=self.title, insights=insights)

    async def get_embedded_chunks(self) -> int:
        try:
            result = await repo_query(
                """
                select count() as chunks from source_embedding where source=$id GROUP ALL
                """,
                {"id": ensure_record_id(self.id)},
            )
            if len(result) == 0:
                return 0
            return result[0]["chunks"]
        except Exception as e:
            logger.error(f"Error fetching chunks count for source {self.id}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError(f"Failed to count chunks for source: {str(e)}")

    async def get_insights(self) -> list[SourceInsight]:
        try:
            result = await repo_query(
                """
                SELECT * FROM source_insight WHERE source=$id
                """,
                {"id": ensure_record_id(self.id)},
            )
            return [SourceInsight(**insight) for insight in result]
        except Exception as e:
            logger.error(f"Error fetching insights for source {self.id}: {str(e)}")
            logger.exception(e)
            raise DatabaseOperationError("Failed to fetch insights for source")

    async def add_to_notebook(self, notebook_id: str) -> Any:
        if not notebook_id:
            raise InvalidInputError("Notebook ID must be provided")
        # v0.7.73 — defensive dedup at the domain layer. The HTTP endpoint
        # POST /notebooks/{notebook_id}/sources/{source_id} already has
        # an idempotency check (fixed in v0.7.60), but direct domain
        # calls (sources.py:493/572 upload flow, studio.py:375 batch
        # upload, the Source.add_to_notebook path from the upcoming
        # bulk-link feature) didn't. A duplicate call would create a
        # second `reference` edge, inflating source_count and
        # requiring multiple deletes-from-notebook clicks to remove
        # the source.
        existing = await repo_query(
            "SELECT * FROM reference WHERE out = $notebook_id AND in = $source_id",
            {
                "notebook_id": ensure_record_id(notebook_id),
                "source_id": ensure_record_id(self.id),
            },
        )
        if existing:
            return existing[0]
        return await self.relate("reference", notebook_id)

    async def vectorize(self) -> str:
        """
        Submit vectorization as a background job using the embed_source command.

        This method leverages the job-based architecture to prevent HTTP connection
        pool exhaustion when processing large documents. The embed_source command:
        1. Detects content type from file path
        2. Chunks text using content-type aware splitter
        3. Generates all embeddings in batches
        4. Bulk inserts source_embedding records

        Returns:
            str: The command/job ID that can be used to track progress via the commands API

        Raises:
            ValueError: If source has no text to vectorize
            DatabaseOperationError: If job submission fails
        """
        logger.info(f"Submitting embed_source job for source {self.id}")
        # v0.7.76 — same to_thread treatment as v0.7.55/57/62/68/70.
        # surreal_commands.submit_command opens a synchronous SurrealDB
        # WebSocket; running it directly inside this `async def` blocks
        # the FastAPI event loop for the handshake duration. Move it
        # to a worker thread.

        try:
            if not self.full_text or not self.full_text.strip():
                raise ValueError(f"Source {self.id} has no text to vectorize")

            # Submit the embed_source command
            command_id = await asyncio.to_thread(
                submit_command,
                "open_notebook",
                "embed_source",
                {"source_id": str(self.id)},
            )

            command_id_str = str(command_id)
            logger.info(
                f"Embed source job submitted for source {self.id}: "
                f"command_id={command_id_str}"
            )

            return command_id_str

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to submit embed_source job for source {self.id}: {e}"
            )
            logger.exception(e)
            raise DatabaseOperationError(e)

    async def add_insight(self, insight_type: str, content: str) -> Optional[str]:
        """
        Submit insight creation as an async command (fire-and-forget).

        Submits a create_insight command that handles database operations with
        automatic retry logic for transaction conflicts. The command also submits
        an embed_insight command for async embedding.

        This method returns immediately after submitting the command - it does NOT
        wait for the insight to be created. Use this for batch operations where
        throughput is more important than immediate confirmation.

        Args:
            insight_type: Type/category of the insight
            content: The insight content text

        Returns:
            command_id for optional tracking, or None if submission failed

        Raises:
            InvalidInputError: If insight_type or content is empty
        """
        if not insight_type or not content:
            raise InvalidInputError("Insight type and content must be provided")

        try:
            # Submit create_insight command (fire-and-forget)
            # Command handles retries internally for transaction conflicts
            # v0.7.76 — to_thread the sync submit_command, see vectorize().
            command_id = await asyncio.to_thread(
                submit_command,
                "open_notebook",
                "create_insight",
                {
                    "source_id": str(self.id),
                    "insight_type": insight_type,
                    "content": content,
                },
            )
            logger.info(
                f"Submitted create_insight command {command_id} for source {self.id} "
                f"(type={insight_type})"
            )
            return str(command_id)

        except Exception as e:
            logger.error(f"Error submitting create_insight for source {self.id}: {e}")
            return None

    def _prepare_save_data(self) -> dict:
        """Override to ensure command field is always RecordID format for database"""
        data = super()._prepare_save_data()

        # Ensure command field is RecordID format if not None
        if data.get("command") is not None:
            data["command"] = ensure_record_id(data["command"])

        return data

    async def delete(self) -> bool:
        """Delete source and clean up associated file, embeddings, and insights.

        v0.6.34 — verifies the file_path is INSIDE UPLOADS_FOLDER before
        unlinking.

        v0.7.32 — also cancels any in-flight processing command. Without
        this, deleting a source mid-embed left the worker running
        against a now-dead source, writing fresh source_embedding rows
        pointing at the deleted source. Orphan data + wasted GPU.
        """
        # v0.7.32 — cancel any in-flight worker command FIRST so the
        # worker doesn't race us to write embeddings on a source we're
        # about to delete. Best-effort: if the cancel fails (command
        # already completed, surreal_commands API change, etc.), we
        # continue with deletion — the legacy orphan-data path is no
        # worse than before this fix.
        if self.command:
            try:
                from surreal_commands import get_command_status
                from surreal_commands.core.service import get_command_service

                status = await get_command_status(str(self.command))
                # `status` is a CommandResult enum value or string. Only
                # nudge active jobs; completed/failed jobs need no action.
                status_str = getattr(status, "value", str(status)).lower()
                if status_str in {"new", "running", "queued"}:
                    svc = get_command_service()
                    await svc.update_command_result(
                        str(self.command),
                        status="canceled",
                        result={},
                        error_message=(
                            f"Source {self.id} was deleted by the user "
                            f"before processing completed."
                        ),
                    )
                    logger.info(
                        f"Cancelled in-flight command {self.command} for "
                        f"source {self.id} (was {status_str})"
                    )
            except Exception as e:
                logger.warning(
                    f"Could not cancel command {self.command} for source "
                    f"{self.id}: {e}. Continuing with deletion."
                )

        # Clean up uploaded file if it exists
        if self.asset and self.asset.file_path:
            file_path = Path(self.asset.file_path)
            # Defense-in-depth: only unlink files inside UPLOADS_FOLDER.
            # Lazy import to avoid a circular dependency at module load.
            from open_notebook.config import UPLOADS_FOLDER as _uploads
            try:
                uploads_root = Path(_uploads).resolve()
                resolved = file_path.resolve()
                inside_uploads = resolved.is_relative_to(uploads_root)
            except (OSError, ValueError) as exc:
                logger.warning(
                    f"Could not validate file_path for source {self.id} "
                    f"({file_path}): {exc}; skipping file cleanup"
                )
                inside_uploads = False
            if not inside_uploads:
                logger.warning(
                    f"Refusing to unlink file_path outside UPLOADS_FOLDER for "
                    f"source {self.id}: {file_path} (uploads root: "
                    f"{_uploads}). DB may be corrupted."
                )
            elif file_path.exists():
                try:
                    os.unlink(file_path)
                    logger.info(f"Deleted file for source {self.id}: {file_path}")
                except Exception as e:
                    logger.warning(
                        f"Failed to delete file {file_path} for source {self.id}: {e}. "
                        "Continuing with database deletion."
                    )
            else:
                logger.debug(
                    f"File {file_path} not found for source {self.id}, skipping cleanup"
                )

        # Delete associated embeddings and insights to prevent orphaned records
        source_id = ensure_record_id(self.id)
        try:
            await repo_query(
                "DELETE source_embedding WHERE source = $source_id",
                {"source_id": source_id},
            )
            await repo_query(
                "DELETE source_insight WHERE source = $source_id",
                {"source_id": source_id},
            )
            # v0.7.76 — also delete the `reference` edges that point this
            # source at notebooks. Without this, get_sources via
            # `select in as source from reference where out=$id fetch source`
            # would fetch null sources (the rows are still there even
            # after the source record is deleted), and Source(**None)
            # crashes the notebook view. Symmetric to the v0.7.61 fix
            # for Notebook.delete -> chat_session edges.
            await repo_query(
                "DELETE reference WHERE in = $source_id",
                {"source_id": source_id},
            )
            logger.debug(
                f"Deleted embeddings, insights, and reference edges for "
                f"source {self.id}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to delete embeddings/insights for source {self.id}: {e}. "
                "Continuing with source deletion."
            )

        # Call parent delete to remove database record
        result = await super().delete()

        # v0.7.133 — Race-window post-sweep (Area for Review #11).
        #
        # The cancel above (`svc.update_command_result(status="canceled")`)
        # writes a row to the surreal_commands tracking table but does
        # NOT actually stop the running worker — surreal_commands has no
        # cancellation-token mechanism. So between the pre-sweep above
        # and this point (single-digit ms in practice, but the worker
        # could complete a write iteration during that window), the
        # worker could insert one or more fresh `source_embedding` rows
        # pointing at the now-deleted source.
        #
        # We re-run the sweep AFTER super().delete(). The DELETE matches
        # by `source = $source_id`, and SurrealDB doesn't enforce the
        # source-existence constraint, so even after the source row is
        # gone we can still purge by ID. Idempotent + cheap.
        #
        # We don't re-sweep `reference` — those edges require an
        # explicit `Source.add_to_notebook` call which can't race against
        # a deleted source (the call path goes through Source.id which
        # is already None post-delete on this instance).
        try:
            await repo_query(
                "DELETE source_embedding WHERE source = $source_id",
                {"source_id": source_id},
            )
            await repo_query(
                "DELETE source_insight WHERE source = $source_id",
                {"source_id": source_id},
            )
            logger.debug(
                "Race-window post-sweep cleared any stragglers for source {}",
                self.id,
            )
        except Exception as e:
            # Best-effort: if this fails the orphan rows are present but
            # not user-visible (no source row to associate them with).
            # Log + continue; periodic cleanup or a future migration
            # can sweep them up.
            logger.warning(
                "Race-window post-sweep failed for source {}: {}. Orphan "
                "embeddings/insights may exist but are unreachable via "
                "the API.", self.id, e,
            )

        return result


class Note(ObjectModel):
    table_name: ClassVar[str] = "note"
    title: Optional[str] = None
    note_type: Optional[Literal["human", "ai"]] = None
    content: Optional[str] = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v):
        if v is not None and not v.strip():
            raise InvalidInputError("Note content cannot be empty")
        return v

    async def save(self) -> Optional[str]:
        """
        Save the note and submit embedding command.

        Overrides ObjectModel.save() to submit an async embed_note command
        after saving, instead of inline embedding.

        Returns:
            Optional[str]: The command_id if embedding was submitted, None otherwise
        """
        # Call parent save (without embedding)
        await super().save()

        # Submit embedding command (fire-and-forget) if note has content
        if self.id and self.content and self.content.strip():
            # v0.7.76 — to_thread the sync submit_command, see vectorize().
            #
            # v0.7.129 — wrap submission in a try/except so a missing
            # registry entry (worker not running yet, worker not
            # importing the `commands` module, integration tests with
            # no worker process at all) doesn't fail an otherwise
            # successful save. Per the "fire-and-forget" contract
            # documented in domain/CLAUDE.md, embedding is
            # eventual-consistency — the note row itself is what
            # matters.
            #
            # v0.7.133 — replaced fragile string-match against the
            # exception message ("Command not found") with a direct
            # registry-introspection pre-check. The previous code did
            # `except ValueError: if "Command not found" in str(e)`,
            # which would silently break if surreal_commands ever
            # changed its error message (the library just raises plain
            # ValueError, no typed exception class). Now we ask the
            # registry directly via `registry.get_command_by_id()` —
            # returns None if the command isn't registered, no
            # exception. Cleaner intent + no string brittleness.
            if not _is_command_registered("open_notebook.embed_note"):
                logger.warning(
                    f"embed_note not in surreal-commands registry — "
                    f"note {self.id} saved without embedding. Embedding "
                    f"will run when the worker starts and the note is "
                    f"re-saved, or via a manual re-embed."
                )
                return None

            try:
                command_id = await asyncio.to_thread(
                    submit_command,
                    "open_notebook",
                    "embed_note",
                    {"note_id": str(self.id)},
                )
                logger.debug(
                    f"Submitted embed_note command {command_id} for {self.id}"
                )
                return command_id
            except ValueError:
                # v0.7.133 — Narrow propagation for ValueError. The
                # registry-miss case was already filtered by the
                # `_is_command_registered` pre-check above, so a
                # ValueError reaching here represents a real bug
                # (bad argument from caller, validation in
                # surreal_commands itself) that should surface, not
                # silently turn into "note saved without embedding".
                # Pinned by test_save_propagates_unrelated_value_errors.
                raise
            except Exception as e:
                # Connection failure, worker DB unreachable, transient
                # surreal_commands DB write error — the save is durable;
                # embedding is best-effort.
                logger.warning(
                    f"Failed to submit embed_note for {self.id}: {e}. "
                    f"Note saved; embedding will retry on next save."
                )
                return None

        return None

    async def add_to_notebook(self, notebook_id: str) -> Any:
        if not notebook_id:
            raise InvalidInputError("Notebook ID must be provided")
        # v0.7.73 — defensive dedup at the domain layer. Same rationale
        # as Source.add_to_notebook: the artifact-edge create was not
        # idempotent, and `notes.py:90` (create_note flow) could
        # double-link if the request was retried. Inflated note_count
        # required multiple unlinks per note.
        existing = await repo_query(
            "SELECT * FROM artifact WHERE out = $notebook_id AND in = $note_id",
            {
                "notebook_id": ensure_record_id(notebook_id),
                "note_id": ensure_record_id(self.id),
            },
        )
        if existing:
            return existing[0]
        return await self.relate("artifact", notebook_id)

    async def delete(self) -> bool:
        """Delete the note and cascade its artifact edges (the embedding is a
        column on the row, removed with it — there is no note_embedding table).

        v0.7.76 — base ObjectModel.delete only deletes the note record.
        Without explicit cascade, the `artifact` edges pointing at the
        note survive: get_notes on the parent notebook does
        `select in as note from artifact where out=$id fetch note`,
        which would then `fetch note` → null and crash on `Note(**None)`.
        Symmetric to Source.delete (v0.6.34 / v0.7.32) and the
        Notebook.delete chat_session cascade (v0.7.61).
        """
        if self.id is None:
            from open_notebook.exceptions import InvalidInputError as _IIE
            raise _IIE("Cannot delete note without an ID")
        try:
            note_id = ensure_record_id(self.id)
            # Delete artifact edges first so the FETCH path in
            # get_notes can't race a half-deleted note.
            await repo_query(
                "DELETE artifact WHERE in = $note_id",
                {"note_id": note_id},
            )
            # v0.8.66 (audit D-1) — removed the dead `DELETE note_embedding`
            # cleanup. `note_embedding` is a phantom table (no migration defines
            # it); the note's embedding is a column on the row and is removed by
            # super().delete() below. (Edges are still deleted FIRST, above, to
            # keep the get_notes FETCH path from racing a half-deleted note —
            # v0.7.76.)
        except Exception as exc:
            logger.warning(
                f"Failed to cascade-clean artifact edges for note "
                f"{self.id}: {exc}. Continuing with note deletion."
            )
        return await super().delete()

    # v0.8.67 (audit A3) — "short" note context budget. Was a flat 100-CHAR
    # slice (`self.content[:100]`) that truncated mid-word with no marker, so
    # the LLM treated a fragment as the whole note. Now a token-based budget
    # with an explicit ellipsis so the model knows the note was elided. ~160
    # tokens ≈ a few sentences — enough to convey the gist in "short" mode
    # without flooding the budget.
    _SHORT_CONTEXT_MAX_TOKENS: ClassVar[int] = 160

    def get_context(
        self, context_size: Literal["short", "long"] = "short"
    ) -> dict[str, Any]:
        if context_size == "long":
            return dict(id=self.id, title=self.title, content=self.content)
        else:
            return dict(
                id=self.id,
                title=self.title,
                content=self._short_content(),
            )

    def _short_content(self) -> Optional[str]:
        """Trim note content to a token budget on a word boundary, appending
        ' […]' when truncated. Returns None for empty content (v0.8.67 A3)."""
        if not self.content:
            return None
        from open_notebook.utils.token_utils import token_count

        if token_count(self.content) <= self._SHORT_CONTEXT_MAX_TOKENS:
            return self.content
        # Coarse char budget (~4 chars/token), then shrink to the token cap on
        # whitespace boundaries so we don't cut mid-word.
        approx = self._SHORT_CONTEXT_MAX_TOKENS * 4
        trimmed = self.content[:approx]
        while trimmed and token_count(trimmed) > self._SHORT_CONTEXT_MAX_TOKENS:
            cut = trimmed.rsplit(None, 1)[0] if " " in trimmed.strip() else trimmed[:-50]
            if cut == trimmed:
                trimmed = trimmed[:-50]
            else:
                trimmed = cut
        return trimmed.rstrip() + " […]"


StudioArtifactType = Literal[
    "report",
    "study_guide",
    "course_pack",
    "training_guide",
    "briefing",
    "faq",
    "flashcards",
    "quiz",
    "data_table",
    "mind_map",
    "timeline",
    "infographic",
    "slide_deck",
    "podcast_outline",
    "podcast_audio",
    "research_run",
]

StudioArtifactStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
]

StudioWorkflowRunStatus = Literal[
    "queued",
    "awaiting_approval",
    "running",
    "completed",
    "failed",
    "cancelled",
]


class StudioArtifact(ObjectModel):
    table_name: ClassVar[str] = "studio_artifact"
    nullable_fields: ClassVar[set[str]] = {"revision_of_id"}

    notebook_id: str
    artifact_type: StudioArtifactType
    title: str
    status: StudioArtifactStatus = "pending"
    source_ids: list[str] = Field(default_factory=list)
    prompt: Optional[str] = None
    model_id: Optional[str] = None
    provider: Optional[str] = None
    output_format: Optional[str] = None
    output_payload: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    export_paths: dict[str, str] = Field(default_factory=dict)
    revision_of_id: Optional[str] = None

    def _prepare_save_data(self) -> dict[str, Any]:
        data = super()._prepare_save_data()
        data["notebook_id"] = ensure_record_id(self.notebook_id)
        data["source_ids"] = [ensure_record_id(source_id) for source_id in self.source_ids]
        if self.revision_of_id is not None:
            data["revision_of_id"] = ensure_record_id(self.revision_of_id)
        return data

    @classmethod
    async def get_for_notebook(cls, notebook_id: str) -> list["StudioArtifact"]:
        if not notebook_id:
            raise InvalidInputError("Notebook ID must be provided")
        try:
            rows = await repo_query(
                """
                SELECT * FROM studio_artifact
                WHERE notebook_id = $notebook_id
                AND revision_of_id = NONE
                ORDER BY updated DESC
                """,
                {"notebook_id": ensure_record_id(notebook_id)},
            )
            return [cls(**row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Error fetching Studio artifacts for {notebook_id}: {e}")
            logger.exception(e)
            raise DatabaseOperationError(e)

    @classmethod
    async def get_revisions(cls, artifact_id: str) -> list["StudioArtifact"]:
        if not artifact_id:
            raise InvalidInputError("Artifact ID must be provided")
        try:
            rows = await repo_query(
                """
                SELECT * FROM studio_artifact
                WHERE revision_of_id = $artifact_id
                ORDER BY updated DESC
                """,
                {"artifact_id": ensure_record_id(artifact_id)},
            )
            return [cls(**row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Error fetching Studio artifact revisions for {artifact_id}: {e}")
            logger.exception(e)
            raise DatabaseOperationError(e)


class StudioWorkflowRun(ObjectModel):
    table_name: ClassVar[str] = "studio_workflow_run"
    nullable_fields: ClassVar[set[str]] = {"command_id"}

    artifact_id: str
    notebook_id: str
    title: str
    status: StudioWorkflowRunStatus = "queued"
    source_ids: list[str] = Field(default_factory=list)
    approval_required: bool = False
    steps: list[dict[str, Any]] = Field(default_factory=list)
    command_id: Optional[str] = None

    def _prepare_save_data(self) -> dict[str, Any]:
        data = super()._prepare_save_data()
        data["artifact_id"] = ensure_record_id(self.artifact_id)
        data["notebook_id"] = ensure_record_id(self.notebook_id)
        data["source_ids"] = [ensure_record_id(source_id) for source_id in self.source_ids]
        if self.command_id is not None:
            data["command_id"] = ensure_record_id(self.command_id)
        return data

    @classmethod
    async def get_for_artifact(cls, artifact_id: str) -> list["StudioWorkflowRun"]:
        if not artifact_id:
            raise InvalidInputError("Artifact ID must be provided")
        try:
            rows = await repo_query(
                """
                SELECT * FROM studio_workflow_run
                WHERE artifact_id = $artifact_id
                ORDER BY updated DESC
                """,
                {"artifact_id": ensure_record_id(artifact_id)},
            )
            return [cls(**row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Error fetching Studio workflow runs for {artifact_id}: {e}")
            logger.exception(e)
            raise DatabaseOperationError(e)


class ChatSession(ObjectModel):
    table_name: ClassVar[str] = "chat_session"
    # v0.8.43 — disabled_mcp_servers joins model_override as nullable.
    # None / unset = "all MCP servers visible for this session"
    # (the v0.8.42 default, no regression for pre-migration rows).
    nullable_fields: ClassVar[set[str]] = {"model_override", "disabled_mcp_servers"}
    title: Optional[str] = None
    model_override: Optional[str] = None
    # v0.8.43 — Persistent per-conversation MCP server disable picks.
    # The user's "load only what I need" choices stick across page
    # navigations + browser reloads. Names match `mcp_server.name`
    # case-insensitively in `_resolve_chat_tools`; we DON'T normalize
    # at write-time so the registry's exact casing round-trips.
    disabled_mcp_servers: Optional[list[str]] = None

    async def relate_to_notebook(self, notebook_id: str) -> Any:
        if not notebook_id:
            raise InvalidInputError("Notebook ID must be provided")
        # v0.8.66 (audit D-3) — idempotent relate. A retried session-create
        # (chat.py / source_chat.py) previously RELATE'd a SECOND `refers_to`
        # edge each time (SurrealDB RELATE is not upsert), and `dedup_edges`
        # doesn't sweep refers_to. Mirror the hardened reference/artifact path:
        # return the existing edge if present, else create one.
        if self.id:
            existing = await repo_query(
                "SELECT * FROM refers_to WHERE in = $sid AND out = $nid LIMIT 1",
                {
                    "sid": ensure_record_id(self.id),
                    "nid": ensure_record_id(notebook_id),
                },
            )
            if existing:
                return existing[0]
        return await self.relate("refers_to", notebook_id)

    async def relate_to_source(self, source_id: str) -> Any:
        if not source_id:
            raise InvalidInputError("Source ID must be provided")
        # v0.8.66 (audit D-3) — idempotent (see relate_to_notebook).
        if self.id:
            existing = await repo_query(
                "SELECT * FROM refers_to WHERE in = $sid AND out = $tid LIMIT 1",
                {
                    "sid": ensure_record_id(self.id),
                    "tid": ensure_record_id(source_id),
                },
            )
            if existing:
                return existing[0]
        return await self.relate("refers_to", source_id)

    async def delete(self) -> bool:
        """v0.8.68 — sweep this session's `refers_to` edges before the row
        delete. The base ObjectModel.delete only removes the record, so every
        deleted chat session previously left a dangling graph edge
        (session→notebook or session→source) that accumulated forever — only
        deleting the whole NOTEBOOK swept them (notebook.py Notebook.delete),
        and standalone session deletes (the common path: the session-list
        trash button in both chat UIs) never did. Mirrors the hardened
        cascade pattern on Source (v0.7.86) and Note (v0.7.76): best-effort,
        never blocks the primary delete.
        """
        if self.id is None:
            return False
        try:
            await repo_query(
                "DELETE refers_to WHERE in = $sid",
                {"sid": ensure_record_id(self.id)},
            )
        except Exception as exc:
            logger.warning(
                f"ChatSession.delete: could not sweep refers_to edges for "
                f"{self.id} (non-fatal, edge rows orphaned): {exc}"
            )
        return await super().delete()


# v0.8.67 (audit A1) — default semantic-search relevance floor. Raised from the
# old 0.2 to 0.3 to match the memory layer's own _MIN_SCORE (memory_recall.py),
# whose comment calls 0.0-0.3 "unrelated". 0.2 surfaced near-random sources into
# the LLM context. Env-tunable so operators can dial it without a rebuild and so
# the change is trivially reversible if a corpus needs a looser floor.
_DEFAULT_VECTOR_MIN_SCORE = 0.3


def _vector_min_score() -> float:
    raw = (os.environ.get("ONP_VECTOR_MIN_SCORE") or "").strip()
    if not raw:
        return _DEFAULT_VECTOR_MIN_SCORE
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_VECTOR_MIN_SCORE
    # Clamp to a sane cosine range; outside [0,1] is always a misconfig.
    return val if 0.0 <= val <= 1.0 else _DEFAULT_VECTOR_MIN_SCORE


async def text_search(
    keyword: str, results: int, source: bool = True, note: bool = True
):
    if not keyword:
        raise InvalidInputError("Search keyword cannot be empty")
    try:
        search_results = await repo_query(
            """
            select *
            from fn::text_search($keyword, $results, $source, $note)
            """,
            {"keyword": keyword, "results": results, "source": source, "note": note},
        )
        return search_results
    except Exception as e:
        error_text = str(e).lower()
        if "position overflow" in error_text:
            logger.warning(
                "Text-search highlight overflow for {!r}; falling back to vector search",
                keyword,
            )
            try:
                return await vector_search(keyword, results, source, note)
            except Exception as vector_error:
                logger.error(
                    "Vector-search fallback also failed for {!r}: {}",
                    keyword,
                    vector_error,
                )
                raise DatabaseOperationError(vector_error)
        logger.error(f"Error performing text search: {str(e)}")
        logger.exception(e)
        raise DatabaseOperationError(e)


async def vector_search(
    keyword: str,
    results: int,
    source: bool = True,
    note: bool = True,
    minimum_score: float | None = None,
):
    if not keyword:
        raise InvalidInputError("Search keyword cannot be empty")
    # v0.8.67 (audit A1) — None → env-tunable default (0.3); an explicit caller
    # value (e.g. the /search/ask request) is still honored as-is.
    if minimum_score is None:
        minimum_score = _vector_min_score()
    try:
        from open_notebook.utils.embedding import generate_embedding

        # Use unified embedding function (handles chunking if query is very long)
        embed = await generate_embedding(keyword)
        search_results = await repo_query(
            """
            SELECT * FROM fn::vector_search($embed, $results, $source, $note, $minimum_score);
            """,
            {
                "embed": embed,
                "results": results,
                "source": source,
                "note": note,
                "minimum_score": minimum_score,
            },
        )
        return search_results
    except Exception as e:
        logger.error(f"Error performing vector search: {str(e)}")
        logger.exception(e)
        raise DatabaseOperationError(e)
