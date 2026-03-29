#!/usr/bin/env python3
"""Standalone validation script for VeraBench problem definitions."""

import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from vera_bench.validate import run_validation

if __name__ == "__main__":
    sys.exit(run_validation())
