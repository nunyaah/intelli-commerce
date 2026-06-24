"""Guardrail pipeline wrapping the live agent.

Layers:
  * SQL safety   -- enforced at the tool boundary (see agent.tools.query_orders).
  * PII redaction-- strips personal data from the answer before it's returned.
  * Grounding    -- flags numeric claims unsupported by tool results.
  * Cost breaker -- caps spend per run.

Every guardrail action is logged to the store so it surfaces in the dashboard.
A tripped guard yields a clean, explicit fallback instead of a broken response.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from reliability.config import Budgets
from reliability.guardrails import grounding_guard, pii
from reliability.guardrails.circuit_breaker import CircuitBreaker
from reliability.store import log_guardrail_event


@dataclass
class GuardOutput:
    text: str
    events: list[dict] = field(default_factory=list)
    pii_redacted: bool = False
    grounding_flagged: bool = False


class GuardrailPipeline:
    def __init__(
        self,
        budgets: Optional[Budgets] = None,
        trace_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        use_presidio: bool = False,
        persist: bool = True,
    ):
        self.budgets = budgets or Budgets()
        self.trace_id = trace_id
        self.thread_id = thread_id
        self.use_presidio = use_presidio
        self.persist = persist
        self.breaker = CircuitBreaker(max_cost_usd=self.budgets.max_cost_usd)
        self.events: list[dict] = []

    def _log(self, guard: str, action: str, severity: str, detail: dict) -> None:
        event = {"guard": guard, "action": action, "severity": severity, "detail": detail}
        self.events.append(event)
        if self.persist:
            try:
                log_guardrail_event(self.trace_id, self.thread_id, guard, action, severity, detail)
            except Exception:  # noqa: BLE001 — logging must never break the request
                pass

    # --- cost circuit breaker ----------------------------------------------
    def record_cost(self, cost_usd: float) -> bool:
        tripped = self.breaker.add(cost_usd)
        if tripped:
            self._log("cost_circuit_breaker", "trip", "high",
                      {"spent_usd": self.breaker.spent_usd, "max_cost_usd": self.budgets.max_cost_usd})
        return tripped

    def check_total(self, total_cost_usd: float) -> bool:
        """Set cumulative spend (for the streaming live path) and trip once over budget."""
        already = self.breaker.tripped
        self.breaker.spent_usd = round(total_cost_usd, 8)
        if total_cost_usd > self.breaker.max_cost_usd:
            self.breaker.tripped = True
        if self.breaker.tripped and not already:
            self._log("cost_circuit_breaker", "trip", "high",
                      {"spent_usd": self.breaker.spent_usd, "max_cost_usd": self.budgets.max_cost_usd})
        return self.breaker.tripped

    @property
    def tripped(self) -> bool:
        return self.breaker.tripped

    def fallback_message(self) -> str:
        return (
            "I had to stop early to stay within the cost budget for this request. "
            "Please narrow the question and try again."
        )

    # --- output guards ------------------------------------------------------
    def guard_output(self, answer: str, evidence_text: str) -> GuardOutput:
        out = GuardOutput(text=answer or "")

        pres = pii.scan(out.text, use_presidio=self.use_presidio)
        if pres.has_pii:
            out.text = pres.redacted_text
            out.pii_redacted = True
            self._log("pii", "redact", "high",
                      {"entity_types": pres.entity_types, "count": len(pres.found)})

        verdict = grounding_guard.check(out.text, evidence_text)
        if not verdict.grounded:
            out.grounding_flagged = True
            self._log("grounding", "flag", "medium",
                      {"score": verdict.score, "ungrounded": verdict.ungrounded})
            out.text += (
                "\n\n[unverified] Some figures above could not be verified against "
                "the tool results and may be unreliable."
            )
        else:
            self._log("grounding", "allow", "info", {"score": verdict.score})

        return out
