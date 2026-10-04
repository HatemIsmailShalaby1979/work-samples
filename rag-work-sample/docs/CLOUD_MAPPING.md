# Cloud deployment mapping — a design exercise

> ## ⚠️ NOT PERFORMED
>
> **Nothing in this document has been executed.** No cloud account was created, no
> resource was provisioned, no image was pushed to a registry, no domain was configured,
> and no traffic has ever reached this service.
>
> This is a paper exercise: what would have to change for the local service in this
> repository to run on a managed platform, and what that would cost in effort and money.
> It exists because the ability to reason about a deployment is different from having
> performed one, and this document does not claim the second.
>
> **Reading this document is not evidence of cloud production experience.** It is evidence
> that the author can produce a deployment plan. Those are not the same thing, and the
> difference is stated here rather than left for a reader to discover.

---

## Why one platform and not three

The service is a single stateless container with one read-only data file. Choosing AWS as
the worked example keeps the mapping concrete; the shape transfers to GCP or Azure with
different service names. Writing three versions would produce three shallow sketches
instead of one considered one.

---

## What the local setup already provides

| Concern | Local implementation | Holds up in a deployment? |
|---|---|---|
| Packaging | `Dockerfile`, non-root user, pinned dependencies | **Yes** — unchanged |
| Configuration | Environment variables, validated at startup, fail-fast | **Yes** — maps to platform config |
| Liveness / readiness | `/health`, `/ready` | **Yes** — becomes the platform's probe config |
| Structured logs | JSON on stdout | **Yes** — becomes the log shipping source |
| Correlation | `X-Request-Id`, echoed and logged | **Yes** |
| Redaction | Query text excluded by default | **Yes**, but see the gap below |
| Graceful shutdown | SIGTERM handler | **Yes** |
| Immutable filesystem | `read_only: true`, no writes | **Yes** — becomes an enforced property |
| Dependency pinning | `requirements.txt`, transitive pins | **Partly** — no digest pinning |

The local setup is not a toy. Most of the operational discipline survives translation; what
does not survive is everything that requires an account.

---

## The mapping

### 1. Compute

| | |
|---|---|
| **Local** | `docker compose up` on a laptop |
| **AWS** | ECS on Fargate, behind an Application Load Balancer |
| **Why not Lambda** | The service loads a corpus and builds an index at startup. That is a cold-start cost paid per invocation on Lambda and paid once on a long-lived task. A container is the honest fit for the current design. |
| **Changes required** | Task definition carrying the environment variables from `config.py`; the container port; a health check path of `/health`; a stop timeout ≥ the `stop_grace_period` so SIGTERM handling completes. |
| **Cost shape** | Billed per vCPU-second and GB-second while running. Two small tasks running continuously is the dominant fixed cost of this design. |

### 2. Image registry

| | |
|---|---|
| **Local** | Image built and run on the same machine |
| **AWS** | ECR, image pushed by CI with an OIDC role — **no long-lived registry credential** |
| **Changes required** | `docker push` in CI, and an IAM role trust policy scoped to the repository. |
| **Not done here** | CI builds the image and deliberately does not push it. There is no registry login in the workflow and no credential to leak. |

### 3. Configuration and secrets

| | |
|---|---|
| **Local** | Environment variables, `.env` optional |
| **AWS** | Non-secret configuration as task-definition environment; anything sensitive in Secrets Manager injected at task start |
| **Current state** | **The service reads no secret at all.** There is nothing to move yet. If a secret is added, `Settings.redacted_summary()` must be updated in the same change — that is the enforcement point, and it is a code change, not a policy. |
| **Changes required** | None today. A future model API key would be the first. |

### 4. Data

| | |
|---|---|
| **Local** | `corpus/harbourline_procedures.json`, baked into the image, read-only |
| **AWS** | The same file from S3 at startup, or baked into the image |
| **Trade-off** | Baking it in makes the corpus version equal to the image version — simple and reproducible, but a corpus fix needs a rebuild. Loading from S3 allows a corpus update without a deploy, at the cost of a startup dependency and a failure mode where the service starts with a stale corpus. |
| **Recommendation** | Keep it baked in for now. The corpus changes rarely and reproducibility is worth more than the flexibility. Revisit when the corpus is tenant-specific. |
| **Not needed** | No database. The service holds no state, so RDS or DynamoDB would be a cost with no purpose. |

### 5. Observability

| | |
|---|---|
| **Local** | JSON to stdout |
| **AWS** | CloudWatch Logs via the log driver; metric filters on the structured `event` and `decision` fields; alarms on error rate and on the 504 rate |
| **Monitoring definitions that would matter** | `escalate` rate per hour (a rising rate means the corpus is degrading); `abstain` rate (a spike means retrieval or the corpus broke); p95 latency; 5xx rate; task restart count |
| **Status** | **Not implemented.** The service emits the fields a metric filter would need, and nothing consumes them. This is the largest gap between the design and the local reality. |

### 6. Networking

| | |
|---|---|
| **Local** | Bound to `127.0.0.1`, no auth, no rate limiting |
| **AWS** | ALB in public subnets, tasks in private subnets, security group allowing only the ALB |
| **Hard requirement** | The service has **no authentication and no rate limiting**. Exposing it without an authenticating layer in front would be a defect, not a configuration choice. Any real deployment must put WAF, an authorizer, or an API gateway in front of it. |
| **Not done here** | Nothing is exposed. |

### 7. Scaling

| | |
|---|---|
| **Local** | One process, one container |
| **AWS** | Target-tracking on CPU or request count, minimum two tasks for availability |
| **What breaks first** | The corpus is loaded per task and held in memory. At 15 procedures this is trivial; at 5,000 it is a per-task memory cost and a startup cost that would justify a shared index service. The scaling question is about the corpus, not the request rate. |

### 8. Availability and rollback

| | |
|---|---|
| **Local** | Stop, check out, restart |
| **AWS** | Rolling or blue/green deployment with the ALB health check gating traffic; rollback by redeploying the previous task definition revision |
| **Why this is straightforward here** | The service is stateless and writes nothing, so there is no migration to reverse. Rollback is a version change. That property was designed in, not discovered. |

### 9. CI/CD

| | |
|---|---|
| **Local** | `scripts/ci.py` |
| **AWS** | The same steps in the workflow, plus an authenticated push to ECR and a task-definition update |
| **Not done here** | The workflow stops at `docker build` and a local health check. It has no credential, so it cannot deploy even by accident. |

---

## What this design deliberately leaves out

- **No secrets manager wiring** — there are no secrets.
- **No TLS** — nothing is exposed.
- **No authentication or rate limiting** — the local service binds to localhost for exactly
  this reason.
- **No database, cache, or queue** — the service has no state to put in them.
- **No autoscaling, no multi-region, no DR** — there is nothing to scale and nothing to
  recover.
- **No cost estimate in currency** — a figure would be invented, and an invented figure is
  worse than no figure. The cost *shape* is stated per component instead.

---

## The honest gap

Everything above is reasoning, not operation. Specifically, none of the following has been
done, and none of it should be inferred from this document:

- Provisioning any cloud resource
- Pushing an image to any registry
- Configuring a load balancer, a security group, or a DNS record
- Running a task on a managed platform
- Operating a service under real traffic
- Handling an incident, a rollback under load, or an on-call page
- Any of the above at scale, under budget, or against a real SLA

The distance between this document and cloud production experience is the whole of the list
above. It is written down because a plan that reads like experience is more dangerous than
no plan at all.
