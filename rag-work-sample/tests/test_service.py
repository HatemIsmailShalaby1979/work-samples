"""Tests for the HTTP surface.

The server is started on an ephemeral port in a background thread, so these
tests exercise the real handler, the real routing and the real serialisation
rather than calling functions directly.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from support_assistant.config import Settings
from support_assistant.service import build_server


def _settings(**overrides: object) -> Settings:
    """Settings pointed at the corpus by absolute path, for a test process."""
    import pathlib

    corpus = (
        pathlib.Path(__file__).resolve().parents[1]
        / "corpus"
        / "harbourline_procedures.json"
    )
    base: dict[str, object] = {"corpus_path": str(corpus), "host": "127.0.0.1"}
    base.update(overrides)
    return Settings.model_validate(base)


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    """Start the service on an ephemeral port and yield its base URL."""
    server = build_server(_settings(), bind_port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(
    url: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    """Issue a request and return (status, json body, headers)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (
                response.status,
                json.loads(response.read().decode("utf-8")),
                dict(response.headers),
            )
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8")
        return error.code, json.loads(payload) if payload else {}, dict(error.headers)


# --- Liveness, readiness, version ---------------------------------------------


def test_health_returns_ok(base_url: str) -> None:
    status, body, _ = _request(f"{base_url}/health")
    assert status == 200
    assert body["status"] == "ok"


def test_ready_returns_ready_once_the_corpus_is_loaded(base_url: str) -> None:
    status, body, _ = _request(f"{base_url}/ready")
    assert status == 200
    assert body["status"] == "ready"


def test_version_reports_dependencies_and_config(base_url: str) -> None:
    status, body, _ = _request(f"{base_url}/version")
    assert status == 200
    assert body["service"] == "support-assistant-work-sample"
    assert "python" in body["dependencies"]
    assert "pydantic" in body["dependencies"]
    # The config summary must not expose anything sensitive.
    assert "password" not in json.dumps(body).lower()


def test_unknown_path_returns_404(base_url: str) -> None:
    status, body, _ = _request(f"{base_url}/nope")
    assert status == 404
    assert body["error"] == "not_found"


# --- /ask ---------------------------------------------------------------------


def test_ask_answers_a_supported_question(base_url: str) -> None:
    status, body, _ = _request(
        f"{base_url}/ask",
        method="POST",
        body={"query": "How do I book a crossing online?"},
    )
    assert status == 200
    assert body["decision"] == "answer"
    assert body["citations"] == ["booking-online"]
    assert body["answer"]


def test_ask_abstains_on_an_out_of_scope_question(base_url: str) -> None:
    status, body, _ = _request(
        f"{base_url}/ask",
        method="POST",
        body={"query": "Can you recommend a hotel near the port?"},
    )
    assert status == 200
    assert body["decision"] == "abstain"
    assert body["reason"] == "no_evidence"
    assert body["answer"] is None


def test_ask_escalates_on_a_conflicting_topic(base_url: str) -> None:
    status, body, _ = _request(
        f"{base_url}/ask",
        method="POST",
        body={"query": "What is the baggage allowance?"},
    )
    assert status == 200
    assert body["decision"] == "escalate"
    assert body["reason"] == "conflicting_procedures"


def test_ask_proposes_but_does_not_execute_a_consequential_action(
    base_url: str,
) -> None:
    status, body, _ = _request(
        f"{base_url}/ask",
        method="POST",
        body={"query": "I want a refund for my crossing"},
    )
    assert status == 200
    assert body["proposed_action"] == "issue_refund"
    assert body["approval_status"] == "pending"


def test_correlation_id_is_echoed_when_supplied(base_url: str) -> None:
    status, body, headers = _request(
        f"{base_url}/ask",
        method="POST",
        body={"query": "How do I book a crossing online?"},
        headers={"X-Request-Id": "test-correlation-1"},
    )
    assert status == 200
    assert body["request_id"] == "test-correlation-1"
    assert headers.get("X-Request-Id") == "test-correlation-1"


def test_correlation_id_is_generated_when_absent(base_url: str) -> None:
    status, body, _ = _request(
        f"{base_url}/ask",
        method="POST",
        body={"query": "How do I book a crossing online?"},
    )
    assert status == 200
    assert len(body["request_id"]) == 16


# --- Negative -----------------------------------------------------------------


@pytest.mark.parametrize("bad_query", ["", "   ", "hi", "!!", "x" * 501])
def test_invalid_query_returns_422(base_url: str, bad_query: str) -> None:
    status, body, _ = _request(
        f"{base_url}/ask", method="POST", body={"query": bad_query}
    )
    assert status == 422
    assert body["error"] == "invalid_query"


def test_rejected_input_is_not_echoed_back(base_url: str) -> None:
    """A validation error must not reflect the rejected value.

    The value is repeated so the request is rejected for length — the point is
    that a rejected body is never echoed, whatever the reason for rejection.
    """
    secret = "this-should-not-be-reflected@example.com"
    status, body, _ = _request(
        f"{base_url}/ask", method="POST", body={"query": secret * 20}
    )
    assert status == 422
    assert secret not in json.dumps(body)


def test_malformed_json_returns_400(base_url: str) -> None:
    request = urllib.request.Request(
        f"{base_url}/ask", data=b"{not json", method="POST"
    )
    request.add_header("Content-Type", "application/json")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=10)
    assert error.value.code == 400


def test_oversized_body_returns_413(base_url: str) -> None:
    request = urllib.request.Request(
        f"{base_url}/ask", data=b"x" * (64 * 1024 + 1), method="POST"
    )
    request.add_header("Content-Type", "application/json")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=10)
    assert error.value.code == 413


def test_ask_on_a_get_request_is_not_found(base_url: str) -> None:
    """GET /ask is not routed; only POST is."""
    status, _, _ = _request(f"{base_url}/ask")
    assert status == 404
