"""Tests for the decision gate.

The gate is tested against hand-built retrieval hits rather than real queries,
so each rule is exercised in isolation. A gate test that depended on BM25
scoring would be testing the retriever by accident.
"""

from __future__ import annotations

import pytest

from support_assistant import (
    Corpus,
    Decision,
    DecisionReason,
    GateConfig,
    Procedure,
    ProcedureStatus,
    RetrievalHit,
    evaluate,
)


def proc(
    procedure_id: str,
    topic_key: str,
    status: ProcedureStatus,
    superseded_by: str | None = None,
    title: str | None = None,
) -> Procedure:
    return Procedure(
        procedure_id=procedure_id,
        title=title or procedure_id.replace("-", " ").title(),
        topic_key=topic_key,
        body=f"Body text for {procedure_id}.",
        status=status,
        version="1.0",
        superseded_by=superseded_by,
    )


def hit(procedure: Procedure, score: float, rank: int) -> RetrievalHit:
    return RetrievalHit(procedure=procedure, score=score, rank=rank)


def corpus_of(*procedures: Procedure) -> Corpus:
    return Corpus(
        corpus_id="test",
        description="test corpus",
        tenant="test",
        snapshot_date="2026-10-04",  # type: ignore[arg-type]
        procedures=procedures,
    )


# --- Rule 1: no evidence ------------------------------------------------------


def test_no_hits_abstains() -> None:
    """An empty hit list abstains even when the corpus is non-empty."""
    active = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    outcome = evaluate([], corpus_of(active))
    assert outcome.decision is Decision.ABSTAIN
    assert outcome.reason is DecisionReason.NO_EVIDENCE
    assert outcome.top_score == 0.0


def test_score_below_floor_abstains() -> None:
    active = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    outcome = evaluate(
        [hit(active, 0.4, 1)], corpus_of(active), GateConfig(min_score=3.0)
    )
    assert outcome.decision is Decision.ABSTAIN
    assert outcome.reason is DecisionReason.NO_EVIDENCE


def test_score_exactly_at_floor_is_evidence() -> None:
    """The floor is inclusive; this pins the boundary so it cannot drift."""
    active = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    outcome = evaluate(
        [hit(active, 3.0, 1)], corpus_of(active), GateConfig(min_score=3.0)
    )
    assert outcome.decision is Decision.ANSWER


# --- Rules 2-4: unusable and superseded matches -------------------------------


def test_draft_material_escalates() -> None:
    draft = proc("p1", "topic.a", ProcedureStatus.DRAFT)
    outcome = evaluate([hit(draft, 9.0, 1)], corpus_of(draft))
    assert outcome.decision is Decision.ESCALATE
    assert outcome.reason is DecisionReason.DRAFT_MATERIAL


def test_retired_topic_escalates() -> None:
    retired = proc("p1", "topic.a", ProcedureStatus.RETIRED)
    outcome = evaluate([hit(retired, 9.0, 1)], corpus_of(retired))
    assert outcome.decision is Decision.ESCALATE
    assert outcome.reason is DecisionReason.TOPIC_RETIRED


def test_superseded_resolves_to_live_successor() -> None:
    old = proc("old", "topic.a", ProcedureStatus.SUPERSEDED, superseded_by="new")
    new = proc("new", "topic.a", ProcedureStatus.ACTIVE)
    outcome = evaluate([hit(old, 9.0, 1)], corpus_of(old, new))
    assert outcome.decision is Decision.ANSWER
    assert outcome.reason is DecisionReason.SUPERSEDED_RESOLVED
    assert outcome.chosen_procedure_id == "new"


def test_superseded_without_live_successor_escalates() -> None:
    """A successor that is itself retired is not a usable answer."""
    old = proc("old", "topic.a", ProcedureStatus.SUPERSEDED, superseded_by="dead")
    dead = proc("dead", "topic.a", ProcedureStatus.RETIRED)
    outcome = evaluate([hit(old, 9.0, 1)], corpus_of(old, dead))
    assert outcome.decision is Decision.ESCALATE
    assert outcome.reason is DecisionReason.SUPERSEDED_UNRESOLVED


def test_live_match_does_not_consult_a_superseded_sibling() -> None:
    """Answering from the current version must not be blocked by an old one."""
    old = proc("old", "topic.a", ProcedureStatus.SUPERSEDED, superseded_by="new")
    new = proc("new", "topic.a", ProcedureStatus.ACTIVE)
    outcome = evaluate([hit(new, 9.0, 1), hit(old, 8.0, 2)], corpus_of(old, new))
    assert outcome.decision is Decision.ANSWER
    assert outcome.chosen_procedure_id == "new"


# --- Rule 5: conflicting live coverage ----------------------------------------


def test_two_live_procedures_on_one_topic_conflict() -> None:
    first = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    second = proc("p2", "topic.a", ProcedureStatus.ACTIVE)
    outcome = evaluate(
        [hit(first, 9.0, 1), hit(second, 8.5, 2)], corpus_of(first, second)
    )
    assert outcome.decision is Decision.ESCALATE
    assert outcome.reason is DecisionReason.CONFLICTING_PROCEDURES


def test_single_live_procedure_on_a_topic_does_not_conflict() -> None:
    only = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    outcome = evaluate([hit(only, 9.0, 1)], corpus_of(only))
    assert outcome.decision is Decision.ANSWER


# --- Rule 6: ambiguity across topics ------------------------------------------


def test_close_scores_across_topics_escalate_as_ambiguous() -> None:
    first = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    second = proc("p2", "topic.b", ProcedureStatus.ACTIVE)
    outcome = evaluate(
        [hit(first, 9.0, 1), hit(second, 8.7, 2)],
        corpus_of(first, second),
        GateConfig(min_margin=1.0),
    )
    assert outcome.decision is Decision.ESCALATE
    assert outcome.reason is DecisionReason.AMBIGUOUS_MATCH


def test_distant_second_topic_does_not_escalate() -> None:
    first = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    second = proc("p2", "topic.b", ProcedureStatus.ACTIVE)
    outcome = evaluate(
        [hit(first, 9.0, 1), hit(second, 2.0, 2)],
        corpus_of(first, second),
        GateConfig(min_margin=1.0),
    )
    assert outcome.decision is Decision.ANSWER


# --- Rule 7: supported --------------------------------------------------------


def test_supported_answer_cites_the_procedure() -> None:
    active = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    outcome = evaluate([hit(active, 9.0, 1)], corpus_of(active))
    assert outcome.decision is Decision.ANSWER
    assert outcome.reason is DecisionReason.SUPPORTED
    assert outcome.chosen_procedure_id == "p1"


def test_outcome_records_the_scores_that_produced_it() -> None:
    first = proc("p1", "topic.a", ProcedureStatus.ACTIVE)
    second = proc("p2", "topic.b", ProcedureStatus.ACTIVE)
    outcome = evaluate(
        [hit(first, 9.0, 1), hit(second, 2.0, 2)], corpus_of(first, second)
    )
    assert outcome.top_score == 9.0
    assert outcome.second_score == 2.0
    assert outcome.margin == pytest.approx(7.0)
