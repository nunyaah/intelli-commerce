"""Env-based configuration for the reliability suite.

Everything is driven by environment variables with safe defaults so the suite
runs locally, in Docker, and in CI without code changes or hardcoded secrets.

The two DBs are deliberately separate:
  * DB_PATH            -- the agent's operational data (orders/tickets/...). The
                          agent tools read this. Offline evals point it at a
                          deterministic fixture DB.
  * RELIABILITY_DB     -- where we persist traces, eval runs, and guardrail
                          events. Always-on source of truth for the dashboard.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# --- Storage -----------------------------------------------------------------

def reliability_db_path() -> str:
    """Path to the reliability store. Defaults to a repo-local file so the suite
    works on a dev laptop with zero setup; override with RELIABILITY_DB in
    Docker (e.g. /data/reliability.db)."""
    return os.environ.get("RELIABILITY_DB", os.path.join(".reliability", "reliability.db"))


def agent_db_path() -> str:
    """Path to the agent's operational DB (what the tools query)."""
    return os.environ.get("DB_PATH", os.path.join("data", "commerce.db"))


# --- Default agent definition ------------------------------------------------

DEFAULT_MODEL = "llama-3.1-8b-instant"

DEFAULT_SYSTEM_PROMPT = """You are IntelliCommerce AI, an intelligent real-time e-commerce analyst.

You have access to:
- query_orders: SQL queries on live order data
- search_tickets: Semantic search over support tickets
- get_metrics: Aggregated KPIs (today / last_hour / last_7_days)
- detect_anomaly: Z-score anomaly detection (revenue / tickets / refunds)
- web_search: External benchmarks and context

Rules:
- Always back conclusions with data from your tools.
- When detect_anomaly returns status=critical, prefix your response with [HITL_ALERT] and describe the anomaly clearly for human review.
- Be concise and analytical. Think like a data-driven operations manager."""


@dataclass
class AgentConfig:
    """A fully-specified, reproducible agent version.

    The fingerprint() is recorded with every eval run so a verdict can always be
    traced back to the exact prompt/model/variant that produced it.
    """

    provider: str = field(default_factory=lambda: _env("AGENT_PROVIDER", "groq"))
    model: str = field(default_factory=lambda: _env("AGENT_MODEL", DEFAULT_MODEL))
    temperature: float = field(default_factory=lambda: _env_float("AGENT_TEMPERATURE", 0.0))
    system_prompt: str = field(default_factory=lambda: DEFAULT_SYSTEM_PROMPT)
    # Named scenario script used only by the deterministic FakeChatModel. Lets the
    # "break it" demo swap in a degraded agent without touching real model calls.
    variant: str = field(default_factory=lambda: _env("AGENT_VARIANT", "base"))
    # Recorded for reproducibility; the agent itself is temperature-0.
    seed: int = field(default_factory=lambda: int(_env("AGENT_SEED", "1234")))

    @property
    def is_mock(self) -> bool:
        return self.provider == "fake"

    def prompt_hash(self) -> str:
        return hashlib.sha256(self.system_prompt.encode()).hexdigest()[:12]

    def version_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "variant": self.variant,
            "prompt_hash": self.prompt_hash(),
            "seed": self.seed,
        }

    def fingerprint(self) -> str:
        """Stable short id for this exact agent version."""
        blob = json.dumps(self.version_dict(), sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    def label(self) -> str:
        return f"{self.provider}:{self.model}:{self.variant}@{self.prompt_hash()}"


@dataclass
class JudgeConfig:
    """LLM-as-judge backend. Falls back to a deterministic mock in CI."""

    provider: str = field(default_factory=lambda: _env("JUDGE_PROVIDER", "groq"))
    model: str = field(default_factory=lambda: _env("JUDGE_MODEL", "llama-3.3-70b-versatile"))
    temperature: float = field(default_factory=lambda: _env_float("JUDGE_TEMPERATURE", 0.0))

    @property
    def is_mock(self) -> bool:
        return self.provider == "fake"


# --- Budgets (used by gate + budget grader) ----------------------------------

@dataclass
class Budgets:
    """Per-run hard ceilings. A run exceeding either fails the budget grader and
    can trip the circuit breaker."""

    max_cost_usd: float = field(default_factory=lambda: _env_float("BUDGET_MAX_COST_USD", 0.01))
    max_latency_ms: float = field(default_factory=lambda: _env_float("BUDGET_MAX_LATENCY_MS", 15000.0))

    def as_dict(self) -> dict:
        return asdict(self)


def otlp_endpoint() -> Optional[str]:
    """Optional OTLP/HTTP endpoint for exporting OTel GenAI spans (e.g. Langfuse
    v3 at http://localhost:3001/api/public/otel). None => local store only."""
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or None


def mock_mode_default() -> bool:
    """CI / offline default. When RELIABILITY_MOCK=1, agent + judge run fully
    deterministic and free."""
    return os.environ.get("RELIABILITY_MOCK", "0") == "1"
