import asyncio
import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Literal, Optional, Tuple, Union

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator
from surreal_commands import submit_command
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

    async def get_chat_sessions(self) -> list["ChatSession"]:
        try:
            srcs = await repo_query(
                """
                select * from (
                    select
                    <- chat_session as chat_session
                    from refers_to
                    where out=$id
                    fetch chat_session
                )
                order by chat_session.updated desc
            """,
                {"id": ensure_record_id(self.id)},
            )
            return (
                [ChatSession(**src["chat_session"][0]) for src in srcs] if srcs else []
            )
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
            import asyncio as _asyncio_for_delete  # local alias avoids name shadowing
            notes = await self.get_notes()
            if notes:
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
            if chat_session_ids:
                await repo_query(
                    "DELETE $ids",
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
            }

        except Exception as e:
            logger.error(f"Error deleting notebook {self.id}: {e}")
            logger.exception(e)
            raise DatabaseOperationError(f"Failed to delete notebook: {e}")


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

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, value):
        """Parse id field to handle both string and RecordID inputs"""
        if value is None:
            return None
        if isinstance(value, RecordID):
            return str(value)
        return str(value) if value else None

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
        try:
            source_id = ensure_record_id(self.id)
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
        return await super().delete()


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
            # successful save. The contract documented in
            # domain/CLAUDE.md is "fire-and-forget": embedding is
            # eventual-consistency, the note row itself is what matters.
            #
            # The original code surfaced `ValueError: Command not
            # found: open_notebook.embed_note` to callers, which
            # meant Note creation broke whenever surreal-commands
            # hadn't started or hadn't been imported with
            # `--import-modules commands`. Tests, CI, fresh installs,
            # and the moment-after-restart window all hit this.
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
            except ValueError as e:
                # Specifically catches the registry-miss case; broader
                # ValueErrors from inside the command handler itself
                # would have surfaced at execution time, not submission.
                if "Command not found" in str(e):
                    logger.warning(
                        f"embed_note not in surreal-commands registry — "
                        f"note {self.id} saved without embedding. "
                        f"Embedding will run when the worker starts and "
                        f"the note is re-saved, or via a manual re-embed."
                    )
                    return None
                raise
            except Exception as e:
                # Connection failure, worker DB unreachable, etc. The
                # save is durable; embedding is best-effort.
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
        """Delete the note and cascade artifact edges + note_embedding rows.

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
            # Also drop note_embedding rows so vector search doesn't
            # return ghosts. Tolerant: table may not exist on very old
            # databases.
            try:
                await repo_query(
                    "DELETE note_embedding WHERE note = $note_id",
                    {"note_id": note_id},
                )
            except Exception as exc:
                logger.debug(
                    f"Skipping note_embedding cleanup for {self.id}: {exc}"
                )
        except Exception as exc:
            logger.warning(
                f"Failed to cascade-clean artifact/embeddings for note "
                f"{self.id}: {exc}. Continuing with note deletion."
            )
        return await super().delete()

    def get_context(
        self, context_size: Literal["short", "long"] = "short"
    ) -> dict[str, Any]:
        if context_size == "long":
            return dict(id=self.id, title=self.title, content=self.content)
        else:
            return dict(
                id=self.id,
                title=self.title,
                content=self.content[:100] if self.content else None,
            )


class ChatSession(ObjectModel):
    table_name: ClassVar[str] = "chat_session"
    nullable_fields: ClassVar[set[str]] = {"model_override"}
    title: Optional[str] = None
    model_override: Optional[str] = None

    async def relate_to_notebook(self, notebook_id: str) -> Any:
        if not notebook_id:
            raise InvalidInputError("Notebook ID must be provided")
        return await self.relate("refers_to", notebook_id)

    async def relate_to_source(self, source_id: str) -> Any:
        if not source_id:
            raise InvalidInputError("Source ID must be provided")
        return await self.relate("refers_to", source_id)


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
        logger.error(f"Error performing text search: {str(e)}")
        logger.exception(e)
        raise DatabaseOperationError(e)


async def vector_search(
    keyword: str,
    results: int,
    source: bool = True,
    note: bool = True,
    minimum_score=0.2,
):
    if not keyword:
        raise InvalidInputError("Search keyword cannot be empty")
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
