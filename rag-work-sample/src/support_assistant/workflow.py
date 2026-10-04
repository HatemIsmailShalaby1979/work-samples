"""The controlled workflow, and the baseline it is measured against.

Two strategies live here, and the evaluation harness runs both over the same
labelled query set:

``RetrievalOnlyBaseline``
    The simplest thing that could work: retrieve, then always answer with the
    top hit. No gate, no abstention, no escalation. It is included because the
    comparison is the point — it shows what the gate actually buys, measured
    rather than asserted.

``SupportAssistant``
    The same retrieval, followed by the decision gate, citation recording, a
    consequential-action check, and a human-approval gate that fails closed.

Both are async. Retrieval itself is synchronous and CPU-bound, so it is called
directly; only the answer generator is awaited.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from support_assistant.adapters import (
    AnswerGenerator,
    GenerationError,
    MockAnswerGenerator,
)
from support_assistant.gate import GateConfig, evaluate
from support_assistant.models import (
    AnswerSource,
    ApprovalRecord,
    ApprovalStatus,
    AssistantResponse,
    ConsequentialAction,
    Corpus,
    Decision,
    DecisionReason,
    GateOutcome,
    QueryRequest,
    RetrievalHit,
)
from support_assistant.retrieval import Bm25Index


class WorkflowConfig(BaseModel):
    """Tunables for one assistant instance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    top_k: int = Field(default=5, ge=1, le=50)
    gate: GateConfig = Field(default_factory=GateConfig)
    #: Whole-request budget. A slow generator must not hang the workflow.
    timeout_seconds: float = Field(default=30.0, gt=0.0)


class WorkflowTimeout(RuntimeError):
    """Raised when a request exceeds its configured budget."""


# --- Consequential-action detection ------------------------------------------

#: Deterministic keyword mapping. A production system would classify this with a
#: model or an explicit action schema; here it is a readable table so the
#: approval gate can be tested without any model in the loop.
_ACTION_KEYWORDS: tuple[tuple[ConsequentialAction, tuple[str, ...]], ...] = (
    (ConsequentialAction.ISSUE_REFUND, ("refund", "money back", "reimburse")),
    (
        ConsequentialAction.APPLY_COMPENSATION,
        ("compensation", "compensated", "voucher", "owed"),
    ),
    (ConsequentialAction.WAIVE_FEE, ("waive", "waived", "no charge", "free of charge")),
)


def detect_consequential_action(query: str) -> ConsequentialAction | None:
    """Return the consequential action a query implies, if any."""
    lowered = query.lower()
    for action, keywords in _ACTION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return action
    return None


def execute_approved_action(
    action: ConsequentialAction,
    approval: ApprovalRecord | None,
) -> str:
    """Execute a consequential action — but only with a recorded human approval.

    This is the fail-closed boundary of the whole sample. It raises rather than
    proceeding when the approval is missing, pending, rejected, or for a
    different action than the one being executed. A mismatched approval is the
    interesting case: it is the shape of bug that lets an approval for one thing
    authorise another.
    """
    if approval is None:
        raise PermissionError("no approval record supplied")
    if approval.status is ApprovalStatus.PENDING:
        raise PermissionError("approval is still pending; a human must decide first")
    if approval.status is ApprovalStatus.REJECTED:
        raise PermissionError("the action was rejected by the approver")
    if approval.action is not action:
        raise PermissionError(
            f"approval is for {approval.action.value!r}, not {action.value!r}"
        )
    return f"executed {action.value} (approved by {approval.approver})"


# --- Baseline ----------------------------------------------------------------


class RetrievalOnlyBaseline:
    """Retrieve and answer with the top hit. No gate, no refusal path.

    This is the honest "simplest thing that could work" baseline the brief asks
    for. Its failure mode is the reason the gate exists.
    """

    name = "baseline_retrieval_only"

    def __init__(
        self,
        corpus: Corpus,
        generator: AnswerGenerator | None = None,
        top_k: int = 5,
    ) -> None:
        self._index = Bm25Index(corpus)
        self._generator = generator or MockAnswerGenerator()
        self._top_k = top_k

    async def handle(self, request: QueryRequest) -> AssistantResponse:
        started = time.perf_counter()
        hits = self._index.search(request.query, top_k=self._top_k)

        if not hits:
            return AssistantResponse(
                request_id=request.request_id or request.query[:32],
                decision=Decision.ABSTAIN,
                reason=DecisionReason.NO_EVIDENCE,
                answer_text=None,
                citations=(),
                proposed_action=None,
                approval=None,
                gate=GateOutcome(
                    decision=Decision.ABSTAIN,
                    reason=DecisionReason.NO_EVIDENCE,
                    chosen_procedure_id=None,
                    top_score=0.0,
                    second_score=None,
                    margin=None,
                ),
                latency_ms=(time.perf_counter() - started) * 1000.0,
                answer_source="none",
                notes=("baseline: no hits at all",),
            )

        top = hits[0]
        text = await self._generator.generate(request.query, top.procedure)
        return AssistantResponse(
            request_id=request.request_id or request.query[:32],
            decision=Decision.ANSWER,
            reason=DecisionReason.SUPPORTED,
            answer_text=text,
            citations=(top.procedure.procedure_id,),
            proposed_action=None,
            approval=None,
            gate=GateOutcome(
                decision=Decision.ANSWER,
                reason=DecisionReason.SUPPORTED,
                chosen_procedure_id=top.procedure.procedure_id,
                top_score=top.score,
                second_score=hits[1].score if len(hits) > 1 else None,
                margin=(top.score - hits[1].score) if len(hits) > 1 else None,
            ),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            answer_source=self._generator.name,
            notes=("baseline: no gate — the top hit is always answered",),
        )


# --- The controlled workflow -------------------------------------------------


class SupportAssistant:
    """Retrieval, then a deterministic gate, then a human-approval boundary."""

    name = "workflow_gated"

    def __init__(
        self,
        corpus: Corpus,
        generator: AnswerGenerator | None = None,
        config: WorkflowConfig | None = None,
    ) -> None:
        self._corpus = corpus
        self._index = Bm25Index(corpus)
        self._generator = generator or MockAnswerGenerator()
        self._config = config or WorkflowConfig()

    @property
    def config(self) -> WorkflowConfig:
        return self._config

    def retrieve(self, query: str) -> list[RetrievalHit]:
        """Expose retrieval on its own, for the retrieval-recall metric."""
        return self._index.search(query, top_k=self._config.top_k)

    async def handle(self, request: QueryRequest) -> AssistantResponse:
        """Run one request through the full workflow."""
        try:
            return await asyncio.wait_for(
                self._handle_inner(request),
                timeout=self._config.timeout_seconds,
            )
        except TimeoutError as error:
            raise WorkflowTimeout(
                f"request exceeded {self._config.timeout_seconds:.0f}s"
            ) from error

    async def _handle_inner(self, request: QueryRequest) -> AssistantResponse:
        started = time.perf_counter()
        notes: list[str] = []

        hits = self.retrieve(request.query)
        outcome = evaluate(hits, self._corpus, self._config.gate)

        citations: tuple[str, ...] = ()
        answer_text: str | None = None
        answer_source: AnswerSource = "none"
        proposed_action: ConsequentialAction | None = None
        approval: ApprovalRecord | None = None

        if (
            outcome.decision is Decision.ANSWER
            and outcome.chosen_procedure_id is not None
        ):
            chosen = self._corpus.by_id(outcome.chosen_procedure_id)
            if chosen is None:  # pragma: no cover - gate only returns known ids
                raise RuntimeError(
                    f"gate chose unknown procedure {outcome.chosen_procedure_id!r}"
                )
            citations = (chosen.procedure_id,)
            if outcome.reason is DecisionReason.SUPERSEDED_RESOLVED:
                notes.append("resolved a superseded procedure to its current version")
            try:
                answer_text = await self._generator.generate(request.query, chosen)
                answer_source = self._generator.name
            except GenerationError as error:
                # A generator failure must not become a silent answer.
                answer_text = None
                answer_source = "none"
                notes.append(f"generator failed, escalated: {error}")

        # Consequential actions are proposed, never executed here.
        action = detect_consequential_action(request.query)
        if action is not None:
            proposed_action = action
            approval = ApprovalRecord(action=action, status=ApprovalStatus.PENDING)
            notes.append(
                f"proposed {action.value}: awaiting human approval, not executed"
            )

        return AssistantResponse(
            request_id=request.request_id or request.query[:32],
            decision=outcome.decision,
            reason=outcome.reason,
            answer_text=answer_text,
            citations=citations,
            proposed_action=proposed_action,
            approval=approval,
            gate=outcome,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            answer_source=answer_source,
            notes=tuple(notes),
        )


def build_assistant(
    corpus: Corpus,
    generator: AnswerGenerator | None = None,
    config: WorkflowConfig | None = None,
) -> SupportAssistant:
    """Convenience constructor used by the harness and the tests."""
    return SupportAssistant(corpus=corpus, generator=generator, config=config)


def strategies(
    corpus: Corpus, generator: AnswerGenerator | None = None
) -> Sequence[object]:
    """Return the two strategies the harness compares, in report order."""
    return (
        RetrievalOnlyBaseline(corpus=corpus, generator=generator),
        SupportAssistant(corpus=corpus, generator=generator),
    )
