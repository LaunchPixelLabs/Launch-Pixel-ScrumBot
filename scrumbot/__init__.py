"""AI ScrumBot — an async, low-latency AI Scrum Master for Discord + DevOps.

The package is intentionally light at import time: submodules pull their own
(heavier) dependencies lazily, so importing ``scrumbot`` stays cheap.
"""
from __future__ import annotations

__version__ = "3.0.0"

__all__ = ["__version__"]
