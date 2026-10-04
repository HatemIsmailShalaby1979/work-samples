# Runbook — support-assistant work sample

**Scope: local execution only.** This service runs on a developer machine. It has never
been deployed to any environment, and nothing in this document describes production
operation. Where a real deployment would need something, it is marked as such and left
undone.

---

## Prerequisites

| Requirement | Version used | Notes |
|---|---|---|
| Python | 3.13 | 3.12+ required by `pyproject.toml` |
| Pydantic | 2.13.4 | pinned in `requirements.txt` |
| Docker | 29.8.1 | only for the container path |
| Docker Compose | v5.5.1 | only for the compose path |

No credential, no account, no network access is required. The default answer generator is
local and deterministic.

---

## Running it

### Directly

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m support_assistant.service
```

### With Docker Compose

```bash
docker compose up --build          # service on 127.0.0.1:8080
docker compose down                # stop and remove
docker compose --profile tools run --rm eval    # run the evaluation harness in the image
```

The port is published to `127.0.0.1` only, not to all interfaces.

### Verifying it started

```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/ready
curl -s http://127.0.0.1:8080/version
```

---

## Endpoints

| Method | Path | Meaning |
|---|---|---|
| `GET` | `/health` | **Liveness.** Returns 200 while the process is serving. Says nothing about readiness. |
| `GET` | `/ready` | **Readiness.** Returns 200 only once the corpus is loaded and indexed; 503 otherwise. |
| `GET` | `/version` | Service version, dependency versions, and a redacted configuration summary. |
| `POST` | `/ask` | Run one query. Body: `{"query": "..."}`. |

### `/ask` responses

| Status | Meaning |
|---|---|
| 200 | Handled. Body carries `decision` (`answer` / `escalate` / `abstain`), `reason`, `answer`, `citations`. |
| 400 | Body was not valid JSON, or was not a JSON object. |
| 413 | Body exceeded 64 KB. |
| 422 | Query failed validation. The rejected value is **not** echoed back. |
| 500 | Unhandled internal error. The response carries no internal detail. |
| 504 | The workflow exceeded `SUPPORT_REQUEST_TIMEOUT_SECONDS`. |

`decision` is the operational signal, not just a field:

- `answer` — the gate found one live procedure and cited it.
- `escalate` — the match was unusable: conflicting, draft, retired, or ambiguous.
- `abstain` — there was no evidence above the floor. **This is a successful outcome, not a
  failure.** The service refusing to guess is the product working.

---

## Configuration

Every value is read once, from the environment, in `config.py`. No other module reads the
environment. Invalid values fail at startup rather than at first use.

| Variable | Default | Meaning |
|---|---|---|
| `SUPPORT_HOST` | `0.0.0.0` | Bind address. |
| `SUPPORT_PORT` | `8080` | Bind port. |
| `SUPPORT_REQUEST_TIMEOUT_SECONDS` | `10` | Whole-request budget. Exceeding it returns 504. |
| `SUPPORT_CLIENT_TIMEOUT_SECONDS` | `15` | Client read timeout. |
| `SUPPORT_LOG_LEVEL` | `INFO` | One of DEBUG, INFO, WARNING, ERROR. |
| `SUPPORT_LOG_QUERY_TEXT` | `false` | **Leave false unless debugging locally.** See below. |
| `SUPPORT_GENERATOR` | `mock` | `mock` (deterministic) or `ollama` (local model). |
| `SUPPORT_OLLAMA_URL` | `http://127.0.0.1:11434` | Only used when the generator is `ollama`. |
| `SUPPORT_OLLAMA_MODEL` | `qwen2.5-coder:latest` | Only used when the generator is `ollama`. |
| `SUPPORT_CORPUS_PATH` | `corpus/harbourline_procedures.json` | Procedure corpus. |
| `SUPPORT_DATA_DIR` | `build` | Declared so a deployment can assert nothing is written. |

**No secret is read by this service, and none is required.** If one is ever added, it must
be added to `Settings` and deliberately excluded from `redacted_summary()`.

---

## Logs

Structured JSON, one object per line on stdout. Fields: `ts`, `level`, `logger`, `message`,
and — when applicable — `request_id`, `event`, `decision`, `reason`, `procedure_id`,
`latency_ms`.

### Correlation

Every request carries a correlation id: taken from the `X-Request-Id` header when the caller
supplies one, generated otherwise. It appears in every log line the request produces, in the
response body, and in the `X-Request-Id` response header.

### Redaction policy

**Query text is not logged by default.** A support query is customer text, so the default
log line carries a truncated digest and a character count instead:

```json
{"ts":"...","level":"INFO","message":"query received","request_id":"a1b2...","event":"query_received","query_digest":"9f2c...","query_chars":38}
```

Setting `SUPPORT_LOG_QUERY_TEXT=true` opts in. Even then the text is redacted first, and the
redactor runs on the raw value **before** formatting — never on a rendered string.

The redactor catches email addresses, card-like digit runs, and telephone numbers. It is
**pattern-based and therefore incomplete**: it is best effort, not a guarantee. Do not treat
it as a data-protection control, and do not enable query-text logging against real customer
text.

### What is never logged

- Query text (unless explicitly enabled, and then redacted).
- Rejected input. Validation failures return a generic message and log only the event.
- Any internal exception detail in an HTTP response body. The detail goes to the log, with
  the correlation id, and the caller gets a generic 500.

---

## Failure modes and responses

| Symptom | Likely cause | Action |
|---|---|---|
| `/health` fails | Process died or is not bound | Check container/process state; read the last log lines. |
| `/health` passes but `/ready` returns 503 | Corpus missing, empty, or failed to load | Verify `SUPPORT_CORPUS_PATH` and that the file parses. Readiness failing while liveness passes is the correct signal for this. |
| `/ask` returns 504 | Generator slower than the budget | Raise `SUPPORT_REQUEST_TIMEOUT_SECONDS`, or check the local model runtime. |
| `/ask` returns 500 | Unhandled error | Find the correlation id in the response, then grep the logs for it. |
| Every query returns `abstain` | Corpus not loaded, or all scores below the floor | Check `/version` for the corpus path, then `/ready`. |
| Every query returns `escalate` | Corpus has duplicate live procedures per topic | Inspect the corpus for two `active` procedures sharing a `topic_key`. |
| Container exits immediately | Configuration validation failed | `docker compose logs assistant`. Validation errors name the variable. |
| Container healthy but writes fail | `read_only: true` | Expected. The service needs no writable filesystem; a write attempt is a bug. |

---

## Rollback

The service holds no state and writes nothing, so rollback is a version change and nothing
else. There is no migration to reverse and no data to restore.

### Container path

```bash
# Stop the running version.
docker compose down

# Return to the previous known-good revision.
git checkout <previous-revision>

# Rebuild and start.
docker compose up --build -d
curl -s http://127.0.0.1:8080/ready
```

The health check gates the rollout: `docker compose up -d` will not report the service as
healthy until `/health` returns 200, and the healthcheck is defined on the image so a
regression in the entrypoint shows up as an unhealthy container rather than a silent one.

### Direct path

Stop the process, check out the previous revision, restart. Configuration is
environment-only, so no config rollback step exists.

### What rollback cannot fix

If the **corpus** is the problem — a contradictory procedure set, or an empty one — rolling
back the code will not help. `/ready` will tell you the corpus loaded; `/ask` returning
`escalate` for everything tells you the corpus is contradictory. Fix the corpus.

### Verification after any rollback

```bash
curl -s http://127.0.0.1:8080/ready
curl -s -X POST http://127.0.0.1:8080/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"How do I book a crossing online?"}'
python run_eval.py    # the committed report must still match
```

---

## Dependency pinning

`requirements.txt` pins the direct dependency **and** its transitive dependencies to the
versions the committed evaluation report was produced against. A rebuild therefore resolves
to the same tree rather than to whatever is current.

To refresh the pins deliberately:

```bash
python -c "import importlib.metadata as m; [print(f'{p}=={m.version(p)}') for p in ('pydantic','pydantic_core','annotated-types','typing_extensions','typing-inspection')]"
```

Then re-run `python run_eval.py` and confirm the report still matches before committing.

---

## Limitations of this runbook

- It describes a **local** service. There is no deployment, no environment promotion, no
  on-call rotation, and no incident history, because none exists.
- The health check is a single endpoint with no dependency checks beyond the corpus. A real
  service would distinguish "process up" from "dependencies reachable".
- There is no metrics endpoint. Monitoring is defined in `docs/CLOUD_MAPPING.md` as a design
  exercise and is **not implemented**.
- The service has no authentication and no rate limiting. It binds to `127.0.0.1` for that
  reason and must not be exposed.
