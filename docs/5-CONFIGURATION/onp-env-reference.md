# ONP_* Environment Variable Reference

Open Notebook **Plus** introduces a set of `ONP_*` env vars specific
to the desktop / local-first build. They tune the v0.7.x context-
overflow caps, the connection pool, file logging, the source upload
ceiling, and encryption key rotation. **All have sensible defaults
— set them only when you need to deviate.**

This file is the canonical reference. The shorter cheatsheet lives in
`.env.example`.

> All knobs use defensive parsing: garbage values fall back to the
> default with a logged WARNING. Below-minimum values (typo guard)
> also fall back. Watch the API log if a knob isn't taking effect.

---

## Encryption (v0.7.17)

| Variable | Default | Purpose |
|---|---|---|
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` | _(none — required)_ | Single passphrase used to derive the Fernet key. Encrypts API credentials at rest. |
| `OPEN_NOTEBOOK_ENCRYPTION_KEYS` | _(unset)_ | Comma-separated list for rotation. First entry is the active key (used for all new encryption); remaining entries are accepted for decryption only. Overrides the singular var when set. |
| `OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE` | _(unset)_ | Docker-secrets variant: path to a file containing the key. Same precedence as the env var. |

**Rotation workflow:**

1. Set `OPEN_NOTEBOOK_ENCRYPTION_KEYS="new-secret,old-secret"` and restart.
2. (Optional) Run a sweep that calls `re_encrypt_value(blob)` on each
   stored credential. Once swept, the old key is no longer needed.
3. Set `OPEN_NOTEBOOK_ENCRYPTION_KEYS="new-secret"` and restart.

If you drop the old key BEFORE running the sweep, existing data
becomes undecryptable until you re-add it. The error message points
you at this case explicitly.

---

## Logging (v0.7.14)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_LOG_DIR` | `~/.open-notebook-plus/logs` | Directory for rotated log files. Created if missing. |
| `ONP_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `ONP_LOG_JSON` | `0` | Set to `1` for a parallel `<component>.jsonl` file (for log aggregators). |

**Files written:**
- `api.log` (rotated at 20 MB, kept 14 days, gzip-compressed)
- `launcher.log` + `bootstrap.log` (already handled by the desktop bundle)

---

## Health probes (v0.7.15)

These are endpoints, not env vars — listed here for discoverability.

| Endpoint | Use |
|---|---|
| `GET /livez` | Process responding. No I/O. Used by external watchdogs. |
| `GET /readyz` | Full dependency check: DB reachable + migrations applied. 200 on success, 503 on any failure. |
| `GET /health` | Backward-compat alias for `/livez`. |

---

## Source upload byte cap (v0.7.16)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_SOURCE_UPLOAD_MAX_BYTES` | `524288000` (500 MB) | Hard cap on POST /api/sources upload size. Returns 413 if exceeded. Minimum 1 MB (typo guard). |

---

## SurrealDB connection pool (v0.7.18)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_DB_POOL_SIZE` | `4` | Number of pooled `AsyncSurreal` connections. Range 1–32. |
| `ONP_DB_POOL_DISABLED` | _(unset)_ | Set to `1` to fall back to per-query open/close (legacy behavior, useful for debugging). |

---

## Studio one-shot generation (v0.7.4)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_STUDIO_MAX_FILE_CHARS` | `15000` | Per-file character ceiling for the Studio extractor. Local-model-friendly. |
| `ONP_STUDIO_MAX_COMBINED_CHARS` | `60000` | Combined-input ceiling across all files in one Studio request. |

---

## Chat LLM server (v0.7.5, v0.7.8)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_CHAT_LLM_CTX` | `16384` | `--n_ctx` for the spawned `llama-cpp-python` server. Modern local models (Hermes-3, Qwen 2.5/3.x, Mistral-7B, Llama-3.2) support 32k–131k; raise this if your hardware allows. |
| `ONP_CHAT_TIMEOUT_S` | `30` | Per-turn timeout for the memory writer's LLM call. |
| `ONP_CHAT_MODEL_NAME` | `default` | Model name string passed to the local OpenAI-compatible endpoint. Most local servers accept `default` or echo back whatever was loaded. |
| `ONP_CHAT_RAM_GB_CEILING` | _(unset)_ | Optional ceiling for the capability-aware spawner. Skips models the host can't run. |

---

## Ask graph result caps (v0.7.9)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_ASK_MAX_RESULTS` | `10` | Max rows kept from `vector_search` before feeding the LLM. |
| `ONP_ASK_PER_RESULT_CHAR_CAP` | `1500` | Per-result `matches` content cap (truncation marker appended). Minimum 200. |

---

## Transformation input cap (v0.7.10)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_TRANSFORMATION_INPUT_CAP` | `12000` | `source.full_text` (or `input_text`) character cap before the LLM call. Minimum 500. |

---

## Chat history caps (v0.7.11 + v0.7.13)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_CHAT_HISTORY_CHAR_CAP` | `12000` | Total character budget for persisted message history in the standard chat graph. Older turns dropped from the front; current turn always kept. |
| `ONP_SOURCE_CHAT_HISTORY_CHAR_CAP` | `8000` | Same idea, separate knob for source-chat (which already burns context budget on injected source + insight content). |

Both have a minimum of 500. Truncation prepends a `SystemMessage`
marker so the model knows context was elided.

---

## source_chat context caps (v0.7.12)

| Variable | Default | Purpose |
|---|---|---|
| `ONP_SOURCE_CHAT_SOURCE_CHAR_CAP` | `4000` | Source `full_text` cap inside `_format_source_context`. Minimum 500. |
| `ONP_SOURCE_CHAT_INSIGHT_CHAR_CAP` | `1000` | Per-insight content cap. Minimum 200. |
| `ONP_SOURCE_CHAT_MAX_INSIGHTS` | `10` | Max insights injected. Excess elided with a footer noting how many were dropped. |

---

## Piper TTS shim (v0.7.7)

| Variable | Default | Purpose |
|---|---|---|
| (no env var) | _(internal cap)_ | The shim hard-caps a single TTS request at 50,000 chars (about 10 minutes of audio). Callers that need more must split the script into segments. |

---

## Internal / launcher-injected (not user-configurable)

These are set by `desktop/launcher.py` when spawning child processes
and shouldn't be set manually:

- `ONP_MEMORY_URL` — memory-shim endpoint (when the memory bundle is enabled)
- `ONP_MEMORY_INJECTED` — flag indicating memory layer is wired
- `ONP_STT_URL` — local speech-to-text shim endpoint
- `ONP_TTS_URL` — local text-to-speech shim endpoint
- `ONP_VOICE_INJECTED` — flag indicating voice stack is wired
- `ONP_REMIND_OPENCHRONICLE` — first-run wizard reminder flag

---

## Version history of caps

| Version | What changed |
|---|---|
| v0.7.4 | Studio file/combined caps env-driven |
| v0.7.5 | Memory writer timeout + model name env vars |
| v0.7.7 | Piper input cap (internal constant) |
| v0.7.8 | Chat LLM `n_ctx` env var |
| v0.7.9 | Ask graph result + content caps |
| v0.7.10 | Transformation input cap |
| v0.7.11 | Chat message history cap |
| v0.7.12 | source_chat context caps |
| v0.7.13 | source_chat history cap (separate from chat) |
| v0.7.14 | Logging env vars |
| v0.7.16 | Source upload byte cap |
| v0.7.17 | Encryption key rotation (`OPEN_NOTEBOOK_ENCRYPTION_KEYS`) |
| v0.7.18 | DB pool size + disable flag |
