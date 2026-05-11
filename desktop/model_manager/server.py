"""Aiohttp server backing the Model Manager PyWebView window.

Exposes:
    GET    /                              → static UI
    GET    /api/installed                 → list of installed models by class
    GET    /api/catalog                   → curated downloadable models
    GET    /api/theme                     → {"theme": "<name>"} from user config
    POST   /api/download                  → {category, name} — kick off a download
    DELETE /api/installed/<rel-path>      → remove a model file
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from aiohttp import web

STATIC_DIR = Path(__file__).parent / "static"
CATALOG_PATH = Path(__file__).parent / "catalog.json"
_CONFIG_PATH = Path(os.environ.get("HOME", "~")) / ".open-notebook-plus" / "config.toml"

_MIN_BYTES = 100_000


def _classify(rel: str) -> str:
    if rel.startswith("STT/"):
        return "stt"
    if rel.startswith("TTS/") and rel.endswith(".onnx"):
        return "tts"
    if rel.startswith("GGUF/") and (
            "embed" in rel.lower() or "bge" in rel.lower() or "nomic" in rel.lower()):
        return "embedding"
    return "chat"


def build_app(model_dir: Path) -> web.Application:
    app = web.Application()
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    async def index(_: web.Request) -> web.Response:
        if (STATIC_DIR / "index.html").exists():
            return web.FileResponse(STATIC_DIR / "index.html")
        return web.Response(text="<html><body>Model Manager (static UI not built yet)</body></html>",
                            content_type="text/html")

    async def theme(_: web.Request) -> web.Response:
        try:
            raw = tomllib.loads(_CONFIG_PATH.read_text())
            t = raw.get("theme", "light-blue")
        except Exception:
            t = "light-blue"
        return web.json_response({"theme": t})

    async def installed(_: web.Request) -> web.Response:
        models = []
        if model_dir.exists():
            for p in model_dir.rglob("*"):
                if p.is_file() and p.stat().st_size >= _MIN_BYTES:
                    rel = str(p.relative_to(model_dir))
                    models.append({
                        "name": p.name,
                        "rel": rel,
                        "size_mb": p.stat().st_size // 1024 // 1024,
                        "class": _classify(rel),
                    })
        return web.json_response({"models": models})

    async def catalog(_: web.Request) -> web.Response:
        if CATALOG_PATH.exists():
            return web.json_response(json.loads(CATALOG_PATH.read_text()))
        return web.json_response({})

    async def delete_model(req: web.Request) -> web.Response:
        rel = req.match_info["rel"]
        # Defensive: refuse paths trying to escape model_dir
        target = (model_dir / rel).resolve()
        if not str(target).startswith(str(model_dir.resolve())):
            return web.json_response({"error": "invalid path"}, status=400)
        if target.exists():
            target.unlink()
            return web.json_response({"ok": True})
        return web.json_response({"error": "not found"}, status=404)

    app.router.add_get("/", index)
    app.router.add_get("/api/installed", installed)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_get("/api/theme", theme)
    app.router.add_delete("/api/installed/{rel:.+}", delete_model)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR)
    return app
