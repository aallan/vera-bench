"""VeraBench — benchmark suite for the Vera programming language."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vera-bench")
except PackageNotFoundError:
    # Fallback for development checkouts without `pip install -e .`.
    # Kept in sync with pyproject.toml `version`; the canonical source
    # is the installed package metadata above.
    __version__ = "0.0.15"
