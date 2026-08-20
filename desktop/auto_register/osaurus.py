"""v0.8.36 — Osaurus (https://github.com/osaurus-ai/osaurus) auto-register.

Osaurus is a native macOS / Apple Silicon local AI server that exposes a
**full OpenAI-compatible API** on port 1337 by default. From our
auto-register's point of view it is just another openai_compatible
server — same probe, same credential kind, same model-discovery
endpoints. The only special-cases are:

  - **Default port**: 1337 (overridable via DEEPER_NOTEBOOK_OSAURUS_PORT).
  - **Branding**: the credential is named "Osaurus (local MLX)" so it's
    distinguishable from llama-cpp / Ollama in the UI.
  - **Probe-before-register**: if nothing's listening on :1337 we
    silently skip — there's no Osaurus to register.
  - **Idempotency**: identical-credential-name dedupe via
    `existing_cred_names` from the caller, same as
    `register_llamacpp_models` / `register_ollama_models`.

For Apple-Silicon users this delivers MLX-optimized inference (typically
2-4× the throughput of llama-cpp on the same hardware) without us
needing to ship or maintain an MLX runtime — they install Osaurus once
(`brew install --cask osaurus`), we detect it on next launch, and the
smart router (v0.8.0+) starts using it.
"""

from __future__ import annotations

import logging
import os

import httpx

from deeper_notebook.environment import resolve_env
from desktop.auto_register._http import _ensure_credential, _ensure_model

log = logging.getLogger(__name__)

# Osaurus's documented default port. The user can move it (Settings →
# Server Port inside the Osaurus app); we honor an override via
# DEEPER_NOTEBOOK_OSAURUS_PORT so power users with two Osaurus instances
# or a non-default install can still wire us up without code changes.
DEFAULT_OSAURUS_PORT = 1337

# Same structured timeout shape as `deeper_notebook/health/local_models.py`
# uses for its OpenAI-compatible probe — connect + read kept tight so a
# black-hole port doesn't stall launcher startup.
_PROBE_TIMEOUT = httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0)


def _osaurus_port() -> int:
    """Read the configured Osaurus port from env, fall back to default."""
    raw = resolve_env("DEEPER_NOTEBOOK_OSAURUS_PORT", "").strip()
    if not raw:
        return DEFAULT_OSAURUS_PORT
    try:
        return int(raw)
    except ValueError:
        log.warning(
            "DEEPER_NOTEBOOK_OSAURUS_PORT=%r is not an integer; falling back to %d",
            raw,
            DEFAULT_OSAURUS_PORT,
        )
        return DEFAULT_OSAURUS_PORT


def _osaurus_running(port: int) -> tuple[bool, list[str]]:
    """Probe http://127.0.0.1:{port}/v1/models — same shape as our
    OpenAI-compatible health probe in
    `deeper_notebook/health/local_models.py:_probe_openai_compatible`.

    Returns (running, discovered_model_ids). `running` is True iff the
    endpoint returns 200 with parseable JSON. On any error (connect
    refused, timeout, non-200, malformed body), returns (False, []).

    This is intentionally synchronous + standalone — auto_register
    runs from the launcher (not the FastAPI event loop) so blocking
    HTTP is fine here.
    """
    url = f"http://127.0.0.1:{port}/v1/models"
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                log.debug(
                    "Osaurus probe at %s returned HTTP %d — skipping",
                    url,
                    resp.status_code,
                )
                return False, []
            data = resp.json()
            models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            return True, models
    except httpx.ConnectError:
        # Most common path — Osaurus simply isn't running. Log at DEBUG
        # so we don't spam INFO on every launch of users who don't use it.
        log.debug("Osaurus not running on :%d (connect refused)", port)
        return False, []
    except Exception as exc:
        # Surprising failures (timeout, bad JSON, etc.) log at INFO so
        # operators can see them without re-enabling DEBUG.
        log.info(
            "Osaurus probe at %s failed unexpectedly (%s) — skipping",
            url,
            exc,
        )
        return False, []


def register_osaurus_models(
    *,
    client: httpx.Client,
    existing_cred_names: set[str],
    existing_model_keys: set[tuple[str, str]],
    port: int | None = None,
) -> bool:
    """Discover-and-register a running Osaurus instance.

    Mirrors `register_llamacpp_models` / `register_ollama_models`:

      1. Probe the configured port. Bail silently if nothing listens.
      2. Create/refresh the "Osaurus (local MLX)" openai_compatible
         credential pointing at base_url=http://127.0.0.1:{port}/v1.
      3. For each model id returned by /v1/models, register a Model
         row of type "language" linked to that credential, skipping
         (provider, name) pairs already present in
         `existing_model_keys`.

    Returns True if at least one model was registered or refreshed.

    Idempotency: re-running on next launch finds the credential already
    in `existing_cred_names`, refreshes base_url via _ensure_credential's
    PUT path (handles port changes — Osaurus port is user-configurable),
    and skips models already in `existing_model_keys`.
    """
    target_port = port if port is not None else _osaurus_port()
    running, models = _osaurus_running(target_port)
    if not running:
        return False

    base_url = f"http://127.0.0.1:{target_port}/v1"
    cred_name = "Osaurus (local MLX)"
    cred_id = _ensure_credential(
        client=client,
        existing_names=existing_cred_names,
        name=cred_name,
        provider="openai_compatible",
        # Osaurus serves both language and (per their docs) embeddings.
        # The actual capability per-model surfaces via discovery; here
        # we just declare the credential's supported modalities up
        # front.
        modalities=["language", "embedding"],
        base_url=base_url,
    )
    if cred_id is None:
        # _ensure_credential logs the reason at WARNING. Nothing we
        # can do here except skip — don't crash the whole launcher.
        return False

    registered = False
    for model_name in models:
        # `_ensure_model` does its own (name.lower(), type.lower())
        # dedupe against `existing_keys` and returns False when the
        # row is already present — no need to pre-filter here.
        ok = _ensure_model(
            client=client,
            existing_keys=existing_model_keys,
            name=model_name,
            provider="openai_compatible",
            model_type="language",
            credential_id=cred_id,
        )
        if ok:
            registered = True
            log.info(
                "Registered Osaurus model %r against credential %r (port %d)",
                model_name,
                cred_name,
                target_port,
            )

    return registered
