#!/usr/bin/env bash
#
# repair_desktop_db.sh — v0.8.67g
#
# Recovers the desktop app's SurrealDB from a "stale live-query" corruption that
# bricks source processing. Symptom: the surreal-commands worker crashes on
# startup with:
#
#     worker.py: db.live("command", diff=True)
#     InternalError: There was a problem with the database: The key being
#     inserted already exists
#
# Cause: an UNCLEAN SurrealDB shutdown (SIGKILL / power loss / force-quit) leaves
# persisted live-query bookkeeping in surreal_data that collides when the next
# worker re-registers. (v0.8.67g raises the shutdown grace to make this rarer;
# this script is the recovery if it still happens.)
#
# What it does — SAFE BY DESIGN, no data loss:
#   1. Aborts if the app/SurrealDB is still running (quit the app first).
#   2. Exports the current DB to ~/deeper-notebook-backups/ (logical .surql) and copies
#      surreal_data physically — TWO backups before touching anything.
#   3. Moves the stale surreal_data aside (never deletes it).
#   4. Imports the export into a fresh surreal_data — clearing the bad
#      live-query state while preserving every notebook / source / note / chat.
#
# Usage:
#   quit Deeper Notebook, then: bash scripts/repair_desktop_db.sh
#   if both roots exist: bash scripts/repair_desktop_db.sh \
#     --data-home "$HOME/.deeper-notebook"
set -euo pipefail

CANONICAL_DATA_HOME="${HOME}/.deeper-notebook"
LEGACY_DATA_HOME="${HOME}/.open-notebook-plus"
SELECTED_DATA_HOME=""

err() { echo "❌ $*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --data-home)
      [ "$#" -ge 2 ] || err "--data-home requires an exact data-root path."
      SELECTED_DATA_HOME="$2"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [--data-home PATH]"
      exit 0
      ;;
    *)
      err "Unknown argument: $1. Usage: $0 [--data-home PATH]"
      ;;
  esac
done

resolve_existing_dir() {
  [ -d "$1" ] || return 1
  (cd "$1" && pwd -P)
}

CANONICAL_RESOLVED="$(resolve_existing_dir "$CANONICAL_DATA_HOME" || true)"
LEGACY_RESOLVED="$(resolve_existing_dir "$LEGACY_DATA_HOME" || true)"

if [ -n "$SELECTED_DATA_HOME" ]; then
  SELECTED_RESOLVED="$(resolve_existing_dir "$SELECTED_DATA_HOME" || true)"
  [ -n "$SELECTED_RESOLVED" ] || err \
    "Selected --data-home is not an existing directory: $SELECTED_DATA_HOME"
  if [ "$SELECTED_RESOLVED" != "$CANONICAL_RESOLVED" ] \
    && [ "$SELECTED_RESOLVED" != "$LEGACY_RESOLVED" ]; then
    err "--data-home must resolve exactly to $CANONICAL_DATA_HOME or $LEGACY_DATA_HOME."
  fi
  DATA_HOME="$SELECTED_RESOLVED"
elif [ -n "$CANONICAL_RESOLVED" ] && [ -n "$LEGACY_RESOLVED" ]; then
  err "Both Deeper Notebook data roots exist. Refusing to choose or write. Re-run with --data-home set exactly to $CANONICAL_DATA_HOME or $LEGACY_DATA_HOME."
elif [ -n "$CANONICAL_RESOLVED" ]; then
  DATA_HOME="$CANONICAL_DATA_HOME"
elif [ -n "$LEGACY_RESOLVED" ]; then
  DATA_HOME="$LEGACY_DATA_HOME"
else
  DATA_HOME="$CANONICAL_DATA_HOME"
fi
DATA_DIR="${DATA_HOME}/surreal_data"
CONFIG="${DATA_HOME}/config.toml"
BACKUP_DIR="${HOME}/deeper-notebook-backups"
NS="open_notebook"; DB="open_notebook"
PORT="${DEEPER_NOTEBOOK_REPAIR_PORT:-${DN_REPAIR_PORT:-${DEEPER_NOTEBOOK_REPAIR_PORT:-${DEEPER_NOTEBOOK_REPAIR_PORT:-18799}}}}"
TS="$(date +%Y%m%d-%H%M%S)"

# 1) Refuse to run against a live instance.
if pgrep -f 'surreal-darwin' >/dev/null 2>&1 \
  || pgrep -f '/Applications/Deeper Notebook.app/Contents/MacOS' >/dev/null 2>&1 \
  || pgrep -f '/Applications/Open Notebook Plus.app/Contents/MacOS' >/dev/null 2>&1; then
  err "Deeper Notebook, its legacy predecessor, or SurrealDB is still running. Quit the app fully, then re-run."
fi
[ -d "$DATA_DIR" ] || err "No surreal_data at $DATA_DIR — nothing to repair."
[ -f "$CONFIG" ]   || err "No config.toml at $CONFIG."

BIN="$(ls /Applications/Deeper\ Notebook.app/Contents/Resources/desktop/bin/surreal-darwin-* 2>/dev/null | head -1 || true)"
if [ ! -x "$BIN" ]; then
  BIN="$(ls /Applications/Open\ Notebook\ Plus.app/Contents/Resources/desktop/bin/surreal-darwin-* 2>/dev/null | head -1 || true)"
fi
[ -x "$BIN" ] || err "Bundled surreal binary not found under the installed .app."
PW="$(grep '^surreal_password' "$CONFIG" | sed "s/.*= *'\(.*\)'.*/\1/")"
[ -n "$PW" ] || err "Could not read surreal_password from config.toml."

mkdir -p "$BACKUP_DIR"
EXPORT="${BACKUP_DIR}/surreal-export-${TS}.surql"

start_surreal() { # $1 = data dir
  "$BIN" start --user=root --pass="$PW" --bind="127.0.0.1:${PORT}" "file://$1" >/tmp/repair_surreal.log 2>&1 &
  SPID=$!
  for _ in $(seq 1 40); do
    [ "$(curl -s -o /dev/null -m2 -w '%{http_code}' "http://127.0.0.1:${PORT}/health" 2>/dev/null)" = "200" ] && return 0
    sleep 1
  done
  err "Temp SurrealDB did not become ready on :${PORT} (see /tmp/repair_surreal.log)."
}
stop_surreal() { kill -TERM "${SPID:-0}" 2>/dev/null || true; for _ in $(seq 1 15); do pgrep -f "surreal-darwin.*${PORT}" >/dev/null 2>&1 || break; sleep 1; done; }

echo "📤 1/3  Backing up current DB…"
start_surreal "$DATA_DIR"
"$BIN" export --endpoint "http://127.0.0.1:${PORT}" --username root --password "$PW" --namespace "$NS" --database "$DB" "$EXPORT"
stop_surreal
[ -s "$EXPORT" ] || err "Export came out empty — aborting (no changes made)."
grep -q 'source:' "$EXPORT" || echo "⚠️  (export has no 'source:' rows — continuing, but double-check $EXPORT)"
cp -R "$DATA_DIR" "${BACKUP_DIR}/surreal_data.physbak-${TS}"
echo "    logical:  $EXPORT  ($(wc -c <"$EXPORT") bytes)"
echo "    physical: ${BACKUP_DIR}/surreal_data.physbak-${TS}"

echo "🧹 2/3  Moving stale data aside → ${DATA_DIR}.stale-${TS}"
mv "$DATA_DIR" "${DATA_DIR}.stale-${TS}"
mkdir -p "$DATA_DIR"

echo "📥 3/3  Importing into a fresh, clean DB…"
start_surreal "$DATA_DIR"
"$BIN" import --endpoint "http://127.0.0.1:${PORT}" --username root --password "$PW" --namespace "$NS" --database "$DB" "$EXPORT"
stop_surreal

echo ""
echo "✅ Repair complete. Relaunch Deeper Notebook — the worker should start"
echo "   cleanly and source processing should work."
echo "   Backups kept in $BACKUP_DIR ; old DB at ${DATA_DIR}.stale-${TS}"
echo "   (delete the .stale dir once you've confirmed everything works)."
