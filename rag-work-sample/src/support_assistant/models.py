"""Typed domain models for the support-policy assistant.

Every value that crosses a boundary in this package is a Pydantic v2 model or a
plain immutable type. Nothing is passed as a bare ``dict``.

The models are deliberately strict: validation failures are meant to be loud,
because the whole point of the sample is that a support assistant should refuse
rather than guess.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


class ProcedureStatus(StrEnum):
    """Lifecycle state of a procedure in the corpus."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETIRED = "retired"
    DRAFT = "draft"


class Procedure(BaseModel):
    """One customer-support procedure.

    ``topic_key`` groups procedures that answer the same underlying question.
    It is what lets the gate tell a *conflict* (two live procedures disagreeing)
    apart from an *ambiguity* (two unrelated procedures scoring alike).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    procedure_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    topic_key: str = Field(min_length=1)
    body: str = Field(min_length=1)
    status: ProcedureStatus
    version: str = Field(min_length=1)
    effective_from: date | None = None
    effective_to: date | None = None
    supersedes: str | None = None
    superseded_by: str | None = None

    @model_validator(mode="after")
    def _check_supersession_is_consistent(self) -> Procedure:
        """A superseded procedure must name its successor; nothing else may."""
        if self.status is ProcedureStatus.SUPERSEDED and self.superseded_by is None:
            raise ValueError(
                f"{self.procedure_id}: status is 'superseded' but superseded_by is null"
            )
        if (
            self.status is not ProcedureStatus.SUPERSEDED
            and self.superseded_by is not None
        ):
            raise ValueError(
                f"{self.procedure_id}: superseded_by is set but status is {self.status.value!r}"
            )
        return self

    @property
    def is_answerable(self) -> bool:
        """Whether this procedure may be used to answer a customer directly."""
        return self.status is ProcedureStatus.ACTIVE

    @property
    def is_usable_with_resolution(self) -> bool:
        """Superseded procedures are usable only to find their successor."""
        return self.status is ProcedureStatus.SUPERSEDED


class Corpus(BaseModel):
    """A tenant's procedure set, plus the date it was snapshotted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_id: str
    description: str
    tenant: str
    snapshot_date: date
    procedures: tuple[Procedure, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_ids_are_unique(self) -> Corpus:
        seen: set[str] = set()
        for procedure in self.procedures:
            if procedure.procedure_id in seen:
                raise ValueError(f"duplicate procedure_id: {procedure.procedure_id}")
            seen.add(procedure.procedure_id)
        return self

    @model_validator(mode="after")
    def _check_successors_exist(self) -> Corpus:
        known = {procedure.procedure_id for procedure in self.procedures}
        for procedure in self.procedures:
            if (
                procedure.superseded_by is not None
                and procedure.superseded_by not in known
            ):
                raise ValueError(
                    f"{procedure.procedure_id}: superseded_by points at unknown "
                    f"procedure {procedure.superseded_by!r}"
                )
        return self

    def by_id(self, procedure_id: str) -> Procedure | None:
        """Look a procedure up by id, or return ``None``."""
        for procedure in self.procedures:
            if procedure.procedure_id == procedure_id:
                return procedure
        return None


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class RetrievalHit(BaseModel):
    """One scored procedure returned by the retriever."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    procedure: Procedure
    score: float
    rank: int = Field(ge=1)


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


class Decision(StrEnum):
    """What the assistant decided to do with a query."""

    ANSWER = "answer"
    ESCALATE = "escalate"
    ABSTAIN = "abstain"


class DecisionReason(StrEnum):
    """Why the assistant reached its decision. Recorded for every query."""

    SUPPORTED = "supported"
    NO_EVIDENCE = "no_evidence"
    AMBIGUOUS_MATCH = "ambiguous_match"
    CONFLICTING_PROCEDURES = "conflicting_procedures"
    SUPERSEDED_RESOLVED = "superseded_resolved"
    SUPERSEDED_UNRESOLVED = "superseded_unresolved"
    TOPIC_RETIRED = "topic_retired"
    DRAFT_MATERIAL = "draft_material"


class GateOutcome(BaseModel):
    """The gate's verdict, with the numbers that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Decision
    reason: DecisionReason
    chosen_procedure_id: str | None
    top_score: float
    second_score: float | None
    margin: float | None


# ---------------------------------------------------------------------------
# Consequential actions and human approval
# ---------------------------------------------------------------------------


class ConsequentialAction(StrEnum):
    """An action that must not execute without a human decision."""

    ISSUE_REFUND = "issue_refund"
    APPLY_COMPENSATION = "apply_compensation"
    WAIVE_FEE = "waive_fee"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRecord(BaseModel):
    """The recorded human decision on a proposed consequential action."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ConsequentialAction
    status: ApprovalStatus
    approver: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _check_approver_present_when_decided(self) -> ApprovalRecord:
        if self.status is not ApprovalStatus.PENDING and not self.approver:
            raise ValueError("a decided approval must name an approver")
        return self


# ---------------------------------------------------------------------------
# Request and response
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """An inbound customer query, validated before it reaches retrieval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: Annotated[str, Field(min_length=3, max_length=500)]
    tenant: str = Field(default="harbourline-ferries-support-procedures", min_length=1)
    request_id: str | None = None

    @field_validator("query")
    @classmethod
    def _reject_non_questions(cls, value: str) -> str:
        """Reject input that is empty once stripped, or is only punctuation."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        if not any(character.isalnum() for character in stripped):
            raise ValueError("query must contain at least one alphanumeric character")
        return stripped


#: Where a response's answer text came from. Constrained so an unexpected
#: generator cannot silently record an unrecognised source.
AnswerSource = Literal["extractive_mock", "ollama", "none", "custom"]


class AssistantResponse(BaseModel):
    """The full result of one assistant turn, including its reasoning trail."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    decision: Decision
    reason: DecisionReason
    answer_text: str | None
    citations: tuple[str, ...]
    proposed_action: ConsequentialAction | None
    approval: ApprovalRecord | None
    gate: GateOutcome
    latency_ms: float = Field(ge=0.0)
    answer_source: AnswerSource
    notes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class EvalCategory(StrEnum):
    ANSWERABLE = "answerable"
    PARAPHRASED = "paraphrased"
    CONFLICTING = "conflicting"
    OUTDATED = "outdated"
    OUT_OF_SCOPE = "out_of_scope"


class EvalCase(BaseModel):
    """One labelled evaluation query with its expected outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str
    category: EvalCategory
    query: str = Field(min_length=1)
    expected_decision: Decision
    expected_reason: DecisionReason | None = None
    expected_procedure_id: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _check_expected_procedure_only_when_answering(self) -> EvalCase:
        if (
            self.expected_decision is Decision.ANSWER
            and self.expected_procedure_id is None
        ):
            raise ValueError(
                f"{self.query_id}: an 'answer' label must name the expected procedure"
            )
        return self


class CaseResult(BaseModel):
    """The measured outcome of one evaluation case under one strategy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_id: str
    category: EvalCategory
    strategy: str
    decision: Decision
    reason: DecisionReason
    expected_decision: Decision
    expected_procedure_id: str | None
    chosen_procedure_id: str | None
    retrieved_ids: tuple[str, ...]
    decision_correct: bool
    procedure_correct: bool | None
    retrieval_hit: bool | None
    unsupported_answer: bool
    latency_ms: float = Field(ge=0.0)


class Metrics(BaseModel):
    """Aggregate metrics for one strategy over one evaluation set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: str
    cases: int = Field(ge=1)
    decision_accuracy: float
    retrieval_recall_at_k: float
    retrieval_cases: int
    unsupported_answers: int
    unsupported_answer_rate: float
    correct_abstentions: int
    abstention_cases: int
    correct_escalations: int
    escalation_cases: int
    answered_when_should_abstain_or_escalate: int
    latency_p50_ms: float
    latency_p95_ms: float
