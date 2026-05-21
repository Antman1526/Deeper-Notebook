import asyncio
import json
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from loguru import logger
from pydantic import BaseModel, Field

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import ChatSession, Source
from open_notebook.exceptions import (
    NotFoundError,
)
from open_notebook.graphs.source_chat import source_chat_graph as source_chat_graph
from open_notebook.utils.graph_utils import get_session_message_count

router = APIRouter()


# Request/Response models
class CreateSourceChatSessionRequest(BaseModel):
    source_id: str = Field(..., description="Source ID to create chat session for")
    title: Optional[str] = Field(None, description="Optional session title")
    model_override: Optional[str] = Field(
        None, description="Optional model override for this session"
    )

class UpdateSourceChatSessionRequest(BaseModel):
    title: Optional[str] = Field(None, description="New session title")
    model_override: Optional[str] = Field(
        None, description="Model override for this session"
    )

class ChatMessage(BaseModel):
    id: str = Field(..., description="Message ID")
    type: str = Field(..., description="Message type (human|ai)")
    content: str = Field(..., description="Message content")
    timestamp: Optional[str] = Field(None, description="Message timestamp")


class ContextIndicator(BaseModel):
    sources: list[str] = Field(
        default_factory=list, description="Source IDs used in context"
    )
    insights: list[str] = Field(
        default_factory=list, description="Insight IDs used in context"
    )
    notes: list[str] = Field(
        default_factory=list, description="Note IDs used in context"
    )

class SourceChatSessionResponse(BaseModel):
    id: str = Field(..., description="Session ID")
    title: str = Field(..., description="Session title")
    source_id: str = Field(..., description="Source ID")
    model_override: Optional[str] = Field(
        None, description="Model override for this session"
    )
    created: str = Field(..., description="Creation timestamp")
    updated: str = Field(..., description="Last update timestamp")
    message_count: Optional[int] = Field(
        None, description="Number of messages in session"
    )

class SourceChatSessionWithMessagesResponse(SourceChatSessionResponse):
    messages: list[ChatMessage] = Field(
        default_factory=list, description="Session messages"
    )
    context_indicators: Optional[ContextIndicator] = Field(
        None, description="Context indicators from last response"
    )

class SendMessageRequest(BaseModel):
    message: str = Field(..., description="User message content")
    model_override: Optional[str] = Field(
        None, description="Optional model override for this message"
    )

class SuccessResponse(BaseModel):
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Success message")


@router.post(
    "/sources/{source_id}/chat/sessions", response_model=SourceChatSessionResponse
)
async def create_source_chat_session(
    request: CreateSourceChatSessionRequest,
    source_id: str = Path(..., description="Source ID"),
):
    """Create a new chat session for a source."""
    try:
        # Verify source exists
        full_source_id = (
            source_id if source_id.startswith("source:") else f"source:{source_id}"
        )
        source = await Source.get(full_source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Create new session with model_override support
        session = ChatSession(
            title=request.title or f"Source Chat {asyncio.get_event_loop().time():.0f}",
            model_override=request.model_override,
        )
        await session.save()

        # Relate session to source using "refers_to" relation
        await session.relate("refers_to", full_source_id)

        return SourceChatSessionResponse(
            id=session.id or "",
            title=session.title or "Untitled Session",
            source_id=source_id,
            model_override=session.model_override,
            created=str(session.created),
            updated=str(session.updated),
            message_count=0,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error creating source chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error creating source chat session"
        )


@router.get(
    "/sources/{source_id}/chat/sessions", response_model=list[SourceChatSessionResponse]
)
async def get_source_chat_sessions(source_id: str = Path(..., description="Source ID")):
    """Get all chat sessions for a source."""
    try:
        # Verify source exists
        full_source_id = (
            source_id if source_id.startswith("source:") else f"source:{source_id}"
        )
        source = await Source.get(full_source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Get sessions that refer to this source - first get relations, then sessions
        relations = await repo_query(
            "SELECT in FROM refers_to WHERE out = $source_id",
            {"source_id": ensure_record_id(full_source_id)},
        )

        # v0.7.161 — N+1 fix: previously this loop did TWO sequential
        # round-trips per session (a row fetch + a LangGraph checkpoint
        # read). A source with 30 chat sessions paid 60 sequential
        # network/disk hits. Now we issue both fan-outs concurrently:
        #   1. asyncio.gather all session-row fetches in parallel
        #   2. then asyncio.gather all message-count reads in parallel
        # Each phase has its wall-clock bounded by the slowest single
        # call instead of the sum.
        session_ids: list[str] = [
            str(r["in"]) for r in relations if r.get("in")
        ]
        session_rows = await asyncio.gather(*[
            repo_query("SELECT * FROM $id", {"id": ensure_record_id(sid)})
            for sid in session_ids
        ])
        msg_counts = await asyncio.gather(*[
            get_session_message_count(source_chat_graph, sid)
            for sid in session_ids
        ])

        sessions: list[SourceChatSessionResponse] = []
        for sid, session_result, msg_count in zip(
            session_ids, session_rows, msg_counts
        ):
            if not session_result or len(session_result) == 0:
                # Session record was deleted between the relations
                # query and the fan-out fetch; skip cleanly.
                continue
            session_data = session_result[0]
            sessions.append(
                SourceChatSessionResponse(
                    id=session_data.get("id") or "",
                    title=session_data.get("title") or "Untitled Session",
                    source_id=source_id,
                    model_override=session_data.get("model_override"),
                    created=str(session_data.get("created")),
                    updated=str(session_data.get("updated")),
                    message_count=msg_count,
                )
            )

        # Sort sessions by created date (newest first)
        sessions.sort(key=lambda x: x.created, reverse=True)
        return sessions
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error fetching source chat sessions: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error fetching source chat sessions"
        )


@router.get(
    "/sources/{source_id}/chat/sessions/{session_id}",
    response_model=SourceChatSessionWithMessagesResponse,
)
async def get_source_chat_session(
    source_id: str = Path(..., description="Source ID"),
    session_id: str = Path(..., description="Session ID"),
):
    """Get a specific source chat session with its messages."""
    try:
        # Verify source exists
        full_source_id = (
            source_id if source_id.startswith("source:") else f"source:{source_id}"
        )
        source = await Source.get(full_source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Get session
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify session is related to this source
        relation_query = await repo_query(
            "SELECT * FROM refers_to WHERE in = $session_id AND out = $source_id",
            {
                "session_id": ensure_record_id(full_session_id),
                "source_id": ensure_record_id(full_source_id),
            },
        )

        if not relation_query:
            raise HTTPException(
                status_code=404, detail="Session not found for this source"
            )

        # Get session state from LangGraph to retrieve messages
        # Use sync get_state() in a thread since SqliteSaver doesn't support async
        thread_state = await asyncio.to_thread(
            source_chat_graph.get_state,
            config=RunnableConfig(configurable={"thread_id": full_session_id}),
        )

        # Extract messages from state
        messages: list[ChatMessage] = []
        context_indicators = None

        if thread_state and thread_state.values:
            # Extract messages
            if "messages" in thread_state.values:
                for msg in thread_state.values["messages"]:
                    messages.append(
                        ChatMessage(
                            id=getattr(msg, "id", f"msg_{len(messages)}"),
                            type=msg.type if hasattr(msg, "type") else "unknown",
                            content=msg.content
                            if hasattr(msg, "content")
                            else str(msg),
                            timestamp=None,  # LangChain messages don't have timestamps by default
                        )
                    )

            # Extract context indicators from the last state
            if "context_indicators" in thread_state.values:
                context_data = thread_state.values["context_indicators"]
                context_indicators = ContextIndicator(
                    sources=context_data.get("sources", []),
                    insights=context_data.get("insights", []),
                    notes=context_data.get("notes", []),
                )

        return SourceChatSessionWithMessagesResponse(
            id=session.id or "",
            title=session.title or "Untitled Session",
            source_id=source_id,
            model_override=getattr(session, "model_override", None),
            created=str(session.created),
            updated=str(session.updated),
            message_count=len(messages),
            messages=messages,
            context_indicators=context_indicators,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source or session not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error fetching source chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error fetching source chat session"
        )


@router.put(
    "/sources/{source_id}/chat/sessions/{session_id}",
    response_model=SourceChatSessionResponse,
)
async def update_source_chat_session(
    request: UpdateSourceChatSessionRequest,
    source_id: str = Path(..., description="Source ID"),
    session_id: str = Path(..., description="Session ID"),
):
    """Update source chat session title and/or model override."""
    try:
        # Verify source exists
        full_source_id = (
            source_id if source_id.startswith("source:") else f"source:{source_id}"
        )
        source = await Source.get(full_source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Get session
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify session is related to this source
        relation_query = await repo_query(
            "SELECT * FROM refers_to WHERE in = $session_id AND out = $source_id",
            {
                "session_id": ensure_record_id(full_session_id),
                "source_id": ensure_record_id(full_source_id),
            },
        )

        if not relation_query:
            raise HTTPException(
                status_code=404, detail="Session not found for this source"
            )

        # Update session fields
        if request.title is not None:
            session.title = request.title
        if request.model_override is not None:
            session.model_override = request.model_override

        await session.save()

        # Get message count from LangGraph state
        msg_count = await get_session_message_count(source_chat_graph, full_session_id)

        return SourceChatSessionResponse(
            id=session.id or "",
            title=session.title or "Untitled Session",
            source_id=source_id,
            model_override=getattr(session, "model_override", None),
            created=str(session.created),
            updated=str(session.updated),
            message_count=msg_count,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source or session not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error updating source chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error updating source chat session"
        )


@router.delete(
    "/sources/{source_id}/chat/sessions/{session_id}", response_model=SuccessResponse
)
async def delete_source_chat_session(
    source_id: str = Path(..., description="Source ID"),
    session_id: str = Path(..., description="Session ID"),
):
    """Delete a source chat session."""
    try:
        # Verify source exists
        full_source_id = (
            source_id if source_id.startswith("source:") else f"source:{source_id}"
        )
        source = await Source.get(full_source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Get session
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify session is related to this source
        relation_query = await repo_query(
            "SELECT * FROM refers_to WHERE in = $session_id AND out = $source_id",
            {
                "session_id": ensure_record_id(full_session_id),
                "source_id": ensure_record_id(full_source_id),
            },
        )

        if not relation_query:
            raise HTTPException(
                status_code=404, detail="Session not found for this source"
            )

        await session.delete()

        return SuccessResponse(
            success=True, message="Source chat session deleted successfully"
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Source or session not found")
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error deleting source chat session: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error deleting source chat session"
        )


async def stream_source_chat_response(
    session_id: str,
    source_id: str,
    message: str,
    model_override: Optional[str] = None,
    fastapi_request: Optional["Request"] = None,
) -> AsyncGenerator[str, None]:
    """Stream the source chat response as Server-Sent Events.

    v0.7.42 — REAL token streaming. The previous implementation called
    `await source_chat_graph.ainvoke(...)` which blocked until the
    entire AI message was built, then yielded one
    `{"type":"ai_message", "content": <full>}` event. For local 5-30
    tok/s LLMs a 400-token answer hung the source-chat UI 13-80s with
    no incremental output. Mirrors the notebook-chat streaming wired
    in v0.7.38.

    Event types emitted:
      - `user_message`         — confirms the user message landed
      - `ai_message_delta`     — one LLM token chunk (concat to build)
      - `ai_message`           — terminal full text (canonical final
                                  value once streaming finishes; also
                                  acts as a fallback for clients that
                                  ignore deltas)
      - `context_indicators`   — final source/insight references
      - `complete`             — done
      - `error`                — terminal failure
    """
    try:
        # Get current state — SqliteSaver.get_state is still sync.
        current_state = await asyncio.to_thread(
            source_chat_graph.get_state,
            config=RunnableConfig(configurable={"thread_id": session_id}),
        )

        # Prepare state for execution
        state_values = current_state.values if current_state else {}
        state_values["messages"] = state_values.get("messages", [])
        state_values["source_id"] = source_id
        state_values["model_override"] = model_override

        # Add user message to state
        user_message = HumanMessage(content=message)
        state_values["messages"].append(user_message)

        # Send user message event
        user_event = {"type": "user_message", "content": message, "timestamp": None}
        yield f"data: {json.dumps(user_event)}\n\n"

        # v0.7.42 — token streaming via LangGraph astream_events. The
        # source_chat_graph node is `async def` (v0.7.37) so this
        # routes natively. We collect:
        #   - on_chat_model_stream events → ai_message_delta events
        #   - on_chain_end terminal event with final state → context_indicators
        accumulated_content = ""
        final_state: Optional[dict] = None
        async for event in source_chat_graph.astream_events(
            input=state_values,  # type: ignore[arg-type]
            config=RunnableConfig(
                configurable={"thread_id": session_id, "model_id": model_override}
            ),
            version="v2",
        ):
            # Early-cancel parity with /chat/stream — stop generation
            # the moment the client gives up on the response.
            if fastapi_request is not None and await fastapi_request.is_disconnected():
                logger.info(
                    "source chat stream: client disconnected for "
                    "session {}; halting", session_id,
                )
                return

            etype = event.get("event")
            if etype == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                content = getattr(chunk, "content", None)
                if isinstance(content, str) and content:
                    accumulated_content += content
                    yield (
                        "data: "
                        + json.dumps({
                            "type": "ai_message_delta",
                            "content": content,
                        })
                        + "\n\n"
                    )
            elif etype == "on_chain_end":
                # Capture the outer chain's final state — has
                # context_indicators + canonical messages.
                # v0.7.56 — accept both dict and Pydantic state shapes
                # (same root cause as v0.7.52 chat.py fix). If LangGraph
                # ever yields a model instance the SSE consumer would
                # otherwise never see the terminal context_indicators
                # event.
                output = event.get("data", {}).get("output")
                if isinstance(output, dict):
                    final_state = output
                elif output is not None and hasattr(output, "messages"):
                    final_state = {
                        "messages": getattr(output, "messages", None),
                        "context_indicators": getattr(
                            output, "context_indicators", None
                        ),
                    }

        # Emit the terminal ai_message event so clients that ignore
        # the deltas still see a single canonical "full message" event
        # (back-compat with anything written for the v0.6.x SSE
        # contract before v0.7.42).
        if accumulated_content:
            yield (
                "data: "
                + json.dumps({
                    "type": "ai_message",
                    "content": accumulated_content,
                    "timestamp": None,
                })
                + "\n\n"
            )

        # Stream context indicators
        if final_state and "context_indicators" in final_state:
            yield (
                "data: "
                + json.dumps({
                    "type": "context_indicators",
                    "data": final_state["context_indicators"],
                })
                + "\n\n"
            )

        # Send completion signal
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        from open_notebook.utils.error_classifier import classify_error

        _, user_friendly_message = classify_error(e)
        logger.error(f"Error in source chat streaming: {str(e)}")
        error_event = {"type": "error", "message": user_friendly_message}
        yield f"data: {json.dumps(error_event)}\n\n"


@router.post("/sources/{source_id}/chat/sessions/{session_id}/messages")
async def send_message_to_source_chat(
    request: SendMessageRequest,
    fastapi_request: Request,
    source_id: str = Path(..., description="Source ID"),
    session_id: str = Path(..., description="Session ID"),
):
    """Send a message to source chat session with SSE streaming response."""
    try:
        # Verify source exists
        full_source_id = (
            source_id if source_id.startswith("source:") else f"source:{source_id}"
        )
        source = await Source.get(full_source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Verify session exists and is related to source
        full_session_id = (
            session_id
            if session_id.startswith("chat_session:")
            else f"chat_session:{session_id}"
        )
        session = await ChatSession.get(full_session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify session is related to this source
        relation_query = await repo_query(
            "SELECT * FROM refers_to WHERE in = $session_id AND out = $source_id",
            {
                "session_id": ensure_record_id(full_session_id),
                "source_id": ensure_record_id(full_source_id),
            },
        )

        if not relation_query:
            raise HTTPException(
                status_code=404, detail="Session not found for this source"
            )

        if not request.message:
            raise HTTPException(status_code=400, detail="Message content is required")

        # Determine model override (request override takes precedence over session override)
        model_override = request.model_override or getattr(
            session, "model_override", None
        )

        # Update session timestamp
        await session.save()

        # Return streaming response
        return StreamingResponse(
            stream_source_chat_response(
                session_id=full_session_id,
                source_id=full_source_id,
                message=request.message,
                model_override=model_override,
                fastapi_request=fastapi_request,
            ),
            media_type="text/plain",
            headers={
                # v0.7.42 — same proxy-flush hints v0.7.38 uses on
                # /chat/stream so each SSE event lands client-side
                # immediately, not buffered.
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "Content-Type": "text/plain; charset=utf-8",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message to source chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Error sending message")
