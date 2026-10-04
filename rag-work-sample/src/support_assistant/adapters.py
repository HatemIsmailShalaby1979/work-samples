"""Answer generators: a deterministic mock, and an optional local model.

Both implement the same protocol, so the evaluation harness can run against
either without knowing which it has.

The default is the mock. That is a deliberate choice, not a shortcut:

* the evaluation metrics are reproducible run to run, which is what makes the
  baseline-versus-workflow comparison meaningful;
* a clean clone with no model runtime installed can still run the harness and
  reproduce the committed report;
* LLM output quality is therefore **untested by default**, and the report says
  so rather than implying otherwise.

The Ollama adapter is implemented and its failure and timeout paths are covered by
tests, but it is **not verified end to end**. In the environment this sample was built
in, a trivial prompt timed out at 120s via raw curl and at 300s through the adapter,
while the runtime reported no model loaded in memory. Nothing here should be read as
evidence that a local generation completes.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Protocol

from support_assistant.models import AnswerSource, Procedure

#: Ollama's default local endpoint. Nothing here leaves the machine.
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:latest"


class GenerationError(RuntimeError):
    """Raised when a generator cannot produce an answer."""


class AnswerGenerator(Protocol):
    """Produces a customer-facing answer from one retrieved procedure."""

    name: AnswerSource

    async def generate(self, query: str, procedure: Procedure) -> str:
        """Return answer text grounded in ``procedure``."""
        ...


class MockAnswerGenerator:
    """Deterministic extractive generator.

    It returns the procedure's own opening sentences and adds nothing. That is
    the whole design: an extractive answer cannot hallucinate, so any
    unsupported answer in the evaluation is attributable to the *gate* letting a
    bad match through, not to the generator inventing content. That separation
    is what makes the failure analysis in the report possible.
    """

    name: AnswerSource = "extractive_mock"

    def __init__(self, max_sentences: int = 2) -> None:
        if max_sentences < 1:
            raise ValueError("max_sentences must be at least 1")
        self._max_sentences = max_sentences

    async def generate(self, query: str, procedure: Procedure) -> str:
        del query  # the mock is extractive; the query does not shape the answer
        sentences = _split_sentences(procedure.body)
        selected = sentences[: self._max_sentences]
        return " ".join(selected)


def _split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation, keeping the punctuation."""
    sentences: list[str] = []
    current: list[str] = []
    for character in text:
        current.append(character)
        if character in ".!?":
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    tail = "".join(current).strip()
    if tail:
        sentences.append(tail)
    return sentences


class OllamaAnswerGenerator:
    """Answer generator backed by a local Ollama model.

    Opt-in only. Uses the standard library over HTTP — no client package is
    required — and applies an explicit timeout so a hung model cannot hang the
    workflow.
    """

    name: AnswerSource = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout_seconds: float = 60.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, query: str, procedure: Procedure) -> str:
        prompt = _build_prompt(query, procedure)
        payload = json.dumps(
            {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                # temperature 0 for as much determinism as a local model offers
                "options": {"temperature": 0},
            }
        ).encode("utf-8")

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._post, payload),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as error:
            raise GenerationError(
                f"ollama did not respond within {self._timeout_seconds:.0f}s"
            ) from error

    def _post(self, payload: bytes) -> str:
        request = urllib.request.Request(
            url=f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise GenerationError(f"ollama unreachable: {error}") from error
        except json.JSONDecodeError as error:
            raise GenerationError("ollama returned a non-JSON response") from error

        answer = body.get("response")
        if not isinstance(answer, str) or not answer.strip():
            raise GenerationError("ollama returned an empty answer")
        return answer.strip()


def _build_prompt(query: str, procedure: Procedure) -> str:
    """Build a strictly grounded prompt.

    The instruction to answer only from the supplied procedure — and to say so
    if the procedure does not cover the question — is the prompt-level half of
    the same discipline the gate enforces in code.
    """
    return (
        "You are a customer-support assistant for a ferry operator.\n"
        "Answer the customer's question using ONLY the procedure below.\n"
        "If the procedure does not answer the question, reply exactly: "
        "NOT_COVERED.\n"
        "Do not add information that is not in the procedure.\n\n"
        f"PROCEDURE: {procedure.title}\n"
        f"{procedure.body}\n\n"
        f"CUSTOMER QUESTION: {query}\n\n"
        "ANSWER:"
    )


async def is_ollama_available(
    base_url: str = DEFAULT_OLLAMA_URL,
    timeout_seconds: float = 2.0,
) -> bool:
    """Best-effort reachability probe for a local Ollama runtime."""

    def _probe() -> bool:
        try:
            with urllib.request.urlopen(
                f"{base_url.rstrip('/')}/api/tags", timeout=timeout_seconds
            ) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError):
            return False

    return await asyncio.to_thread(_probe)
