"""Deprecated import compatibility for :mod:`deeper_notebook`.

New code must import :mod:`deeper_notebook`. This package remains as a
warning-free forwarding shim for integrations that still use the legacy
Python package name.
"""

from __future__ import annotations

import importlib
import sys

from ._alias import LegacyAliasFinder

if not any(isinstance(finder, LegacyAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, LegacyAliasFinder())

_canonical = importlib.import_module("deeper_notebook")
sys.modules[__name__] = _canonical
