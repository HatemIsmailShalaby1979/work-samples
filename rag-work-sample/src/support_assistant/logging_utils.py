"""Structured logging, correlation IDs, and redaction.

Two rules govern this module, and both are enforced in code rather than trusted
to reviewers:

1. **Query text is not logged by default.** A support query is customer text.
   The default log line carries a short digest and a character count instead, so
   the request can still be correlated without the content being written to disk.
   Setting ``SUPPORT_LOG_QUERY_TEXT=true`` opts in, and even then the text is
   redacted first.

2. **Redaction happens before formatting, never after.** A redactor that runs on
   an already-rendered string will miss anything the formatter escaped. The
   redactor here operates on the raw value.

The redactor is pattern-based and therefore incomplete by construction. It
catches the shapes that matter for this domain — email, telephone, and long
digit runs — and is documented as best-effort rather than as a guarantee.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

#: Header carrying a caller-supplied correlation id.
REQUEST_ID_HEADER = "X-Request-Id"

_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    # Card-like: 13-19 digits, optionally grouped in fours.
    ("card", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    # Telephone: optional +, then 8-15 digits with optional separators.
    ("phone", re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,14}\d(?!\w)")),
)

_REDACTION_TOKEN = "[REDACTED:{kind}]"


def redact(text: str) -> str:
    """Replace recognised sensitive shapes in ``text`` with a marker.

    Best effort, not a guarantee. Order matters: card and phone patterns overlap,
    so card runs first and consumes its matches before the phone pattern sees
    them.
    """
    redacted = text
    for kind, pattern in _REDACTION_PATTERNS:
        redacted = pattern.sub(_REDACTION_TOKEN.format(kind=kind), redacted)
    return redacted


def digest(text: str) -> str:
    """A short, stable digest of a value, safe to log.

    Not a security control — it is a correlation aid. A short digest of a
    low-entropy string is guessable, which is why the character count is logged
    beside it rather than instead of it.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def new_request_id() -> str:
    """Generate a correlation id."""
    return uuid.uuid4().hex[:16]


class JsonFormatter(logging.Formatter):
    """Render log records as one JSON object per line.

    Structured output so a log shipper can index fields rather than parse prose.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Fields attached by the service via `extra=` land on the record.
        for key in (
            "request_id",
            "event",
            "decision",
            "reason",
            "procedure_id",
            "latency_ms",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO", stream: Any | None = None) -> None:
    """Install the JSON formatter on the root logger, once."""
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def describe_query(query: str, *, include_text: bool) -> dict[str, Any]:
    """Build the loggable description of a query.

    Returns a digest and a length always; the redacted text only when the
    operator has explicitly opted in.
    """
    description: dict[str, Any] = {
        "query_digest": digest(query),
        "query_chars": len(query),
    }
    if include_text:
        description["query_redacted"] = redact(query)
    return description
