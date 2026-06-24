"""PII detection & redaction.

Default backend is dependency-free regex + a Luhn check for card numbers (so CI
stays light). Presidio is used automatically *if installed* for higher-recall
detection. Used both as a runtime output guard and by the eval graders.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Phone: NANP-style with separators; avoids matching long plain integers.
_PHONE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

_PLACEHOLDER = {
    "EMAIL": "[REDACTED_EMAIL]",
    "PHONE": "[REDACTED_PHONE]",
    "SSN": "[REDACTED_SSN]",
    "CREDIT_CARD": "[REDACTED_CARD]",
    "IP_ADDRESS": "[REDACTED_IP]",
}


@dataclass
class PIIResult:
    found: list[dict] = field(default_factory=list)
    redacted_text: str = ""

    @property
    def has_pii(self) -> bool:
        return len(self.found) > 0

    @property
    def entity_types(self) -> list[str]:
        return sorted({f["type"] for f in self.found})


def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if len(nums) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(nums)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detect(text: str) -> PIIResult:
    if not text:
        return PIIResult(found=[], redacted_text=text or "")

    found: list[dict] = []

    def _scan(rx: re.Pattern, label: str, validate=None):
        for m in rx.finditer(text):
            val = m.group(0)
            if validate and not validate(val):
                continue
            found.append({"type": label, "value": val, "start": m.start(), "end": m.end()})

    _scan(_EMAIL, "EMAIL")
    _scan(_PHONE, "PHONE")
    _scan(_SSN, "SSN")
    _scan(_CARD, "CREDIT_CARD", validate=_luhn_ok)
    _scan(_IP, "IP_ADDRESS")

    redacted = redact(text, found)
    return PIIResult(found=found, redacted_text=redacted)


def redact(text: str, found: list[dict] | None = None) -> str:
    if found is None:
        found = detect(text).found
    # Replace from the end so offsets stay valid.
    out = text
    for f in sorted(found, key=lambda x: x["start"], reverse=True):
        placeholder = _PLACEHOLDER.get(f["type"], "[REDACTED]")
        out = out[: f["start"]] + placeholder + out[f["end"]:]
    return out


def detect_presidio(text: str) -> PIIResult | None:
    """Higher-recall detection via Presidio, if installed. Returns None otherwise."""
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
    except ImportError:
        return None
    analyzer = AnalyzerEngine()
    results = analyzer.analyze(text=text, language="en")
    found = [
        {"type": r.entity_type, "value": text[r.start:r.end], "start": r.start, "end": r.end}
        for r in results
    ]
    anonymizer = AnonymizerEngine()
    redacted = anonymizer.anonymize(text=text, analyzer_results=results).text
    return PIIResult(found=found, redacted_text=redacted)


def scan(text: str, use_presidio: bool = False) -> PIIResult:
    if use_presidio:
        res = detect_presidio(text)
        if res is not None:
            return res
    return detect(text)
