# 12 — Error Handling & Logging

> Governing principle: **a failure in an optional subsystem must never abort a chat turn
> or the application launch.** Everything below is an elaboration of that rule, plus the
> counter-rule that fail-soft must never mean fail-*silent*.

---

## 1. Exception taxonomy

`deeper_notebook/exceptions.py` defines the typed set; `api/main.py` maps them:

| Exception | HTTP | Meaning |
|---|---|---|
| `NotFoundError` | 404 | Record absent |
| `InvalidInputError` | 400 | Validation failure |
| `ConfigurationError` | 500 | Impossible configuration (e.g. offline + cloud + no local) |
| `StudyAssistantPolicyError` | 403 | Scope/authority violation |
| `OutboundURLPolicyError` | 400 | URL failed the SSRF boundary |
| `SourceVisualStorageError` | 409 | Cache/authority conflict |

**Re-raise typed exceptions before the broad catch**, or the global handlers never see
them and legitimate 404/400s become 500s:

```python
except HTTPException:
    raise
except (NotFoundError, InvalidInputError):
    raise                                  # v0.7.179
except Exception as e:
    logger.error(f"Error fetching notebooks: {str(e)}")
    raise HTTPException(status_code=500, detail="Error fetching notebooks")
```

Note the asymmetry: the log gets the exception text, the client gets a fixed string.

## 2. Degradation patterns

### Best-effort with a WARNING (a *configured* thing failed)

```python
except Exception as exc:
    # WARNING (not DEBUG): a configured attempt failing is worth seeing. We log
    # provider + instance URL + error text — NEVER the API key (which lives in
    # headers/body, not in exc's string form for these endpoints).
    logger.warning("web_search attempt via {}{} failed: {}",
                   provider, f" ({target})" if target else "", exc)
    continue
```

### Fail-soft with DEBUG (an *expected* absence)

```python
except Exception as bind_exc:
    _logger.debug("tool bind failed (degrading to no-tools): {}", bind_exc)
    mcp_tools = []
```

Severity encodes expectation: local models that can't tool-call are normal (DEBUG); a
configured provider erroring is not (WARNING).

### Fail-open (the guard must never be the failure)

```python
# offline_gate — any internal error returns the original candidate.
# The ONLY raise is ConfigurationError when offline + cloud + no local model:
# that turn was going to fail anyway, so fail fast with an actionable message
# instead of a 300s hang.
```

### Fail-loud when silence hid the cause

```python
# MlxProvider.start — v0.8.84
if not path.exists():
    raise FileNotFoundError(
        f"Configured MLX model no longer exists on disk: {path} — "
        "pick an existing model in Launch Preferences")
```

...caught one level up so the launch continues without the provider:

```python
except FileNotFoundError as exc:
    log.error("MLX model provider disabled for this launch: %s", exc)
else:
    extra_env["DEEPER_NOTEBOOK_ACTIVE_MLX_MODEL"] = model
    ctx.model_provider_runtime = provider
```

This exact defect — a deleted configured model, spawned anyway with `stderr=DEVNULL`,
dying silently, leaving a credential on a dead port — presented only as a "Degraded"
badge with no cause. It cost hours.

## 3. Logging architecture

Loguru. Sinks:

| Sink | Path | Content |
|---|---|---|
| launcher | `~/.deeper-notebook/logs/launcher.log` | Phases, ports, sidecar lifecycle |
| api | `…/api.log` | Request lines, errors |
| surreal | `…/surreal.log` | DB engine |
| worker | `…/worker.log` | Background jobs |
| llamacpp_chat/embed | `…/llamacpp_*.log` | Sidecar stdout+stderr |
| whisper / piper | `…/whisper.log`, `piper.log` | Voice sidecars |
| mlx | `…/mlx_server.log` | **v0.8.85** — was DEVNULL |
| bootstrap | `…/bootstrap.log`, `bootstrap-subprocess.log` | venv provisioning |
| `.tail` files | `…/<child>.tail` | Last ~50 stderr lines per sidecar |

```
DEEPER_NOTEBOOK_LOG_DIR=      DEEPER_NOTEBOOK_LOG_LEVEL=INFO      DEEPER_NOTEBOOK_LOG_JSON=0
```

### Sidecar stderr capture (v0.8.38)

```python
if self.debug_mode:
    stdout, stderr = subprocess.PIPE, subprocess.PIPE
else:
    stdout = subprocess.DEVNULL
    stderr = subprocess.PIPE      # drained to a tail-only file
```

Cost: one drainer thread + a tiny rolling file per sidecar. Benefit: when a sidecar
crashes (bad GGUF, OOM, port collision), the API can surface the real cause via
`/healthz/sidecars/{kind}/log` instead of a stale "down" badge. **Never use `PIPE` without
a reader** — the OS buffer fills and the child deadlocks.

### Bounded logs

```python
_BOOTSTRAP_LOG_MAX_BYTES = 5 * 1024 * 1024
def _rotate_log_if_oversized(log_path: Path) -> None:
    try:
        if log_path.exists() and log_path.stat().st_size > _BOOTSTRAP_LOG_MAX_BYTES:
            old = log_path.with_suffix(log_path.suffix + ".old")
            old.unlink(missing_ok=True)
            log_path.rename(old)
    except Exception:
        pass  # never fatal
```

### Subprocess failures carry evidence

```python
if proc.returncode != 0:
    tail = log_path.read_text(errors="replace").splitlines()[-25:]
    raise RuntimeError(
        f"[{tag}] subprocess failed with exit={proc.returncode}. "
        f"Last 25 lines of {log_path}:\n" + "\n".join(tail))
```

Without this, errors from `uv pip install` vanished entirely when the .app was launched
from Finder (no attached terminal).

## 4. What must never be logged

- API keys, tokens, passwords — including inside exception text from providers that echo
  request bodies
- Encryption keys, `.env` values
- Source content or note bodies (user data)
- Full record payloads (ids only)

`resolve_env` deliberately returns values but records only **names** in receipts and
deprecation warnings.

## 5. Health & monitoring

| Endpoint | Purpose |
|---|---|
| `/livez` | Process alive |
| `/readyz` | Dependencies ready |
| `/healthz/deep` | Deep dependency check |
| `/healthz/sidecars/{kind}/log` | Tail of a sidecar's stderr |
| `/api/local-models/health` | Per-model probe with latency |
| `/api/runtime/snapshot` | Bounded runtime projection |
| `/metrics` | Prometheus (token-guarded) |

Startup receipts (`~/.deeper-notebook/startup_receipt.json`) record staged timings:

```json
{ "schema_version": 1,
  "stages": [ {"stage": "chat_model_scan", "elapsed_ms": 2195},
              {"stage": "core_ready", "elapsed_ms": 97398} ] }
```

Surfaced in the UI for stages ≥ 100 ms, so a slow launch is diagnosable without the log
directory.

## 6. Debugging playbook

| Symptom | First move |
|---|---|
| No window, sidecars stalled | `sample <pid>`; `os_scandir → open$NOCANCEL` = TCC consent wedge |
| Model "Degraded", no cause | `~/.deeper-notebook/logs/mlx_server.log`, then `/healthz/sidecars/…/log` |
| Search returns nothing | `grep "web_search attempt" api.log` — provider + status |
| Feature absent in packaged app | Verify inlined flag literals in SSR chunks (doc 11 §7) |
| Sidecar port dead but process alive | It bound before loading; probe TCP, not just HTTP |
| Silent subprocess death | Check for `stderr=DEVNULL` on that spawn path |

## 7. Anti-patterns (all previously shipped, all now guarded)

| Anti-pattern | Consequence |
|---|---|
| `stderr=subprocess.DEVNULL` | Fatal errors invisible for hours |
| `subprocess.PIPE` without a reader | Child deadlocks when the buffer fills |
| Piping a gate to `tail` | Exit status always 0; gate toothless |
| Broad `except` before typed re-raise | 404/400 masked as 500 |
| Logging exception text from key-bearing calls | Potential key leak |
| Unbounded log files | Disk exhaustion |
| Treating a read timeout as "down" | Working server marked unhealthy |

---

*Continues in [13 — Performance Optimization & Caching](./13-performance-optimization-caching.md).*
