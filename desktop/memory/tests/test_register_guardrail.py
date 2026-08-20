"""Guardrail tests for mem0 monkey-patch fragility (P2-HIGH-02).

desktop/memory/_register.py mutates three mem0 internals at import time:

  1. VectorStoreConfig._provider_configs.default  (a Pydantic ModelPrivateAttr)
  2. VectorStoreFactory.provider_to_class         (a regular class-level dict)
  3. sys.modules["mem0.configs.vector_stores.surreal"]  (injected synthetic module)

If a future mem0 release reshapes any of these (e.g. switches the dict to a
default_factory, or moves the allowlist into a Pydantic model_config), our
registration will silently break and `Memory.from_config({provider: "surreal"})`
will fail at runtime — usually in a writer subprocess where the error is hard
to surface.

These tests assert the SHAPE of the targets we mutate. If they break, we know
to revisit _register.py before shipping.
"""

from __future__ import annotations

import importlib
import sys

import pytest


def _reload_mem0_clean():
    """Reload mem0 modules so we test the unpatched shape."""
    for mod_name in list(sys.modules):
        if mod_name.startswith("mem0") or mod_name.startswith(
            "desktop.memory._register"
        ):
            del sys.modules[mod_name]


def test_VectorStoreConfig_has_provider_configs_as_mutable_dict():
    """If this fails: mem0 changed _provider_configs from a class-level dict
    to something else (e.g. a property, default_factory, or frozen). The
    Pydantic v2 ModelPrivateAttr.default attribute must still be a dict
    supporting __setitem__."""
    _reload_mem0_clean()
    from mem0.vector_stores.configs import VectorStoreConfig

    attr = VectorStoreConfig._provider_configs
    assert hasattr(attr, "default"), (
        "mem0 changed _provider_configs shape — no .default attribute. "
        "Inspect mem0.vector_stores.configs.VectorStoreConfig and update _register.py."
    )
    assert isinstance(attr.default, dict), (
        f"mem0._provider_configs.default is {type(attr.default).__name__}, expected dict"
    )
    try:
        attr.default["__guardrail_test__"] = "x"
        del attr.default["__guardrail_test__"]
    except Exception as e:
        pytest.fail(f"_provider_configs.default rejects __setitem__: {e}")


def test_VectorStoreFactory_provider_to_class_is_mutable_dict():
    """If this fails: mem0 changed provider_to_class from a class-level dict
    (e.g. promoted to a ClassVar or moved to a registry helper). Our
    monkey-patch needs to find the new mutation point."""
    _reload_mem0_clean()
    from mem0.utils.factory import VectorStoreFactory

    assert isinstance(VectorStoreFactory.provider_to_class, dict)
    try:
        VectorStoreFactory.provider_to_class["__guardrail_test__"] = "x"
        del VectorStoreFactory.provider_to_class["__guardrail_test__"]
    except Exception as e:
        pytest.fail(f"VectorStoreFactory.provider_to_class rejects __setitem__: {e}")


def test_register_module_installs_surreal_provider():
    """End-to-end: importing _register actually makes 'surreal' a valid mem0
    provider name. This is the highest-value guardrail — if it fails, all of
    the writer / retriever / capture-approve flows are broken."""
    _reload_mem0_clean()
    importlib.import_module("desktop.memory._register")
    from mem0.utils.factory import VectorStoreFactory
    from mem0.vector_stores.configs import VectorStoreConfig

    assert "surreal" in VectorStoreConfig._provider_configs.default
    assert "surreal" in VectorStoreFactory.provider_to_class
    cfg_mod = importlib.import_module("mem0.configs.vector_stores.surreal")
    assert hasattr(cfg_mod, "SurrealVectorStoreConfig")
