"""Tests for redaction, digests, and the loggable query description.

Redaction is a best-effort control, and these tests pin its actual behaviour
rather than an aspiration. Where the redactor is imperfect, the test says so.
"""

from __future__ import annotations

from support_assistant.logging_utils import (
    JsonFormatter,
    describe_query,
    digest,
    new_request_id,
    redact,
)

# --- Redaction ----------------------------------------------------------------


def test_email_is_redacted() -> None:
    assert redact("contact me at a.person@example.com please") == (
        "contact me at [REDACTED:email] please"
    )


def test_telephone_is_redacted() -> None:
    assert "[REDACTED" in redact("call me on +20 100 123 4567")


def test_card_like_digit_run_is_redacted() -> None:
    assert "[REDACTED:card]" in redact("card 4111 1111 1111 1111 expired")


def test_ordinary_text_is_untouched() -> None:
    """The redactor must not mangle the queries it is supposed to log."""
    for text in (
        "how many bags am I allowed",
        "can I take my dog on the ferry",
        "what is the refund policy for a cancelled booking",
    ):
        assert redact(text) == text


def test_short_numbers_are_not_redacted() -> None:
    """A four-digit figure is not a phone number; over-redacting breaks logs."""
    assert redact("the crossing takes 90 minutes") == "the crossing takes 90 minutes"


def test_redaction_is_idempotent() -> None:
    once = redact("mail a@b.com or call +20 100 123 4567")
    assert redact(once) == once


# --- Digest and query description ---------------------------------------------


def test_digest_is_stable_and_short() -> None:
    assert digest("refund policy") == digest("refund policy")
    assert len(digest("refund policy")) == 12
    assert digest("refund policy") != digest("baggage policy")


def test_describe_query_omits_text_by_default() -> None:
    description = describe_query("my email is a@b.com", include_text=False)
    assert "query_redacted" not in description
    assert description["query_chars"] == len("my email is a@b.com")
    assert "query_digest" in description


def test_describe_query_includes_redacted_text_only_when_opted_in() -> None:
    description = describe_query("my email is a@b.com", include_text=True)
    assert "query_redacted" in description
    assert "a@b.com" not in description["query_redacted"]
    assert "[REDACTED:email]" in description["query_redacted"]


# --- Request ids --------------------------------------------------------------


def test_request_ids_are_unique() -> None:
    assert new_request_id() != new_request_id()
    assert len(new_request_id()) == 16


# --- Formatter ----------------------------------------------------------------


def test_json_formatter_emits_one_object_with_extra_fields() -> None:
    import json
    import logging

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="query handled",
        args=(),
        exc_info=None,
    )
    record.request_id = "abc123"  # type: ignore[attr-defined]
    record.decision = "answer"  # type: ignore[attr-defined]

    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "query handled"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "abc123"
    assert payload["decision"] == "answer"
    assert "ts" in payload


def test_json_formatter_omits_absent_extra_fields() -> None:
    import json
    import logging

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="startup",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert "request_id" not in payload
