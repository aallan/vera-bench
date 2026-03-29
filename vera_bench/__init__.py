"""VeraBench — benchmark suite for the Vera programming language."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vera-bench")
except PackageNotFoundError:
    __version__ = "0.1.0"
