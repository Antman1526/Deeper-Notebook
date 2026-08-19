"""v0.8.104 — structural health of the model configuration.

WHY THIS EXISTS

When chat breaks because of configuration, the app has historically died
opaquely. Three real examples from one week:

  * `default_chat_model` pointing at a row deleted long ago. `get_default_model`
    already logs a precise diagnostic — "the configured model_id may have been
    deleted or misconfigured" — and returns None. That log goes to a file the
    user never opens; the UI just fails to answer.
  * `default_chat_model` pointing at a legacy env-migration artifact (a row
    literally named `default_model`) that no server can answer to.
  * Auto-route enabled with no benchmark history and no cloud credential, which
    before v0.8.100 killed every turn with "No model available — neither local
    nor cloud" while a perfectly good default sat unused.

In all three the information needed to explain the failure existed somewhere in
the process. None of it reached the person who could fix it.

WHAT THIS CAN AND CANNOT DETECT

Structural checks only — no model is called, nothing is spawned, no network I/O.
That is a deliberate limit, not an oversight: this runs inside the runtime
snapshot, which must stay a bounded read-only projection.

So it catches "the default is unset", "the default points at nothing", and "the
default's credential has no endpoint". It CANNOT catch "the model row is valid
but the server rejects its name" — that one is only observable by asking the
server, which is what tests/integration/test_chat_model_seams.py does instead.
Claiming otherwise would be worse than not checking.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Providers that talk to an HTTP endpoint and are therefore unusable without a
# base_url. Cloud providers (openai, anthropic, ...) carry their own default
# endpoints, so a missing base_url there is normal rather than broken.
_ENDPOINT_REQUIRED_PROVIDERS = frozenset({"openai_compatible", "ollama"})

# The slots a user would notice immediately. Deliberately not every slot: a
# missing TTS default degrades one feature, while a missing chat default is the
# product not working.
_CRITICAL_SLOTS = ("default_chat_model",)


@dataclass(frozen=True)
class ModelConfigIssue:
    """One actionable problem, phrased for the person who has to fix it."""

    code: str
    detail: str
    remedy: str


@dataclass
class ModelConfigHealth:
    ok: bool = True
    issues: list[ModelConfigIssue] = field(default_factory=list)

    def add(self, code: str, detail: str, remedy: str) -> None:
        self.ok = False
        self.issues.append(ModelConfigIssue(code=code, detail=detail, remedy=remedy))


async def evaluate_model_config_health(
    *,
    defaults_loader=None,
    model_loader=None,
    credential_loader=None,
) -> ModelConfigHealth:
    """Inspect default model assignments; never raise, never call a model.

    The three loaders are injected so this is unit-testable without a database
    and so the runtime snapshot can pass cheaper readers if it ever needs to.
    """
    health = ModelConfigHealth()

    if defaults_loader is None or model_loader is None:
        from deeper_notebook.ai.models import Model, model_manager

        async def _defaults():
            return await model_manager.get_defaults()

        async def _model(model_id: str):
            return await Model.get(model_id)

        defaults_loader = defaults_loader or _defaults
        model_loader = model_loader or _model

    try:
        defaults = await defaults_loader()
    except Exception as exc:  # noqa: BLE001 - a snapshot must not fail the app
        health.add(
            "model_defaults_unreadable",
            f"Could not read the model defaults record ({type(exc).__name__}).",
            "Open Settings → Models; saving any default rewrites the record.",
        )
        return health

    for slot in _CRITICAL_SLOTS:
        model_id = getattr(defaults, slot, None)
        label = slot.replace("default_", "").replace("_model", "")

        if not model_id:
            health.add(
                "chat_default_missing",
                f"No {label} model is configured.",
                "Settings → Models → set a default chat model.",
            )
            continue

        try:
            model = await model_loader(model_id)
        except Exception:
            model = None

        if model is None:
            health.add(
                "chat_default_dangling",
                (
                    f"The configured {label} model ({model_id}) no longer exists — "
                    "it was probably deleted, or left behind by an older install."
                ),
                "Settings → Models → pick a different default chat model.",
            )
            continue

        credential_id = getattr(model, "credential", None)
        provider = (getattr(model, "provider", "") or "").strip().lower()
        if provider in _ENDPOINT_REQUIRED_PROVIDERS:
            credential = None
            if credential_id and credential_loader is not None:
                try:
                    credential = await credential_loader(credential_id)
                except Exception:
                    credential = None
            elif credential_id:
                try:
                    from deeper_notebook.domain.credential import Credential

                    credential = await Credential.get(credential_id)
                except Exception:
                    credential = None

            if credential is None:
                health.add(
                    "chat_default_credential_missing",
                    (
                        f"The {label} model '{getattr(model, 'name', model_id)}' is a "
                        f"{provider} model but has no credential attached, so there is "
                        "no endpoint to send the request to."
                    ),
                    "Settings → Models → re-select the model, or re-add its provider.",
                )
            elif not (getattr(credential, "base_url", None) or "").strip():
                health.add(
                    "chat_default_endpoint_missing",
                    (
                        f"The {label} model '{getattr(model, 'name', model_id)}' uses "
                        f"credential '{getattr(credential, 'name', credential_id)}', "
                        "which has no base URL."
                    ),
                    "Settings → API keys → set the base URL for that provider.",
                )

    # Auto-route is a distinct failure shape: nothing is *wrong* with the
    # default, but the toggle promises routing it cannot perform. Since v0.8.100
    # this degrades to the default instead of dying, so it is informational —
    # the user should still be told the toggle is doing nothing.
    if getattr(defaults, "auto_route_enabled", False) and not getattr(
        defaults, "auto_route_cloud", None
    ):
        health.add(
            "auto_route_without_cloud",
            (
                "Auto-route is on but no cloud model is configured for it, so every "
                "turn uses the local default regardless."
            ),
            "Settings → Models → set an auto-route cloud model, or turn auto-route off.",
        )

    return health
