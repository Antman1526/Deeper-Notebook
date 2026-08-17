# 09 — Configuration & Environment Variables

> **151 registered product settings.** Configuration is centralised, alias-aware, and
> *closed*: an unregistered `DEEPER_NOTEBOOK_*` name raises `KeyError` rather than
> silently reading as unset.

---

## 1. The resolution contract

`deeper_notebook/environment.py` is the single authority.

```
DEEPER_NOTEBOOK_* > DN_* > OPEN_NOTEBOOK_* > ONP_*
```

```python
@dataclass(frozen=True)
class SettingAliases:
    canonical: str
    canonical_short: str | None = None
    legacy: str | None = None
    legacy_short: str | None = None

def _short_aliases(suffix: str) -> SettingAliases:
    return SettingAliases(
        canonical=f"DEEPER_NOTEBOOK_{suffix}",
        canonical_short=f"DN_{suffix}",
        legacy=f"OPEN_NOTEBOOK_{suffix}",
        legacy_short=f"ONP_{suffix}",
    )

def resolve_env(canonical, default=None, *, getter=None, with_receipt=False):
    """Resolve one registered setting without ever exposing its value."""
    aliases = _setting_for(canonical)        # raises KeyError if unregistered
    read = getter or os.environ.get
    values = {name: read(name) for name in aliases.precedence}
    winner = next((n for n in aliases.precedence if values[n] is not None), None)
    ...
    if winner is not None and used_legacy:
        _warn_legacy_once(winner, canonical)   # LegacyEnvironmentWarning, once
```

Two consequences a recreator must honour:

1. **Adding a setting means registering it.** New `DEEPER_NOTEBOOK_X` must be appended to
   `_SHORT_SUFFIXES` (or `_LONG_SUFFIXES`); otherwise the first read throws
   `KeyError: Unknown Deeper Notebook environment setting: …`. This is a feature — it
   catches typos at first use.
2. **Values never appear in receipts or warnings.** Only names.

> **Test-isolation trap.** Product env normalization mirrors a canonical name into its
> legacy spellings. `monkeypatch.setenv` cannot undo writes it did not make, so a test
> that sets `DEEPER_NOTEBOOK_X` leaks "X is set" into later modules via `DN_X`/`ONP_X`.
> Clear **all** spellings — read them from `SETTINGS[...].precedence` rather than
> hardcoding, or patch the predicate function instead of the env.

## 2. Layered configuration

| Layer | Location | Scope |
|---|---|---|
| Defaults | code | Always |
| `.env` | repo root (dev) | Developer machine |
| `config.toml` | `~/.deeper-notebook/config.toml` | Desktop install |
| `launcher.env` | `~/.deeper-notebook/launcher.env` | Launcher prefs UI |
| Process env | shell / launchd | Overrides all |

### `config.toml` (real shape)

```toml
model_dir = '/Users/you/Desktop/MacBook AI models'
provider = 'mlx'                 # 'llamacpp' | 'mlx' | 'none'
default_model = 'MLX/mlx-community__Qwen3.8-27B-4bit'
surreal_user = 'root'
theme = 'tokyo-night'
openchronicle_choice = 'prompt'
execution_policy = 'strict_local'
compute_profile = 'balanced'
local_model_memory_limit_bytes = 25769803776     # 24 GiB
```

`provider` defaults to `'none'`; an invalid value raises at load.

## 3. Required

```bash
DEEPER_NOTEBOOK_ENCRYPTION_KEY=change-me-to-a-secret-string   # ≥16 chars
```

## 4. Setting families (selected, with defaults)

### Database
```
SURREAL_URL=ws://surrealdb:8000/rpc     SURREAL_USER=root
SURREAL_PASSWORD=root                    SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=open_notebook
DEEPER_NOTEBOOK_DB_POOL_SIZE=4           # 1–32
DEEPER_NOTEBOOK_DB_POOL_DISABLED=        # 1 = debug only
DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS=
DEEPER_NOTEBOOK_DISABLE_DB_AUTOREPAIR=
```

### Logging & health
```
DEEPER_NOTEBOOK_LOG_DIR=            # default ~/.deeper-notebook/logs
DEEPER_NOTEBOOK_LOG_LEVEL=INFO      # DEBUG|INFO|WARNING|ERROR
DEEPER_NOTEBOOK_LOG_JSON=0          # 1 → parallel .jsonl sink
DEEPER_NOTEBOOK_METRICS_AUTH_TOKEN=
```

### Chat & context caps
```
DEEPER_NOTEBOOK_CHAT_LLM_CTX=16384         DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX=
DEEPER_NOTEBOOK_CHAT_HISTORY_CHAR_CAP=12000
DEEPER_NOTEBOOK_CHAT_MESSAGE_CHAR_CAP=     DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC=30
DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP=8000
DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP=4000
DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP=1000
DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS=10
DEEPER_NOTEBOOK_AGENT_MAX_ITERATIONS=4      DEEPER_NOTEBOOK_AGENT_FSM=
DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP=12000
DEEPER_NOTEBOOK_ASK_MAX_RESULTS=10          DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP=1500
```

### Web & scholarly search
```
SERPER_API_KEY=      TAVILY_API_KEY=     BRAVE_API_KEY=     SEARXNG_BASE_URL=
DEEPER_NOTEBOOK_WEB_SEARCH_PROVIDER=          # serper|tavily|brave|searxng|wikipedia
DEEPER_NOTEBOOK_WEB_SEARCH_MAX_RESULTS=5      # 1–20
DEEPER_NOTEBOOK_WEB_SEARCH_TIMEOUT_SEC=10     # 1–60
DEEPER_NOTEBOOK_WEB_SEARCH_TOTAL_BUDGET_SEC=25  # 1–120, < 30s tool timeout
DEEPER_NOTEBOOK_WEB_SEARCH_KEYLESS=1          # 0 restores pre-v0.8.82 key-only
DEEPER_NOTEBOOK_WEB_SEARCH_CACHE_TTL_SEC=300  # 0–3600, 0 disables
DEEPER_NOTEBOOK_WEB_SEARCH_WIKI_LANG=en
DEEPER_NOTEBOOK_SCHOLARLY_SEARCH=1
DEEPER_NOTEBOOK_SCHOLARLY_MAILTO=             # OpenAlex polite pool
```

### Memory
```
DEEPER_NOTEBOOK_MEMORY_URL=                DEEPER_NOTEBOOK_MEMORY_BATCH_TURNS=
DEEPER_NOTEBOOK_MEMORY_RECALL_MODE=        DEEPER_NOTEBOOK_MEMORY_RECALL_EPISODES=
DEEPER_NOTEBOOK_MEMORY_RECALL_BUDGET_SEC=  DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR=
DEEPER_NOTEBOOK_MEMORY_KEEP_PER_TABLE=
```

### Feature flags
```
DEEPER_NOTEBOOK_VISUAL_REFRESH=1        DEEPER_NOTEBOOK_EVIDENCE_STUDIO=1
DEEPER_NOTEBOOK_MODEL_FLEET=1           DEEPER_NOTEBOOK_STUDY_WORKBENCH=1
DEEPER_NOTEBOOK_RESEARCH_RUNS=          # default OFF
DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED= # default OFF — the live kill switch
```

### Frontend build-time flags (baked by `next build`)
```
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1     NEXT_PUBLIC_DN_SOURCE_VISUALS=1
NEXT_PUBLIC_DN_EVIDENCE_STUDIO        NEXT_PUBLIC_DN_MODEL_FLEET
NEXT_PUBLIC_DN_RESEARCH_RUNS          NEXT_PUBLIC_DN_STUDY_WORKBENCH
NEXT_PUBLIC_DN_LUMINOUS_FOLIO         NEXT_PUBLIC_DN_VISUAL_REFRESH
NEXT_PUBLIC_API_URL  /  NEXT_PUBLIC_API_BASE     # injected at runtime by the launcher
```

> Only the API URL vars are re-injected at runtime. The feature flags are **frozen at
> build time** — the rollback story for a packaged build is the backend flag alone.

### Build & signing
```
DEEPER_NOTEBOOK_CODESIGN_IDENTITY="Deeper Notebook Local"
BUILD_PYTHON=python3.12
DEEPER_NOTEBOOK_SIDECAR_TCP_TIMEOUT=     DEEPER_NOTEBOOK_API_READY_TIMEOUT=
DEEPER_NOTEBOOK_FRONTEND_READY_TIMEOUT=  DEEPER_NOTEBOOK_SHUTDOWN_GRACE_SECS=
```

### Backup
```
DEEPER_NOTEBOOK_AUTO_EXPORT_HOURS=       DEEPER_NOTEBOOK_AUTO_EXPORT_KEEP=
DEEPER_NOTEBOOK_AUTO_EXPORT_FIRST_DELAY_SECS=
DEEPER_NOTEBOOK_ARTIFACT_EXPORT_DIR=
```

## 5. Validation idioms

Clamp with a safe fallback — a garbage value must never crash a request path:

```python
def _timeout_sec() -> float:
    raw = _env("DEEPER_NOTEBOOK_WEB_SEARCH_TIMEOUT_SEC")
    if not raw: return _DEFAULT_TIMEOUT_SEC
    try: t = float(raw)
    except ValueError: return _DEFAULT_TIMEOUT_SEC
    return max(1.0, min(t, _TIMEOUT_CEILING_SEC))
```

Booleans use a shared truthy set, and blank/whitespace counts as unset:

```python
_TRUTHY = {"1", "true", "t", "yes", "y", "on", "enabled"}
```

A blank API key must **not** enable a provider that then 401s on every turn — hence
`.strip()` in `_env` and emptiness treated as absence.

## 6. Adding a setting — checklist

1. Append the suffix to `_SHORT_SUFFIXES` / `_LONG_SUFFIXES` (alphabetical).
   *If the file has line-pinned rebrand-allowlist entries below your insertion point,
   pack the new names onto an existing line to avoid shifting them — see doc 14.*
2. Add a typed, clamped accessor near its consumer.
3. Document it in `.env.example` with default and range.
4. Test: default, valid override, garbage → fallback.

---

*Continues in [10 — Testing Strategy & Test Cases](./10-testing-strategy-test-cases.md).*
