"""Import machinery for the deprecated :mod:`open_notebook` package."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
from types import ModuleType
from typing import Any


class LegacyAliasLoader(importlib.abc.Loader):
    """Load a legacy module name as its canonical module object."""

    def __init__(self, canonical_name: str) -> None:
        self.canonical_name = canonical_name
        self.canonical_spec = None

    def create_module(self, spec: Any) -> ModuleType:
        module = importlib.import_module(self.canonical_name)
        self.canonical_spec = module.__spec__
        return module

    def exec_module(self, module: ModuleType) -> None:
        if self.canonical_spec is None:
            raise ImportError(f"missing canonical spec for {self.canonical_name}")
        module.__spec__ = self.canonical_spec
        module.__loader__ = self.canonical_spec.loader
        module.__package__ = self.canonical_spec.parent


class LegacyAliasFinder(importlib.abc.MetaPathFinder):
    """Resolve legacy submodules through the canonical package tree."""

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: ModuleType | None = None,
    ):
        if not fullname.startswith("open_notebook."):
            return None
        canonical_name = fullname.replace(
            "open_notebook",
            "deeper_notebook",
            1,
        )
        canonical_spec = importlib.util.find_spec(canonical_name)
        if canonical_spec is None:
            return None
        return importlib.util.spec_from_loader(
            fullname,
            LegacyAliasLoader(canonical_name),
            is_package=canonical_spec.submodule_search_locations is not None,
        )
