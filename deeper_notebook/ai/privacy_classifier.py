"""Phase 5.2b — optional model-backed PII layer for the privacy gate.

The v0.8.51 gate (`privacy_gate.py`) catches STRUCTURED secrets via regex
(API keys, SSNs, cards, emails). This adds an OPTIONAL layer for UNSTRUCTURED
PII — names, postal addresses, health/financial details in prose — that regex
can't match.

Design choices:
  * **Pluggable endpoint, not a bundled model.** Point `DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL`
    at any local OpenAI-compatible server (a dedicated small classifier, or the
    existing chat sidecar). Leaner than shipping a fixed ~2.8 GB GGUF and fits
    the project's local-first / BYO-model ethos. Unset → this layer is off and
    the gate is exactly the v0.8.51 regex behaviour.
  * **Async.** The gate runs on the async provision path; a blocking sync HTTP
    call would freeze the event loop (a bug family this codebase guards
    against), so the call is `httpx.AsyncClient`.
  * **Additive + best-effort.** Returns category labels the caller UNIONs with
    the regex findings — the model can only ever ADD detections, never remove
    them, so the fail-closed regex floor always holds. ANY failure
    (unconfigured, endpoint down, malformed response, timeout) returns `[]`
    so chat is never blocked by a flaky classifier.
"""

from __future__ import annotations

import json
import os
import re

from loguru import logger

from deeper_notebook.environment import resolve_env

_CLASSIFIER_SYSTEM_PROMPT = (
    "You are a strict PII detector. Given the user's text, identify the "
    "categories of personal or sensitive information it contains. Respond with "
    "ONLY a compact JSON array of short snake_case category strings, e.g. "
    '["person_name", "home_address", "phone_number", "health_info", '
    '"financial_account", "government_id"]. If the text contains none, respond '
    "with []. Do not include any explanation, prose, or code fences."
)

# Cap the text we send the classifier — a PII verdict doesn't need the whole
# context, and this bounds latency + the classifier's own context budget.
_MAX_CLASSIFY_CHARS = 8000

_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


# v0.8.59 — Phase 5.2b-2. Sentinel values for DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL that
# mean "reuse the running local chat sidecar as the classifier" — so the model
# PII layer works out-of-box without provisioning a second model. The sidecar's
# OpenAI-compatible base is the same shape (/chat/completions) the classifier
# already POSTs to. Explicit opt-in (operator sets `=auto`); we never silently
# point at the sidecar.
_SIDECAR_SENTINELS = frozenset({"auto", "sidecar", "chat-sidecar", "local"})


def _classifier_url() -> str | None:
    raw = (resolve_env("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL") or "").strip()
    if not raw:
        return None
    if raw.lower() in _SIDECAR_SENTINELS:
        # Resolve to the chat sidecar base (set by the desktop bootstrap when
        # the sidecar registers its port). If that's unset too, no classifier.
        return (
            resolve_env("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL") or ""
        ).strip() or None
    return raw


def _classifier_model() -> str:
    return (
        resolve_env("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_MODEL") or ""
    ).strip() or "default"


def _classifier_timeout() -> float:
    raw = (resolve_env("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_TIMEOUT_SEC") or "").strip()
    if not raw:
        return 5.0
    try:
        v = float(raw)
    except ValueError:
        return 5.0
    return v if v > 0 else 5.0


def parse_categories(content: str) -> list[str]:
    """Extract a JSON array of category strings from model output, tolerant of
    surrounding prose / code fences / casing. Returns a sorted, de-duplicated,
    normalized (lower snake_case) list; [] on anything unparseable."""
    if not content:
        return []
    m = _JSON_ARRAY_RE.search(content)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(arr, list):
        return []
    out: set[str] = set()
    for x in arr:
        if isinstance(x, str) and x.strip():
            out.add(x.strip().lower().replace(" ", "_"))
    return sorted(out)


async def classify_via_model_async(text: str) -> list[str]:
    """Best-effort model-backed PII categories for `text`.

    Returns `[]` when no classifier endpoint is configured, the text is empty,
    or anything goes wrong — the caller then relies on the regex floor alone.
    Never raises.
    """
    url = _classifier_url()
    if not url or not (text or "").strip():
        return []
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_classifier_timeout()) as client:
            r = await client.post(
                f"{url.rstrip('/')}/chat/completions",
                json={
                    "model": _classifier_model(),
                    "messages": [
                        {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
                        {"role": "user", "content": text[:_MAX_CLASSIFY_CHARS]},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 200,
                },
            )
            r.raise_for_status()
            payload = r.json()
            choices = payload.get("choices") or []
            if not choices:
                return []
            content = choices[0].get("message", {}).get("content") or ""
            cats = parse_categories(content)
            if cats:
                logger.debug("privacy classifier flagged categories: {}", cats)
            return cats
    except Exception as exc:
        # Best-effort: a flaky/missing classifier must never block chat. The
        # regex floor (privacy_gate.detect_sensitive) still applies.
        logger.debug(
            "privacy classifier unavailable/failed (regex floor still applies): {}",
            exc,
        )
        return []
