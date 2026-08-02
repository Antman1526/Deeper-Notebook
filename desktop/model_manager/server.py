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

from desktop.data_root import active_data_root

STATIC_DIR = Path(__file__).parent / "static"
CATALOG_PATH = Path(__file__).parent / "catalog.json"
CONFIG_PATH_KEY = web.AppKey("config_path", Path)

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


def build_app(
    model_dir: Path, *, config_path: Path | None = None
) -> web.Application:
    app = web.Application()
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    config_path = (
        Path(config_path)
        if config_path is not None
        else active_data_root() / "config.toml"
    )
    app[CONFIG_PATH_KEY] = config_path

    async def index(_: web.Request) -> web.Response:
        if (STATIC_DIR / "index.html").exists():
            return web.FileResponse(STATIC_DIR / "index.html")
        return web.Response(text="<html><body>Model Manager (static UI not built yet)</body></html>",
                            content_type="text/html")

    async def theme(_: web.Request) -> web.Response:
        try:
            raw = tomllib.loads(config_path.read_text())
            t = raw.get("theme", "research-core-dark")
        except Exception:
            t = "research-core-dark"
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
        # v0.6.31 — path-traversal hardening. The previous check used
        # `str(target).startswith(str(model_dir.resolve()))` which has a
        # well-known prefix bug: if model_dir is "/Users/foo/models" and
        # `rel` resolves to "/Users/foo/models_evil/x.gguf", the str
        # comparison passes (because "/Users/foo/models_evil/..." literally
        # starts with "/Users/foo/models"). Use Path.is_relative_to which
        # operates on path components, not raw strings.
        try:
            target = (model_dir / rel).resolve()
        except (OSError, ValueError):
            return web.json_response({"error": "invalid path"}, status=400)
        root = model_dir.resolve()
        if not target.is_relative_to(root):
            return web.json_response({"error": "invalid path"}, status=400)
        # Refuse to follow symlinks that point outside model_dir — the
        # resolve() above already canonicalizes them, so any symlink chain
        # ending outside the dir is caught by is_relative_to. But also
        # guard the target itself against being a symlink to a sensitive
        # path, just in case: only allow regular files (not symlinks,
        # not dirs).
        if target.is_symlink() or (target.exists() and not target.is_file()):
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
