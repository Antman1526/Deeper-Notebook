#!/usr/bin/env bash
#
# ralph.sh — v0.8.67s
#
# An enhanced "Ralph Wiggum" autonomous AI agent loop for Open Notebook Plus.
# Runs an AI coding CLI (like Claude Code, opencode, or cursor) in a loop,
# using a Product Requirements Document (prd.json) and progress log (progress.txt)
# to track progress, resetting the context window on every iteration.
#
# Features:
#   1. Git Integration: Auto-commits working tree changes after each iteration.
#   2. Circuit Breaker: Stops loop if no changes are made for 3 consecutive loops
#      or if the iteration limit is reached.
#   3. Test Command Quality Gate: Runs test commands (e.g. pytest) after changes.
#   4. Multi-Tool Support: Runs claude, opencode, cursor, or custom commands.
#   5. Workspace Setup: Auto-initializes .ralph/ tracking folder.
#
# Usage:
#   ./scripts/ralph.sh [--tool claude|opencode|cursor] [--test-command "uv run pytest"] [max_iterations]

set -euo pipefail

# Default configuration
TOOL="claude"
MAX_ITERATIONS=10
TEST_COMMAND=""
DRY_RUN=false
RALPH_DIR=".ralph"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper for error logging
err() { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }
info() { echo -e "${BLUE}ℹ️ $*${NC}"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️ $*${NC}"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --tool)
      TOOL="$2"
      shift 2
      ;;
    --tool=*)
      TOOL="${1#*=}"
      shift
      ;;
    --test-command)
      TEST_COMMAND="$2"
      shift 2
      ;;
    --test-command=*)
      TEST_COMMAND="${1#*=}"
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      echo "Usage: ./scripts/ralph.sh [options] [max_iterations]"
      echo "Options:"
      echo "  --tool <name>            CLI tool to run: 'claude' (default), 'opencode', 'cursor'"
      echo "  --test-command <cmd>     Command to run at the end of each loop (e.g. 'uv run pytest')"
      echo "  --dry-run                Simulate the loop without invoking the AI tool"
      echo "  [max_iterations]         Maximum number of loop iterations (default: 10)"
      exit 0
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        MAX_ITERATIONS="$1"
      else
        err "Unknown argument: $1"
      fi
      shift
      ;;
  esac
done

PRD_FILE="$RALPH_DIR/prd.json"
PROGRESS_FILE="$RALPH_DIR/progress.txt"
PROMPT_FILE="$RALPH_DIR/prompt.md"
ACTIVE_PROMPT="$RALPH_DIR/active_prompt.md"
LOG_DIR="$RALPH_DIR/logs"

# 1) Self-initialize Ralph Workspace directory and files
mkdir -p "$RALPH_DIR" "$LOG_DIR"

if [ ! -f "$PRD_FILE" ]; then
  cat > "$PRD_FILE" << EOF
{
  "title": "Ralph Tasks",
  "branchName": "ralph/feature-name",
  "stories": [
    {
      "id": "task-1",
      "description": "Implement task or fix bug",
      "status": "todo",
      "passes": false
    }
  ]
}
EOF
  info "Created default $PRD_FILE. Please update it with your requirements."
fi

if [ ! -f "$PROGRESS_FILE" ]; then
  cat > "$PROGRESS_FILE" << EOF
# Ralph Progress Log
Started: $(date)
---
EOF
fi

if [ ! -f "$PROMPT_FILE" ]; then
  cat > "$PROMPT_FILE" << EOF
# Instructions for Ralph Autonomous Agent

You are an autonomous AI coding assistant running inside a Ralph loop.
Your goal is to implement and verify the tasks listed in \`prd.json\`.

## Guidelines:
1. Read \`prd.json\` to see what needs to be done.
2. Read \`progress.txt\` to see what has been done or learned in prior iterations.
3. Edit the codebase and implement the required changes.
4. Run the test suite to verify your implementation.
5. Update \`prd.json\` by marking completed tasks with \`"status": "completed"\` and \`"passes": true\`.
6. Append a concise summary of your changes, learnings, and test results to \`progress.txt\`.
7. Once all tasks in \`prd.json\` are fully implemented and verified, output \`<promise>COMPLETE</promise>\` at the end of your response to signal the loop to exit.
EOF
fi

# 2) Validate CLI Command availability
if ! command -v git &>/dev/null; then
  err "Git is required to run the Ralph loop."
fi

if [ "$DRY_RUN" = false ]; then
  if [[ "$TOOL" == "claude" ]]; then
    CMD="claude"
    if ! command -v claude &>/dev/null; then
      err "Claude Code CLI ('claude') not found. Install via: npm install -g @anthropic-ai/claude-code"
    fi
  elif [[ "$TOOL" == "opencode" ]]; then
    CMD="opencode"
    if ! command -v opencode &>/dev/null; then
      err "OpenCode CLI ('opencode') not found on the host."
    fi
  elif [[ "$TOOL" == "cursor" ]]; then
    CMD="cursor"
    if ! command -v cursor &>/dev/null; then
      err "Cursor CLI ('cursor') not found."
    fi
  else
    CMD="$TOOL"
    if ! command -v "$CMD" &>/dev/null; then
      err "Custom tool command '$CMD' is not executable."
    fi
  fi
fi

# 3) The Main Loop
success "Starting Ralph Loop: Tool='$TOOL', Max Iterations=$MAX_ITERATIONS"
info "--------------------------------------------------------"

NO_CHANGE_COUNT=0

for i in $(seq 1 "$MAX_ITERATIONS"); do
  echo ""
  success "🔄 [Iteration $i of $MAX_ITERATIONS] Starting..."
  
  # Check if all tasks are already complete in prd.json
  if command -v jq &>/dev/null; then
    INCOMPLETE_TASKS=$(jq '[.stories[] | select(.status == "todo" or .passes == false)] | length' "$PRD_FILE" 2>/dev/null || echo "1")
    if [ "$INCOMPLETE_TASKS" -eq 0 ]; then
      success "🎉 All tasks in prd.json marked complete. Stopping loop!"
      break
    fi
  fi

  # Build consolidated prompt
  cat "$PROMPT_FILE" > "$ACTIVE_PROMPT"
  echo -e "\n\n## Current prd.json Content:\n\`\`\`json" >> "$ACTIVE_PROMPT"
  cat "$PRD_FILE" >> "$ACTIVE_PROMPT"
  echo -e "\n\`\`\`\n\n## Current progress.txt Content:\n" >> "$ACTIVE_PROMPT"
  cat "$PROGRESS_FILE" >> "$ACTIVE_PROMPT"

  # Capture Git commit state before tool invocation
  START_COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "no-git-repository")

  # Run the AI CLI Tool
  ITERATION_LOG="$LOG_DIR/iteration_$i.log"
  echo "🤖 Invoking $TOOL..."

  # Run tool using set +e to capture failure codes without exiting
  set +e
  if [ "$DRY_RUN" = true ]; then
    sleep 1
    echo "Dry run: Simulated iteration $i" > "$ITERATION_LOG"
    RCODE=0
  else
    if [[ "$TOOL" == "claude" ]]; then
      # Run Claude Code CLI in non-interactive permission mode with the prompt
      claude --permission-mode acceptEdits -p "$(cat "$ACTIVE_PROMPT")" > >(tee "$ITERATION_LOG") 2>&1
      RCODE=$?
    elif [[ "$TOOL" == "opencode" ]]; then
      opencode run "$(cat "$ACTIVE_PROMPT")" > >(tee "$ITERATION_LOG") 2>&1
      RCODE=$?
    elif [[ "$TOOL" == "cursor" ]]; then
      cursor --prompt "$(cat "$ACTIVE_PROMPT")" > >(tee "$ITERATION_LOG") 2>&1
      RCODE=$?
    else
      # Custom command fallback
      $CMD "$(cat "$ACTIVE_PROMPT")" > >(tee "$ITERATION_LOG") 2>&1
      RCODE=$?
    fi
  fi
  set -e

  # Validate execution status
  if [ "$RCODE" -ne 0 ]; then
    warn "Iteration $i exited with code $RCODE. Log is saved in $ITERATION_LOG."
  fi

  # Check for explicit completion promise signal
  if grep -qi "<promise>COMPLETE</promise>" "$ITERATION_LOG"; then
    success "🎉 Agent signaled task completion (<promise>COMPLETE</promise> found). Stopping loop!"
    rm -f "$ACTIVE_PROMPT"
    break
  fi

  # Git Check & Commit
  END_COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "no-git-repository")
  WORKING_DIR_DIRTY=0
  if ! git diff --quiet 2>/dev/null || [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    WORKING_DIR_DIRTY=1
  fi

  # Circuit breaker: check if any changes were made
  if [ "$START_COMMIT_SHA" != "$END_COMMIT_SHA" ] || [ "$WORKING_DIR_DIRTY" -eq 1 ]; then
    NO_CHANGE_COUNT=0
    # Auto-commit if changes exist in working tree
    if [ "$WORKING_DIR_DIRTY" -eq 1 ]; then
      info "💾 Files modified in workspace. Performing auto-commit..."
      git add .
      git commit -m "ralph: iteration $i progress auto-commit" || true
    fi
  else
    ((NO_CHANGE_COUNT++))
    warn "No workspace changes (commits or edits) detected in iteration $i."
    if [ "$NO_CHANGE_COUNT" -ge 3 ]; then
      err "🚨 Circuit Breaker Triggered: No changes made for 3 consecutive iterations. Stopping loop to prevent runaway token costs."
    fi
  fi

  # Optional Quality Gate: run test command
  if [ -n "$TEST_COMMAND" ]; then
    info "🧪 Running post-iteration quality gate: $TEST_COMMAND"
    set +e
    eval "$TEST_COMMAND" > "$LOG_DIR/test_run_$i.log" 2>&1
    TEST_RCODE=$?
    set -e
    if [ "$TEST_RCODE" -eq 0 ]; then
      success "Tests passed successfully!"
    else
      warn "Tests failed! Appending failure trace to progress log so the agent can fix it next iteration."
      echo -e "\n\n### Quality Gate Failure (Iteration $i):\n" >> "$PROGRESS_FILE"
      echo -e "Command \`$TEST_COMMAND\` failed with code $TEST_RCODE. Trace:\n\`\`\`text" >> "$PROGRESS_FILE"
      tail -n 30 "$LOG_DIR/test_run_$i.log" >> "$PROGRESS_FILE"
      echo -e "\`\`\`" >> "$PROGRESS_FILE"
    fi
  fi

  # Clean up temp files
  rm -f "$ACTIVE_PROMPT"

  # Sleep slightly to prevent rate limit storms
  sleep 2
done

success "Ralph loop finished execution."
