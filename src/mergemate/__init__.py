"""MergeMate package."""

from importlib.metadata import version

PACKAGE_NAME = "mergemate"

__version__ = version(PACKAGE_NAME)

__all__ = ["__version__"]