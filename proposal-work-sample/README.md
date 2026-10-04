# Proposal and estimation work sample

A consulting proposal and a bottom-up estimate, written against a **fictional** client and
a **synthetic** use case. Built to demonstrate structuring a problem, comparing options
honestly, and deriving an estimate rather than guessing one.

> ## ⚠️ Not a real proposal
>
> - **The client is fictional.** Harbourline Ferries is a synthetic organisation invented for
>   the technical work sample in `../rag-work-sample/`. It is not a real company.
> - **No engagement exists** and none has existed.
> - **No figure has been measured, researched, negotiated, or quoted.** No day rate appears
>   anywhere. No saving has been realised.
> - **Not an offer.** Nothing here may be relied on commercially.

---

## How to read it

Two audiences, two documents. They overlap deliberately — the proposal states the position,
the estimate shows the derivation behind it.

| If you are… | Read | You will find |
|---|---|---|
| **A non-technical stakeholder** | [`PROPOSAL.md`](PROPOSAL.md) | The problem, four options with trade-offs, a recommendation, what is in and out of scope, acceptance criteria, risks, and an example change request. No code. |
| **A technical reviewer** | [`PROPOSAL.md`](PROPOSAL.md) §6, then [`ESTIMATE.md`](ESTIMATE.md) | The architecture and decision gate; the man-day derivation line by line; the assumption register with the basis for each; the ROI formula and its placeholder inputs. |
| **A commercial reviewer** | [`ESTIMATE.md`](ESTIMATE.md) §3, §5, §6 | The work breakdown, the contingency stated separately, and break-even expressed without quoting a rate. |

---

## What the documents contain

**`PROPOSAL.md`**

1. Executive summary — the recommendation, and the two findings that shape it
2. Discovery workshop agenda — a half-day, with an output per item
3. Problem statement and baseline — including where the baseline does not exist
4. **Four options** — do nothing, deterministic, retrieval with a gate, full RAG — compared on
   cost, benefit, risk, and failure mode
5. Recommendation — and what would have to be true to change it
6. Architecture and data flow, including the decision gate stated as four readable rules
7. Scope in, scope out, and **seven acceptance criteria** agreed before design
8. Delivery plan, five phases, thirteen weeks
9. Governance, security, and privacy
10. Commercial summary
11. Risks and dependencies
12. Exclusions
13. **Change control, with a worked example** — adding a second language, assessed on corpus,
    evaluation, estimate and timeline
14. What the document is not

**`ESTIMATE.md`**

1. Estimation method — bottom-up from deliverables, and why not by analogy
2. Role definitions, including which role cannot be substituted
3. Work breakdown by phase and by role — **84 man-days**, every line traced to a deliverable
4. **Assumption register** — thirteen assumptions, each with its basis (illustrative /
   derived / to be confirmed)
5. Contingency, stated separately so it can be removed by a reviewer who disagrees
6. **ROI model** — the formula, three scenarios, and break-even expressed as a maximum
   blended day rate rather than a quoted price
7. Change control by change class
8. What would change the estimate most
9. What the estimate is not

---

## The two findings the whole proposal turns on

1. **Corpus quality dominates model quality.** Two live procedures disagreeing on baggage
   allowance cannot be resolved by a better model. Only a person can resolve it, in the
   corpus, before any automation is worth building. This is why corpus remediation is the
   second phase and 20% of the estimate.

2. **Refusing is a feature.** The recommended design abstains or escalates rather than
   guessing. Against a metric that expects an answer, that scores as a failure. Against the
   safety metric, it is the point. The proposal states both, and the acceptance criteria
   make zero unsupported answers a **gate rather than a target**.

The evidence for both comes from the reference implementation in `../rag-work-sample/`,
where a retrieval-only baseline produced **16 unsupported answers out of 36** and the gated
workflow produced **zero** — at the cost of refusing questions it could not resolve.

---

## Facts, estimates, and placeholders

Kept strictly separate throughout, and the distinction is the point:

| Category | Examples | Status |
|---|---|---|
| **Facts** | The gate removed 16 of 16 unsupported answers; paraphrased retrieval scored 2 of 8; non-English retrieval scored 32.0% and 31.0% against 62.1% in English | Measured in the reference implementation, on synthetic data |
| **Estimates** | All man-days, all durations, all role shares | Reasoned construction — not a recollection of a delivered job |
| **Placeholders** | Every ROI input: volume, handling time, cost per hour | Chosen to make the arithmetic legible. Not researched. |

---

## What this is not

- Not a real proposal, quote, offer, or forecast.
- Not evidence of having delivered a consulting engagement. **The author has not delivered
  this engagement**, and the estimate is a construction rather than a recollection of a
  comparable job.
- Not market research. No rate card, benchmark, or comparator was consulted.
- Not a claim of cloud or production experience. The deployment question is handled in
  `../rag-work-sample/docs/CLOUD_MAPPING.md`, which is explicitly labelled **not performed**.

What it is: a demonstration that a problem can be structured, options compared without
stacking the deck, an estimate derived line by line, and the assumptions written down where
a reviewer can argue with them.
