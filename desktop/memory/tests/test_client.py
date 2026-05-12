from __future__ import annotations

from unittest.mock import patch, MagicMock

from desktop.memory.client import build_memory_client


def test_build_memory_client_uses_surreal_provider_and_local_endpoints():
    fake_cfg = MagicMock(
        surreal_user="root", surreal_password="x" * 24,
    )
    with patch("desktop.memory.client.Memory") as mem0_cls:
        build_memory_client(
            cfg=fake_cfg,
            surreal_url="ws://127.0.0.1:50000/rpc",
            embed_url="http://127.0.0.1:51000/v1",
            llm_url="http://127.0.0.1:52000/v1",
        )
        call_args = mem0_cls.from_config.call_args
        config = call_args.kwargs.get("config") or call_args.args[0]
        # Vector store wired to our registered surreal provider, not "custom"
        assert config["vector_store"]["provider"] == "surreal"
        assert config["vector_store"]["config"]["surreal_url"] == "ws://127.0.0.1:50000/rpc"
        assert config["vector_store"]["config"]["user"] == "root"
        assert config["vector_store"]["config"]["password"] == "x" * 24
        # Embedder + LLM point at local servers
        assert config["embedder"]["config"]["base_url"] == "http://127.0.0.1:51000/v1"
        assert config["embedder"]["config"]["model"] == "nomic-embed-text-v1.5"
        assert config["llm"]["config"]["base_url"] == "http://127.0.0.1:52000/v1"
        assert config["llm"]["config"]["model"] == "Hermes-3-Llama-3.1-8B-Q4_K_M"


def test_build_memory_client_imports_register_module_for_side_effect():
    """If `desktop.memory._register` hasn't run by the time Memory.from_config
    is called, mem0 will reject `provider: 'surreal'` as unknown. Verify the
    side-effect import happened. Note: `_provider_configs` is a Pydantic v2
    ModelPrivateAttr at class level — read its `.default` to see the dict."""
    import sys
    assert "desktop.memory._register" in sys.modules
    from mem0.vector_stores.configs import VectorStoreConfig
    assert "surreal" in VectorStoreConfig._provider_configs.default
