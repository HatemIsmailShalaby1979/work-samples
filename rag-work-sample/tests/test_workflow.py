"""Tests for the two strategies: the baseline and the gated workflow."""

from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from support_assistant import (
    ApprovalStatus,
    ConsequentialAction,
    Corpus,
    Decision,
    DecisionReason,
    MockAnswerGenerator,
    QueryRequest,
    RetrievalOnlyBaseline,
    SupportAssistant,
    detect_consequential_action,
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


@pytest.fixture(scope="module")
def assistant(corpus: Corpus) -> SupportAssistant:
    return SupportAssistant(corpus=corpus, generator=MockAnswerGenerator())


@pytest.fixture(scope="module")
def baseline(corpus: Corpus) -> RetrievalOnlyBaseline:
    return RetrievalOnlyBaseline(corpus=corpus, generator=MockAnswerGenerator())


# --- The baseline's defining behaviour ----------------------------------------


@pytest.mark.anyio
async def test_baseline_answers_everything(
    baseline: RetrievalOnlyBaseline,
) -> None:
    """The baseline has no refusal path. That is the point of including it."""
    response = await baseline.handle(
        QueryRequest(query="What is the weather tomorrow?")
    )
    assert response.decision is Decision.ANSWER


@pytest.mark.anyio
async def test_baseline_answers_from_a_draft(
    baseline: RetrievalOnlyBaseline,
) -> None:
    """The baseline will happily answer from unapproved material."""
    response = await baseline.handle(
        QueryRequest(query="Is there an off-peak discount before eight in the morning?")
    )
    assert response.decision is Decision.ANSWER


# --- The workflow's refusals --------------------------------------------------


@pytest.mark.anyio
async def test_workflow_abstains_on_out_of_scope(assistant: SupportAssistant) -> None:
    response = await assistant.handle(
        QueryRequest(query="Can you recommend a hotel near the port?")
    )
    assert response.decision is Decision.ABSTAIN
    assert response.reason is DecisionReason.NO_EVIDENCE
    assert response.answer_text is None
    assert response.citations == ()


@pytest.mark.anyio
async def test_workflow_escalates_on_conflicting_procedures(
    assistant: SupportAssistant,
) -> None:
    response = await assistant.handle(
        QueryRequest(query="What is the baggage allowance?")
    )
    assert response.decision is Decision.ESCALATE
    assert response.reason is DecisionReason.CONFLICTING_PROCEDURES


@pytest.mark.anyio
async def test_workflow_escalates_on_draft_material(
    assistant: SupportAssistant,
) -> None:
    response = await assistant.handle(
        QueryRequest(
            query="Is there a discount for sailings before eight in the morning?"
        )
    )
    assert response.decision is Decision.ESCALATE
    assert response.reason is DecisionReason.DRAFT_MATERIAL


@pytest.mark.anyio
async def test_workflow_escalates_on_retired_topic(assistant: SupportAssistant) -> None:
    response = await assistant.handle(
        QueryRequest(query="How do I redeem my Harbourline Rewards points?")
    )
    assert response.decision is Decision.ESCALATE
    assert response.reason is DecisionReason.TOPIC_RETIRED


# --- The workflow's answers ---------------------------------------------------


@pytest.mark.anyio
async def test_workflow_answers_with_a_citation(assistant: SupportAssistant) -> None:
    response = await assistant.handle(
        QueryRequest(query="How do I book a crossing online?")
    )
    assert response.decision is Decision.ANSWER
    assert response.citations == ("booking-online",)
    assert response.answer_text
    assert response.answer_source == "extractive_mock"


@pytest.mark.anyio
async def test_workflow_resolves_a_superseded_procedure(
    assistant: SupportAssistant,
) -> None:
    """The refund topic's older procedure must never be the one cited.

    This query ranks ``refund-standard`` (superseded) above
    ``refund-standard-v2`` (active), so it exercises the resolution path rather
    than the plain-match path.
    """
    response = await assistant.handle(
        QueryRequest(
            query="How many days before departure must I cancel for a full refund?"
        )
    )
    assert response.decision is Decision.ANSWER
    assert response.reason is DecisionReason.SUPERSEDED_RESOLVED
    assert response.citations == ("refund-standard-v2",)
    assert "refund-standard" not in response.citations


@pytest.mark.anyio
async def test_legitimate_but_weak_query_abstains_at_the_configured_floor(
    assistant: SupportAssistant,
) -> None:
    """Pins the deliberate cost of the operating point.

    This question is genuinely answerable, but its best BM25 score is 2.90 —
    just below the 3.0 floor. The gate abstains. The calibration sweep in
    run_eval.py shows that lowering the floor to 2.5 would answer it and would
    also let one unsupported answer through. Zero unsupported answers is the
    chosen trade-off, and this test records what it costs.
    """
    response = await assistant.handle(
        QueryRequest(query="How long do refunds take to reach my account?")
    )
    assert response.decision is Decision.ABSTAIN
    assert response.gate.top_score < 3.0
    assert response.gate.top_score > 2.5


@pytest.mark.anyio
async def test_mock_answer_is_extractive(assistant: SupportAssistant) -> None:
    """The mock must not invent text: its answer comes from the procedure body."""
    response = await assistant.handle(
        QueryRequest(query="Can I take my dog on the ferry?")
    )
    assert response.answer_text is not None
    procedure = assistant._corpus.by_id("pet-travel")
    assert procedure is not None
    assert response.answer_text.strip(".") in procedure.body


# --- Consequential actions and the approval gate ------------------------------


def test_action_detection_is_deterministic() -> None:
    assert (
        detect_consequential_action("I want a refund")
        is ConsequentialAction.ISSUE_REFUND
    )
    assert detect_consequential_action("am I owed compensation") is (
        ConsequentialAction.APPLY_COMPENSATION
    )
    assert detect_consequential_action("can you waive the fee") is (
        ConsequentialAction.WAIVE_FEE
    )
    assert detect_consequential_action("what time is the ferry") is None


@pytest.mark.anyio
async def test_consequential_action_is_proposed_not_executed(
    assistant: SupportAssistant,
) -> None:
    response = await assistant.handle(
        QueryRequest(query="I want a refund for my cancelled crossing")
    )
    assert response.proposed_action is ConsequentialAction.ISSUE_REFUND
    assert response.approval is not None
    assert response.approval.status is ApprovalStatus.PENDING
    assert response.approval.approver is None
    assert "not executed" in " ".join(response.notes)


@pytest.mark.anyio
async def test_response_is_immutable(assistant: SupportAssistant) -> None:
    """Every response model is frozen; a caller cannot mutate an audit record."""
    response = await assistant.handle(QueryRequest(query="How do I book online?"))
    with pytest.raises(ValidationError):
        response.decision = Decision.ABSTAIN  # type: ignore[misc]
