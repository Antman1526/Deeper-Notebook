"""v0.8.68 — guard against retired model ids creeping back into the
connection tester and the credential discovery static lists.

Retired ids make "Test Connection" report failure for valid keys and let
discovery register models that 404 on first use. The blacklist below is
models known retired/removed upstream as of 2026-06; extend it when
providers retire more.
"""

from __future__ import annotations

RETIRED_MODEL_IDS = {
    # OpenAI
    "gpt-3.5-turbo",
    "text-davinci-003",
    # Anthropic (per the official model catalog)
    "claude-3-haiku-20240307",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-7-sonnet-20250219",
    "claude-2.1",
    "claude-2.0",
    # xAI
    "grok-beta",
}


def test_connection_tester_uses_no_retired_models():
    from deeper_notebook.ai.connection_tester import TEST_MODELS

    for provider, (model_name, _type) in TEST_MODELS.items():
        if model_name is None:
            continue
        bare = model_name.split("/")[-1]  # openrouter ids are prefixed
        assert model_name not in RETIRED_MODEL_IDS and bare not in RETIRED_MODEL_IDS, (
            f"TEST_MODELS[{provider!r}] = {model_name!r} is a retired model — "
            f"connection tests will fail for valid keys"
        )


def test_anthropic_test_model_is_current_cheap_tier():
    from deeper_notebook.ai.connection_tester import TEST_MODELS

    model, mtype = TEST_MODELS["anthropic"]
    assert model == "claude-haiku-4-5"
    assert mtype == "language"


def test_discovery_static_list_has_no_retired_anthropic_models():
    import inspect

    from api import credentials_service

    src = inspect.getsource(credentials_service)
    for retired in RETIRED_MODEL_IDS:
        if retired.startswith("claude"):
            assert f'"{retired}"' not in src, (
                f"credentials_service still offers retired model {retired!r} "
                f"in a discovery list"
            )
