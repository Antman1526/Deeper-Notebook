import httpx
import pytest

from desktop.providers import ProviderEnv
from desktop.providers.ollama import OllamaProvider


@pytest.fixture
def provider():
    return OllamaProvider(base_url="http://127.0.0.1:11434")


def test_is_available_true_when_endpoint_responds(provider, monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **kw: httpx.Response(200, json={"models": []})
    )
    assert provider.is_available() is True


def test_is_available_false_when_endpoint_unreachable(provider, monkeypatch):
    def raise_(*a, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx, "get", raise_)
    assert provider.is_available() is False


def test_list_models_returns_names(provider, monkeypatch):
    payload = {"models": [{"name": "llama3.1:latest"}, {"name": "mistral:7b"}]}
    monkeypatch.setattr(
        httpx, "get", lambda *a, **kw: httpx.Response(200, json=payload)
    )
    assert provider.list_models() == ["llama3.1:latest", "mistral:7b"]


def test_start_returns_env_with_correct_base_url(provider):
    env = provider.start("llama3.1:latest")
    assert isinstance(env, ProviderEnv)
    assert env["OLLAMA_API_BASE"] == "http://127.0.0.1:11434"
    assert "DEFAULT_MODEL" not in env  # model selection is not env-driven
    assert (
        "OLLAMA_BASE_URL" not in env
    )  # this is the wrong key (langchain convention only)


def test_stop_is_noop(provider):
    provider.stop()  # should not raise; Ollama is daemon-managed
