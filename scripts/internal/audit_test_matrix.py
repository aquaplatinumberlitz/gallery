#!/usr/bin/env python3
"""Compatibility entrypoint for the test matrix audit."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    script = Path(__file__).resolve().parents[1] / "audit_test_matrix.py"
    runpy.run_path(str(script), run_name="__main__")
