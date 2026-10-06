#!/usr/bin/env python3
"""Run the labelled evaluation set against both strategies and report metrics.

    python run_eval.py                     # deterministic mock generator (default)
    python run_eval.py --generator ollama  # opt-in: call the local model
    python run_eval.py --update-expected   # regenerate expected/eval_report.txt

The default run is hermetic: no network, no model, no dependency beyond Pydantic
and the standard library. It produces byte-identical output every time, which is
what makes the committed report in ``expected/`` a meaningful specification.

This is a work sample. It is not production experience and nothing here is
deployed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from support_assistant import (
    Bm25Index,
    CaseResult,
    Corpus,
    Decision,
    EvalCase,
    GateConfig,
    MockAnswerGenerator,
    OllamaAnswerGenerator,
    QueryRequest,
    RetrievalOnlyBaseline,
    SupportAssistant,
    WorkflowConfig,
    category_breakdown,
    compute_metrics,
    load_corpus,
)
from support_assistant.adapters import AnswerGenerator
from support_assistant.models import Metrics

CORPUS_PATH = ROOT / "corpus" / "harbourline_procedures.json"
EVALSET_PATH = ROOT / "evalset" / "eval_queries.jsonl"
EXPECTED_PATH = ROOT / "expected" / "eval_report.txt"

MAX_FAILURE_EXAMPLES = 12

#: Latency is a wall-clock measurement taken on one machine, so it cannot be
#: byte-stable between runs. Rather than drop it from the report — it is a real
#: measurement and worth printing — the *committed* report records the line as
#: unpinned, and the comparison is made between canonicalised reports. This is
#: the only non-deterministic field in the whole output; everything else, every
#: decision and every score, is reproducible.
_LATENCY_LINE = re.compile(r"^(  latency p50 / p95\s+).*$", re.MULTILINE)
_LATENCY_UNPINNED = "measured at runtime — not pinned (see limitations)"


def canonicalise(report: str) -> str:
    """Replace the unpinnable latency values with a fixed marker."""
    return _LATENCY_LINE.sub(rf"\g<1>{_LATENCY_UNPINNED}", report)


# --- Loading ------------------------------------------------------------------


def load_eval_set(path: pathlib.Path) -> list[EvalCase]:
    """Read the JSONL evaluation set into validated models."""
    cases: list[EvalCase] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            cases.append(EvalCase.model_validate(json.loads(stripped)))
        except Exception as error:
            raise ValueError(f"{path.name}:{line_number}: {error}") from error
    if not cases:
        raise ValueError(f"{path.name}: no evaluation cases found")
    return cases


# --- Execution ----------------------------------------------------------------


async def run_strategy(
    strategy: RetrievalOnlyBaseline | SupportAssistant,
    cases: list[EvalCase],
    index: Bm25Index,
    top_k: int,
) -> list[CaseResult]:
    """Run every case through one strategy and record the outcome."""
    results: list[CaseResult] = []
    for case in cases:
        request = QueryRequest(query=case.query, request_id=case.query_id)
        response = await strategy.handle(request)

        retrieved_ids = tuple(
            hit.procedure.procedure_id for hit in index.search(case.query, top_k=top_k)
        )

        retrieval_hit: bool | None = None
        if case.expected_procedure_id is not None:
            retrieval_hit = case.expected_procedure_id in retrieved_ids

        chosen_procedure_id = response.gate.chosen_procedure_id

        # Decision correctness has two parts when the expected outcome is an
        # answer: the assistant must decide to answer AND must answer from the
        # right procedure. Counting only the first would let a wrong answer
        # score as a success, which is exactly the defect this metric exists to
        # catch.
        procedure_correct: bool | None = None
        if case.expected_procedure_id is not None:
            procedure_correct = chosen_procedure_id == case.expected_procedure_id

        if case.expected_decision is Decision.ANSWER:
            decision_correct = (
                response.decision is Decision.ANSWER
                and chosen_procedure_id == case.expected_procedure_id
            )
        else:
            decision_correct = response.decision is case.expected_decision

        results.append(
            CaseResult(
                query_id=case.query_id,
                category=case.category,
                strategy=strategy.name,
                decision=response.decision,
                reason=response.reason,
                expected_decision=case.expected_decision,
                expected_procedure_id=case.expected_procedure_id,
                chosen_procedure_id=chosen_procedure_id,
                retrieved_ids=retrieved_ids,
                decision_correct=decision_correct,
                procedure_correct=procedure_correct,
                retrieval_hit=retrieval_hit,
                unsupported_answer=(
                    response.decision is Decision.ANSWER
                    and case.expected_decision is not Decision.ANSWER
                ),
                latency_ms=response.latency_ms,
            )
        )
    return results


# --- Calibration --------------------------------------------------------------

CALIBRATION_THRESHOLDS: tuple[float, ...] = (
    0.0,
    1.0,
    2.0,
    2.5,
    3.0,
    3.5,
    4.0,
    5.0,
    6.0,
    8.0,
)


async def sweep_thresholds(
    corpus: Corpus,
    cases: list[EvalCase],
    generator: AnswerGenerator,
    index: Bm25Index,
    top_k: int,
    thresholds: tuple[float, ...] = CALIBRATION_THRESHOLDS,
) -> list[tuple[float, Metrics]]:
    """Re-run the whole evaluation at each candidate score floor."""
    rows: list[tuple[float, Metrics]] = []
    for threshold in thresholds:
        config = WorkflowConfig(gate=GateConfig(min_score=threshold))
        assistant = SupportAssistant(corpus=corpus, generator=generator, config=config)
        results = await run_strategy(assistant, cases, index, top_k)
        rows.append((threshold, compute_metrics(results, f"min_score={threshold}")))
    return rows


def render_calibration(rows: list[tuple[float, Metrics]], default: float) -> list[str]:
    """Render the threshold sweep, marking the chosen operating point."""
    lines = [
        "  min_score   decision_acc   unsupported   abstain_ok   escalate_ok   chosen",
        "  " + "-" * 74,
    ]
    for threshold, metrics in rows:
        marker = "<-- default" if threshold == default else ""
        lines.append(
            f"  {threshold:>9.1f}   {metrics.decision_accuracy:>12.4f}   "
            f"{metrics.unsupported_answers:>11d}   "
            f"{metrics.correct_abstentions:>6d}/{metrics.abstention_cases:<2d}   "
            f"{metrics.correct_escalations:>6d}/{metrics.escalation_cases:<2d}   {marker}"
        )
    lines.append("")
    lines.append(
        "  The floor is the one number in this sample that is chosen rather than"
    )
    lines.append(
        "  derived, so the sweep is reported rather than hidden. 3.0 is the lowest"
    )
    lines.append(
        "  value at which unsupported answers reach zero. 2.5 would answer one more"
    )
    lines.append(
        "  legitimate question and would also let one unsupported answer through —"
    )
    lines.append(
        "  which is the trade-off the floor exists to make. Above 3.5, accuracy falls"
    )
    lines.append("  as the gate refuses questions it could have answered.")
    lines.append("")
    lines.append(
        "  These thresholds were tuned on this evaluation set, which is fitting on"
    )
    lines.append("  the test set. A deployment would calibrate on a held-out set.")
    return lines


# --- Reporting ----------------------------------------------------------------


def render_metrics(metrics: Metrics) -> list[str]:
    """Render one strategy's metrics block."""
    return [
        f"  strategy                      {metrics.strategy}",
        f"  cases                         {metrics.cases}",
        (
            f"  decision accuracy             {metrics.decision_accuracy:.4f}"
            f"  ({round(metrics.decision_accuracy * metrics.cases)}/{metrics.cases})"
        ),
        (
            f"  retrieval recall@k            {metrics.retrieval_recall_at_k:.4f}"
            f"  ({metrics.retrieval_cases} labelled cases)"
        ),
        (
            f"  UNSUPPORTED ANSWERS           {metrics.unsupported_answers}"
            f"  (rate {metrics.unsupported_answer_rate:.4f})"
        ),
        f"  answered when it should not   {metrics.answered_when_should_abstain_or_escalate}",
        f"  correct abstentions           {metrics.correct_abstentions}/{metrics.abstention_cases}",
        f"  correct escalations           {metrics.correct_escalations}/{metrics.escalation_cases}",
        (
            f"  latency p50 / p95             {metrics.latency_p50_ms:.3f} ms / "
            f"{metrics.latency_p95_ms:.3f} ms"
        ),
    ]


def render_category_table(results: list[CaseResult], strategy: str) -> list[str]:
    """Render the per-category accuracy table for one strategy."""
    breakdown = category_breakdown(results)
    lines = [f"  {strategy}"]
    for category in sorted(breakdown, key=lambda item: item.value):
        correct, total = breakdown[category]
        marker = "OK " if correct == total else "!! "
        lines.append(f"    {marker}{category.value:<14} {correct}/{total}")
    return lines


def render_failures(results: list[CaseResult], strategy: str) -> list[str]:
    """Render failure examples — the part of the report worth reading."""
    failures = [result for result in results if not result.decision_correct]
    if not failures:
        return [f"  {strategy}: no failures."]

    lines = [f"  {strategy}: {len(failures)} failure(s)"]
    for result in failures[:MAX_FAILURE_EXAMPLES]:
        lines.append(
            f"    {result.query_id} [{result.category.value}] "
            f"expected={result.expected_decision.value} "
            f"got={result.decision.value}/{result.reason.value}"
        )
        if result.expected_decision is Decision.ANSWER:
            lines.append(f"        expected procedure: {result.expected_procedure_id}")
            lines.append(
                f"        chosen procedure:   {result.chosen_procedure_id or '(none)'}"
            )
        lines.append(f"        retrieved: {', '.join(result.retrieved_ids[:3])}")
    if len(failures) > MAX_FAILURE_EXAMPLES:
        lines.append(f"    ... and {len(failures) - MAX_FAILURE_EXAMPLES} more")
    return lines


def count_procedure_correct(results: list[CaseResult]) -> tuple[int, int]:
    """Count cases where the correct procedure was chosen, over labelled cases."""
    labelled = [result for result in results if result.procedure_correct is not None]
    correct = sum(1 for result in labelled if result.procedure_correct)
    return correct, len(labelled)


def build_report(
    corpus_size: int,
    case_count: int,
    generator_name: str,
    top_k: int,
    min_score: float,
    min_margin: float,
    baseline_results: list[CaseResult],
    workflow_results: list[CaseResult],
    baseline_metrics: Metrics,
    workflow_metrics: Metrics,
    calibration: list[tuple[float, Metrics]],
) -> str:
    """Assemble the full text report."""
    unsupported_delta = (
        baseline_metrics.unsupported_answers - workflow_metrics.unsupported_answers
    )
    accuracy_delta = (
        workflow_metrics.decision_accuracy - baseline_metrics.decision_accuracy
    )

    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("Support-policy assistant — evaluation report")
    add("=" * 78)
    add("")
    add("This is a WORK SAMPLE, not production delivery. Nothing here is deployed.")
    add("Every figure below was produced locally on synthetic data.")
    add("")
    add("configuration")
    add(f"  corpus procedures             {corpus_size}")
    add(f"  evaluation cases              {case_count}")
    add(f"  answer generator              {generator_name}")
    add(f"  top_k                         {top_k}")
    add(f"  gate min_score                {min_score}")
    add(f"  gate min_margin               {min_margin}")
    add("")

    add("-" * 78)
    add("metrics by strategy")
    add("-" * 78)
    add("")
    add("  [A] baseline — retrieval only, always answers the top hit")
    lines.extend(render_metrics(baseline_metrics))
    add("")
    add("  [B] workflow — retrieval + deterministic gate + citations")
    lines.extend(render_metrics(workflow_metrics))
    add("")

    add("-" * 78)
    add("what the gate changed")
    add("-" * 78)
    add("")
    add(
        f"  unsupported answers      {baseline_metrics.unsupported_answers} "
        f"-> {workflow_metrics.unsupported_answers}   (delta {unsupported_delta:+d})"
    )
    add(
        f"  decision accuracy        {baseline_metrics.decision_accuracy:.4f} "
        f"-> {workflow_metrics.decision_accuracy:.4f}   (delta {accuracy_delta:+.4f})"
    )
    baseline_proc, labelled = count_procedure_correct(baseline_results)
    workflow_proc, _ = count_procedure_correct(workflow_results)
    add(
        f"  correct procedure cited  {baseline_proc}/{labelled} -> "
        f"{workflow_proc}/{labelled}   (of labelled cases)"
    )
    add(
        f"  correct escalations      {baseline_metrics.correct_escalations}"
        f"/{baseline_metrics.escalation_cases} -> {workflow_metrics.correct_escalations}"
        f"/{workflow_metrics.escalation_cases}"
    )
    add(
        f"  correct abstentions      {baseline_metrics.correct_abstentions}"
        f"/{baseline_metrics.abstention_cases} -> {workflow_metrics.correct_abstentions}"
        f"/{workflow_metrics.abstention_cases}"
    )
    add("")
    add("  Reading: the baseline answers everything, so every conflicting, outdated")
    add("  and out-of-scope case becomes an unsupported answer. The gate removes")
    add("  those, and the price it pays is over-escalation on cases it cannot")
    add("  resolve — visible as a decision-accuracy figure that is not perfect.")
    add("")

    add("-" * 78)
    add("accuracy by category")
    add("-" * 78)
    add("")
    lines.extend(render_category_table(baseline_results, "baseline_retrieval_only"))
    add("")
    lines.extend(render_category_table(workflow_results, "workflow_gated"))
    add("")

    add("-" * 78)
    add("threshold calibration — gate min_score sweep")
    add("-" * 78)
    add("")
    lines.extend(render_calibration(calibration, min_score))
    add("")

    add("-" * 78)
    add("failure examples")
    add("-" * 78)
    add("")
    lines.extend(render_failures(baseline_results, "baseline_retrieval_only"))
    add("")
    lines.extend(render_failures(workflow_results, "workflow_gated"))
    add("")

    add("-" * 78)
    add("limitations — read before citing any number above")
    add("-" * 78)
    add("")
    for line in (
        "1. Synthetic corpus and synthetic queries. Both were written by the same",
        "   author, so they share vocabulary. Real queries would be harder, and",
        "   recall@k here is optimistic.",
        "2. Lexical retrieval only. BM25 cannot match a paraphrase that shares no",
        "   terms with the procedure. The paraphrased cases show this directly.",
        "3. The conflict rule counts live procedures per topic. It detects duplicate",
        "   coverage, not actual disagreement between procedures — that would need",
        "   contradiction detection over the text.",
        "4. LLM output quality is UNTESTED. The default generator is an extractive",
        "   mock. The Ollama adapter is implemented and its failure and timeout",
        "   paths are covered by tests, but no real generation was observed to",
        "   complete in the environment this was built in: a trivial prompt timed",
        "   out at 120s via curl and at 300s via the adapter, and the runtime",
        "   reported no model loaded in memory. Treat the adapter as unverified",
        "   end to end until a generation is actually seen to return.",
        "5. No human review of answers took place. The approval gate covers",
        "   consequential actions only, not the wording of replies.",
        "6. Thresholds (min_score, min_margin) were calibrated on this evaluation",
        "   set. That is fitting on the test set, and a real deployment would need",
        "   a held-out set to calibrate against.",
        "7. Latency is measured on one machine, in-process, with no concurrency.",
        "   It is not a throughput figure and does not describe any deployed system.",
        "   It is the one field the committed report does not pin: wall-clock",
        "   measurements are not reproducible, so the expected file marks the",
        "   latency line unpinned while every decision and score is byte-checked.",
        "8. No production deployment, no external audit, no real traffic, no",
        "   revenue. This is a work sample built in one sitting.",
    ):
        add(f"  {line}")
    add("")

    return "\n".join(lines)


# --- Entry point --------------------------------------------------------------


async def main_async(args: argparse.Namespace) -> int:
    corpus = load_corpus(CORPUS_PATH)
    cases = load_eval_set(EVALSET_PATH)

    if args.generator == "ollama":
        generator: AnswerGenerator = OllamaAnswerGenerator(model=args.model)
    else:
        generator = MockAnswerGenerator()

    baseline = RetrievalOnlyBaseline(
        corpus=corpus, generator=generator, top_k=args.top_k
    )
    workflow = SupportAssistant(corpus=corpus, generator=generator)
    index = Bm25Index(corpus)

    calibration = await sweep_thresholds(
        corpus=corpus,
        cases=cases,
        generator=generator,
        index=index,
        top_k=args.top_k,
    )

    if args.calibrate:
        print("=" * 78)
        print("threshold calibration — gate min_score sweep")
        print("=" * 78)
        print()
        for line in render_calibration(calibration, workflow.config.gate.min_score):
            print(line)
        print()
        return 0

    baseline_results = await run_strategy(baseline, cases, index, args.top_k)
    workflow_results = await run_strategy(workflow, cases, index, args.top_k)

    baseline_metrics = compute_metrics(baseline_results, baseline.name)
    workflow_metrics = compute_metrics(workflow_results, workflow.name)

    report = build_report(
        corpus_size=len(corpus.procedures),
        case_count=len(cases),
        generator_name=generator.name,
        top_k=args.top_k,
        min_score=workflow.config.gate.min_score,
        min_margin=workflow.config.gate.min_margin,
        baseline_results=baseline_results,
        workflow_results=workflow_results,
        baseline_metrics=baseline_metrics,
        workflow_metrics=workflow_metrics,
        calibration=calibration,
    )

    print(report)

    EXPECTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Normalise before comparing: the report string ends with a newline from its
    # final blank line, and the stored file is compared without one.
    canonical = canonicalise(report).rstrip("\n")
    if args.update_expected:
        EXPECTED_PATH.write_text(canonical + "\n", encoding="utf-8", newline="\n")
        print(f"\nwrote {EXPECTED_PATH.relative_to(ROOT)} (latency line not pinned)")
        return 0

    if not EXPECTED_PATH.exists():
        print(
            f"\nno expected report at {EXPECTED_PATH.relative_to(ROOT)}",
            file=sys.stderr,
        )
        return 1

    expected = EXPECTED_PATH.read_text(encoding="utf-8").rstrip("\n")
    if expected == canonical:
        print("\nreport matches expected/eval_report.txt (latency excluded)")
        return 0

    print("\nREPORT MISMATCH against expected/eval_report.txt", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generator",
        choices=("mock", "ollama"),
        default="mock",
        help="answer generator (default: mock, deterministic)",
    )
    parser.add_argument(
        "--model",
        default="qwen2.5-coder:latest",
        help="model name when --generator ollama",
    )
    parser.add_argument(
        "--top-k", type=int, default=5, help="retrieval depth (default: 5)"
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="sweep the gate score floor and print the trade-off",
    )
    parser.add_argument(
        "--update-expected",
        action="store_true",
        help="regenerate expected/eval_report.txt from this run",
    )
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
