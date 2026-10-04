"""Negative tests: the paths that must fail loudly.

A support assistant that fails silently is worse than one that fails. Every
test in this file asserts that something is *refused*, and most of them assert
the specific reason. These are the tests worth keeping when the happy path
tests get trimmed.
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest
from pydantic import ValidationError

from support_assistant import (
    ApprovalRecord,
    ApprovalStatus,
    ConsequentialAction,
    Corpus,
    Decision,
    GenerationError,
    MockAnswerGenerator,
    Procedure,
    ProcedureStatus,
    QueryRequest,
    RetrievalHit,
    SupportAssistant,
    WorkflowConfig,
    WorkflowTimeout,
    execute_approved_action,
    load_corpus,
)

CORPUS_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "corpus"
    / "harbourline_procedures.json"
)


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return load_corpus(CORPUS_PATH)


# --- Input validation ---------------------------------------------------------


@pytest.mark.parametrize(
    "bad_query",
    [
        "",  # empty
        "   ",  # whitespace only
        "!!",  # punctuation only, and too short
        "hi",  # below the minimum length
        "x" * 501,  # above the maximum length
    ],
)
def test_invalid_queries_are_rejected(bad_query: str) -> None:
    with pytest.raises(ValidationError):
        QueryRequest(query=bad_query)


def test_valid_query_is_stripped() -> None:
    assert QueryRequest(query="  refund policy  ").query == "refund policy"


def test_unknown_fields_are_rejected() -> None:
    """extra='forbid' everywhere: an unexpected field is a bug, not a no-op."""
    with pytest.raises(ValidationError):
        QueryRequest(query="refund policy", unexpected="value")  # type: ignore[call-arg]


# --- Approval gate: the fail-closed boundary ----------------------------------


def _approved(action: ConsequentialAction) -> ApprovalRecord:
    return ApprovalRecord(
        action=action, status=ApprovalStatus.APPROVED, approver="ops-lead"
    )


def test_missing_approval_is_refused() -> None:
    with pytest.raises(PermissionError, match="no approval record"):
        execute_approved_action(ConsequentialAction.ISSUE_REFUND, None)


def test_pending_approval_is_refused() -> None:
    pending = ApprovalRecord(
        action=ConsequentialAction.ISSUE_REFUND, status=ApprovalStatus.PENDING
    )
    with pytest.raises(PermissionError, match="still pending"):
        execute_approved_action(ConsequentialAction.ISSUE_REFUND, pending)


def test_rejected_approval_is_refused() -> None:
    rejected = ApprovalRecord(
        action=ConsequentialAction.ISSUE_REFUND,
        status=ApprovalStatus.REJECTED,
        approver="ops-lead",
    )
    with pytest.raises(PermissionError, match="rejected"):
        execute_approved_action(ConsequentialAction.ISSUE_REFUND, rejected)


def test_approval_for_a_different_action_is_refused() -> None:
    """An approval for one thing must not authorise another."""
    wrong = _approved(ConsequentialAction.WAIVE_FEE)
    with pytest.raises(PermissionError, match="not"):
        execute_approved_action(ConsequentialAction.ISSUE_REFUND, wrong)


def test_matching_approval_executes() -> None:
    assert "executed issue_refund" in execute_approved_action(
        ConsequentialAction.ISSUE_REFUND, _approved(ConsequentialAction.ISSUE_REFUND)
    )


def test_decided_approval_must_name_an_approver() -> None:
    with pytest.raises(ValidationError):
        ApprovalRecord(
            action=ConsequentialAction.ISSUE_REFUND, status=ApprovalStatus.APPROVED
        )


# --- Generator failure must not become a silent answer ------------------------


class _FailingGenerator:
    name = "failing"

    async def generate(self, query: str, procedure: Procedure) -> str:
        raise GenerationError("simulated generator failure")


class _SlowGenerator:
    name = "slow"

    async def generate(self, query: str, procedure: Procedure) -> str:
        await asyncio.sleep(5.0)
        return "too late"


@pytest.mark.anyio
async def test_generator_failure_escalates_instead_of_answering(corpus: Corpus) -> None:
    assistant = SupportAssistant(corpus=corpus, generator=_FailingGenerator())
    response = await assistant.handle(
        QueryRequest(query="How do I book a crossing online?")
    )
    assert response.answer_text is None
    assert response.answer_source == "none"
    assert "generator failed" in " ".join(response.notes)


@pytest.mark.anyio
async def test_slow_generator_times_out(corpus: Corpus) -> None:
    config = WorkflowConfig(timeout_seconds=0.05)
    assistant = SupportAssistant(
        corpus=corpus, generator=_SlowGenerator(), config=config
    )
    with pytest.raises(WorkflowTimeout):
        await assistant.handle(QueryRequest(query="How do I book a crossing online?"))


@pytest.mark.anyio
async def test_default_generator_still_answers(corpus: Corpus) -> None:
    """Control for the two tests above: the happy path is not broken."""
    assistant = SupportAssistant(corpus=corpus, generator=MockAnswerGenerator())
    response = await assistant.handle(
        QueryRequest(query="How do I book a crossing online?")
    )
    assert response.decision is Decision.ANSWER


# --- Schema validation --------------------------------------------------------


def _procedure(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "procedure_id": "p1",
        "title": "Title",
        "topic_key": "topic.a",
        "body": "Body.",
        "status": ProcedureStatus.ACTIVE,
        "version": "1.0",
    }
    base.update(overrides)
    return base


def test_superseded_status_requires_a_successor() -> None:
    with pytest.raises(ValidationError):
        Procedure.model_validate(_procedure(status=ProcedureStatus.SUPERSEDED))


def test_successor_link_on_a_live_procedure_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Procedure.model_validate(
            _procedure(status=ProcedureStatus.ACTIVE, superseded_by="other")
        )


def test_duplicate_procedure_ids_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Corpus(
            corpus_id="c",
            description="d",
            tenant="t",
            snapshot_date="2026-10-04",  # type: ignore[arg-type]
            procedures=(
                Procedure.model_validate(_procedure()),
                Procedure.model_validate(_procedure()),
            ),
        )


def test_dangling_successor_reference_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Corpus(
            corpus_id="c",
            description="d",
            tenant="t",
            snapshot_date="2026-10-04",  # type: ignore[arg-type]
            procedures=(
                Procedure.model_validate(
                    _procedure(status=ProcedureStatus.SUPERSEDED, superseded_by="ghost")
                ),
            ),
        )


def test_retrieval_hit_rejects_a_zero_rank() -> None:
    procedure = Procedure.model_validate(_procedure())
    with pytest.raises(ValidationError):
        RetrievalHit(procedure=procedure, score=1.0, rank=0)


def test_workflow_config_rejects_a_non_positive_timeout() -> None:
    with pytest.raises(ValidationError):
        WorkflowConfig(timeout_seconds=0.0)
