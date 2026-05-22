import asyncio
import json
import os
import traceback
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from loguru import logger
from pydantic import BaseModel, Field

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import ChatSession, Note, Notebook, Source
from open_notebook.exceptions import (
    NotFoundError,
)
from open_notebook.graphs.chat import graph as chat_graph
from open_notebook.utils.graph_utils import get_session_message_count

router = APIRouter()


# v0.7.68 — memory-writer hook. The bundled desktop build registers
# `memory_extract_turn` + `memory_summarize_session` surreal_commands
# handlers (desktop/memory/memory_commands.py, registered through
# desktop/app.py:_phase_register_memory_commands). They've been wired
# up since v0.7.47, but until now NOTHING in the chat path actually
# submitted those jobs after a turn — so the memory feature was
# entirely inert at runtime. Both /chat/execute and /chat/stream now
# fire `open_notebook.memory_extract_turn` fire-and-forget after the
# turn's session.save() succeeds.
#
# Best-effort: any failure is logged at debug and swallowed. The
# user's chat experience is unaffected when the memory worker is
# down, the chat LLM is missing, or the launcher is the upstream
# (non-desktop) build that doesn't ship memory commands.
def _memory_extraction_configured() -> bool:
    """True when the memory worker stack is configured (desktop build)."""
    return all(
        os.environ.get(var)
        for var in (
            "MEMORY_SURREAL_URL",
            "MEMORY_EMBED_URL",
            "MEMORY_CHAT_LLM_URL",
        )
    )


def _extract_text(msg: Any) -> str:
    """Coerce a LangChain message-or-dict's content to a plain string."""
    if msg is None:
        return ""
    c = getattr(msg, "content", None)
    if c is None and isinstance(msg, dict):
        c = msg.get("content")
    if c is None:
        return ""
    return c if isinstance(c, str) else str(c)


async def _fire_memory_extract_turn(
    chat_session_id: str,
    user_text: str,
    assistant_text: str,
    model_override: Optional[str] = None,
) -> None:
    """Submit the memory_extract_turn job fire-and-forget.

    Caller does NOT await the actual extraction — surreal_commands.submit_command
    only queues the row. The worker picks it up asynchronously. We still wrap
    submit_command in asyncio.to_thread (matches v0.7.55/57/62 sites) because
    it opens a synchronous SurrealDB WebSocket.

    v0.7.83 — `model_override` is now plumbed through to the worker. The
    memory writer's LLM client previously always used the bundled chat
    model (ONP_CHAT_MODEL_NAME env var or "default"). When the user
    explicitly picked a different model for their chat session, the
    memory extractor still ran against the bundled model, producing
    facts that disagreed with the assistant's voice. Passing the
    override here lets the worker fall through to it; absent → falls
    back to the bundled model as before.
    """
    if not _memory_extraction_configured():
        # Upstream (non-desktop) build, or memory env vars not wired —
        # silently skip. The desktop launcher sets all three before
        # spawning the API.
        return
    if not (user_text or assistant_text):
        return
    try:
        from surreal_commands import submit_command

        args = {
            "chat_session_id": chat_session_id,
            "user_text": user_text,
            "assistant_text": assistant_text,
        }
        if model_override:
            args["model_override"] = model_override
        await asyncio.to_thread(
            submit_command,
            "open_notebook",
            "memory_extract_turn",
            args,
        )
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as exc:
        # Memory is best-effort. A failed submit_command (worker down,
        # SurrealDB blip, command not registered on this build) MUST
        # NOT take the chat response down with it.
        logger.debug(
            "memory_extract_turn submit failed (best-effort, ignored): {}",
            exc,
        )


async def _fire_memory_summarize_session(
    chat_session_id: str,
    model_override: Optional[str] = None,
) -> None:
    """Submit the memory_summarize_session job fire-and-forget.

    v0.7.70 — also wired up alongside the per-turn extractor. Fires
    when a chat session is deleted: the user's explicit "end of
    conversation" signal. We pull the full transcript from the
    LangGraph SQLite checkpoint via chat_graph.get_state, render it
    as a plain-text exchange, and queue the summarizer. The writer's
    16k-char truncation guard kicks in for very long sessions.

    v0.7.83 — `model_override` plumbed through (see _fire_memory_extract_turn
    for the rationale). For the summarizer, the right model is the same
    one the chat session was using, so the episode record's voice
    matches the chat's voice.
    """
    if not _memory_extraction_configured():
        return
    try:
        # Read messages from the graph checkpoint. Sync API; run on a
        # worker thread to keep the FastAPI event loop free.
        current_state = await asyncio.to_thread(
            chat_graph.get_state,
            config=RunnableConfig(configurable={"thread_id": chat_session_id}),
        )
        msgs = (current_state.values.get("messages", []) if current_state else [])
        if not msgs:
            return
        # Render as "USER: ..." / "ASSISTANT: ..." lines so the
        # summarize prompt sees a clean transcript regardless of how
        # the upstream chat graph stored the messages.
        lines = []
        for m in msgs:
            mtype = getattr(m, "type", None)
            if mtype == "human":
                lines.append(f"USER: {_extract_text(m)}")
            elif mtype == "ai":
                lines.append(f"ASSISTANT: {_extract_text(m)}")
            # System messages and tool messages don't help the summary.
        transcript = "\n\n".join(lines).strip()
        if not transcript:
            return
        from surreal_commands import submit_command

        args = {
            "chat_session_id": chat_session_id,
            "transcript": transcript,
        }
        if model_override:
            args["model_override"] = model_override
        await asyncio.to_thread(
            submit_command,
            "open_notebook",
            "memory_summarize_session",
            args,
        )
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as exc:
        logger.debug(
            "memory_summarize_session submit failed (best-effort, ignored): {}",
            exc,
        )


# Request/Response models
class CreateSessionRequest(BaseModel):
    notebook_id: str = Field(..., description="Notebook ID to create session for")
    title: Optional[str] = Field(None, description="Optional session title")
    model_override: Optional[str] = Field(
        None, description="Optional model override for this session"
    )


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="New session title")
    model_override: Optional[str] = Field(
        None, description="Model override for this session"
    )


class ChatMessage(BaseModel):
    id: str = Field(..., description="Message ID")
    type: str = Field(..., description="Message type (human|ai)")
    content: str = Field(..., description="Message content")
    timestamp: Optional[str] = Field(None, description="Message timestamp")


class ChatSessionResponse(BaseModel):
    id: str = Field(..., description="Session ID")
    title: str = Field(..., description="Session title")
    notebook_id: Optional[str] = Field(None, description="Notebook ID")
    created: str = Field(..., description="Creation timestamp")
    updated: str = Field(..., description="Last update timestamp")
    message_count: Optional[int] = Field(
        None, description="Number of messages in session"
    )
    model_override: Optional[str] = Field(
        None, description="Model override for this session"
    )


class ChatSessionWithMessagesResponse(ChatSessionResponse):
    messages: list[ChatMessage] = Field(
        default_factory=list, description="Session messages"
    )


class ExecuteChatRequest(BaseModel):
    session_id: str = Field(..., description="Chat session ID")
    message: str = Field(..., description="User message content")
    context: dict[str, Any] = Field(
        ..., description="Chat context with sources and notes"
    )
    model_override: Optional[str] = Field(
        None, description="Optional model override for this message"
    )


class ExecuteChatResponse(BaseModel):
    session_id: str = Field(..., description="Session ID")
    messages: list[ChatMessage] = Field(..., description="Updated message list")


class BuildContextRequest(BaseModel):
    notebook_id: str = Field(..., description="Notebook ID")
    context_config: dict[str, Any] = Field(..., description="Context configuration")


class BuildContextResponse(BaseModel):
    context: dict[str, Any] = Field(..., description="Built context data")
    token_count: int = Field(..., description="Estimated token count")
    char_count: int = Field(..., description="Character count")


class SuccessResponse(BaseModel):
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")


@router.get("/chat/sessions", response_model=list[ChatSessionResponse])
async def get_sessions(
    notebook_id: str = Query(..., description="Notebook ID"),
    # v0.7.169 — Pagination follow-through. The right-rail Chat list
    # on every notebook page open used to return EVERY session attached
    # to the notebook with no bound, and each one then paid for a
    # LangGraph checkpoint read (v0.7.161 made those concurrent, but
    # the underlying SELECT was still unbounded). Default cap = 100
    # newest sessions; 1000 hard ceiling.
    limit: int = Query(
        100, ge=1, le=1000,
        description="Max sessions to return (default 100, max 1000).",
    ),
    offset: int = Query(
        0, ge=0,
        description="Sessions to skip for pagination (default 0).",
    ),
):
    """Get all chat sessions for a notebook."""
    try:
        # Get notebook to verify it exists
        notebook = await Notebook.get(notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")

        # Get sessions for this notebook
        # v0.7.169 — pass through `limit` / `offset` so the inner
        # SELECT is bounded server-side.
        sessions_list = await notebook.get_chat_sessions(
            limit=limit, offset=offset,
        )

        # v0.7.161 — N+1 fix: parallelize the per-session LangGraph
        # checkpoint reads. Previously this loop awaited
        # get_session_message_count() sequentially, so a notebook with
        # 50 sessions paid 50 × ~30ms = ~1.5s wall-clock before the
        # right-rail Chat list could render (each call does a
        # sync-in-thread SQLite checkpoint read via the graph_utils
        # helper). With asyncio.gather, those reads run concurrently
        # — wall-clock drops to ~30ms for the single longest read,
        # regardless of session count. The reads themselves are still
        # made; the bigger fix (denormalize total_messages onto the
        # chat_session row at write time) requires a schema migration
        # and a LangGraph checkpoint hook; tracked as deferred.
        msg_counts = await asyncio.gather(*[
            get_session_message_count(chat_graph, str(session.id))
            for session in sessions_list
        ])

        results = [
            ChatSessionResponse(
                id=session.id or "",
                title=session.title or "Untitled Session",
                notebook_id=notebook_id,
                created=str(session.created),
                updated=str(session.updated),
                message_count=msg_count,
                model_override=getattr(session, "model_override", None),
            )
            for session, msg_count in zip(sessions_list, msg_counts)
        ]

        return results
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error fetching chat sessions: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error fetching chat sessions"
        )


@router.post("/chat/sessions", response_model=ChatSessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new chat session."""
    try:
        # Verify notebook exists
        notebook = await Notebook.get(request.notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")

        # Create new session
        session = ChatSession(
            title=request.title
            or f"Chat Session {asyncio.get_event_loop().time():.0f}",
            model_override=request.model_override,
        )
        await session.save()

        # Relate session to notebook
        await session.relate_to_notebook(request.notebook_id)

        return ChatSessionResponse(
            id=session.id or "",
            title=session.title or "",
            notebook_id=request.notebook_id,
            created=str(session.created),
            updated=str(session.updated),
            message_count=0,
            model_override=session.model_override,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error creating chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error creating chat session"
        )


@router.get(
    "/chat/sessions/{session_id}", response_model=ChatSessionWithMessagesResponse
)
async def get_session(session_id: str):
    """Get a specific session with its messages."""
    try:
        # Get session
        # Ensure session_id has proper table prefix
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get session state from LangGraph to retrieve messages
        # Use sync get_state() in a thread since SqliteSaver doesn't support async
        thread_state = await asyncio.to_thread(
            chat_graph.get_state,
            config=RunnableConfig(configurable={"thread_id": full_session_id}),
        )

        # Extract messages from state
        messages: list[ChatMessage] = []
        if thread_state and thread_state.values and "messages" in thread_state.values:
            for msg in thread_state.values["messages"]:
                messages.append(
                    ChatMessage(
                        id=getattr(msg, "id", f"msg_{len(messages)}"),
                        type=msg.type if hasattr(msg, "type") else "unknown",
                        content=msg.content if hasattr(msg, "content") else str(msg),
                        timestamp=None,  # LangChain messages don't have timestamps by default
                    )
                )

        # Find notebook_id (we need to query the relationship)
        # Ensure session_id has proper table prefix
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )

        notebook_query = await repo_query(
            "SELECT out FROM refers_to WHERE in = $session_id",
            {"session_id": ensure_record_id(full_session_id)},
        )

        notebook_id = notebook_query[0]["out"] if notebook_query else None

        if not notebook_id:
            # This might be an old session created before API migration
            logger.warning(
                f"No notebook relationship found for session {session_id} - may be an orphaned session"
            )

        return ChatSessionWithMessagesResponse(
            id=session.id or "",
            title=session.title or "Untitled Session",
            notebook_id=notebook_id,
            created=str(session.created),
            updated=str(session.updated),
            message_count=len(messages),
            messages=messages,
            model_override=getattr(session, "model_override", None),
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error fetching session: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching session")


@router.put("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def update_session(session_id: str, request: UpdateSessionRequest):
    """Update session title."""
    try:
        # Ensure session_id has proper table prefix
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        update_data = request.model_dump(exclude_unset=True)

        if "title" in update_data:
            session.title = update_data["title"]

        if "model_override" in update_data:
            session.model_override = update_data["model_override"]

        await session.save()

        # Find notebook_id
        # Ensure session_id has proper table prefix
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )
        notebook_query = await repo_query(
            "SELECT out FROM refers_to WHERE in = $session_id",
            {"session_id": ensure_record_id(full_session_id)},
        )
        notebook_id = notebook_query[0]["out"] if notebook_query else None

        # Get message count from LangGraph state
        msg_count = await get_session_message_count(chat_graph, full_session_id)

        return ChatSessionResponse(
            id=session.id or "",
            title=session.title or "",
            notebook_id=notebook_id,
            created=str(session.created),
            updated=str(session.updated),
            message_count=msg_count,
            model_override=session.model_override,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error updating session: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating session")


@router.delete("/chat/sessions/{session_id}", response_model=SuccessResponse)
async def delete_session(session_id: str):
    """Delete a chat session."""
    try:
        # Ensure session_id has proper table prefix
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # v0.7.70 — fire the session-end summarizer BEFORE we delete the
        # checkpoint. Session deletion is the explicit "end of
        # conversation" signal: distill the transcript into one memory
        # episode record before the underlying state goes away. Fire-
        # and-forget — failure does not block the delete.
        # v0.7.83 — pass the session's model_override so the summarizer
        # uses the same model the chat was using.
        await _fire_memory_summarize_session(
            full_session_id,
            model_override=getattr(session, "model_override", None),
        )

        await session.delete()

        return SuccessResponse(success=True, message="Session deleted successfully")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting session")


@router.post("/chat/execute", response_model=ExecuteChatResponse)
async def execute_chat(request: ExecuteChatRequest):
    """Execute a chat request and get AI response."""
    try:
        # Verify session exists
        # Ensure session_id has proper table prefix
        full_session_id = (
            request.session_id
            if request.session_id.startswith("chat_session:")
            else f"chat_session:{request.session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Determine model override (per-request override takes precedence over session-level)
        model_override = (
            request.model_override
            if request.model_override is not None
            else getattr(session, "model_override", None)
        )

        # Get current state
        # Use sync get_state() in a thread since SqliteSaver doesn't support async
        current_state = await asyncio.to_thread(
            chat_graph.get_state,
            config=RunnableConfig(configurable={"thread_id": full_session_id}),
        )

        # Prepare state for execution
        state_values = current_state.values if current_state else {}
        state_values["messages"] = state_values.get("messages", [])
        state_values["context"] = request.context
        state_values["model_override"] = model_override

        # Add user message to state
        from langchain_core.messages import HumanMessage

        user_message = HumanMessage(content=request.message)
        state_values["messages"].append(user_message)

        # Execute chat graph
        # v0.7.37 — native async. The v0.6.10 asyncio.to_thread wrapper
        # is no longer needed because the chat-graph node itself is
        # now `async def call_model_with_messages`. LangGraph routes
        # ainvoke() directly to the async node without re-bridging
        # through a thread pool.
        # v0.7.99 — wrap in wait_for so a hung local chat model can't
        # block the non-streaming /chat endpoint indefinitely. Default
        # 300s is generous (chat graphs can do memory recall + tool
        # calls + long generations); cloud users can lower, slow-LLM
        # users can raise. The streaming endpoint /chat/stream is
        # naturally bounded by SSE disconnect handling (v0.7.50+) and
        # doesn't need this wrap.
        _chat_timeout = float(
            os.environ.get("ONP_CHAT_TIMEOUT_SEC", "300").strip() or 300
        )
        try:
            result = await asyncio.wait_for(
                chat_graph.ainvoke(
                    input=state_values,  # type: ignore[arg-type]
                    config=RunnableConfig(
                        configurable={
                            "thread_id": full_session_id,
                            "model_id": model_override,
                        }
                    ),
                ),
                timeout=_chat_timeout,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "Chat /chat: timed out after {}s for session {}",
                _chat_timeout, full_session_id,
            )
            raise HTTPException(
                status_code=504,
                detail=(
                    f"Chat timed out after {_chat_timeout}s. The model may "
                    "be loading, overloaded, or generating a very long "
                    "response. Raise ONP_CHAT_TIMEOUT_SEC, switch to a "
                    "faster model, or try /chat/stream for token-by-token "
                    "responses that surface progress immediately."
                ),
            ) from exc

        # Update session timestamp
        await session.save()

        # v0.7.165 — LangGraph state-shape variance guard. The graph
        # currently returns a TypedDict so `result.get("messages")`
        # works, but the streaming path in this file (lines ~820-836)
        # already applies the dual dict/Pydantic guard because past
        # LangGraph releases have shipped Pydantic-typed states and
        # the CLAUDE.md standing audit calls this out as a recurring
        # footgun (v0.7.52/55/56/75/81/95 are prior fixes for the
        # same pattern). Normalize once at the top so both reads
        # below (response conversion + memory extractor) share the
        # same source-of-truth list.
        result_messages = (
            result.get("messages", []) if isinstance(result, dict)
            else (getattr(result, "messages", None) or [])
        )

        # Convert messages to response format
        messages: list[ChatMessage] = []
        for msg in result_messages:
            messages.append(
                ChatMessage(
                    id=getattr(msg, "id", f"msg_{len(messages)}"),
                    type=msg.type if hasattr(msg, "type") else "unknown",
                    content=msg.content if hasattr(msg, "content") else str(msg),
                    timestamp=None,
                )
            )

        # v0.7.68 — fire the memory extractor for this turn. The user's
        # text is request.message; the assistant's reply is the last
        # AIMessage in the message list. Last-message heuristic is safe
        # here because the chat graph appends exactly one AI response
        # per turn (state["messages"] is a reducer-added list).
        # v0.7.165 — iterate the dual-path-normalized `result_messages`
        # so the Pydantic-state case is covered here too.
        ai_text = ""
        for msg in reversed(result_messages):
            mtype = getattr(msg, "type", None)
            if mtype == "ai":
                ai_text = _extract_text(msg)
                break
        # v0.7.83 — pass model_override (the same one we already
        # resolved at line 348 for the chat graph itself) so the
        # memory worker matches the chat's model.
        await _fire_memory_extract_turn(
            chat_session_id=full_session_id,
            user_text=request.message,
            assistant_text=ai_text,
            model_override=model_override,
        )

        return ExecuteChatResponse(session_id=request.session_id, messages=messages)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        # v0.7.108 — Pre-existing bug exposed by the timeout test:
        # `except Exception as e` below was swallowing the v0.7.99
        # HTTPException(504) raise and re-wrapping it as a 500. Now
        # we re-raise typed HTTPExceptions (404, 504, etc.) so the
        # client sees the right status code + actionable detail.
        # Same fix pattern applies anywhere with `except Exception`
        # around an inner `raise HTTPException(...)`.
        raise
    except Exception as e:
        # Log detailed error with context for debugging
        logger.error(
            f"Error executing chat: {str(e)}\n"
            f"  Session ID: {request.session_id}\n"
            f"  Model override: {request.model_override}\n"
            f"  Traceback:\n{traceback.format_exc()}"
        )
        raise HTTPException(status_code=500, detail="Error executing chat")


# ---------------------------------------------------------------------------
# v0.7.38 — Streaming chat endpoint
#
# Streams tokens as the LLM emits them, instead of buffering the full
# response and returning it as one payload. For local-LLM users (5-30
# tok/s), this turns a 15-30s wall of blank screen into a typewriter-
# style flow — dramatically improves perceived latency.
#
# Wire format: newline-delimited JSON (NDJSON), one event per line. Each
# line is a complete JSON object the frontend can parse without buffering
# partial bytes. Five event types:
#
#   {"type":"start", "session_id":"..."}
#       First event. Signals SSE connection is established.
#
#   {"type":"token", "content":"hello"}
#       One chunk of model output. Concatenate `content` values across
#       all `token` events to reconstruct the message.
#
#   {"type":"done", "messages":[...]}
#       Final event on success. `messages` is the same shape as
#       /chat/execute's response — full history including the AI reply,
#       so the frontend can replace its streaming buffer with canonical
#       state.
#
#   {"type":"error", "detail":"..."}
#       Terminal error. The frontend should surface the detail string.
#
# The endpoint is /chat/stream (alongside /chat/execute which is kept
# for the non-streaming path: tests, scripted clients, OpenAPI consumers
# that don't want SSE).
# ---------------------------------------------------------------------------


async def _stream_chat_events(
    request: ExecuteChatRequest,
    fastapi_request: Request,
) -> AsyncGenerator[str, None]:
    """Generator yielding NDJSON event lines for the streaming endpoint.

    Errors are surfaced as {"type":"error"} events so a partial-stream
    failure doesn't leave the client stuck waiting on a half-written
    response. Client disconnects are detected between yields and stop
    the stream early — important for local LLMs where cancelling a
    long-running token stream actually saves compute.
    """
    try:
        full_session_id = (
            request.session_id
            if request.session_id.startswith("chat_session:")
            else f"chat_session:{request.session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            yield json.dumps({"type": "error", "detail": "Session not found"}) + "\n"
            return

        model_override = (
            request.model_override
            if request.model_override is not None
            else getattr(session, "model_override", None)
        )

        # Get current state — same as /chat/execute
        current_state = await asyncio.to_thread(
            chat_graph.get_state,
            config=RunnableConfig(configurable={"thread_id": full_session_id}),
        )
        state_values = current_state.values if current_state else {}
        state_values["messages"] = state_values.get("messages", [])
        state_values["context"] = request.context
        state_values["model_override"] = model_override

        from langchain_core.messages import HumanMessage

        user_message = HumanMessage(content=request.message)
        state_values["messages"].append(user_message)

        yield json.dumps({
            "type": "start",
            "session_id": request.session_id,
        }) + "\n"

        # Stream events from the LangGraph. astream_events yields a rich
        # event stream — we filter for `on_chat_model_stream` which fires
        # for each token chunk the LLM emits.
        # v0.7.52 — removed dead `last_token_idx` counter (was incremented
        # but never read).
        final_result: Optional[dict[str, Any]] = None
        async for event in chat_graph.astream_events(
            input=state_values,  # type: ignore[arg-type]
            config=RunnableConfig(
                configurable={
                    "thread_id": full_session_id,
                    "model_id": model_override,
                }
            ),
            version="v2",
        ):
            # Stop the stream if the client disconnected — saves the
            # local LLM from churning out tokens nobody will see.
            if await fastapi_request.is_disconnected():
                logger.info(
                    "chat stream: client disconnected for session {}; "
                    "halting", full_session_id,
                )
                return

            etype = event.get("event")
            if etype == "on_chat_model_stream":
                # Event shape: {"event": "on_chat_model_stream",
                #               "data": {"chunk": AIMessageChunk(content="...")}}
                chunk = event.get("data", {}).get("chunk")
                content = getattr(chunk, "content", None)
                if isinstance(content, str) and content:
                    yield json.dumps({
                        "type": "token",
                        "content": content,
                    }) + "\n"
            elif etype == "on_chain_end":
                # The outer graph's on_chain_end carries the final state.
                # We capture it to send the canonical messages list with
                # the done event.
                #
                # v0.7.52 — accept either dict or Pydantic state. LangGraph
                # graphs that declare a TypedDict yield dicts at chain
                # boundaries; graphs that declare a Pydantic BaseModel
                # yield model instances. Our graph happens to use a
                # TypedDict today, but other graphs invoked through the
                # same streaming machinery may not — and an upstream
                # LangGraph release could legitimately change this. The
                # previous `isinstance(output, dict)` guard silently
                # dropped the final result for the Pydantic shape and
                # the stream's `done` event would arrive with messages=[],
                # causing the frontend to fall back to refetching the
                # session — slow and racy.
                data = event.get("data", {})
                output = data.get("output")
                msgs = None
                if isinstance(output, dict):
                    msgs = output.get("messages")
                else:
                    msgs = getattr(output, "messages", None)
                if msgs is not None:
                    # Normalize to a dict either way so downstream code
                    # can stay simple.
                    final_result = (
                        output if isinstance(output, dict)
                        else {"messages": msgs}
                    )

        # Final event with the canonical message list
        messages: list = []
        if final_result and "messages" in final_result:
            for msg in final_result.get("messages", []):
                messages.append({
                    "id": getattr(msg, "id", f"msg_{len(messages)}"),
                    "type": msg.type if hasattr(msg, "type") else "unknown",
                    "content": msg.content if hasattr(msg, "content") else str(msg),
                    "timestamp": None,
                })

        # Update session timestamp (same as /chat/execute)
        try:
            await session.save()
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            logger.warning("chat stream: session save failed: {}", exc)

        # v0.7.68 — fire the memory extractor. Same logic as
        # /chat/execute: the user's text is the inbound request.message,
        # the assistant's reply is the last AIMessage in the final
        # canonical state. Fire-and-forget; failure does NOT take the
        # stream down.
        # v0.7.83 — pass model_override (already resolved as
        # `model_override` in this handler) so memory writer matches
        # the chat's model.
        ai_text = ""
        if final_result and "messages" in final_result:
            for msg in reversed(final_result["messages"]):
                mtype = getattr(msg, "type", None)
                if mtype == "ai":
                    ai_text = _extract_text(msg)
                    break
        await _fire_memory_extract_turn(
            chat_session_id=full_session_id,
            user_text=request.message,
            assistant_text=ai_text,
            model_override=model_override,
        )

        yield json.dumps({"type": "done", "messages": messages}) + "\n"

    except NotFoundError:
        yield json.dumps({"type": "error", "detail": "Session not found"}) + "\n"
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(
            "Error in /chat/stream for session {}: {}\n{}",
            request.session_id, str(e), traceback.format_exc(),
        )
        yield json.dumps({"type": "error", "detail": str(e)}) + "\n"


@router.post("/chat/stream")
async def stream_chat(request: ExecuteChatRequest, fastapi_request: Request):
    """Streaming variant of /chat/execute. NDJSON event stream — see
    _stream_chat_events docstring for wire format."""
    return StreamingResponse(
        _stream_chat_events(request, fastapi_request),
        media_type="application/x-ndjson",
        # Disable HTTP/1.1 keep-alive buffering on the proxy side. Some
        # reverse proxies (and the Next.js dev proxy) hold buffered
        # responses until they hit a flush threshold; X-Accel-Buffering
        # tells nginx-family proxies to disable that.
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-transform",
        },
    )


@router.post("/chat/context", response_model=BuildContextResponse)
async def build_context(request: BuildContextRequest):
    """Build context for a notebook based on context configuration."""
    try:
        # Verify notebook exists
        notebook = await Notebook.get(request.notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")

        context_data: dict[str, list[dict[str, str]]] = {"sources": [], "notes": []}
        total_content = ""

        # Process context configuration if provided
        if request.context_config:
            # Process sources
            for source_id, status in request.context_config.get("sources", {}).items():
                if "not in" in status:
                    continue

                try:
                    # Add table prefix if not present
                    full_source_id = (
                        source_id
                        if source_id.startswith("source:")
                        else f"source:{source_id}"
                    )

                    try:
                        source = await Source.get(full_source_id)
                    except HTTPException:
                        # v0.7.108 — re-raise typed HTTPExceptions so the next
                        # `except Exception` doesn't clobber them to 500.
                        raise
                    except Exception:
                        continue

                    if "insights" in status:
                        source_context = await source.get_context(context_size="short")
                        context_data["sources"].append(source_context)
                        total_content += str(source_context)
                    elif "full content" in status:
                        source_context = await source.get_context(context_size="long")
                        context_data["sources"].append(source_context)
                        total_content += str(source_context)
                except HTTPException:
                    # v0.7.108 — re-raise typed HTTPExceptions so the next
                    # `except Exception` doesn't clobber them to 500.
                    raise
                except Exception as e:
                    logger.warning(f"Error processing source {source_id}: {str(e)}")
                    continue

            # Process notes
            for note_id, status in request.context_config.get("notes", {}).items():
                if "not in" in status:
                    continue

                try:
                    # Add table prefix if not present
                    full_note_id = (
                        note_id if note_id.startswith("note:") else f"note:{note_id}"
                    )
                    note = await Note.get(full_note_id)
                    if not note:
                        continue

                    if "full content" in status:
                        note_context = note.get_context(context_size="long")
                        context_data["notes"].append(note_context)
                        total_content += str(note_context)
                except HTTPException:
                    # v0.7.108 — re-raise typed HTTPExceptions so the next
                    # `except Exception` doesn't clobber them to 500.
                    raise
                except Exception as e:
                    logger.warning(f"Error processing note {note_id}: {str(e)}")
                    continue
        else:
            # Default behavior - include all sources and notes with short context
            sources = await notebook.get_sources()
            for source in sources:
                try:
                    source_context = await source.get_context(context_size="short")
                    context_data["sources"].append(source_context)
                    total_content += str(source_context)
                except HTTPException:
                    # v0.7.108 — re-raise typed HTTPExceptions so the next
                    # `except Exception` doesn't clobber them to 500.
                    raise
                except Exception as e:
                    logger.warning(f"Error processing source {source.id}: {str(e)}")
                    continue

            notes = await notebook.get_notes()
            for note in notes:
                try:
                    note_context = note.get_context(context_size="short")
                    context_data["notes"].append(note_context)
                    total_content += str(note_context)
                except HTTPException:
                    # v0.7.108 — re-raise typed HTTPExceptions so the next
                    # `except Exception` doesn't clobber them to 500.
                    raise
                except Exception as e:
                    logger.warning(f"Error processing note {note.id}: {str(e)}")
                    continue

        # Calculate character and token counts
        char_count = len(total_content)
        # Use token count utility if available
        try:
            from open_notebook.utils import token_count

            estimated_tokens = token_count(total_content) if total_content else 0
        except ImportError:
            # Fallback to simple estimation
            estimated_tokens = char_count // 4

        return BuildContextResponse(
            context=context_data, token_count=estimated_tokens, char_count=char_count
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building context: {str(e)}")
        raise HTTPException(status_code=500, detail="Error building context")
