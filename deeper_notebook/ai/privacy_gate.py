"""Phase 5.2a — fail-closed privacy gate for cloud routing.

The smart router (`deeper_notebook/ai/router.py:pick_provider`) may route a chat
turn to a CLOUD provider when the local sidecar is unhealthy or the content is
too big for the local context window. For a privacy-first app that's a leak
risk: the turn's text — which can contain API keys, SSNs, card numbers, etc.
pasted from a source — would be shipped off-device.

This module is the **no-model first slice** (5.2a) of the privacy filter. It
runs a fast, high-confidence *structured-secret* detector over the outbound
content and, when the gate is enabled and the router chose cloud, **fails
closed**: it reroutes the turn to the local model (so the secret never leaves
the machine), or — if no local model is configured — blocks the request with a
clear, actionable error rather than leaking.

Scope / honesty:
  * This catches STRUCTURED secrets/identifiers (keys, SSN, card numbers,
    emails, secret= assignments) with low false-positive rates. It does NOT
    detect unstructured PII (names/addresses in prose) — that needs the local
    classifier model planned for Phase 5.2b.
  * It gates the AUTO-ROUTE cloud-fallback path only (callers that go through
    `provision_langchain_chat_model`). A user whose *default* chat model is a
    cloud model (no auto-route) explicitly chose cloud and isn't gated;
    extending coverage there is a documented follow-up.

Default OFF — set `DEEPER_NOTEBOOK_PRIVACY_GATE=on` (aliases: 1/true/yes/local) to enable.
"""

from __future__ import annotations

import os
import re

from loguru import logger

from deeper_notebook.ai.router import ModelChoice
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import ConfigurationError

# --------------------------------------------------------------- detectors
#
# Each pattern is chosen to be high-confidence (rare false positives) because a
# false positive needlessly forces a turn onto the (possibly slower/smaller)
# local model. Card numbers are additionally Luhn-validated. Categories are
# returned as labels so the routing reason + logs say WHAT was caught.

_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("us_ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|access[_-]?token|"
            r"auth[_-]?token|bearer)\b\s*[:=]\s*['\"]?\S{6,}"
        ),
    ),
]

# Candidate runs of 13–19 digits (optionally separated by spaces/hyphens), then
# Luhn-validated before being counted as a card number.
_CC_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    """Standard Luhn checksum. `digits` must be 13–19 digit characters."""
    if not (13 <= len(digits) <= 19) or not digits.isdigit():
        return False
    total = 0
    # Double every second digit from the right.
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detect_sensitive(text: str) -> list[str]:
    """Return the sorted, de-duplicated list of structured-secret categories
    found in `text` (empty list == nothing sensitive detected)."""
    if not text:
        return []
    found: set[str] = set()
    for label, pat in _PATTERNS:
        if pat.search(text):
            found.add(label)
    for m in _CC_CANDIDATE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if _luhn_ok(digits):
            found.add("credit_card")
            break
    return sorted(found)


# --------------------------------------------------------------- gate config


def _privacy_gate_enabled(mode: str | None = None) -> bool:
    raw = (
        mode
        if mode is not None
        else (resolve_env("DEEPER_NOTEBOOK_PRIVACY_GATE") or "")
    )
    return raw.strip().lower() in ("on", "1", "true", "yes", "local", "local-only")


def _record_redirect(outcome: str) -> None:
    """Best-effort metric — observability must never break routing."""
    try:
        from api.metrics import record_privacy_gate_redirect

        record_privacy_gate_redirect(outcome)
    except Exception:
        pass


def apply_privacy_gate(
    choice: ModelChoice,
    *,
    content: str,
    local_model_id: str | None,
    cloud_model_id: str | None,
    mode: str | None = None,
    extra_findings: list[str] | None = None,
    findings_out: list[str] | None = None,
) -> ModelChoice:
    """Fail-closed privacy gate over a routing decision.

    Pass-through unless ALL of: the gate is enabled, `choice` routes to the
    cloud model, and `content` contains structured secrets/PII. In that case:
      * reroute to `local_model_id` if available (the secret stays on-device), or
      * raise ConfigurationError if there is no local model (block, don't leak).

    v0.8.57 — `extra_findings` lets the async caller inject additional detected
    categories from the optional model-backed classifier (privacy_classifier).
    They are UNIONed with the regex findings, so the model layer can only ever
    catch MORE; the regex floor is never weakened. Kept SYNC + pure (the async
    classifier call happens in the caller) so this stays trivially testable.

    Pure except for a best-effort metric + a log line — easy to unit-test.
    """
    if not _privacy_gate_enabled(mode):
        return choice
    # Only cloud-bound turns are a leak risk.
    if not cloud_model_id or choice.model_id != cloud_model_id:
        return choice
    findings = sorted(set(detect_sensitive(content or "")) | set(extra_findings or []))
    if not findings:
        return choice

    # v0.8.58 — expose the acted-on category LABELS (never the matched secret
    # values) so the caller can surface "kept on-device for privacy" + the
    # categories in the response / review UI. Populated whether we reroute or
    # block. Existing callers pass findings_out=None and are unaffected.
    if findings_out is not None:
        findings_out.extend(findings)

    summary = ", ".join(findings)
    if local_model_id:
        logger.warning(
            "privacy gate: rerouting cloud→local — detected {} in outbound "
            "content (set DEEPER_NOTEBOOK_PRIVACY_GATE=off to disable)",
            summary,
        )
        _record_redirect("local")
        return ModelChoice(
            local_model_id,
            f"privacy-gate: kept on-device ({summary})",
        )

    # No local fallback — fail closed rather than leak to cloud.
    _record_redirect("blocked")
    logger.warning(
        "privacy gate: BLOCKED a cloud request — detected {} and no local "
        "model is configured to handle it on-device",
        summary,
    )
    raise ConfigurationError(
        f"Privacy gate blocked a cloud request: sensitive data ({summary}) "
        "was detected in the prompt and no local chat model is configured to "
        "handle it on-device. Configure a local chat model, or set "
        "DEEPER_NOTEBOOK_PRIVACY_GATE=off to allow cloud routing for this content."
    )
