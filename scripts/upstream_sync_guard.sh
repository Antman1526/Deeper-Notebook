#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

UPSTREAM_REMOTE="${UPSTREAM_REMOTE:-upstream}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"
BASE_BRANCH="${BASE_BRANCH:-desktop-app}"
DATE_STAMP="$(date +%Y%m%d-%H%M%S)"
SYNC_BRANCH="${SYNC_BRANCH:-integrate/${UPSTREAM_REMOTE}-${UPSTREAM_BRANCH}-${DATE_STAMP}}"
WORKTREE_DIR="${WORKTREE_DIR:-../open-notebook-plus-upstream-sync-${DATE_STAMP}}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-output/upstream-sync/${DATE_STAMP}}"

usage() {
  cat <<'USAGE'
Safe upstream integration guard for Open Notebook Plus.

Commands:
  scripts/upstream_sync_guard.sh snapshot
  scripts/upstream_sync_guard.sh prepare
  scripts/upstream_sync_guard.sh compare

Environment overrides:
  UPSTREAM_REMOTE=upstream
  UPSTREAM_BRANCH=main
  BASE_BRANCH=desktop-app
  SYNC_BRANCH=integrate/upstream-main-YYYYMMDD-HHMMSS
  WORKTREE_DIR=../open-notebook-plus-upstream-sync-YYYYMMDD-HHMMSS
  SNAPSHOT_DIR=output/upstream-sync/YYYYMMDD-HHMMSS
USAGE
}

ensure_remote() {
  if ! git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1; then
    echo "Missing remote: $UPSTREAM_REMOTE" >&2
    exit 1
  fi
}

disable_upstream_push() {
  if [[ "$(git remote get-url --push "$UPSTREAM_REMOTE" 2>/dev/null || true)" == "DISABLED" ]]; then
    return
  fi
  git remote set-url --push "$UPSTREAM_REMOTE" DISABLED
}

fetch_upstream() {
  git fetch "$UPSTREAM_REMOTE" --prune --tags
}

write_snapshot() {
  mkdir -p "$SNAPSHOT_DIR"
  git status --short > "$SNAPSHOT_DIR/status-short.txt"
  git diff --binary > "$SNAPSHOT_DIR/tracked-changes.patch"
  git diff --cached --binary > "$SNAPSHOT_DIR/staged-changes.patch"
  git ls-files --others --exclude-standard > "$SNAPSHOT_DIR/untracked-files.txt"

  if [[ -s "$SNAPSHOT_DIR/untracked-files.txt" ]]; then
    tar -czf "$SNAPSHOT_DIR/untracked-files.tgz" -T "$SNAPSHOT_DIR/untracked-files.txt"
  fi

  cat > "$SNAPSHOT_DIR/README.md" <<EOF
# Upstream Sync Safety Snapshot

Created: ${DATE_STAMP}
Repository: ${ROOT}
Base branch: ${BASE_BRANCH}
Upstream: ${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}

Files:

- \`status-short.txt\`: dirty worktree inventory.
- \`tracked-changes.patch\`: binary-safe patch for modified tracked files.
- \`staged-changes.patch\`: binary-safe patch for staged changes, if any.
- \`untracked-files.txt\`: untracked path list.
- \`untracked-files.tgz\`: untracked file archive, if any existed.

This snapshot is for recovery only. Prefer committing clean Plus work before
running an upstream merge.
EOF

  echo "Safety snapshot written to $SNAPSHOT_DIR"
}

require_clean_worktree() {
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Refusing upstream integration because the current worktree is dirty." >&2
    echo "A safety snapshot was written to: $SNAPSHOT_DIR" >&2
    echo "Commit or stash the current Plus work, then rerun:" >&2
    echo "  scripts/upstream_sync_guard.sh prepare" >&2
    exit 2
  fi
}

compare_upstream() {
  git rev-list --left-right --count "${BASE_BRANCH}...${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}"
  git diff --stat "${BASE_BRANCH}..${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}" | sed -n '1,120p'
}

prepare_worktree() {
  require_clean_worktree
  git worktree add -b "$SYNC_BRANCH" "$WORKTREE_DIR" "$BASE_BRANCH"
  (
    cd "$WORKTREE_DIR"
    git merge --no-commit --no-ff "${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}" || true
    echo
    echo "Integration worktree: $WORKTREE_DIR"
    echo "Branch: $SYNC_BRANCH"
    echo
    echo "Resolve conflicts there, then run:"
    echo "  uv run pytest tests/test_evidence_studio_artifact_api.py tests/test_sources_api.py tests/test_v0_8_39_local_models_inventory.py tests/test_local_model_role_routing.py"
    echo "  cd frontend && npm test -- --run src/components/onp/ArtifactRail.test.tsx src/app/'(dashboard)'/settings/local-models/page.test.tsx"
    echo "  cd frontend && npx tsc --noEmit && npm run lint"
    echo "  PORT=3100 NEXT_PUBLIC_API_URL=http://127.0.0.1:5055 npm run start"
    echo "  ONP_BASE_URL=http://127.0.0.1:3100 ONP_FIXTURE_API_PORT=5055 node output/playwright/onp-visual-smoke.mjs"
  )
}

main() {
  local command="${1:-prepare}"
  case "$command" in
    -h|--help|help)
      usage
      ;;
    snapshot)
      write_snapshot
      ;;
    compare)
      ensure_remote
      disable_upstream_push
      fetch_upstream
      compare_upstream
      ;;
    prepare)
      write_snapshot
      ensure_remote
      disable_upstream_push
      fetch_upstream
      prepare_worktree
      ;;
    *)
      echo "Unknown command: $command" >&2
      usage >&2
      exit 64
      ;;
  esac
}

main "$@"
