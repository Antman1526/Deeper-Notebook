"""v0.7.184 — Backend HIGH-severity audit fixes.

Three independent bugs surfaced by the round-9 audit:

1.  Notebook.delete() chat-session cascade used `DELETE $ids` —
    invalid SurrealQL syntax. The query silently no-op'd (or
    errored, driver-dependent), so EVERY chat_session row that
    ever pointed at a deleted notebook leaked into the database.
    DATA INTEGRITY bug across the v0.7.61-v0.7.183 window. Fixed
    by switching to `DELETE chat_session WHERE id IN $ids`.

2.  /chat/stream had a `except NotFoundError:` handler that shadowed
    the v0.7.183 bulk-inserted `except (NotFoundError, InvalidInputError):
    raise` — making the v0.7.183 clause unreachable AND incorrect
    for a streaming context anyway (the HTTP response has already
    started; we can't change the status code mid-stream). Narrowed
    the v0.7.183 bulk handler to `except InvalidInputError as e:`
    + yield-as-event, matching the NotFoundError treatment.

3.  /sources/{id}/process (sync mode) raised
    `HTTPException(500, detail=f"Processing failed: {result.error_message}")`
    — the worker-side error message could carry SurrealDB driver
    frames, partial RecordIDs, file paths. Same info-leak class
    v0.7.168/v0.7.177 sanitised for podcast_service. Tightened to
    a generic detail; logger.error still captures the full message
    for ops.

  Plus: the existing `test_stream_emits_error_event_on_graph_exception`
  test was updated — it had been effectively asserting the str(e)
  leak (`assert "LLM provider unreachable" in err["detail"]`). Now
  asserts the sanitised wire payload and the absence of the raw
  exception text.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Notebook delete cascade — SurrealQL syntax fix
# ---------------------------------------------------------------------------


def test_notebook_delete_uses_valid_surrealql_for_chat_cascade():
    """v0.7.184: the chat-session cascade-delete query must bind
    captured transaction IDs inside a `WHERE id IN ...` clause. The pre-fix
    `DELETE $ids` was invalid SurrealQL and silently leaked every
    chat_session row tied to a deleted notebook."""
    src = _read_source("deeper_notebook/domain/notebook.py")
    # The new, correct form is present.
    assert "DELETE chat_session WHERE id IN $chat_session_ids" in src, (
        "v0.7.184 regression: chat-session cascade-delete reverted "
        "to invalid SurrealQL. Every deleted notebook will leak its "
        "chat_session rows again."
    )
    # And the broken form must NOT be present anymore.
    # (Search for the specific broken shape; not just the substring,
    # since other code may legitimately use `DELETE` differently.)
    bad = '"DELETE $ids"'
    assert bad not in src, (
        "v0.7.184 regression: invalid `DELETE $ids` SurrealQL is back."
    )


# ---------------------------------------------------------------------------
# /chat/stream dead handler removed + sanitised error detail
# ---------------------------------------------------------------------------


def test_chat_stream_handler_no_longer_has_dead_clause():
    """v0.7.184: the v0.7.183 bulk-inserted
    `except (NotFoundError, InvalidInputError): raise` in
    _stream_chat_events was DEAD code (NotFoundError already caught
    above) and SEMANTICALLY WRONG (streaming responses can't
    bubble — the HTTP status has already been emitted). Narrowed
    to InvalidInputError + yield-as-event."""
    src = _read_source("api/routers/chat.py")
    # The explicit NotFoundError handler still exists (correct for
    # streaming: yield error event, don't bubble).
    idx_nf = src.find('"detail": "Session not found"')
    assert idx_nf != -1, (
        "v0.7.184 regression: streaming NotFoundError handler is "
        "gone. Without it, missing-session errors will surface "
        "as bare connection drops instead of structured error "
        "events the frontend can render."
    )

    # The InvalidInputError handler exists in the stream region
    # and yields an event (rather than raising — which would be
    # wrong for streaming context).
    idx_iie = src.find("except InvalidInputError as e:", idx_nf)
    assert idx_iie != -1, (
        "v0.7.184 regression: streaming InvalidInputError handler "
        "is gone or reverted to the v0.7.183 bulk form."
    )


def test_chat_stream_does_not_leak_raw_exception_in_error_event():
    """v0.7.184: the catch-all `except Exception` in
    _stream_chat_events must NOT echo str(e) into the SSE event.
    Driver internals (SurrealDB frames, partial RecordIDs) ride
    that string out to the client.

    Note: yielding str(e) is FINE for typed InvalidInputError —
    those carry controlled, user-facing messages we WROTE. The
    rule is specifically about the generic `except Exception`
    fallback that catches unknown failures."""
    src = _read_source("api/routers/chat.py")
    # Locate the generic `except Exception as e:` block in the
    # streaming generator and confirm its yield does NOT include
    # `str(e)`.
    stream_idx = src.find("async def _stream_chat_events")
    assert stream_idx != -1
    # Find the catch-all in the streaming function (the LAST `except
    # Exception` inside the function body — the generic fallback).
    block = src[stream_idx : src.find("\n\n@router.post", stream_idx)]
    catch_all_idx = block.rfind("except Exception as e:")
    assert catch_all_idx != -1, "couldn't find generic catch-all"
    catch_all_body = block[catch_all_idx : catch_all_idx + 800]
    # The body must NOT yield str(e) directly.
    assert (
        'yield json.dumps({"type": "error", "detail": str(e)})' not in catch_all_body
    ), (
        "v0.7.184 regression: streaming catch-all echoes str(e) "
        "into the SSE error event. Use a generic message; the raw "
        "exception still lives in the log."
    )
    # And the sanitised generic detail is present somewhere in the body.
    assert "Chat stream failed unexpectedly." in catch_all_body


# ---------------------------------------------------------------------------
# sources.py sync processing error_message info leak fixed
# ---------------------------------------------------------------------------


def test_sources_sync_processing_does_not_leak_worker_error_message():
    """v0.7.184: the sync source-processing path used to do
    `HTTPException(500, detail=f"Processing failed: {result.error_message}")`.
    Worker error messages can carry driver frames + partial paths —
    same info-leak class v0.7.177 closed for podcast_service."""
    src = _read_source("api/routers/sources.py")
    bad = 'detail=f"Processing failed: {result.error_message}"'
    assert bad not in src, (
        "v0.7.184 regression: source sync-processing leaks "
        "result.error_message into the 500 detail. Use a generic "
        "message; logger captures the worker text for ops."
    )
    assert 'detail="Source processing failed"' in src
    # And the log line that captures the full message survives.
    assert (
        '"Sync source processing failed for source {}: {}"' in src
        or "Sync source processing failed for source" in src
    ), (
        "v0.7.184 regression: the logger.error that captures the "
        "full error_message for ops is gone. Without it,sanitising "
        "the response leaves no audit trail for the failure."
    )
