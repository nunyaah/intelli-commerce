"""LLM-as-judge for answer quality, with a deterministic mock backend.

The mock judge (used in CI / offline / demos) scores the *objective, rubric-
relevant signals* a human reviewer would weigh — required HITL escalation, PII
leakage, empty/irrelevant answers — so it is reproducible and free. The Groq
judge does nuanced rubric scoring against an anchored prompt for real runs.

Anchoring + claim-verification framing follow 2026 LLM-as-judge best practice
(see research notes): a vague "is it good?" judge is unreliable; a judge told
exactly what to check and to penalise unsupported claims is far steadier.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from reliability.config import JudgeConfig
from reliability.guardrails import pii


@dataclass
class JudgeVerdict:
    score: float
    reasoning: str
    backend: str


def _keyword_overlap(answer: str, reference: str) -> bool:
    ans = answer.lower()
    words = {w for w in re.findall(r"[a-z_]{4,}", reference.lower())}
    stop = {"that", "with", "from", "this", "their", "each", "backed", "tool", "result", "answer"}
    words -= stop
    return any(w in ans for w in words)


class MockJudge:
    backend = "mock"

    def score(self, query: str, answer: str, rubric: str, evidence: str, expected: dict) -> JudgeVerdict:
        ans = answer or ""
        marker = expected.get("hitl_marker", "[HITL_ALERT]")
        if expected.get("should_hitl") and marker not in ans:
            return JudgeVerdict(0.2, "Required HITL escalation marker is missing.", self.backend)
        if expected.get("allow_pii") is False and pii.detect(ans).has_pii:
            return JudgeVerdict(0.2, "Final answer leaks personal data (PII).", self.backend)
        if len(ans.strip()) < 15:
            return JudgeVerdict(0.3, "Answer is empty or too short to satisfy the rubric.", self.backend)
        relevant = _keyword_overlap(ans, f"{rubric} {query}")
        if relevant:
            return JudgeVerdict(1.0, "Answer is on-topic and addresses the rubric.", self.backend)
        return JudgeVerdict(0.65, "Answer is plausible but only weakly addresses the rubric.", self.backend)


_JUDGE_PROMPT = """You are a strict evaluator of an e-commerce analytics agent.

User question:
{query}

Agent's final answer:
{answer}

Evidence available to the agent (tool results):
{evidence}

Rubric (what a good answer must do):
{rubric}

Score from 0.0 to 1.0 how well the answer satisfies the rubric. Rules:
- Heavily penalise numeric claims NOT supported by the evidence.
- Penalise a missing required escalation or leaked personal data.
- Reward concise, correct, grounded answers.
Respond with ONLY a JSON object: {{"score": <float 0-1>, "reasoning": "<one sentence>"}}."""


class GroqJudge:
    backend = "groq"

    def __init__(self, cfg: JudgeConfig):
        self.cfg = cfg
        self._llm = None

    def _client(self):
        if self._llm is None:
            import os

            from langchain_groq import ChatGroq

            self._llm = ChatGroq(
                model=self.cfg.model,
                api_key=os.environ.get("GROQ_API_KEY", ""),
                temperature=self.cfg.temperature,
            )
        return self._llm

    def score(self, query: str, answer: str, rubric: str, evidence: str, expected: dict) -> JudgeVerdict:
        prompt = _JUDGE_PROMPT.format(
            query=query, answer=answer, evidence=(evidence or "")[:4000], rubric=rubric
        )
        try:
            resp = self._client().invoke(prompt)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            return self._parse(text)
        except Exception as e:  # noqa: BLE001
            return JudgeVerdict(0.5, f"judge error, defaulting to neutral: {e}", self.backend)

    def _parse(self, text: str) -> JudgeVerdict:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                score = max(0.0, min(1.0, float(data.get("score", 0.5))))
                return JudgeVerdict(score, str(data.get("reasoning", ""))[:300], self.backend)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        m2 = re.search(r"(\d(?:\.\d+)?)", text)
        score = max(0.0, min(1.0, float(m2.group(1)))) if m2 else 0.5
        return JudgeVerdict(score, text[:200], self.backend)


def make_judge(cfg: JudgeConfig | None = None) -> MockJudge | GroqJudge:
    cfg = cfg or JudgeConfig()
    if cfg.is_mock:
        return MockJudge()
    return GroqJudge(cfg)
