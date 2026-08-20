"""Memory retriever HTTP shim.

Exposes:
    GET    /health                          → {"status":"ok"}
    GET    /api/memory/relevant?topic&k     → top-K records mix of kinds
    GET    /api/memory/preferences          → all preference records
    GET    /api/memory/facts                → all fact records
    GET    /api/memory/episodes             → all episode records
    GET    /api/memory/search?q             → semantic search across all
    DELETE /api/memory/{kind}/{id}          → forget a specific record
    GET    /api/memory/ambient/status       → bridge state
    POST   /api/memory/ambient/pause        → pause bridge for this session

Run as:
    python -m desktop_shims.memory_shim --port 8767
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from fastapi import FastAPI, HTTPException


def _unwrap(results: Any) -> list:
    """mem0 2.x's Memory.search() returns {"results": [...]}; the test mock
    may return a bare list. Normalize to a list either way."""
    if isinstance(results, dict):
        return list(results.get("results") or [])
    return list(results or [])


def build_app(mem_client: Any, ambient_status_fn=None) -> FastAPI:
    app = FastAPI(title="Deeper Notebook — Memory retriever")
    state = {"ambient_paused": False}

    # mem0 2.x requires every search/add to be scoped to a user/agent/run.
    # We're a single-user desktop app — pin to "local".
    USER_ID = "local"

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # v0.7.209 — `/models` discovery endpoint for the OpenAI-compatible
    # credential probe. Same root cause as the whisper/piper fix in
    # v0.7.207: the connection_tester hits `{base_url}/models` and
    # 404s otherwise. Memory shim's base_url is registered WITHOUT
    # a `/v1` prefix (see desktop/auto_register/memory.py:41), so
    # the endpoint is `/models` here, NOT `/v1/models`. Surface a
    # single OpenAI-shaped entry naming the local memory layer so
    # the credential test in the UI goes green.
    @app.get("/models")
    def list_models() -> dict:
        return {
            "object": "list",
            "data": [
                {
                    "id": "memory-local",
                    "object": "model",
                    "owned_by": "deeper-notebook",
                }
            ],
        }

    @app.get("/api/memory/relevant")
    def relevant(topic: str = "", k: int = 5) -> dict:
        if not topic:
            return {"records": []}
        records = _unwrap(
            mem_client.search(query=topic, top_k=k, filters={"user_id": USER_ID})
        )
        return {"records": records[:k]}

    @app.get("/api/memory/preferences")
    def preferences() -> dict:
        records = _unwrap(
            mem_client.search(
                query="", top_k=200, filters={"user_id": USER_ID, "kind": "preference"}
            )
        )
        return {"records": records}

    @app.get("/api/memory/facts")
    def facts() -> dict:
        records = _unwrap(
            mem_client.search(
                query="", top_k=200, filters={"user_id": USER_ID, "kind": "fact"}
            )
        )
        return {"records": records}

    @app.get("/api/memory/episodes")
    def episodes() -> dict:
        records = _unwrap(
            mem_client.search(
                query="", top_k=200, filters={"user_id": USER_ID, "kind": "episode"}
            )
        )
        return {"records": records}

    @app.get("/api/memory/search")
    def search(q: str) -> dict:
        if not q:
            return {"records": []}
        records = _unwrap(
            mem_client.search(query=q, top_k=50, filters={"user_id": USER_ID})
        )
        return {"records": records}

    # Map the user-facing kind names (fact/preference/episode) to the actual
    # SurrealDB table names mem0 stores under. `memory_id` in SurrealMemoryStore
    # is a full record reference like `memory_fact:abc-123` — without this
    # mapping, DELETE `fact:abc` references a non-existent table.
    from desktop.memory.constants import KIND_TO_TABLE as _KIND_TO_TABLE

    @app.delete("/api/memory/{kind}/{id}")
    def delete(kind: str, id: str) -> dict:
        table = _KIND_TO_TABLE.get(kind)
        if table is None:
            raise HTTPException(status_code=400, detail="invalid kind")
        # Defense in depth: reject ids containing anything outside the safe
        # whitelist before forwarding to mem0 / SurrealQL.
        import re as _re

        if not _re.fullmatch(r"[A-Za-z0-9_\-]+", id):
            raise HTTPException(status_code=400, detail="invalid id")
        mem_client.delete(memory_id=f"{table}:{id}")
        return {"ok": True}

    @app.get("/api/memory/ambient/status")
    def ambient_status() -> dict:
        if ambient_status_fn is None:
            return {"available": False, "paused": state["ambient_paused"]}
        return {**ambient_status_fn(), "paused": state["ambient_paused"]}

    @app.post("/api/memory/ambient/pause")
    def ambient_pause() -> dict:
        state["ambient_paused"] = True
        return {"ok": True}

    # --- ONP v0.5 — OpenChronicle Capture Inbox ----------------------------
    # The dashboard's Capture Inbox calls /api/memory/capture/approve after
    # the user clicks "Save as fact / preference / episode" on a recent
    # OpenChronicle event. We commit it via mem_client.add (same path as the
    # writer worker), with source attribution baked into metadata.

    @app.post("/api/memory/capture/approve")
    def capture_approve(body: dict) -> dict:
        text = (body.get("text") or "").strip()
        kind = body.get("kind") or "fact"
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        if kind not in ("fact", "preference", "episode"):
            raise HTTPException(status_code=400, detail="invalid kind")
        metadata = {
            "kind": kind,
            "scope": "user",
            "source": "openchronicle",
            "source_app": body.get("source_app", ""),
            "source_event_id": body.get("event_id", ""),
            "captured_at": body.get("ts", ""),
        }
        mem_client.add(
            messages=text,
            user_id=USER_ID,
            metadata=metadata,
        )
        return {"ok": True}

    # --- ONP v0.5.8 — edit-in-place for memory rows ------------------------
    # The dashboard's "Edit" button posts here. mem0's Memory.update handles
    # re-embedding so semantic search reflects the new text.

    @app.post("/api/memory/update")
    def memory_update(body: dict) -> dict:
        kind = body.get("kind")
        rid = (body.get("id") or "").strip()
        text = (body.get("text") or "").strip()
        if kind not in _KIND_TO_TABLE:
            raise HTTPException(status_code=400, detail="invalid kind")
        if not rid:
            raise HTTPException(status_code=400, detail="id required")
        if not text:
            raise HTTPException(status_code=400, detail="text required")
        table = _KIND_TO_TABLE[kind]
        # mem0's Memory.update takes the full record id (table:id). The data
        # dict is the new memory content; mem0 re-embeds before persisting.
        memory_id = rid if ":" in rid else f"{table}:{rid}"
        try:
            mem_client.update(memory_id=memory_id, data=text)
        except Exception as exc:
            # mem0 raises on unknown id / bad shape — surface as 400
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--surreal-url", required=True)
    parser.add_argument("--embed-url", required=True)
    parser.add_argument("--llm-url", required=True)
    args = parser.parse_args(argv)

    # Lazy imports — only at runtime
    from desktop.config import default_config_path, load_or_create
    from desktop.memory.client import build_memory_client

    cfg = load_or_create(default_config_path())
    mem_client = build_memory_client(
        cfg=cfg,
        surreal_url=args.surreal_url,
        embed_url=args.embed_url,
        llm_url=args.llm_url,
    )
    app = build_app(mem_client=mem_client)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
