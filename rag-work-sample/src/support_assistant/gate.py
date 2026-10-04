"""The decision gate: what the assistant is allowed to do with a retrieval result.

The gate is deliberately deterministic and rule-based. No model is consulted
here. That is the point of the sample: the decision to answer, abstain or
escalate is made by readable rules that can be argued with, not by a model's
judgement.

Order of evaluation matters, and is tested:

1. ``NO_EVIDENCE``           nothing scored above the floor — abstain
2. ``DRAFT_MATERIAL``        the best match is unapproved — escalate
3. ``TOPIC_RETIRED``         the best match is withdrawn with no successor — escalate
4. ``SUPERSEDED_RESOLVED``   the best match is replaced by its live successor
   ``SUPERSEDED_UNRESOLVED``  the best match is superseded with no usable successor — escalate
5. ``CONFLICTING_PROCEDURES`` the topic has more than one live procedure — escalate
6. ``AMBIGUOUS_MATCH``       a different topic scored nearly as highly — escalate
7. ``SUPPORTED``             answer, citing the chosen procedure

A known limitation, stated here rather than hidden
--------------------------------------------------
Rule 5 detects that a topic is covered by more than one *live* procedure. It
does not detect whether those procedures actually disagree — it cannot, because
disagreement is semantic. A production system would need contradiction
detection over the procedure text (the author's LIVE Support Assistant uses a
conflict lint for exactly this). Here the corpus is constructed so that
duplicate live coverage and genuine contradiction coincide, and the limitation
is recorded in the README.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from support_assistant.models import (
    Corpus,
    Decision,
    DecisionReason,
    GateOutcome,
    Procedure,
    ProcedureStatus,
    RetrievalHit,
)


class GateConfig(BaseModel):
    """Thresholds for the gate. Every value is explicit and tunable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Minimum BM25 score for the best hit to count as evidence at all.
    #: 3.0 was chosen by sweeping the threshold (see ``run_eval.py --calibrate``):
    #: it is the lowest value at which unsupported answers reach zero, and it
    #: keeps 8/8 escalations and 7/8 abstentions, the single miss being a safe
    #: escalation rather than an unsupported answer. Raising it to 4.0 buys the
    #: last abstention at the cost of two correct escalations.
    min_score: float = Field(default=3.0, ge=0.0)
    #: How close the runner-up may be, on a different topic, before the match
    #: is treated as ambiguous rather than clear.
    min_margin: float = Field(default=1.0, ge=0.0)


def _resolve(
    procedure: Procedure, corpus: Corpus
) -> tuple[Procedure | None, DecisionReason]:
    """Resolve a candidate procedure to something answerable.

    Returns the procedure that may be used to answer, and the reason that
    records how it was arrived at. ``None`` means the gate must escalate.
    """
    if procedure.status is ProcedureStatus.ACTIVE:
        return procedure, DecisionReason.SUPPORTED

    if procedure.status is ProcedureStatus.DRAFT:
        return None, DecisionReason.DRAFT_MATERIAL

    if procedure.status is ProcedureStatus.RETIRED:
        return None, DecisionReason.TOPIC_RETIRED

    # Superseded: follow the link, but only if it lands on a live procedure.
    if procedure.superseded_by is not None:
        successor = corpus.by_id(procedure.superseded_by)
        if successor is not None and successor.status is ProcedureStatus.ACTIVE:
            return successor, DecisionReason.SUPERSEDED_RESOLVED

    return None, DecisionReason.SUPERSEDED_UNRESOLVED


def _live_procedures_for_topic(corpus: Corpus, topic_key: str) -> tuple[Procedure, ...]:
    """Every live procedure sharing a topic key."""
    return tuple(
        procedure
        for procedure in corpus.procedures
        if procedure.topic_key == topic_key
        and procedure.status is ProcedureStatus.ACTIVE
    )


def evaluate(
    hits: list[RetrievalHit],
    corpus: Corpus,
    config: GateConfig | None = None,
) -> GateOutcome:
    """Apply the gate to a ranked retrieval result."""
    settings = config or GateConfig()

    if not hits:
        return GateOutcome(
            decision=Decision.ABSTAIN,
            reason=DecisionReason.NO_EVIDENCE,
            chosen_procedure_id=None,
            top_score=0.0,
            second_score=None,
            margin=None,
        )

    top = hits[0]
    second = hits[1] if len(hits) > 1 else None
    margin = (top.score - second.score) if second is not None else None

    # 1. Is there any evidence at all?
    if top.score < settings.min_score:
        return GateOutcome(
            decision=Decision.ABSTAIN,
            reason=DecisionReason.NO_EVIDENCE,
            chosen_procedure_id=None,
            top_score=top.score,
            second_score=second.score if second else None,
            margin=margin,
        )

    # 2-4. Can the best match be used, or resolved to something usable?
    chosen, reason = _resolve(top.procedure, corpus)
    if chosen is None:
        return GateOutcome(
            decision=Decision.ESCALATE,
            reason=reason,
            chosen_procedure_id=None,
            top_score=top.score,
            second_score=second.score if second else None,
            margin=margin,
        )

    # 5. Is the topic covered by more than one live procedure?
    if len(_live_procedures_for_topic(corpus, chosen.topic_key)) > 1:
        return GateOutcome(
            decision=Decision.ESCALATE,
            reason=DecisionReason.CONFLICTING_PROCEDURES,
            chosen_procedure_id=None,
            top_score=top.score,
            second_score=second.score if second else None,
            margin=margin,
        )

    # 6. Did a different topic score nearly as highly?
    best_other_topic = next(
        (hit for hit in hits if hit.procedure.topic_key != chosen.topic_key),
        None,
    )
    if best_other_topic is not None:
        gap = top.score - best_other_topic.score
        if gap < settings.min_margin:
            return GateOutcome(
                decision=Decision.ESCALATE,
                reason=DecisionReason.AMBIGUOUS_MATCH,
                chosen_procedure_id=None,
                top_score=top.score,
                second_score=best_other_topic.score,
                margin=gap,
            )

    # 7. Answer.
    return GateOutcome(
        decision=Decision.ANSWER,
        reason=reason,
        chosen_procedure_id=chosen.procedure_id,
        top_score=top.score,
        second_score=second.score if second else None,
        margin=margin,
    )
