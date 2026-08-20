"""HTTP bridge from Deeper Notebook to OpenChronicle's MCP daemon.

OpenChronicle exposes (per https://github.com/Einsia/OpenChronicle):
  recent_activity({minutes: int}) → list of screen events
  search({query: str, limit: int}) → topic-matched events

We translate those into a small HTTP API the memory retriever can consume.

Run as:
    python -m desktop_shims.openchronicle_shim --port 8768 \\
        --mcp-url http://127.0.0.1:8742/mcp
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from fastapi import FastAPI, HTTPException


def build_app(mcp_client: Any) -> FastAPI:
    app = FastAPI(title="Deeper Notebook — OpenChronicle bridge")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    async def _call(tool: str, args: dict) -> dict:
        try:
            return await mcp_client.call_tool(tool, args)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/context/recent")
    async def recent(minutes: int = 10) -> dict:
        return await _call("recent_activity", {"minutes": minutes})

    @app.get("/context/search")
    async def search(topic: str, limit: int = 5) -> dict:
        return await _call("search", {"query": topic, "limit": limit})

    return app


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    # OPENCHRONICLE_MCP_URL env var overrides the default for users who run
    # OpenChronicle on a non-standard port (P1-MED-10 audit fix).
    parser.add_argument(
        "--mcp-url",
        default=os.environ.get("OPENCHRONICLE_MCP_URL", "http://127.0.0.1:8742/mcp"),
    )
    args = parser.parse_args(argv)

    # Lazy import; only when running for real.
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    class _PerCallMcpClient:
        """Opens a fresh MCP session per tool call.

        We can't hold a session across HTTP requests because `streamablehttp_client`
        and `ClientSession` are async context managers — once the `with` blocks
        exit, the connection is closed. Per-call setup adds ~50–100 ms latency but
        is simple, correct, and reconnects automatically if OpenChronicle
        restarts.
        """

        def __init__(self, url: str):
            self._url = url

        async def call_tool(self, name: str, arguments: dict) -> dict:
            async with streamablehttp_client(self._url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    return (
                        result.model_dump() if hasattr(result, "model_dump") else result
                    )

    app = build_app(mcp_client=_PerCallMcpClient(args.mcp_url))

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
