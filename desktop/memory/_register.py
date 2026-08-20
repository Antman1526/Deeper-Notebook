"""Register `surreal` as a mem0 vector-store provider.

mem0 2.x guards `Memory.from_config({"vector_store": {"provider": ...}})` with two
hardcoded allowlists:

  1. `VectorStoreConfig._provider_configs` — Pydantic config-class names per
     provider. The validator does
     `__import__(f"mem0.configs.vector_stores.{provider}")` and
     `getattr(module, _provider_configs[provider])` to load the config class.
  2. `VectorStoreFactory.provider_to_class` — dotted import paths to the store
     class. The factory does `load_class(class_type)(**config.model_dump())`.

There is no public `register_provider()` for vector stores (only for LLMs and
embedders — see `LlmFactory.register_provider` in `mem0/utils/factory.py`).
We mutate the underlying dicts directly and inject a synthetic Pydantic-config
module into `sys.modules` so the validator's `__import__` lookup resolves.

Note on Pydantic v2 mechanics: `VectorStoreConfig._provider_configs` is declared
as `_provider_configs: Dict[str, str] = {...}` on a `BaseModel` subclass, which
Pydantic v2 turns into a `ModelPrivateAttr` descriptor. The underlying dict
(used as the per-instance default) lives at `.default`. Mutating
`VectorStoreConfig._provider_configs.default[...]` updates the allowlist for
all subsequent instances.

Importing this module has the side effect of installing the `surreal` provider.
`desktop/memory/client.py` (Task 5) imports it before calling `Memory.from_config`.
"""

from __future__ import annotations

import sys
import types

from mem0.utils.factory import VectorStoreFactory
from mem0.vector_stores.configs import VectorStoreConfig
from pydantic import BaseModel


class SurrealVectorStoreConfig(BaseModel):
    """Pydantic config for our SurrealDB-backed memory store.

    These fields become kwargs to `SurrealMemoryStore.__init__` because mem0's
    `VectorStoreFactory.create` calls `cls(**config.model_dump())`.
    """

    collection_name: str = "memory"  # mem0 reads .collection_name — unused for routing
    embedding_model_dims: int = 768  # nomic-embed-text-v1.5 native dim
    surreal_url: str
    namespace: str = "open_notebook"
    database: str = "open_notebook"
    user: str
    password: str


_synthetic_module = types.ModuleType("mem0.configs.vector_stores.surreal")
_synthetic_module.SurrealVectorStoreConfig = SurrealVectorStoreConfig
sys.modules["mem0.configs.vector_stores.surreal"] = _synthetic_module

# `._provider_configs` is a Pydantic v2 ModelPrivateAttr — mutate its `.default`.
VectorStoreConfig._provider_configs.default["surreal"] = "SurrealVectorStoreConfig"
VectorStoreFactory.provider_to_class["surreal"] = (
    "desktop.memory.surreal_store.SurrealMemoryStore"
)
