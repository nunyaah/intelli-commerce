"""Swappable LLM backend.

The graph stays identical; only the model behind it changes. This is what lets
the user "change the model" and re-run the gate, and what lets CI run a fully
deterministic FakeChatModel for free.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from reliability.config import AgentConfig
from reliability.agent_harness.fake_llm import FakeChatModel

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_FAKE_SCRIPTS = os.path.join(_DATA_DIR, "fake_scripts.yaml")


@lru_cache(maxsize=4)
def load_fake_scripts(path: str = _FAKE_SCRIPTS) -> tuple:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Return a tuple so it is hashable/cacheable; callers treat it as a list.
    return tuple(data.get("scenarios", []))


def make_llm(cfg: AgentConfig) -> Any:
    """Return an unbound chat model for the given agent version."""
    if cfg.is_mock:
        return FakeChatModel(
            scenarios=list(load_fake_scripts()),
            variant=cfg.variant,
            model_name=cfg.model,
        )

    from langchain_groq import ChatGroq

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. For a free/offline run use mock mode "
            "(--mock or RELIABILITY_MOCK=1)."
        )
    return ChatGroq(model=cfg.model, api_key=api_key, temperature=cfg.temperature)
