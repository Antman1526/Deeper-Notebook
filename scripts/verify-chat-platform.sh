#!/usr/bin/env bash
# =============================================================================
# verify-chat-platform.sh — Deeper Notebook v0.8.0 E2E platform smoke test
# =============================================================================
#
# PURPOSE
#   Five-step end-to-end verification of the v0.8.0 chat-platform features:
#   local-model health, MCP server registry, MCP-triggered citation markers,
#   and (manual) local-vs-cloud routing validation.
#
# USAGE
#   export NOTEBOOK_ID="notebooks:abc123"
#   bash scripts/verify-chat-platform.sh
#
#   # Or inline:
#   NOTEBOOK_ID=notebooks:abc123 bash scripts/verify-chat-platform.sh
#
#   # Find a notebook ID:
#   curl -s -H "Authorization: Bearer $DEEPER_NOTEBOOK_PASSWORD" \
#        $API_URL/api/notebooks | jq -r '.[0].id'
#
# CONFIGURATION (env vars)
#   API_URL             Default: http://127.0.0.1:5055
#   API_PASSWORD        Default: value of DEEPER_NOTEBOOK_PASSWORD, then the
#                                deprecated DEEPER_NOTEBOOK_PASSWORD alias, or
#                                open-notebook-change-me if that is also unset
#   NOTEBOOK_ID         Required — see USAGE above
#
# INTROSPECTION (Steps 4 + 5) — v0.8.1 / v0.8.37
#   ExecuteChatResponse now carries `selected_provider` ("local"/"cloud"/null).
#   Steps 4 and 5 assert on that field directly — no more manual eyeball
#   checks. Requires the API to be launched with:
#     EITHER  DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT=1 (env-var path)
#     OR      DefaultModels.auto_route_enabled=True via Settings → API Keys →
#             Smart routing toggle                  (v0.8.37 UI path)
#   plus a configured local model id, cloud model id, and (for Step 4) a
#   healthy local chat sidecar. The env var, when set, takes precedence
#   over the UI toggle (back-compat for ops/scripted setups).
#
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_URL="${API_URL:-http://127.0.0.1:5055}"
API_PASSWORD="${API_PASSWORD:-${DEEPER_NOTEBOOK_PASSWORD:-${DEEPER_NOTEBOOK_PASSWORD:-open-notebook-change-me}}}"
AUTH_HEADER="Authorization: Bearer ${API_PASSWORD}"

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'HELP'
verify-chat-platform.sh — Deeper Notebook v0.8.0 platform smoke test

USAGE
  NOTEBOOK_ID=<id> bash scripts/verify-chat-platform.sh

REQUIRED ENV
  NOTEBOOK_ID     SurrealDB notebook ID for chat POST calls.
                  Find it:  curl -s -H "Authorization: Bearer <pw>" \
                               http://127.0.0.1:5055/api/notebooks | jq -r '.[0].id'

OPTIONAL ENV
  API_URL         API base URL (default: http://127.0.0.1:5055)
  API_PASSWORD    Bearer token (default: $DEEPER_NOTEBOOK_PASSWORD, deprecated
                  $DEEPER_NOTEBOOK_PASSWORD, or open-notebook-change-me)

STEPS
  1. GET  /api/local-models/health  → overall != "down"
  2. GET  /api/mcp                  → at least one enabled server
  3. POST /chat/execute             → short news prompt; response contains [mcp:1]
  4. POST /chat/execute             → short prompt; assert selected_provider == "local"
  5. POST /chat/execute             → 32k+ filler prompt; assert selected_provider == "cloud"

NOTE
  Steps 4 and 5 require the API to be running with
  DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT=1 and both local + cloud model IDs configured.
  Without smart routing enabled, selected_provider is null on every turn.

HELP
    exit 0
fi

# ---------------------------------------------------------------------------
# NOTEBOOK_ID guard
# ---------------------------------------------------------------------------
if [[ -z "${NOTEBOOK_ID:-}" ]]; then
    echo "❌  NOTEBOOK_ID is required."
    echo ""
    echo "  Find it with:"
    echo "    curl -s -H \"Authorization: Bearer \$DEEPER_NOTEBOOK_PASSWORD\" \\"
    echo "         \${API_URL:-http://127.0.0.1:5055}/api/notebooks | jq -r '.[0].id'"
    echo ""
    echo "  Then re-run:"
    echo "    NOTEBOOK_ID=notebooks:abc123 bash scripts/verify-chat-platform.sh"
    exit 1
fi

# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------
_step_fail() {
    local step="$1"
    local msg="$2"
    local body="$3"
    echo ""
    echo "❌  Step ${step}: ${msg}"
    echo "    Response was: ${body}"
    exit 1
}

assert_not_eq() {
    local step="$1"
    local label="$2"
    local actual="$3"
    local forbidden="$4"
    local body="$5"
    if [[ "${actual}" == "${forbidden}" ]]; then
        _step_fail "${step}" "${label} must not be '${forbidden}' (got '${actual}')" "${body}"
    fi
    echo "✅  Step ${step}: ${label} = '${actual}' (not '${forbidden}')"
}

assert_eq() {
    local step="$1"
    local label="$2"
    local actual="$3"
    local expected="$4"
    local body="$5"
    if [[ "${actual}" != "${expected}" ]]; then
        _step_fail "${step}" "${label} expected '${expected}', got '${actual}'" "${body}"
    fi
    echo "✅  Step ${step}: ${label} = '${actual}'"
}

assert_contains() {
    local step="$1"
    local label="$2"
    local haystack="$3"
    local needle="$4"
    local body="$5"
    if [[ "${haystack}" != *"${needle}"* ]]; then
        _step_fail "${step}" "${label} does not contain '${needle}'" "${body}"
    fi
    echo "✅  Step ${step}: ${label} contains '${needle}'"
}

# ---------------------------------------------------------------------------
# Helper: create a throwaway chat session and return its ID
# ---------------------------------------------------------------------------
_new_session() {
    local notebook_id="$1"
    curl -s \
        -X POST "${API_URL}/api/chat/sessions" \
        -H "${AUTH_HEADER}" \
        -H "Content-Type: application/json" \
        -d "{\"notebook_id\": \"${notebook_id}\", \"title\": \"verify-platform-$$\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))"
}

# ---------------------------------------------------------------------------
# Step 1 — /api/local-models/health overall != "down"
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 1: Local-model health ==="
HEALTH_BODY=$(curl -s \
    -H "${AUTH_HEADER}" \
    "${API_URL}/api/local-models/health")

OVERALL=$(echo "${HEALTH_BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('overall',''))" 2>/dev/null || echo "")

if [[ -z "${OVERALL}" ]]; then
    _step_fail "1" "Could not parse JSON from /api/local-models/health" "${HEALTH_BODY}"
fi

assert_not_eq "1" "overall" "${OVERALL}" "down" "${HEALTH_BODY}"

# ---------------------------------------------------------------------------
# Step 2 — /api/mcp has at least one enabled server
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 2: MCP server registry ==="
MCP_BODY=$(curl -s \
    -H "${AUTH_HEADER}" \
    "${API_URL}/api/mcp")

ENABLED_COUNT=$(echo "${MCP_BODY}" | python3 -c "
import sys, json
servers = json.load(sys.stdin)
print(sum(1 for s in servers if s.get('enabled', False)))
" 2>/dev/null || echo "0")

if [[ "${ENABLED_COUNT}" -lt 1 ]]; then
    _step_fail "2" "Expected at least 1 enabled MCP server, got ${ENABLED_COUNT}" "${MCP_BODY}"
fi
echo "✅  Step 2: ${ENABLED_COUNT} enabled MCP server(s) found"

# ---------------------------------------------------------------------------
# Step 3 — MCP citation marker: ask a current-events question,
#           assert response body contains [mcp:1]
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 3: MCP-search citation trigger ==="
SESSION_3=$(_new_session "${NOTEBOOK_ID}")
if [[ -z "${SESSION_3}" ]]; then
    _step_fail "3" "Could not create a chat session (is the API running and NOTEBOOK_ID valid?)" ""
fi

CHAT_3_BODY=$(curl -s \
    -X POST "${API_URL}/api/chat/execute" \
    -H "${AUTH_HEADER}" \
    -H "Content-Type: application/json" \
    -d "{
      \"session_id\": \"${SESSION_3}\",
      \"message\": \"What's the top headline on Hacker News right now? Use mcp_search to find out.\"
    }")

MESSAGES_TEXT=$(echo "${CHAT_3_BODY}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
msgs = d.get('messages', [])
# Concatenate all assistant message content
print(' '.join(str(m.get('content','')) for m in msgs if m.get('role')=='assistant'))
" 2>/dev/null || echo "")

assert_contains "3" "assistant reply" "${MESSAGES_TEXT}" "[mcp:1]" "${CHAT_3_BODY}"

# ---------------------------------------------------------------------------
# Step 4 — Short prompt; local model should fit and be selected.
#          v0.8.1: assert ExecuteChatResponse.selected_provider == "local".
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 4: Short prompt — expect selected_provider='local' ==="
SESSION_4=$(_new_session "${NOTEBOOK_ID}")

CHAT_4_BODY=$(curl -s \
    -X POST "${API_URL}/api/chat/execute" \
    -H "${AUTH_HEADER}" \
    -H "Content-Type: application/json" \
    -d "{
      \"session_id\": \"${SESSION_4}\",
      \"message\": \"Hello, what is 2 + 2?\"
    }")

SELECTED_4=$(echo "${CHAT_4_BODY}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('selected_provider') or '')
" 2>/dev/null || echo "")

assert_eq "4" "selected_provider" "${SELECTED_4}" "local" "${CHAT_4_BODY}"

# ---------------------------------------------------------------------------
# Step 5 — Overflow prompt; cloud model should be selected.
#          v0.8.1: assert ExecuteChatResponse.selected_provider == "cloud".
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 5: Overflow prompt — expect selected_provider='cloud' ==="
SESSION_5=$(_new_session "${NOTEBOOK_ID}")

# ~32 000-word filler: "filler text " × 8000 = ~96 000 chars ≈ 24 000 tokens;
# combined with system prompt this reliably exceeds a 32 768-token n_ctx.
FILLER=$(python3 -c "print('filler text ' * 8000)")

CHAT_5_BODY=$(curl -s \
    -X POST "${API_URL}/api/chat/execute" \
    -H "${AUTH_HEADER}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json, sys
payload = {'session_id': '${SESSION_5}', 'message': '${FILLER} Now summarize this in one sentence.'}
print(json.dumps(payload))
")")

SELECTED_5=$(echo "${CHAT_5_BODY}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('selected_provider') or '')
" 2>/dev/null || echo "")

assert_eq "5" "selected_provider" "${SELECTED_5}" "cloud" "${CHAT_5_BODY}"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "======================================="
echo "✅  All 5 steps passed programmatically."
echo "======================================="
