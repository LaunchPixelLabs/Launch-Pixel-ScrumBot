"""Tests for the LLM factory routing logic."""
from __future__ import annotations

import pytest

from scrumbot.config import Settings
from scrumbot.llm import _maybe, get_llm


def test_maybe_omits_empty_values() -> None:
    assert _maybe("api_key", None) == {}
    assert _maybe("api_key", "") == {}
    assert _maybe("api_key", "secret") == {"api_key": "secret"}


def test_unknown_model_raises() -> None:
    # Routing must reject models it can't map before any client is built.
    with pytest.raises(ValueError):
        get_llm("mystery-model-9000", settings=Settings(_env_file=None))
