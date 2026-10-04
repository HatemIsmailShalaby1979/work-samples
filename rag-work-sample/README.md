# RAG / agent work sample — a support-policy assistant

A local-only support assistant over a **synthetic** ferry-operator procedure corpus,
with a labelled evaluation set and a measured comparison between the simplest
possible baseline and a gated workflow.

**This is a work sample, not production software.** It has never been deployed, it has
no users, it has never seen real traffic, and it does not constitute production
experience. It was built in one sitting against invented data.

**Everything is local.** No paid API, no cloud service, no data leaves the machine.
The only runtime dependency is Pydantic v2, which was already present in the
environment. Nothing new was installed.

---

## Run it

```bash
python run_eval.py                  # deterministic mock generator (default)
python run_eval.py --calibrate      # sweep the gate's score floor
python -m pytest                    # 105 tests, including the negative cases
python scripts/ci.py                # the same checks CI runs, run locally
```

No install step. No network. The default run is hermetic and produces byte-identical
output every time.

### Run the service

```bash
# direct
PYTHONPATH=src python -m support_assistant.service

# or in a container
docker compose up --build
```

```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/ready
curl -s -X POST http://127.0.0.1:8080/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"How do I book a crossing online?"}'
```

---

## Operational practices

| Concern | Implementation |
|---|---|
| **Liveness** | `GET /health` — answers while the process serves. Says nothing about readiness. |
| **Readiness** | `GET /ready` — 200 only once the corpus is loaded and indexed, 503 otherwise. A separate signal from liveness, because "process up" and "able to answer" are different failures. |
| **Correlation** | `X-Request-Id` accepted from the caller or generated; echoed in the response body, the response header, and every log line the request produces. |
| **Structured logs** | One JSON object per line on stdout, with `request_id`, `event`, `decision`, `reason`, `procedure_id`, `latency_ms`. |
| **Redaction** | **Query text is not logged by default** — a digest and character count instead. Opting in (`SUPPORT_LOG_QUERY_TEXT=true`) redacts first. The redactor runs on the raw value, never on a formatted string. |
| **No input echo** | A rejected body is never reflected back. Validation failures return a generic message and log only the event. |
| **Body limit** | 64 KB, enforced before parsing. |
| **Timeouts** | Per-request budget; exceeding it returns 504 rather than hanging a worker. |
| **Configuration** | Environment-only, validated at startup, fail-fast. No module reads the environment except `config.py`. |
| **No secrets** | The service reads no credential and needs none. |
| **Immutable filesystem** | `read_only: true` with a small `tmpfs` for `/tmp`. Verified: a write attempt fails with `Read-only file system`. |
| **Non-root** | Runs as uid 10001. |
| **Graceful shutdown** | SIGTERM handler, with `stop_grace_period` giving it time to run. |
| **Dependency locking** | `requirements.txt` pins the direct dependency *and* its transitive dependencies to the versions the committed report was produced against. |
| **Rollback** | Stateless, writes nothing, no migration to reverse. Rollback is a version change — see [`docs/RUNBOOK.md`](docs/RUNBOOK.md). |
| **CI** | `.github/workflows/ci.yml`, mirrored by `scripts/ci.py`. Format, lint, typecheck, tests, evaluation report, container build. **No deploy step and no credential.** |
| **Cloud mapping** | [`docs/CLOUD_MAPPING.md`](docs/CLOUD_MAPPING.md) — **a design exercise, explicitly not performed.** |

### What was actually executed

Every row below was run locally, not asserted:

| Check | Command | Result |
|---|---|---|
| Format | `ruff format --check .` | 23 files already formatted |
| Lint | `ruff check .` | All checks passed |
| Types | `mypy src --ignore-missing-imports` | No issues in 10 source files |
| Tests | `pytest` | **105 passed** in 1.11 s |
| Evaluation | `python run_eval.py` | report matches `expected/` |
| Image build | `docker build` | succeeded, 202 MB |
| Container health | `docker run` + `curl /health` | healthy after 5 attempts |
| Container endpoints | `curl /ready`, `/version`, `/ask` | all correct — answer, abstain, escalate, 422 |
| Query text in logs | `docker logs \| grep` | **0 occurrences** |
| Non-root | `docker exec id` | `uid=10001(appuser)` |
| Read-only filesystem | `docker run --read-only` + `touch` | `Read-only file system` — refused |

`scripts/ci.py` runs all six steps and reports `6/6 steps passed`.

The container path was **not** verified for: sustained load, concurrent requests, memory
limits under pressure, or behaviour on restart. Those are untested.

### Optional: run it against a real local model

```bash
python run_eval.py --generator ollama --model qwen2.5-coder:latest
```

This calls a local Ollama runtime over `http://127.0.0.1:11434`. It is **opt-in and
never used by the default run**, because a model makes the metrics non-reproducible
and a clean clone without Ollama cannot reproduce the committed report.

**The adapter is implemented but NOT verified end to end.** In the environment this was
built in, Ollama 0.34.0 was running and served `/api/tags` and `/api/version`, but a
trivial generation (`"Say OK."`, 8 tokens) timed out at **120 s via raw curl** and at
**300 s through the adapter**, and `/api/ps` reported **no model loaded in memory** —
the first call has to load a 4.7 GB model from disk. The adapter's error and timeout
paths are covered by tests; a completed generation was never observed.

**LLM output quality is therefore untested.** That is stated rather than glossed over.

---

## What it does

```
query ──▶ validate ──▶ BM25 retrieve ──▶ GATE ──┬──▶ answer + citation ──▶ (consequential action?)
                                                 │                              │
                                                 ├──▶ abstain  (no evidence)     └──▶ human approval gate
                                                 └──▶ escalate (draft / retired /      (fails closed)
                                                               conflicting / ambiguous)
```

Two strategies are implemented and compared over the same 36 labelled queries:

| | Strategy | Behaviour |
|---|---|---|
| **A** | `RetrievalOnlyBaseline` | Retrieve, then always answer with the top hit. No gate, no refusal path. |
| **B** | `SupportAssistant` | The same retrieval, then a deterministic gate, citations, and a human-approval boundary. |

The baseline is not a straw man. It is the honest "simplest thing that could work",
and it is what most first implementations actually are.

---

## Results

36 labelled cases, 15 procedures, mock generator. Full report in
[`expected/eval_report.txt`](expected/eval_report.txt).

| Metric | A — baseline | B — workflow |
|---|---|---|
| Decision accuracy | 0.3611 (13/36) | **0.7778 (28/36)** |
| Retrieval recall@5 | 0.8000 | 0.8000 |
| **Unsupported answers** | **16** | **0** |
| Correct abstentions | 0/8 | 7/8 |
| Correct escalations | 0/8 | **8/8** |
| Correct procedure cited | 13/20 | 13/20 |

### What the gate buys, measured

The baseline answers everything. So every conflicting, outdated and out-of-scope
question becomes an **unsupported answer** — 16 of them, 44% of the set. The gate
removes all 16. That is the entire argument for a gate, and it is a measurement rather
than a claim.

### What it costs

Decision accuracy improves from 0.36 to 0.78, but it is not 1.00. The gate
**over-refuses**: it abstains or escalates on cases it cannot resolve, and those score
as decision errors against labels that expect an answer. A system that refuses
correctly is still scored as wrong by a metric that assumes it should answer.

That tension is real and is the most interesting thing in the report.

---

## Findings — including the ones that reflect badly on the sample

### 1. Lexical retrieval cannot handle paraphrase

| Category | Baseline | Workflow |
|---|---|---|
| answerable | 10/10 | 10/10 |
| conflicting | 0/5 | **5/5** |
| out_of_scope | 0/8 | 7/8 |
| outdated | 0/5 | 4/5 |
| **paraphrased** | **3/8** | **2/8** |

BM25 matches terms. A question that shares no vocabulary with the procedure will not
retrieve it, no matter how good the gate is. The paraphrased category exists to expose
exactly this, and it does.

Note the direction of travel: the workflow scores **worse** on paraphrased than the
baseline (2/8 vs 3/8). That is not a regression — it is the gate working. The baseline
guesses and occasionally lands on the right document by accident; the gate refuses when
the evidence is weak. Against a label that says "should answer", refusing scores as an
error. Against the safety metric, it scores as a success.

**This is the finding that motivates embeddings or an LLM.** The baseline is included
precisely so that its failure is visible and attributable rather than assumed.

### 2. The absolute BM25 score is a poor confidence signal for short queries

The gate's floor is an absolute score, and absolute BM25 scores depend on query length
and term rarity. A short but perfectly legitimate question — *"How long do refunds take
to reach my account?"* — scores 2.90 and abstains, while a longer question on the same
topic scores 11.5 and answers. The floor is not scale-free.

The calibration sweep makes this inspectable rather than hidden:

```
  min_score   decision_acc   unsupported   abstain_ok   escalate_ok
        2.5         0.7778             1        6/8         8/8
        3.0         0.7778             0        7/8         8/8    <-- default
        3.5         0.7778             0        8/8         7/8
```

**3.0 is the lowest floor at which unsupported answers reach zero.** Lowering it to 2.5
would answer one more legitimate question and would also let one unsupported answer
through. Zero unsupported answers is the chosen trade-off, and the test
`test_legitimate_but_weak_query_abstains_at_the_configured_floor` records exactly what
that costs.

### 3. The conflict rule detects duplicate coverage, not disagreement

Rule 5 escalates when a topic has more than one *live* procedure. That is a count, not
a semantic comparison — two live procedures on the same topic could agree, and the gate
would still escalate. The corpus is constructed so duplicate coverage and genuine
contradiction coincide, which is convenient and is a limitation. Real contradiction
detection needs to read the text.

### 4. The thresholds are fitted on the test set

`min_score` and `min_margin` were tuned against the same 36 cases used to report the
metrics. A deployment would need a held-out set. This is stated in the report's
limitations section and is not hidden behind the numbers.

---

## Design decisions worth explaining

**No orchestration framework.** LangGraph was not installed and was not requested. The
workflow is an explicit state machine in `workflow.py`. For a graph this small a
framework would add a dependency and a version surface without adding a capability —
and the brief for this sample explicitly asked for the simplest thing that compares
honestly against a baseline.

**The mock generator is extractive, and that is the point.** `MockAnswerGenerator`
returns the procedure's own opening sentences and adds nothing. An extractive answer
*cannot* hallucinate, so every unsupported answer in the evaluation is attributable to
the gate letting a bad match through — never to the generator inventing content. That
separation is what makes the failure analysis possible.

**The approval gate fails closed, and the interesting case is a mismatch.** An approval
recorded for one action must not authorise a different one. `execute_approved_action`
raises on: no approval, a pending approval, a rejected approval, **and an approval for
the wrong action**. That last case is the shape of bug that lets a refund approval
authorise a compensation payment.

**Stemming is conservative on purpose.** `bags`→`bag`, `cancelled`→`cancel`,
`travelling`→`travel`, including collapsing the doubled consonant that naive stripping
leaves behind. Over-stemming would merge unrelated terms, which is worse than
under-stemming in a 15-document corpus.

**Latency is the one field the committed report does not pin.** Wall-clock measurements
are not reproducible. Rather than drop the measurement or loosen the comparison, the
expected file marks the latency line unpinned while every decision and every score is
byte-checked.

---

## Layout

```
rag-work-sample/
├── corpus/harbourline_procedures.json   15 synthetic procedures, with lifecycle traps
├── evalset/eval_queries.jsonl           36 labelled queries across 5 categories
├── src/support_assistant/
│   ├── models.py         Pydantic v2 models, strict and frozen
│   ├── retrieval.py      BM25 + conservative stemmer, standard library
│   ├── gate.py           the decision rules
│   ├── adapters.py       extractive mock + optional local Ollama
│   ├── workflow.py       both strategies + the approval boundary
│   ├── metrics.py        metric computation
│   ├── config.py         environment configuration, validated
│   ├── logging_utils.py  JSON logs, correlation ids, redaction
│   └── service.py        HTTP surface (stdlib only)
├── tests/                105 tests across seven files
├── scripts/ci.py         local CI runner — mirrors the workflow
├── .github/workflows/ci.yml
├── Dockerfile            non-root, pinned, healthcheck
├── docker-compose.yml    read-only, capability-dropped, resource-limited
├── requirements.txt      pinned, including transitive dependencies
├── docs/RUNBOOK.md       start, failure modes, rollback
├── docs/CLOUD_MAPPING.md design exercise — NOT performed
├── run_eval.py           the harness
├── expected/eval_report.txt   committed report — the specification
└── pyproject.toml
```

### The corpus contains deliberate traps

| Trap | Procedure | What it tests |
|---|---|---|
| Two live procedures that disagree | `baggage-allowance`, `baggage-allowance-promo` | The gate must escalate, not pick a side |
| Superseded with a live successor | `refund-standard` → `refund-standard-v2` | The gate must resolve to the current version |
| Retired with no successor | `loyalty-programme` | The gate must escalate: there is no current answer |
| A draft never in force | `fare-discounts-draft` | Draft material must never answer a customer |

### The evaluation set covers five categories

`answerable` (10) · `paraphrased` (8) · `conflicting` (5) · `outdated` (5) ·
`out_of_scope` (8). Each case carries its expected decision, and where the expected
outcome is an answer, the expected procedure — so a right decision citing the wrong
document is not scored as a success.

---

## Limitations

1. **Synthetic corpus and synthetic queries, written by the same author.** They share
   vocabulary. Real queries would be harder and recall@5 here is optimistic.
2. **Lexical retrieval only.** See Finding 1.
3. **Conflict detection is a count, not a comparison.** See Finding 3.
4. **LLM output quality is untested.** The default generator is an extractive mock. The
   Ollama adapter is implemented and its failure paths are tested, but **no generation was
   observed to complete** — see the note above. Treat it as unverified end to end.
5. **No human review of answer wording.** The approval gate covers consequential
   actions only.
6. **Thresholds fitted on the test set.** See Finding 4.
7. **Latency is single-machine, in-process, with no concurrency.** It is not a
   throughput figure and the committed report does not pin it.
8. **No deployment, no external audit, no real traffic, no revenue.** This is a work
   sample built in one sitting.

### Operational limitations

9. **No authentication and no rate limiting.** The service binds to `127.0.0.1` for that
   reason and must not be exposed. `docs/CLOUD_MAPPING.md` treats an authenticating layer
   as a hard requirement, not a configuration choice.
10. **No metrics endpoint.** The structured fields a metric filter would need are emitted;
    nothing consumes them. Monitoring is designed, not implemented.
11. **Health checking is shallow.** `/ready` verifies the corpus loaded. It does not check
    any downstream dependency, because there is none.
12. **The container is untested under load.** No concurrency, no memory pressure, no
    restart behaviour has been measured.
13. **The cloud mapping is a document, not a deployment.** Nothing was provisioned.

---

## What this is not

- Not production experience, and not a claim of any.
- Not evidence of having delivered an LLM system to a client.
- **Not cloud experience.** Nothing was provisioned, deployed, or exposed. The cloud
  mapping is a document.
- **Not a deployed service.** The container runs on a developer machine and nowhere else.
- Not a benchmark. The numbers describe this corpus and this evaluation set only.
- Not a substitute for the author's existing portfolio work — it is a new, self-contained
  exercise over an unrelated corpus, built to demonstrate the evaluation discipline
  rather than to duplicate anything.

---

## Provenance

Built 2026-10-04 as a portfolio work sample.

Runtime: Python 3.13, Pydantic 2.13, standard library.
Dependencies added: **none**.
