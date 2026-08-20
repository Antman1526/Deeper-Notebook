from __future__ import annotations

import importlib
import sys


def test_surreal_provider_is_registered_after_import():
    # Reload mem0 modules clean so the test is order-independent.
    for mod in list(sys.modules):
        if mod.startswith(("mem0", "desktop.memory._register")):
            del sys.modules[mod]
    from mem0.utils.factory import VectorStoreFactory
    from mem0.vector_stores.configs import VectorStoreConfig

    # `VectorStoreConfig._provider_configs` is a Pydantic v2 ModelPrivateAttr;
    # the underlying dict lives at `.default`.
    assert "surreal" not in VectorStoreConfig._provider_configs.default
    assert "surreal" not in VectorStoreFactory.provider_to_class

    # Importing _register installs the provider as a side effect.
    importlib.import_module("desktop.memory._register")

    assert (
        VectorStoreConfig._provider_configs.default["surreal"]
        == "SurrealVectorStoreConfig"
    )
    assert (
        VectorStoreFactory.provider_to_class["surreal"]
        == "desktop.memory.surreal_store.SurrealMemoryStore"
    )


def test_surreal_provider_passes_mem0_pydantic_validation():
    """End-to-end check: after registration, mem0's VectorStoreConfig
    validator accepts `provider: 'surreal'` and instantiates our config."""
    from mem0.vector_stores.configs import VectorStoreConfig

    import desktop.memory._register  # noqa: F401

    cfg = VectorStoreConfig(
        provider="surreal",
        config={
            "surreal_url": "ws://127.0.0.1:50000/rpc",
            "user": "root",
            "password": "x" * 24,
        },
    )
    assert type(cfg.config).__name__ == "SurrealVectorStoreConfig"
    dump = cfg.config.model_dump()
    assert dump["surreal_url"] == "ws://127.0.0.1:50000/rpc"
    assert dump["namespace"] == "open_notebook"


def test_synthetic_config_module_exports_pydantic_class():
    from mem0.configs.vector_stores.surreal import SurrealVectorStoreConfig

    import desktop.memory._register  # noqa: F401

    inst = SurrealVectorStoreConfig(
        surreal_url="ws://localhost:50000/rpc",
        user="root",
        password="x" * 24,
    )
    assert inst.collection_name == "memory"
    assert inst.embedding_model_dims == 768
    assert inst.namespace == "open_notebook"
