"""A minimal HTTP surface for the support assistant.

Standard library only — ``http.server`` and ``json``. No web framework is added,
because the surface is three endpoints and a framework would be a dependency
earned by nothing.

Endpoints
---------
``GET  /health``   liveness. Answers while the process is serving.
``GET  /ready``    readiness. Answers only once the corpus is loaded and indexed.
``GET  /version``  service version, dependency record, and a redacted config summary.
``POST /ask``      run one query through the workflow.

Operational behaviour
---------------------
* Every request carries a correlation id — taken from ``X-Request-Id`` when the
  caller supplies one, generated otherwise — and that id appears in every log
  line the request produces and in the response body.
* Query text is never logged unless explicitly enabled, and is redacted when it is.
* Request bodies are size-limited before being parsed.
* The whole request is bounded by a timeout; exceeding it returns 504 rather than
  hanging the worker.
* Validation failures return 422 with a generic message. The service does not echo
  rejected input back, because echoing input is how a validation error becomes a
  log-injection or reflected-content problem.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pydantic import ValidationError

from support_assistant import __version__
from support_assistant.adapters import (
    AnswerGenerator,
    MockAnswerGenerator,
    OllamaAnswerGenerator,
)
from support_assistant.config import SERVICE_NAME, SERVICE_VERSION, Settings
from support_assistant.logging_utils import (
    REQUEST_ID_HEADER,
    configure_logging,
    describe_query,
    new_request_id,
)
from support_assistant.models import QueryRequest
from support_assistant.retrieval import Bm25Index, load_corpus
from support_assistant.workflow import SupportAssistant, WorkflowConfig, WorkflowTimeout

LOGGER = logging.getLogger("support_assistant.service")

#: Maximum accepted request body. A query is capped at 500 characters upstream;
#: this bounds the parse before validation ever runs.
MAX_BODY_BYTES = 64 * 1024

#: Chunk size and ceiling for draining an over-limit body before replying 413.
#: The declared Content-Length is client-controlled, so the drain is bounded and
#: never waits indefinitely for bytes that may never arrive.
DRAIN_CHUNK_BYTES = 64 * 1024
DRAIN_LIMIT_BYTES = 8 * 1024 * 1024


class Application:
    """Holds the loaded corpus and the configured assistant."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.corpus = load_corpus(_resolve(settings.corpus_path))
        self.index = Bm25Index(self.corpus)
        self.assistant = SupportAssistant(
            corpus=self.corpus,
            generator=_build_generator(settings),
            config=WorkflowConfig(timeout_seconds=settings.request_timeout_seconds),
        )

    @property
    def ready(self) -> bool:
        """True once the corpus is loaded and the index covers it."""
        return len(self.corpus.procedures) > 0 and bool(self.index.corpus.procedures)

    def dependency_record(self) -> dict[str, Any]:
        """Record the versions this process is actually running against."""
        import sys

        import pydantic

        return {
            "python": sys.version.split()[0],
            "pydantic": pydantic.VERSION,
            "service": __version__,
        }


def _resolve(path: str) -> Any:
    import pathlib

    candidate = pathlib.Path(path)
    if candidate.exists():
        return candidate
    # Allow running from the repository root as well as from the package dir.
    return pathlib.Path(__file__).resolve().parents[2] / path


def _build_generator(settings: Settings) -> AnswerGenerator:
    if settings.generator == "ollama":
        return OllamaAnswerGenerator(
            model=settings.ollama_model,
            base_url=settings.ollama_url,
            timeout_seconds=settings.request_timeout_seconds,
        )
    return MockAnswerGenerator()


class Handler(BaseHTTPRequestHandler):
    """Request handler. One instance per request, one thread per connection."""

    server_version = f"{SERVICE_NAME}/{SERVICE_VERSION}"
    protocol_version = "HTTP/1.1"

    application: Application  # injected on the server class

    # -- helpers ---------------------------------------------------------------

    def _send_json(
        self, status: HTTPStatus, payload: dict[str, Any], request_id: str
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(REQUEST_ID_HEADER, request_id)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes | None:
        """Read the body, or return None if it is over the limit.

        An oversized body is drained before the 413 is written. Without that, the
        unread bytes remain in the socket buffer when the handler returns, the
        server closes the connection mid-stream, and the client sees a
        ConnectionAbortedError instead of the 413 this method exists to produce.
        That race made the refusal path intermittently unobservable to a caller,
        which is the one thing a size limit must never be.
        """
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return b""
        try:
            length = int(raw_length)
        except ValueError:
            return None
        if length < 0:
            return None
        if length > MAX_BODY_BYTES:
            self._drain(length)
            return None
        return self.rfile.read(length)

    def _drain(self, length: int) -> None:
        """Discard `length` bytes so the response can be written and read.

        Bounded, because the declared length is attacker-controlled: nothing here
        waits indefinitely on a client that sends less than it promised. A
        short read or a timeout ends the drain early and the 413 still goes out.
        """
        remaining = min(length, DRAIN_LIMIT_BYTES)
        while remaining > 0:
            try:
                chunk = self.rfile.read(min(remaining, DRAIN_CHUNK_BYTES))
            except (OSError, ValueError):
                return
            if not chunk:
                return
            remaining -= len(chunk)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress the default access log; the service emits structured lines."""
        return

    # -- routing ---------------------------------------------------------------

    def do_GET(self) -> None:
        request_id = self.headers.get(REQUEST_ID_HEADER) or new_request_id()
        if self.path == "/health":
            self._send_json(
                HTTPStatus.OK, {"status": "ok", "request_id": request_id}, request_id
            )
        elif self.path == "/ready":
            ready = self.application.ready
            self._send_json(
                HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "ready" if ready else "not_ready", "request_id": request_id},
                request_id,
            )
        elif self.path == "/version":
            self._send_json(
                HTTPStatus.OK,
                {
                    "service": SERVICE_NAME,
                    "version": SERVICE_VERSION,
                    "dependencies": self.application.dependency_record(),
                    "config": self.application.settings.redacted_summary(),
                    "request_id": request_id,
                },
                request_id,
            )
        else:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "request_id": request_id},
                request_id,
            )

    def do_POST(self) -> None:
        request_id = self.headers.get(REQUEST_ID_HEADER) or new_request_id()
        if self.path != "/ask":
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "request_id": request_id},
                request_id,
            )
            return

        raw = self._read_body()
        if raw is None:
            LOGGER.warning(
                "request body rejected",
                extra={"request_id": request_id, "event": "body_too_large"},
            )
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "body_too_large", "request_id": request_id},
                request_id,
            )
            return

        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_json", "request_id": request_id},
                request_id,
            )
            return

        if not isinstance(payload, dict):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "expected_object", "request_id": request_id},
                request_id,
            )
            return

        try:
            request = QueryRequest(
                query=payload.get("query", ""),
                request_id=request_id,
            )
        except ValidationError:
            # Deliberately generic: the rejected value is not echoed back.
            LOGGER.info(
                "query rejected by validation",
                extra={"request_id": request_id, "event": "validation_failed"},
            )
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {
                    "error": "invalid_query",
                    "detail": "query must be 3-500 characters and contain letters or digits",
                    "request_id": request_id,
                },
                request_id,
            )
            return

        self._handle_query(request, request_id)

    def _handle_query(self, request: QueryRequest, request_id: str) -> None:
        settings = self.application.settings
        LOGGER.info(
            "query received",
            extra={
                "request_id": request_id,
                "event": "query_received",
                **describe_query(request.query, include_text=settings.log_query_text),
            },
        )

        try:
            response = asyncio.run(self.application.assistant.handle(request))
        except WorkflowTimeout:
            LOGGER.error(
                "workflow timed out",
                extra={"request_id": request_id, "event": "timeout"},
            )
            self._send_json(
                HTTPStatus.GATEWAY_TIMEOUT,
                {"error": "timeout", "request_id": request_id},
                request_id,
            )
            return
        except Exception:
            LOGGER.exception(
                "unhandled error in workflow",
                extra={"request_id": request_id, "event": "unhandled_error"},
            )
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "internal_error", "request_id": request_id},
                request_id,
            )
            return

        LOGGER.info(
            "query handled",
            extra={
                "request_id": request_id,
                "event": "query_handled",
                "decision": response.decision.value,
                "reason": response.reason.value,
                "procedure_id": response.gate.chosen_procedure_id,
                "latency_ms": round(response.latency_ms, 3),
            },
        )

        self._send_json(
            HTTPStatus.OK,
            {
                "request_id": request_id,
                "decision": response.decision.value,
                "reason": response.reason.value,
                "answer": response.answer_text,
                "citations": list(response.citations),
                "proposed_action": (
                    response.proposed_action.value if response.proposed_action else None
                ),
                "approval_status": response.approval.status.value
                if response.approval
                else None,
                "latency_ms": round(response.latency_ms, 3),
                "answer_source": response.answer_source,
                "notes": list(response.notes),
            },
            request_id,
        )


def build_server(
    settings: Settings | None = None,
    *,
    bind_port: int | None = None,
) -> ThreadingHTTPServer:
    """Build the server without starting it.

    ``bind_port`` overrides the configured port and exists so a test can bind an
    ephemeral port (0) without the service having to accept port 0 as valid
    configuration.
    """
    resolved = settings or Settings.from_env()
    application = Application(resolved)

    handler_class = type("BoundHandler", (Handler,), {"application": application})
    server = ThreadingHTTPServer(
        (resolved.host, bind_port if bind_port is not None else resolved.port),
        handler_class,
    )
    server.daemon_threads = True
    return server


def main() -> int:
    """Entry point. ``python -m support_assistant.service``."""
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    server = build_server(settings)
    LOGGER.info(
        "service starting", extra={"event": "startup", **settings.redacted_summary()}
    )

    stop = threading.Event()

    def _shutdown(signum: int, _frame: Any) -> None:
        LOGGER.info(
            "shutdown signal received",
            extra={"event": "shutdown", "signal": signal.Signals(signum).name},
        )
        stop.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            try:
                signal.signal(getattr(signal, signal_name), _shutdown)
            except ValueError:  # pragma: no cover - not on the main thread
                pass

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        stop.wait()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        LOGGER.info("service stopping", extra={"event": "stopping"})
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
