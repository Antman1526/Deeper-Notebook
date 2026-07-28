# Operating Deeper Notebook locally — runbook

This is the practical "you're running it on your machine + maybe sharing
with 2-5 people, something just broke, what do you do" guide. Every
section is copy-pasteable and assumes a default install at
`~/.deeper-notebook/`. For the full env-var inventory see
[`environment-reference.md`](../docs/5-CONFIGURATION/environment-reference.md).

---

## Where things live

```
~/.deeper-notebook/
├── config.toml          # Desktop config (chosen by first-run wizard)
├── logs/
│   ├── api.log          # FastAPI process — most useful one (v0.7.14)
│   ├── api.log.YYYY-MM-DD_HH-mm-ss_…log.gz   # rotated archives
│   ├── launcher.log     # Desktop supervisor — child process lifecycle
│   └── bootstrap.log    # First-run venv setup / model downloads
├── surreal_data/        # SurrealDB on-disk database
├── venv/                # Bundled Python runtime (first-run extracted)
└── uploads/             # User-uploaded source files
```

---

## "Is it actually running?"

Three health checks, in order of cost:

```bash
# 1. Cheap process check (always responds in <1ms)
curl -sf http://127.0.0.1:5055/livez && echo OK

# 2. Full dependency check (DB up + migrations applied)
curl -sf http://127.0.0.1:5055/readyz | jq

# 3. If /readyz returns 503, the body tells you what failed:
{
  "status": "not_ready",
  "checks": {
    "database": "offline",          # ← here
    "database_error": "Connection refused",
    "migrations_applied": false,
    "migrations_pending": false,
    "migrations_error": null
  }
}
```

If `/livez` is 200 but `/readyz` is 503, the API process is fine; the
problem is downstream (usually SurrealDB).

---

## "Something just broke. Where are the logs?"

```bash
# Live tail (most-recent issues at the bottom)
tail -F ~/.deeper-notebook/logs/api.log

# Last 200 lines, looking for warnings/errors only
grep -E "WARNING|ERROR|CRITICAL" ~/.deeper-notebook/logs/api.log | tail -200

# Search rotated archives for an error from earlier
zgrep "ContextOverflow" ~/.deeper-notebook/logs/*.log.gz

# Bump log level temporarily for a noisy debug session:
DN_LOG_LEVEL=DEBUG make run    # or set in your shell before launching
```

JSON output for tools like `jq` / log aggregators:

```bash
DN_LOG_JSON=1 make run
# → produces parallel ~/.deeper-notebook/logs/api.jsonl
```

---

## Common symptoms → first thing to check

| Symptom | First step | Then |
|---|---|---|
| Chat hangs forever | `curl /readyz` — is DB up? | Check `api.log` for ContextOverflow; lower `DN_CHAT_HISTORY_CHAR_CAP` |
| "Service unavailable" on /readyz | `lsof -iTCP:8000` — is SurrealDB up? | Restart the desktop launcher; check `surreal_data/` permissions |
| File upload fails with 413 | Was the file > 500MB? | Raise `DN_SOURCE_UPLOAD_MAX_BYTES` (in bytes) |
| Local model context overflow | Which graph? Check log for `truncated` | Raise the relevant `*_CHAR_CAP` env var |
| Slow first chat turn | DB pool not yet warm | Subsequent turns should be faster — expected (v0.7.18) |
| Decryption failed errors | Recent key rotation? | See [Encryption key rotation](#encryption-key-rotation) below |
| Source upload mysteriously slow | Watch `du -sh ~/.deeper-notebook/uploads/` | Inspect for stuck partial files (filename ends with random suffix); v0.7.1+ auto-cleans on error but pre-v0.7.x partials may linger |

---

## Encryption key rotation

You set `DEEPER_NOTEBOOK_ENCRYPTION_KEY` originally. To rotate without
losing every stored credential (the v0.7.17 path):

```bash
# 1. Edit .env to use the plural form, NEW key first:
DEEPER_NOTEBOOK_ENCRYPTION_KEYS=brand-new-secret-2026,old-secret-2025

# 2. Restart. Existing data still decrypts (via old key); new writes
#    use the new key.

# 3. (Optional but recommended) Sweep stored credentials so they're
#    re-encrypted under the new key. From a Python REPL:
python -c "
import asyncio
from deeper_notebook.utils.encryption import re_encrypt_value
from deeper_notebook.database.repository import repo_query, repo_update

async def sweep():
    creds = await repo_query('SELECT id, api_key FROM credential WHERE api_key IS NOT NONE')
    for c in creds:
        new_blob = re_encrypt_value(c['api_key'])
        await repo_update('credential', c['id'], {'api_key': new_blob})
        print(f'Rotated {c[\"id\"]}')

asyncio.run(sweep())
"

# 4. Once the sweep is done, drop the old key from the env:
DEEPER_NOTEBOOK_ENCRYPTION_KEYS=brand-new-secret-2026

# 5. Restart. Verify a credential test in the UI still passes.
```

**If you skipped step 3 and dropped the old key prematurely**, existing
data is undecryptable. The error message will say so. Fix: add the old
key back to `DEEPER_NOTEBOOK_ENCRYPTION_KEYS`, run the sweep, then drop it.

---

## Backing up your data

There's no built-in auto-backup yet. A simple before-update snapshot:

```bash
# Stop the app first (so SurrealDB isn't mid-write)
make stop   # or kill the launcher window

# Snapshot
ts=$(date +%Y-%m-%d_%H-%M)
mkdir -p ~/deeper-notebook-backups
tar czf ~/deeper-notebook-backups/deeper-notebook-$ts.tgz \
    -C ~/.deeper-notebook \
    surreal_data config.toml uploads

# Restart
make run
```

For ongoing backups, add a cron / launchd job that runs this nightly
and prunes `~/deeper-notebook-backups/` older than 14 days.

---

## Tuning for your hardware

### Low-RAM laptop (8-16 GB, modest CPU)

```bash
# Shrink everything that can be shrunk
DN_CHAT_LLM_CTX=8192                  # smaller context window
DN_CHAT_HISTORY_CHAR_CAP=6000         # shorter history
DN_SOURCE_CHAT_HISTORY_CHAR_CAP=4000
DN_SOURCE_CHAT_INSIGHT_CHAR_CAP=600
DN_SOURCE_CHAT_MAX_INSIGHTS=5
DN_TRANSFORMATION_INPUT_CAP=6000
DN_ASK_PER_RESULT_CHAR_CAP=800
DN_DB_POOL_SIZE=2                     # fewer concurrent connections
```

### Workstation (32-64 GB, big context-window model loaded)

```bash
# Match the model's actual context window
DN_CHAT_LLM_CTX=131072                # e.g. Hermes-3, Qwen 2.5/3
DN_CHAT_HISTORY_CHAR_CAP=40000
DN_SOURCE_CHAT_HISTORY_CHAR_CAP=30000
DN_SOURCE_CHAT_SOURCE_CHAR_CAP=20000
DN_SOURCE_CHAT_INSIGHT_CHAR_CAP=3000
DN_SOURCE_CHAT_MAX_INSIGHTS=20
DN_TRANSFORMATION_INPUT_CAP=40000
DN_STUDIO_MAX_FILE_CHARS=60000
DN_STUDIO_MAX_COMBINED_CHARS=200000
DN_ASK_PER_RESULT_CHAR_CAP=5000
DN_DB_POOL_SIZE=8
```

### Constrained-disk box

```bash
DN_SOURCE_UPLOAD_MAX_BYTES=104857600   # 100 MB instead of 500
DN_LOG_LEVEL=WARNING                   # less log volume
```

After changing any of these, restart the desktop launcher. Check
`api.log` at startup to confirm the new values took effect — every
defensively-parsed knob logs a WARNING if the value was rejected as
garbage or out-of-range.

---

## Sharing with 2-5 testers (LAN access)

The desktop launcher binds API + frontend to `127.0.0.1` by default,
which means only your machine can reach it. To let testers on the same
network connect, **review the security tradeoffs first:**

- Anyone on the LAN can hit your API with the shared `DEEPER_NOTEBOOK_PASSWORD`.
- There's no per-user identity — they all share one bearer token.
- The frontend Next.js dev server has no CSP set (production deploys
  should add one — see the production-readiness review for details).

Acceptable risk for a trusted local network. Wire it up:

```bash
# 1. Bind the API to all interfaces (Makefile has a target, or set):
HOST=0.0.0.0 PORT=5055 make api

# 2. Find your LAN IP:
ipconfig getifaddr en0    # macOS
ip -o -4 addr | awk '{print $4}'  # Linux

# 3. Share the URL with your testers along with the password:
# http://<your-lan-ip>:5055
```

If you want to expose only over a private mesh (more sane), use
[Tailscale](https://tailscale.com/) — keep `127.0.0.1` binding and
let Tailscale handle the cross-machine routing + auth.

---

## Updating the desktop app

```bash
# 0. Backup first (see above section)

# 1. Pull
cd /path/to/Deeper-Notebook
git pull origin desktop-app

# 2. Bump deps if requirements changed
uv sync   # backend
(cd frontend && npm ci)   # frontend

# 3. Rebuild the desktop bundle (macOS):
make build-mac
# Outputs: dist/Deeper Notebook.app + dist/Deeper-Notebook-mac-<arch>.dmg
# Composite of: build-mac-test → build-mac-venv → build-mac-frontend
#               → build-mac-runtimes → build-mac-pyinstaller → build-mac-dmg

# Useful sub-targets:
make build-mac-test       # just runs desktop pytest as a precondition
make build-mac-install    # copies built .app to /Applications
make build-mac-clean      # remove build artifacts (keeps dmg)
make build-mac-distclean  # remove everything including dmg

# 4. Launch and verify:
open 'dist/Deeper Notebook.app'
curl -sf http://127.0.0.1:5055/readyz | jq    # should be 200 + ready
```

If an update breaks your DB (migrations applied that the new code
can't read), restore your backup:

```bash
make stop
rm -rf ~/.deeper-notebook/surreal_data
mkdir ~/.deeper-notebook/surreal_data
tar xzf ~/deeper-notebook-backups/deeper-notebook-<timestamp>.tgz -C ~/.deeper-notebook
make run
```

---

## When you need to start over

```bash
# Full reset — nukes data, logs, venv. Keeps config.toml.
make stop
rm -rf ~/.deeper-notebook/{surreal_data,logs,venv,uploads}
make run    # first-run wizard re-runs the venv bootstrap
```

To also reset config:

```bash
rm ~/.deeper-notebook/config.toml
make run
```

---

## Disabling the connection pool (debug only)

If a regression ever seems pool-related (e.g. zombie connection after a
SurrealDB restart that the pool isn't reaping), confirm by reverting to
pre-v0.7.18 behavior:

```bash
DN_DB_POOL_DISABLED=1 make run
# Every repo_query opens + closes its own connection (~50-200ms slower
# per query). If the bug disappears, it was the pool — report it.
```

---

## Quick diagnostic dump

For when you need to send something to a maintainer (or your future self):

```bash
cat <<EOF > /tmp/onp-diag.txt
# Deeper Notebook diagnostic — $(date)

## Version
$(cd /path/to/Deeper-Notebook && git rev-parse --short HEAD)
$(cd /path/to/Deeper-Notebook && git log -1 --format='%s')

## Live health
$(curl -sf http://127.0.0.1:5055/readyz 2>&1 | head -20)

## Process tree
$(ps -ef | grep -E 'open-notebook|surreal|llama|piper|whisper' | grep -v grep)

## Disk
$(du -sh ~/.deeper-notebook/{surreal_data,uploads,logs} 2>/dev/null)

## Recent errors (last 50)
$(grep -E 'ERROR|CRITICAL' ~/.deeper-notebook/logs/api.log 2>/dev/null | tail -50)

## DN_ env active
$(env | grep -E '^DN_|^DEEPER_NOTEBOOK_' | sort)
EOF

cat /tmp/onp-diag.txt
```
