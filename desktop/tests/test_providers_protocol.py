from desktop.providers import ModelProvider, ProviderEnv, ProviderError


def test_provider_env_is_dict_subclass():
    env = ProviderEnv(API_KEY="x", BASE_URL="http://localhost:1234")
    assert env["API_KEY"] == "x"
    assert isinstance(env, dict)


def test_provider_protocol_attrs_present():
    # The Protocol itself defines `name`, `is_available`, `list_models`, `start`, `stop`.
    assert hasattr(ModelProvider, "name")
    assert callable(getattr(ModelProvider, "is_available", None))
    assert callable(getattr(ModelProvider, "list_models", None))
    assert callable(getattr(ModelProvider, "start", None))
    assert callable(getattr(ModelProvider, "stop", None))


def test_provider_error_subclass_of_runtimeerror():
    with __import__("pytest").raises(RuntimeError):
        raise ProviderError("boom")


# (paperclip + hermes provider stubs deleted in v0.6 — never used in production)
