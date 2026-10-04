"""Metric computation for the evaluation harness.

The metrics are chosen to answer four separate questions, which are easy to
conflate:

* **Did retrieval find the right document?** — ``retrieval_recall_at_k``. This
  is a property of the retriever alone, independent of any decision.
* **Did the assistant decide correctly?** — ``decision_accuracy``, measured
  against the labels in the evaluation set.
* **Did it answer when it should not have?** — ``unsupported_answers``. This is
  the safety-critical number. Everything else is a quality trade-off; this one
  is a defect.
* **Was it fast enough?** — ``latency_p50_ms`` / ``latency_p95_ms``.

Reporting them separately matters because a single "accuracy" figure would hide
the difference between an assistant that is unhelpful and one that is unsafe.
"""

from __future__ import annotations

from collections.abc import Sequence

from support_assistant.models import CaseResult, Decision, EvalCategory, Metrics


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Nearest-rank percentile. Deterministic, and adequate at this sample size."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = min(len(ordered) - 1, max(0, round(percentile * (len(ordered) - 1))))
    return ordered[index]


def compute_metrics(results: Sequence[CaseResult], strategy: str) -> Metrics:
    """Aggregate a strategy's per-case results into the reported metrics."""
    if not results:
        raise ValueError("cannot compute metrics over zero results")

    total = len(results)

    decision_correct = sum(1 for result in results if result.decision_correct)

    retrieval_cases = [result for result in results if result.retrieval_hit is not None]
    retrieval_hits = sum(1 for result in retrieval_cases if result.retrieval_hit)

    unsupported = sum(1 for result in results if result.unsupported_answer)

    abstention_cases = [
        result for result in results if result.expected_decision is Decision.ABSTAIN
    ]
    correct_abstentions = sum(
        1 for result in abstention_cases if result.decision is Decision.ABSTAIN
    )

    escalation_cases = [
        result for result in results if result.expected_decision is Decision.ESCALATE
    ]
    correct_escalations = sum(
        1 for result in escalation_cases if result.decision is Decision.ESCALATE
    )

    answered_when_should_refuse = sum(
        1
        for result in results
        if result.decision is Decision.ANSWER
        and result.expected_decision is not Decision.ANSWER
    )

    latencies = [result.latency_ms for result in results]

    return Metrics(
        strategy=strategy,
        cases=total,
        decision_accuracy=round(decision_correct / total, 4),
        retrieval_recall_at_k=(
            round(retrieval_hits / len(retrieval_cases), 4) if retrieval_cases else 0.0
        ),
        retrieval_cases=len(retrieval_cases),
        unsupported_answers=unsupported,
        unsupported_answer_rate=round(unsupported / total, 4),
        correct_abstentions=correct_abstentions,
        abstention_cases=len(abstention_cases),
        correct_escalations=correct_escalations,
        escalation_cases=len(escalation_cases),
        answered_when_should_abstain_or_escalate=answered_when_should_refuse,
        latency_p50_ms=round(_percentile(latencies, 0.50), 3),
        latency_p95_ms=round(_percentile(latencies, 0.95), 3),
    )


def category_breakdown(
    results: Sequence[CaseResult],
) -> dict[EvalCategory, tuple[int, int]]:
    """Return ``category -> (correct, total)`` for the per-category table."""
    tally: dict[EvalCategory, list[int]] = {}
    for result in results:
        entry = tally.setdefault(result.category, [0, 0])
        entry[1] += 1
        if result.decision_correct:
            entry[0] += 1
    return {category: (counts[0], counts[1]) for category, counts in tally.items()}
