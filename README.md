# Work samples


<!-- badges:start -->

[![last commit](https://img.shields.io/github/last-commit/HatemIsmailShalaby1979/work-samples)](https://github.com/HatemIsmailShalaby1979/work-samples/commits/main)
![status](https://img.shields.io/badge/ci-no CI-lightgrey?label=no CI%20(2026-10-04))

*Measured 2026-10-06 — head `8f88b7c` (2026-10-04); Python.*

<!-- No static test or coverage count is shown here: a frozen
     number decays silently. Run the suite for a current figure;
     the CI badge above is the live status. -->
<!-- badges:end -->

Three self-contained exercises, each built to demonstrate a specific capability and each
shipped with its own evidence. They are **work samples, not products.**

> [!IMPORTANT]
> **What these are, and what they are not.**
> Every exercise here uses **synthetic data**. None of them has a client, a deployment, real
> traffic, or revenue. None has been externally audited. Each one states its own limitations
> in its own README, including the results that reflect badly on it.
>
> The point of the collection is not that the code works. It is that **each sample publishes
> the evidence for its claims and the reasons for its failures** — so a reviewer can check
> rather than trust.

---

## Why these exist

I spent 28 years in contact-centre operations and started building software seriously in
2025. My portfolio repositories — [Helix Prime](https://github.com/HatemIsmailShalaby1979/Helix-Prime)
and its satellites — demonstrate systems. These three demonstrate something narrower and
easier to check: **whether the evaluation discipline holds up when the numbers are small
enough to inspect line by line.**

Each one follows the same shape:

1. **Synthetic data only.** No employer data, no customer records, nothing confidential.
2. **A committed expected-output file.** The harness rebuilds from scratch and diffs against it.
3. **A baseline to compare against.** A result without a baseline is an assertion.
4. **A limitations section that names the failures** — including the unflattering ones.

---

## The samples

### 1. [`sql-work-sample/`](sql-work-sample/) — SQL over a synthetic contact-centre dataset

A compact schema and eight documented queries on SQLite, covering two-table joins with
measured cardinality, aggregation with `HAVING`, multi-step CTEs, window functions including
a rolling frame, and an index whose effect on the query plan is **measured rather than
assumed**.

**Verified:** 8/8 checks. The index changes the plan from a full table `SCAN` to
`SEARCH tickets USING COVERING INDEX` — a covering-index search, so the table is never read.
No dependencies; rerunnable from a clean setup.

**Why the join cardinality is explained rather than asserted:** `tickets.agent_id` is
nullable on purpose — abandoned contacts have no agent — so the inner join is bounded at
1,079 of 1,122 rows, and the query proves it.

---

### 2. [`rag-work-sample/`](rag-work-sample/) — an evaluated retrieval assistant

A support-policy assistant over a synthetic 15-procedure corpus, with a labelled 36-case
evaluation set and a measured comparison between the simplest baseline and a gated workflow.
**No generative model sits in the answering path.**

**Verified:** 105 tests; the committed evaluation report is reproducible across runs.

| | Baseline (retrieval only) | Workflow (gated) |
|---|---|---|
| Decision accuracy | 0.3611 (13/36) | **0.7778 (28/36)** |
| **Unsupported answers** | **16** | **0** |
| Correct abstentions | 0/8 | 7/8 |
| Correct escalations | 0/8 | **8/8** |

**The honest finding, stated in the README:** the workflow scores **worse** than the baseline
on paraphrased questions — 2 of 8 against 3. That is not a regression. The baseline guesses
and sometimes lands right; the gate refuses when the evidence is weak, and a metric expecting
an answer scores a refusal as an error.

**Also included:** a container and CI layer — Docker and Compose with health checks,
structured JSON logs, correlation IDs, query-text redaction by default, request timeouts and
a rollback runbook. Six CI steps passing. **No cloud deployment was performed**; the mapping
in `docs/CLOUD_MAPPING.md` is labelled as a design exercise.

---

### 3. [`proposal-work-sample/`](proposal-work-sample/) — a consulting proposal and estimate

A client-facing proposal and a bottom-up estimate, written against the fictional operator
from the RAG sample. Four options compared — including **doing nothing** — an architecture,
scope and acceptance criteria, a full assumption register, and conservative/base/upside ROI
scenarios expressed as formulas.

**Verified:** the arithmetic, with a script.

**Stated plainly in the document:** the client is fictional; **no day rate is quoted**
anywhere, because quoting one would imply market research that was not performed. The
estimate is expressed in man-days — **84, plus 13 contingency** — and break-even is given as
*the maximum blended day rate for year-one payback* so the reader supplies their own rate.

**One criterion is a gate, not a target:** zero unsupported answers on a held-out set, or the
phase fails regardless of how the other six criteria score.

---

## What is deliberately not here

- **No résumé material.** Career documents are not part of this repository.
- **No client work.** There is none to publish.
- **No employer data.** Everything is synthetic, and each sample says so in its first paragraph.
- **No claim of production experience.** None of this has been deployed.

---

## Running them

Each sample is self-contained and each has its own README with exact commands.

```bash
# SQL — no dependencies beyond the Python standard library
cd sql-work-sample && python run_checks.py

# RAG — one dependency (Pydantic), no network
cd rag-work-sample && python run_eval.py && python -m pytest

# Proposal — a document, no code
cd proposal-work-sample
```

The RAG sample also runs in Docker: `docker compose up --build` starts the service on
`127.0.0.1:8080` with `/health` and `/ready` endpoints.

---

## Author

**Hatem Ismail Shalaby** — Contact Centre Operations & AI Implementation Lead | WFM & CX Transformation

- GitHub: [HatemIsmailShalaby1979](https://github.com/HatemIsmailShalaby1979)
- LinkedIn: [hatem-shalaby-202902127](https://www.linkedin.com/in/hatem-shalaby-202902127/)
- Email: <hatemshalaby2025@gmail.com>

Based in Al Obour City, Al-Qalyubia Governorate, Egypt.

## Licence

MIT
