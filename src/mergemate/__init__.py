"""MergeMate package."""

try:
    from importlib.metadata import version as _version, PackageNotFoundError
    __version__ = _version("mergemate")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]