from reliability.guardrails import pii


def test_detects_email_phone_card():
    r = pii.detect("Reach john.doe@example.com or 415-555-0142, card 4111 1111 1111 1111")
    assert set(r.entity_types) == {"EMAIL", "PHONE", "CREDIT_CARD"}
    assert r.has_pii


def test_redaction_replaces_values():
    r = pii.detect("Email: a@b.com")
    assert "a@b.com" not in r.redacted_text
    assert "[REDACTED_EMAIL]" in r.redacted_text


def test_luhn_rejects_invalid_card():
    # A 16-digit number that fails the Luhn check should not be flagged as a card.
    r = pii.detect("number 1234 5678 9012 3456")
    assert "CREDIT_CARD" not in r.entity_types


def test_clean_text_has_no_pii():
    r = pii.detect("Revenue today is $2,221 across 20 orders.")
    assert not r.has_pii
    assert r.redacted_text == "Revenue today is $2,221 across 20 orders."
