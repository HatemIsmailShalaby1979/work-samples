# Estimate — man-days, assumptions, and ROI model

> ## ⚠️ ILLUSTRATIVE ONLY — WORK SAMPLE
>
> **No figure in this document has been measured, researched, negotiated, or observed.**
>
> - **No day rate is quoted anywhere.** The estimate is expressed in **man-days** precisely
>   so it can be priced against whatever rate card applies. Quoting a rate would imply
>   market research that was not performed.
> - **The ROI model is a method with placeholder inputs, not a forecast.** No saving has
>   been realised or promised. Substituting your own inputs is the intended use.
> - **No client exists.** Harbourline Ferries is fictional.
>
> Companion to `PROPOSAL.md`. This document exists so that a technical or commercial
> reviewer can challenge the estimate **line by line** rather than accepting or rejecting
> a single total.

---

## 1. Estimation method

**Bottom-up from deliverables, not by analogy.**

Every man-day below traces to a named deliverable in `PROPOSAL.md` §8. The alternative —
estimating by analogy to "a similar project" — is faster and produces a number that cannot
be argued with, because there is nothing to inspect. Since the purpose of this document is
to be inspectable, the slower method is used.

**Three things the estimate deliberately does not do:**

1. **It does not hide the corpus work.** Corpus remediation is 17 of 84 man-days — 20% of
   the engagement and the largest single non-engineering line. Projects of this shape
   routinely under-estimate it or omit it, and then discover it mid-build.
2. **It does not quote a rate.** See the disclaimer.
3. **It does not include contingency in the line items.** Contingency is stated separately
   in §5 so it can be removed by a reader who disagrees with it.

---

## 2. Role definitions

| Role | What they do | Why the engagement needs them |
|---|---|---|
| **Engagement lead** | Owns the plan, the client relationship, the estimate, and the change control. Runs the workshop, writes the reports, presents the pilot result. | Single point of accountability. Without it, the corpus and engineering workstreams drift apart. |
| **Domain SME (contact centre operations)** | Rules on the contested procedure, defines what "correct" means, reviews the labelled evaluation set, judges whether an answer is right. | **This is the role that cannot be substituted.** A retrieval engineer cannot decide which of two conflicting refund policies is correct. |
| **Retrieval / ML engineer** | Builds the index and the ranking, calibrates the gate threshold. | The core technical work. |
| **Backend engineer** | The service, the endpoints, the operational plumbing — logging, health checks, timeouts. | Turns a model into something operable. |
| **Evaluation engineer** | Builds and maintains the labelled set, runs the harness, produces the failure analysis, keeps the metrics honest. | The role most often omitted. Without it, "it seems to work" is the only available evidence. |
| **Compliance contact (operator-side)** | Signs off the data-handling position, the retention rule, and who may read an escalation. | Operator-side role, not billed. Their availability is a dependency, not a cost. |

---

## 3. Work breakdown

### Phase 0 — Discovery · 8 man-days · 1 week

| Role | Man-days | Deliverable |
|---|---:|---|
| Engagement lead | 4 | Workshop run; discovery report |
| Domain SME | 2 | Current-state walkthrough; contested-procedure case study |
| Data engineer | 1 | Baseline data availability assessment |
| Compliance contact | 1 | Draft data-handling position |
| **Total** | **8** | |

### Phase 1 — Corpus remediation · 17 man-days · 3 weeks

| Role | Man-days | Deliverable |
|---|---:|---|
| Domain SME | 9 | Contradiction resolved; superseded procedures marked; ownership assigned |
| Engagement lead | 3 | Corpus governance process; escalation path for future conflicts |
| Data engineer | 3 | Procedure inventory; currency report; versioned corpus export |
| Compliance contact | 2 | Sign-off on retention and access |
| **Total** | **17** | |

### Phase 2 — Build and calibrate · 38 man-days · 6 weeks

| Role | Man-days | Deliverable |
|---|---:|---|
| Retrieval / ML engineer | 14 | Index, ranking, threshold calibration |
| Backend engineer | 9 | Service, endpoints, logging, health checks, timeouts |
| Evaluation engineer | 8 | Labelled set, harness, failure analysis, metrics report |
| Engagement lead | 4 | Design review; acceptance evidence pack |
| Domain SME | 3 | Evaluation-set review; correctness judgements |
| **Total** | **38** | |

### Phase 3 — Shadow-mode pilot · 14 man-days · 3 weeks

| Role | Man-days | Deliverable |
|---|---:|---|
| Evaluation engineer | 6 | Pilot measurement: escalation rate, unsafe answers, latency, per language |
| Engagement lead | 3 | Pilot report; go/no-go recommendation |
| Backend engineer | 3 | Pilot instrumentation and support |
| Domain SME | 2 | Review of escalated cases |
| **Total** | **14** | |

### Phase 4 — Handover · 7 man-days · 2 weeks

| Role | Man-days | Deliverable |
|---|---:|---|
| Engagement lead | 3 | Runbook, monitoring definitions, owner briefing |
| Backend engineer | 2 | Operational handover; rollback rehearsal |
| Domain SME | 2 | Corpus maintenance training |
| **Total** | **7** | |

### Totals

| Phase | Man-days |
|---|---:|
| 0 — Discovery | 8 |
| 1 — Corpus remediation | 17 |
| 2 — Build and calibrate | 38 |
| 3 — Shadow-mode pilot | 14 |
| 4 — Handover | 7 |
| **Subtotal** | **84** |
| Contingency @ 15% (§5) | 13 |
| **Total** | **97** |

**By role:**

| Role | Man-days | Share |
|---|---:|---:|
| Domain SME | 18 | 21% |
| Engagement lead | 17 | 20% |
| Retrieval / ML engineer | 14 | 17% |
| Backend engineer | 14 | 17% |
| Evaluation engineer | 14 | 17% |
| Data engineer | 4 | 5% |
| Compliance contact | 3 | 4% |
| **Total** | **84** | |

**The engineering lines are 42 of 84 man-days — exactly half.** The other half is domain
judgement, evaluation, and coordination. An estimate that is 90% engineering is an estimate
that has not accounted for the corpus.

---

## 4. Assumption register

Every assumption, its value, and **its basis**. The basis column is the important one: it
distinguishes a placeholder from a fact.

| # | Assumption | Value | Basis |
|---|---|---|---|
| A1 | Corpus size | ~15–100 procedures | **Illustrative.** The reference corpus has 15. Real operator corpora are larger; this is the single largest driver of Phase 1. |
| A2 | Known contradictions in the corpus | At least 1 | **Derived** from the reference corpus, which was constructed with one. Real corpora have more. |
| A3 | Proportion of procedures with a named owner | Unknown | **To be confirmed with the operator.** Assumed low; Phase 1 exists to fix it. |
| A4 | Baseline metrics available at kick-off | Partially | **To be confirmed.** At least one is assumed missing, hence the baseline task in Phase 0. |
| A5 | Languages in scope | 1 | **Assumed** for the estimate. Each additional language scales Phase 1 and Phase 2 superlinearly. |
| A6 | Retrieval approach | Lexical (BM25) first | **Assumed.** Vector retrieval would add 4–6 man-days and a model dependency, and would improve paraphrase handling. |
| A7 | Generative model in the answering path | No | **Assumed**, per `PROPOSAL.md` §5. Adding one adds 10–15 man-days plus ongoing cost. |
| A8 | Operator provides a redacted query sample | Yes | **To be confirmed.** Without it, calibration uses synthetic queries and the thresholds are unreliable. |
| A9 | Operator provides a product owner with authority to rule | Yes | **To be confirmed.** Without it, the contradiction cannot be resolved and Phase 1 cannot exit. |
| A10 | Deployment into the operator's production environment | Not in this estimate | **Excluded** per `PROPOSAL.md` §12. |
| A11 | Cloud infrastructure | Not provisioned | **Excluded.** See `../rag-work-sample/docs/CLOUD_MAPPING.md`, which is explicitly a design exercise that was not performed. |
| A12 | Team availability | Full-time, dedicated | **Assumed.** Part-time allocation extends elapsed time roughly proportionally. |
| A13 | Elapsed duration | ~13 weeks | **Derived** from the phase plan with Phases 1 and 2 overlapping by 2 weeks. |

**Facts versus estimates, separated:**

- **Facts** (measured in the reference implementation, on synthetic data): the gate removed
  16 of 16 unsupported answers; paraphrased retrieval scored 2 of 8; non-English retrieval
  scored 32.0% and 31.0% against 62.1% in English.
- **Estimates** (everything in §3): all man-days, all durations, all shares.
- **Placeholders** (everything in §6): all ROI inputs.

None of the three categories is interchangeable with another.

---

## 5. Contingency

| | Man-days |
|---|---:|
| Base estimate | 84 |
| Contingency @ 15% | 13 |
| **Total** | **97** |

**Why 15% and not a rounder number:** it is the author's stated convention, and it is stated
so it can be argued with. A reviewer who believes the corpus is clean may remove it. A
reviewer who has seen a corpus remediation before will likely raise it.

**Contingency is not a buffer for scope.** It covers estimate error, not new requirements.
New requirements go through §7.

---

## 6. ROI model

> **This is a method, not a forecast.** Every input below is a placeholder chosen to make
> the arithmetic legible. Nothing has been measured. The model's purpose is to let a reader
> substitute their own numbers and see which input dominates.

### 6.1 The formula

```
Annual lookup contacts       L  = V × s
Current hours on lookups     H  = L × (AHT / 3600)
Hours released               ΔH = H × r
Annual value of released time A = ΔH × c

where
  V   = annual contact volume                    [placeholder]
  s   = share of contacts that are procedure lookups   [placeholder]
  AHT = average handling time on those contacts, seconds [placeholder]
  r   = reduction in handling time                [placeholder]
  c   = fully-loaded cost per agent hour          [placeholder]
```

### 6.2 Placeholder inputs

| Input | Placeholder | Basis |
|---|---:|---|
| V — annual contact volume | 250,000 | **Illustrative.** Not researched. |
| AHT — handling time on lookup contacts | 300 s (5 min) | **Illustrative.** Not measured. |
| c — fully-loaded cost per agent hour | 25 | **Illustrative placeholder, not a market rate.** Substitute the operator's own figure. |

### 6.3 Scenarios

`s` and `r` are varied; `V`, `AHT` and `c` are held at their placeholders.

| Scenario | s | r | L | H (hours) | ΔH (hours) | Annual value |
|---|---:|---:|---:|---:|---:|---:|
| Conservative | 0.20 | 0.10 | 50,000 | 4,167 | 417 | **10,417** |
| Base | 0.30 | 0.20 | 75,000 | 6,250 | 1,250 | **31,250** |
| Upside | 0.40 | 0.30 | 100,000 | 8,333 | 2,500 | **62,500** |

### 6.4 Break-even, expressed without quoting a rate

Because no day rate is quoted, break-even is expressed as **the maximum blended day rate at
which the engagement pays back within one year**:

```
Maximum blended day rate = Annual value / Total man-days
```

| Scenario | Annual value | Total man-days | Maximum blended day rate for year-one payback |
|---|---:|---:|---:|
| Conservative | 10,417 | 97 | **107** |
| Base | 31,250 | 97 | **322** |
| Upside | 62,500 | 97 | **644** |

**How to read this:** if the applicable blended day rate is below the figure in the last
column, the engagement pays back in the first year under that scenario. If it is above, it
does not. No rate is asserted; the reader supplies one.

### 6.5 What the model does not include — and this matters more than the model

| Omission | Why it matters |
|---|---|
| **Ongoing run cost** | Hosting, monitoring, and corpus maintenance are not modelled. A corpus does not maintain itself; if nobody owns it, the assistant degrades as the procedures drift. |
| **The value of reduced errors** | A compliance breach avoided is real value and is not in the model. It is also not quantifiable here, and inventing a figure would be worse than omitting it. |
| **The cost of over-escalation** | The gate refuses questions it cannot resolve. Every refusal is supervisor time. This is a **cost** of the recommended design and it is not subtracted above. |
| **Released time is not removed cost** | ΔH is *time released*, not headcount removed. It becomes value only if the time is redeployed or if it avoids hiring. If neither happens, the financial benefit is zero and the operational benefit is the only benefit. |
| **Any realised saving** | None exists. Nothing has been deployed. |

### 6.6 Sensitivity

The model is linear in `V`, `s`, `r` and `c`. A 10% change in any one moves the annual value
by 10%. Two consequences:

1. **The estimate of `s` matters most**, because it is the input most likely to be wrong by a
   wide margin and the least likely to be measured. It is worth a two-week measurement task
   before committing to any benefit case.
2. **Precision here is false precision.** Reporting a value to four significant figures from
   three unmeasured inputs would imply a confidence the model does not have. The scenario
   spread — 10,417 to 62,500 — is the honest output, and it is wide.

---

## 7. Change control

Assessed on four axes — **corpus, evaluation, estimate, timeline** — before acceptance or
rejection. Worked example in `PROPOSAL.md` §13.

| Change class | Typical effect | Axis that catches it |
|---|---|---|
| Additional language | Phase 1 and 2 grow superlinearly | Corpus — a translation is a new controlled document, not a copy |
| Generative answers added | +10–15 man-days, plus ongoing model cost | Evaluation — generated output needs its own evaluation design |
| Vector retrieval instead of lexical | +4–6 man-days, plus a model dependency | Estimate — and it improves the paraphrase result, so it may be worth it |
| Integration with the contact platform | Unbounded until scoped | Timeline — this is the classic unbounded change |
| Corpus grows by 10× | Phase 1 scales with the number of procedures, not linearly | Corpus |

---

## 8. What would change this estimate most

Ranked by expected impact:

1. **Corpus size and cleanliness.** A 100-procedure corpus with several contradictions could
   double Phase 1. This is the largest single risk to the estimate (R1 in `PROPOSAL.md` §11).
2. **Whether a baseline exists.** If it does not, Phase 0 grows and the benefit case cannot
   be evidenced later.
3. **Whether the operator can rule on the contested procedure.** If not, Phase 1 cannot exit
   and Phase 3 cannot start.
4. **Languages in scope.** Each additional language scales the corpus and evaluation work.
5. **Whether a generative model is required.** The largest optional line item.

---

## 9. What this estimate is not

- **Not a quote.** No rate, no currency, no commercial terms.
- **Not researched.** No market data, benchmark, or comparator was consulted.
- **Not validated against delivery.** The author has not delivered this engagement, so the
  estimate is a reasoned construction, not a recollection of a comparable job.
- **Not a commitment.** It is a work sample demonstrating an estimation method.

What it *is*: a bottom-up model where every line traces to a deliverable, every assumption
carries its basis, and the ROI is expressed as a formula rather than a claim.
