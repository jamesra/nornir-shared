"""
Headless detection shared by Nornir packages and their pytest hooks.

Stdlib only, so callers such as a ``conftest.py`` can ask without importing
matplotlib, CuPy, or a package ``__init__`` that selects a plotting backend.

Detection (any condition is enough):
- ``NORNIR_HEADLESS`` is ``1``, ``true``, ``yes``, or ``on`` (case-insensitive).
- Non-Windows host with no ``DISPLAY`` (typical Linux CI / Docker agents).
"""

from __future__ import annotations

import os
import sys

__all__ = ["is_headless"]


def is_headless() -> bool:
    """Return True when no interactive display should be used."""
    flag = os.environ.get("NORNIR_HEADLESS", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        return True
    return False
