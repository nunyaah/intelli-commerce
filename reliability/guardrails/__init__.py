"""Runtime guardrails: SQL safety, PII redaction, grounding check, and a
max-cost circuit breaker. The same primitives back the offline eval graders, so
"what we test" and "what we enforce at runtime" never diverge.
"""
