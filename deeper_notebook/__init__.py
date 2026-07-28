"""Deeper Notebook package."""

from importlib.metadata import PackageNotFoundError, version

from deeper_notebook.identity import PRODUCT_NAME, TAGLINE

try:
    __version__ = version("deeper-notebook")
except PackageNotFoundError:
    __version__ = "1.8.5"

__all__ = ["PRODUCT_NAME", "TAGLINE", "__version__"]
