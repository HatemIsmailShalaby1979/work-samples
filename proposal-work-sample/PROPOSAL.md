# Proposal — Harbourline Ferries: contact-centre knowledge assistant

> ## ⚠️ WORK SAMPLE — NOT A REAL PROPOSAL
>
> **This document is a portfolio work sample.** It is not a proposal to any client, it has
> not been sent to anyone, and no engagement described in it exists or has ever existed.
>
> - **The client is fictional.** "Harbourline Ferries" is a synthetic organisation invented
>   for the work sample in `../rag-work-sample/`. It is not a real company.
> - **No commercial figure has been measured, negotiated, quoted, or observed.** Every
>   number is an illustrative placeholder used to demonstrate an estimation *method*. Day
>   rates are placeholders, not market prices. No market research was performed.
> - **No outcome has been delivered.** No savings have been realised, no system has been
>   deployed to a client, and nothing here describes a result that occurred.
> - **This is not an offer.** Nothing in this document may be relied on commercially.
>
> It exists to demonstrate the ability to structure a problem, compare options honestly,
> estimate an engagement bottom-up, and write down the assumptions rather than hide them.
> Those are the skills on display. The numbers are not the point; the method is.

| | |
|---|---|
| **Document** | Proposal and estimate, revision 1 |
| **Prepared** | 2026-10-04 |
| **Status** | Work sample — illustrative only |
| **Basis** | The synthetic Harbourline Ferries procedure corpus and the evaluated assistant in `../rag-work-sample/` |
| **Companion** | `ESTIMATE.md` — the man-day model, assumption register, and ROI formulas |

---

## 1. Executive summary

Harbourline Ferries' contact-centre agents answer a high volume of questions that are
already answered in the operator's own published procedures. The problem is not that the
answers are unknown. It is that they are **hard to find quickly, and hard to trust when
found** — procedures are fragmented, several are out of date, and at least one topic is
covered by two documents that disagree.

This proposal sets out four options, recommends one, and gives an honest estimate.

**The recommendation is not "build an AI assistant".** It is: **fix the corpus first, then
add retrieval, and only then consider a model.** The evaluation in
`../rag-work-sample/` shows why. Retrieval without a decision gate produced unsupported
answers on 16 of 36 test cases. A deterministic gate removed all 16. A generative model was
deliberately excluded from the answering path entirely, because a wrong procedure in a
support reply is a compliance breach, not a drafting inconvenience.

**Two findings shape the whole engagement:**

1. **Corpus quality dominates model quality.** Two live procedures disagreeing on baggage
   allowance cannot be resolved by a better model. It has to be resolved by a person, in the
   corpus, before any automation is worth building.
2. **Refusing is a feature.** The assistant abstains or escalates rather than guessing. That
   is the design, and it should be measured as a success, not as a failure to answer.

**The estimate is 84 man-days** across four phases and roughly thirteen weeks, with a
stated contingency. Every figure is illustrative and the derivation is shown in
`ESTIMATE.md` so it can be challenged line by line.

---

## 2. Discovery workshop agenda

A half-day session, run before any estimate is committed. Its purpose is to replace
assumptions with facts.

| Time | Item | Output |
|---|---|---|
| 09:00 | Introductions, scope of the session, what is out of scope | Shared expectations |
| 09:15 | **Walk the floor.** Two or three real (redacted) queries, traced end to end: where does the agent look, what do they open, how long does it take? | A current-state picture, not a described one |
| 10:00 | **The corpus as it stands.** Who owns each procedure? When was it last reviewed? Which are known to be stale? | A named owner per procedure, or a named gap |
| 10:45 | Break | |
| 11:00 | **The hard case.** Walk the known conflicting topic. How does an agent decide today? | An explicit ruling, or an escalation path |
| 11:30 | **What "good" means.** Agree the acceptance criteria in §7 before agreeing a design | Drafted acceptance criteria |
| 12:00 | **Risk and compliance.** Data classification, retention, who may read an escalation, what must never be logged | A data-handling position |
| 12:30 | **Success measures and the baseline.** What is measured today, and where does the number come from? | A baseline, or an explicit "we do not measure this" |
| 13:00 | Close, actions, owners, dates | Action log |

**A note on the workshop.** The most valuable item is the last one. If the operator cannot
produce a current baseline, then no benefit can be evidenced later, and the engagement
should begin by creating one. That is a finding, not a blocker.

---

## 3. Problem statement and baseline

### 3.1 The problem, stated precisely

Agents resolving a customer contact must locate the governing procedure, confirm it is
current, and apply it. Three failure modes follow from how the procedures are maintained:

| Failure mode | Consequence |
|---|---|
| **Fragmentation** — the answer is spread across documents, none of which is the single source | Time lost per contact; inconsistent answers between agents |
| **Staleness** — superseded procedures remain reachable and are not visibly marked | An agent applies a withdrawn policy in good faith |
| **Contradiction** — two live procedures cover the same topic and disagree | The agent has no rule for choosing, so the answer becomes a judgement call |

The third is the most serious, because it cannot be solved by better search. Search finds
the contradiction; only a person can resolve it.

### 3.2 The baseline

A baseline must be measured, not asserted. Where the operator does not hold the data, the
engagement's first task is to create it.

| Measure | Definition | Status at kick-off |
|---|---|---|
| Contact volume by queue and interval | Contacts offered per 30-minute interval | To be confirmed from the contact platform |
| Average handle time on procedure-lookup contacts | Seconds, for the identifiable subset | To be confirmed — usually needs a reason-code review first |
| Escalation rate | Contacts escalated to a supervisor | To be confirmed |
| Rework rate | Contacts reopened or re-contacted within 7 days | To be confirmed |
| Procedure currency | Share of live procedures reviewed within the last 12 months | **Usually unknown.** Establishing it is task 1 of Phase 1. |

**Stated plainly:** in most engagements of this shape, at least one of these is not
available at kick-off. The plan in §8 assumes a two-week baseline-establishment task rather
than assuming the numbers exist.

---

## 4. Options considered

Four options. The first is the one that is always available and is usually under-analysed.

### Option A — Do nothing

**What it is:** continue as today; rely on agent experience and the existing document store.

| | |
|---|---|
| **Cost** | Zero incremental |
| **Benefit** | None |
| **Risk** | The contradiction and staleness problems persist and compound as the corpus grows |
| **When it is correct** | When contact volume is low, the corpus is small and well-maintained, and no compliance exposure exists |

**Assessment:** defensible only if §3.2 shows the volume is low. It is listed first because
a proposal that cannot argue for doing nothing cannot argue for doing anything.

### Option B — Deterministic lookup, no AI

**What it is:** a maintained index — a keyword or decision-tree front end over the
procedures, with no ranking model and no generation. Agents search, the tool returns exact
matches, an out-of-date procedure is visibly marked.

| | |
|---|---|
| **Cost** | Lowest of the build options |
| **Benefit** | Solves currency and discoverability. Does not solve contradiction. |
| **Risk** | Low. Nothing is inferred; the agent reads the procedure. |
| **Weakness** | Brittle on paraphrase. A query that does not use the procedure's own words does not match. |

**Assessment:** this is the honest baseline for any AI option, and it should be built
regardless — the corpus work it requires is a prerequisite for everything else. It is also
the correct final answer if the evaluation shows the retrieval problem is small.

### Option C — Retrieval with a deterministic decision gate (recommended)

**What it is:** lexical or vector retrieval over the procedures, followed by a
**deterministic, rule-based gate** that decides whether to answer, abstain, or escalate. No
generative model in the answering path. Every answer cites the procedure it came from.

The gate escalates when the match is weak, when the topic is covered by more than one live
procedure, when the best match is a draft, or when it is a withdrawn procedure with no
successor.

| | |
|---|---|
| **Cost** | Moderate — the largest single line in the estimate is corpus remediation, not code |
| **Benefit** | Measurable: the reference implementation removed **16 of 16** unsupported answers relative to a retrieval-only baseline, at the cost of refusing questions it cannot resolve |
| **Risk** | Over-escalation. The gate refuses legitimate questions whose evidence is weak. This is the deliberate trade-off and it must be calibrated per tenant. |
| **Weakness** | Lexical retrieval cannot handle paraphrase — measured at **2 of 8** paraphrased cases. Vector retrieval improves this and adds a model dependency. |

**Assessment:** the best risk-adjusted option. It is explainable to a regulator, it fails
closed, and its failures are visible rather than silent.

### Option D — Retrieval plus generative model (full RAG)

**What it is:** Option C with an LLM composing the answer from retrieved procedures.

| | |
|---|---|
| **Cost** | Highest — adds model hosting or API spend, evaluation of generated output, and prompt-injection surface |
| **Benefit** | Better handling of paraphrase and multi-part questions; more natural replies |
| **Risk** | **A generated answer that is fluent and wrong is harder to detect than an obvious non-answer.** The reference implementation's authors deliberately excluded generation from the answering path for this reason. |
| **When it is correct** | When replies are long-form and composed, when the corpus is clean and well-tested, and when a human review step exists between generation and the customer |

**Assessment:** not recommended as a first phase. Recommended as a **phase 2 candidate**,
gated on the evaluation evidence from Option C. If the operator wants it, the correct
sequence is C first, then D with measured comparison — which is exactly what the reference
implementation's harness is built to do.

### Option comparison

| | A: Do nothing | B: Deterministic | C: Retrieval + gate | D: Retrieval + LLM |
|---|---|---|---|---|
| Solves fragmentation | No | Yes | Yes | Yes |
| Solves staleness | No | Yes | Yes | Yes |
| Solves contradiction | No | No | **Yes** (escalates) | Yes (escalates) |
| Handles paraphrase | n/a | No | Partly | Yes |
| Explainable to a regulator | n/a | Yes | **Yes** | Harder |
| Failure mode | Silent | Silent miss | **Loud refusal** | Silent error |
| Relative effort | — | Low | Moderate | High |

---

## 5. Recommendation

**Build Option B, then Option C. Hold Option D.**

1. **Remediate the corpus first.** Resolve the contradiction, mark the superseded
   procedures, name an owner for each. This is the largest and least glamorous part of the
   work, and it is the part that determines whether anything downstream is trustworthy.
2. **Ship the deterministic gate.** Measured, explainable, fails closed.
3. **Run a shadow-mode pilot** — the assistant runs alongside agents and its answers are
   **not shown to customers**. Measure escalation rate, unsafe answers, and latency.
4. **Decide on Option D with evidence**, not enthusiasm. The decision criterion is stated in
   advance: proceed only if the pilot shows a paraphrased-query failure rate that materially
   harms service, and if a human review step can be funded.

**The recommendation is deliberately conservative.** The reference implementation
demonstrates that a deterministic gate is sufficient to eliminate unsupported answers on
synthetic data. Adding a generative model before the corpus is clean would be adding
capability to a problem that is not a capability problem.

---

## 6. Solution architecture and data flow

### 6.1 Components

```
   agent query
        │
        ▼
  ┌───────────────┐
  │  validation   │  length, shape, reject malformed input
  └───────┬───────┘
          ▼
  ┌───────────────┐
  │   retrieval   │  ranked procedures from the tenant corpus
  └───────┬───────┘
          ▼
  ┌───────────────┐
  │  DECISION GATE │  deterministic, rule-based, fails closed
  └───┬───────┬───┘
      │       │
      │       ├──▶ ABSTAIN   no evidence above the floor
      │       └──▶ ESCALATE  draft / retired / conflicting / ambiguous
      │
      ▼
   ANSWER  + citation to the governing procedure
      │
      ▼
  consequential action? ──yes──▶ HUMAN APPROVAL GATE (fails closed)
      │
      ▼
  audit record (append-only)
```

### 6.2 The decision gate, stated plainly

The gate is the product. It answers four questions in order:

1. Is there evidence at all? — if not, **abstain**.
2. Is the best match usable? — a draft or a withdrawn procedure is not.
3. Is the topic contested? — more than one live procedure on a topic means **escalate**.
4. Is the match decisive? — a close second match on a different topic means **escalate**.

Every branch is a readable rule. Nothing is inferred, and nothing is decided by a model.

### 6.3 Data flow and data handling

| Stage | Data | Handling |
|---|---|---|
| Corpus ingestion | Published procedures | Versioned; only `active` procedures are answerable |
| Query | Customer question | **Not logged by default** — a digest and length are logged instead |
| Retrieval | Query + corpus | In-process; no external call |
| Answer | Procedure text + citation | Extractive; nothing is composed |
| Escalation | Decision + reason | **Carries no procedure text** — the escalation record names the decision, not the content |
| Consequential action | Proposed action | Recorded as **pending**; nothing executes without a named human approval |

### 6.4 Why this architecture, and not a simpler one

The architecture is larger than "search the documents" for one reason: **the failure modes
are asymmetric.** A missed answer costs a customer some time. A confident wrong answer about
a refund policy costs money and, in a regulated setting, a compliance finding. The gate
exists to make the second failure impossible at the cost of the first.

---

## 7. Scope and acceptance criteria

### 7.1 In scope

- Procedure inventory, ownership assignment, and remediation of the known contradiction
- Marking and retiring superseded procedures
- A retrieval index over the tenant corpus
- The deterministic decision gate, calibrated on the tenant's own queries and procedures
- A labelled evaluation set covering answerable, paraphrased, conflicting, outdated and
  out-of-scope queries
- A shadow-mode pilot with measurement
- Runbook, monitoring definitions, and handover to a named owner

### 7.2 Out of scope

- Any change to the contact platform, CRM, or telephony
- Generative answers to customers (Option D — see §5)
- Multi-language support beyond the languages already present in the corpus
- Content authoring: **the operator owns and writes its own procedures.** This engagement
  does not author policy.
- Any deployment into the operator's production environment without the approval gate in §9

### 7.3 Acceptance criteria

Stated before design, agreed in the discovery workshop, and measured against a held-out set
**not** used for calibration.

| # | Criterion | Threshold | How measured |
|---|---|---|---|
| AC1 | Unsupported answers on the held-out set | **Zero** | Counted; any non-zero value fails the phase |
| AC2 | Correct escalations on conflicting and outdated cases | ≥ 90% | Labelled cases |
| AC3 | Correct abstentions on out-of-scope cases | ≥ 85% | Labelled cases |
| AC4 | Citation accuracy — the cited procedure is the governing one | ≥ 95% of answered cases | Manual review of a sample |
| AC5 | Retrieval recall@5 on answerable cases | ≥ 85% | Labelled cases |
| AC6 | Latency, p95, retrieval and gate only | ≤ 250 ms | In-process measurement |
| AC7 | Every answered response carries a citation | 100% | Structural check |

**AC1 is a gate, not a target.** A single unsupported answer on the held-out set fails the
phase, regardless of how the other criteria score. This is the one criterion where a
trade-off is not available.

---

## 8. Delivery plan and timeline

| Phase | Weeks | Objective | Exit condition |
|---|---|---|---|
| **0 — Discovery** | 1 | Replace assumptions with facts | Workshop held; acceptance criteria agreed; baseline status known |
| **1 — Corpus remediation** | 2–4 | A corpus that can be trusted | Contradiction resolved; superseded procedures marked; every procedure has a named owner |
| **2 — Build and calibrate** | 4–9 | A measured assistant | Acceptance criteria met on a held-out set |
| **3 — Shadow-mode pilot** | 10–12 | Evidence under real conditions | Pilot report with escalation rate, unsafe-answer count, and latency, per language |
| **4 — Handover** | 12–13 | The operator can run it | Runbook accepted; a named owner has operated it for two weeks |

Phases 1 and 2 overlap deliberately: retrieval work can begin against the procedures that
are already clean while the contested ones are being resolved.

**A dependency worth stating early:** Phase 3 cannot start until Phase 1 exits. A pilot over
a contradictory corpus measures the corpus, not the assistant.

---

## 9. Governance, security, and privacy

| Area | Position |
|---|---|
| **Data classification** | Procedures are internal. Query text may contain customer personal data and is treated as such. |
| **Logging** | Query text is **excluded by default**. A digest and a character count are logged for correlation. Enabling text logging requires an explicit, documented decision. |
| **Redaction** | Pattern-based redaction of email, telephone, and card-like values. **Best effort, not a control.** It must not be relied on as a data-protection measure. |
| **Retention** | Query text, if retained at all, needs a stated retention period and a stated owner. The reference implementation retains none. |
| **Human oversight** | Every consequential action — refund, compensation, fee waiver — is **proposed, never executed**. Execution requires a named human approval, and an approval for one action does not authorise another. |
| **Transparency** | Every answer cites its source procedure. Abstention and escalation are stated as outcomes, not disguised as answers. |
| **Model limitations** | Where a generative model is used, its limitations are disclosed to the operator and, where relevant, to the customer. |
| **Escalation records** | An escalation carries the decision and the reason, **not** the procedure text — so a routing record does not become a content leak. |
| **Regulatory posture** | This design fails closed. It is intended to be explainable to an auditor: every decision traces to a readable rule. |

---

## 10. Commercial model

The full derivation is in `ESTIMATE.md`. In summary:

- **84 man-days** across five roles, built bottom-up from deliverables rather than by analogy
- **Roughly 13 weeks** elapsed, with two phases overlapping
- **A 15% contingency**, stated separately rather than buried in the line items
- **No day rate is quoted.** The estimate is expressed in man-days precisely so that it can
  be priced against whatever rate card applies. Quoting a rate here would imply market
  research that was not performed.

**All figures are illustrative.** See the disclaimer at the top of this document.

---

## 11. Risks and dependencies

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **The corpus is worse than expected** — more contradictions, no owners, no review dates | High | High | Phase 1 exists for this. It is the first phase because it is the most likely to surprise. |
| R2 | **No usable baseline exists** | Medium | High | Establish one in Phase 0. Without it, no benefit can be evidenced. |
| R3 | **Over-escalation burdens supervisors** | Medium | Medium | Calibrate the threshold on the tenant's own data; measure the escalation rate during the pilot; treat it as a tunable, not a constant. |
| R4 | **Paraphrased queries fail retrieval** | High | Medium | Measured, not assumed. Mitigate with vector retrieval, or accept and design the escalation path for it. |
| R5 | **Shadow-mode pilot never converts to live** | Medium | Medium | Define the go/no-go criteria before the pilot starts. |
| R6 | **Scope creep into content authoring** | High | Medium | Content authoring is explicitly out of scope (§7.2). See the change control example in §13. |
| R7 | **Key-person dependency on the corpus owner** | Medium | High | Require a named owner **and** a deputy in Phase 1. |

**Dependencies on the operator:**

- A product owner with authority to rule on the contested procedure
- A compliance contact who can sign off the data-handling position
- Access to a redacted sample of real queries
- A named owner for the corpus, and a deputy

---

## 12. Exclusions

Explicitly not included, and each one is a common source of overrun:

1. Authoring or rewriting procedures. The operator owns its policy.
2. Integrating with the contact platform, CRM, or telephony beyond a defined interface.
3. Procuring or provisioning cloud infrastructure. See the cloud mapping in
   `../rag-work-sample/docs/CLOUD_MAPPING.md` for what a deployment would additionally
   require — **documented as a design exercise and explicitly not performed.**
4. Generative customer-facing answers.
5. Languages not already present in the corpus.
6. Ongoing operation after handover, unless separately contracted.
7. Legal or regulatory sign-off. The engagement produces evidence for it; it does not
   provide it.

---

## 13. Change control

A worked example, so the mechanism is concrete rather than described.

### Change request CR-001 — add a second language

**Requested by:** operator, during Phase 3
**Description:** extend the assistant to answer in a second language, in addition to the
language already present in the corpus.

| | |
|---|---|
| **Why it is a change** | The scope in §7.1 covers the corpus as it stands. §12 excludes languages not already present. |
| **Impact on corpus** | Every procedure needs a reviewed translation, with the same ownership and currency discipline. This is **not** a machine-translation task — a translated procedure is a new controlled document. |
| **Impact on evaluation** | The labelled evaluation set must be extended per language. The reference implementation measured a **materially worse result in non-English cases** (English 62.1% against Spanish 32.0% and Portuguese 31.0% on the same corpus), so the acceptance criteria in §7.3 cannot be assumed to carry across. |
| **Impact on estimate** | Corpus remediation and evaluation scale with the number of languages. The estimate grows superlinearly, not linearly, because translation introduces a new class of contradiction — between the original and the translation. |
| **Impact on timeline** | Adds elapsed time to Phase 1 and Phase 2. It cannot be absorbed by parallelism, because the translated corpus is an input to calibration, not a parallel workstream. |
| **Recommendation** | Defer to a phase 2 engagement, after the first language is live and measured. If the operator requires it now, it should be re-estimated as a separate engagement rather than added to this one. |

**The mechanism, stated generally:** a change is assessed on four axes — corpus, evaluation,
estimate, timeline — and the assessment is written down before the change is accepted or
rejected. A change that is absorbed silently is a change that will surface as an overrun.

---

## 14. What this document is not

- **Not a real proposal.** The client is fictional and no engagement exists.
- **Not an offer, a quote, or a price.** No rate was researched, quoted, or negotiated.
- **Not a forecast.** The ROI model in `ESTIMATE.md` is a method with placeholder inputs. No
  saving has been measured, achieved, or promised.
- **Not evidence of delivery.** Nothing described here has been built for a client. The
  reference implementation in `../rag-work-sample/` is a local work sample over synthetic
  data, built by the author, and it is labelled as such in its own README.
- **Not a substitute for the operator's own judgement** about its policy, its data, or its
  regulatory position.

What it *is*: a demonstration that the problem can be structured, the options compared
honestly, the estimate derived rather than guessed, and the assumptions written down where a
reviewer can argue with them.
