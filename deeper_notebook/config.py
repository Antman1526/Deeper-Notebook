import os

# ROOT DATA FOLDER
# v0.7.147 — Honor `DATA_FOLDER` env var (falls back to legacy "./data"
# when unset, so existing Docker / dev workflows are unaffected). The
# desktop launcher injects an absolute path under
# `~/.deeper-notebook/data/` because when the .app is launched from
# a mounted DMG (read-only) the CWD-relative "./data" raised
# `OSError: [Errno 30] Read-only file system: './data'` at module
# import time, crashing uvicorn before it bound a port. The launcher
# would then wait 180s for /readyz, time out, and exit silently from
# Finder's perspective — the "app won't open" incident on 2026-05-20.
DATA_FOLDER = os.environ.get("DATA_FOLDER", "").strip() or "./data"

# LANGGRAPH CHECKPOINT FILE
sqlite_folder = f"{DATA_FOLDER}/sqlite-db"
os.makedirs(sqlite_folder, exist_ok=True)
LANGGRAPH_CHECKPOINT_FILE = f"{sqlite_folder}/checkpoints.sqlite"

# UPLOADS FOLDER
UPLOADS_FOLDER = f"{DATA_FOLDER}/uploads"
os.makedirs(UPLOADS_FOLDER, exist_ok=True)

# TIKTOKEN CACHE FOLDER
# Reads TIKTOKEN_CACHE_DIR from the environment so Docker can redirect the cache
# to a path outside /data/ (which is typically volume-mounted and would hide the
# pre-baked encoding baked into the image at build time).
TIKTOKEN_CACHE_DIR = (
    os.environ.get("TIKTOKEN_CACHE_DIR", "").strip() or f"{DATA_FOLDER}/tiktoken-cache"
)
os.makedirs(TIKTOKEN_CACHE_DIR, exist_ok=True)
