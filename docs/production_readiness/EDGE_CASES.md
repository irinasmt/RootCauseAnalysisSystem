# Edge Cases (Production Readiness)

Edge cases are what separate a toy RCA bot from a tool SREs trust. The goal here is to **avoid unnecessary investigations**, **avoid LLM spend**, and **avoid wrong blame**.

See also:
- [Architecture overview](../architecture/ARCHITECTURE.md)
- [Brain (RCA engine)](../brain/BRAIN.md)

## 0) "Ghost change" (manual kubectl / out-of-band mutation)

Problem:
- Someone runs `kubectl edit`, `kubectl set image`, `kubectl scale`, or `kubectl apply -f` from a laptop.
- There is no CI/CD pipeline event, no GitHub webhook, no PR — the change leaves no git trail.
- An incident fires shortly after and the correlator finds no `DeploymentEvent` to blame.

### What the K8s watcher can see

The K8s collector watches the API server (Deployments, ConfigMaps, Secrets, ReplicaSets). Every mutation — regardless of origin — produces a `MODIFIED` event with the full new object spec.

By storing the previous spec and diffing, you know **exactly what changed**:

| Resource | What you can diff |
|---|---|
| Deployment | Image ref, env var names + values, resource limits, replica count, labels |
| ConfigMap | Key names and values that changed |
| Secret | Key names that changed only — **never store secret values** |
| ReplicaSet | Replica count changes |

**Who made the change** is only available if the cluster has [K8s audit logging](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/) enabled. Without it you get what changed and when, but not the actor.

### Handling

- Every out-of-band mutation is recorded as a `ConfigChangeEvent` (see `../data_structure/DATA_MODELS.md`).
- `deploy_type` is set to `manual`; `revision` is `null` (no commit to blame).
- The spec diff (old vs new) is stored as the change payload.
- These events flow through the same triggering and correlation logic as normal `DeploymentEvents`.
- If the anomaly window overlaps with a `ConfigChangeEvent`, the Brain should present it as the leading hypothesis, with the spec diff as the evidence.
- If audit logging is available, the actor field is populated and surfaced in the report.

---

## The Gatekeeper (first node)

Before we invite the LLM (or even start deep correlation), we run a simple deterministic gate.

Inputs (minimum):
- RPS / request rate
- 5xx error rate
- p99 latency
- CPU / memory utilization
- recent DeploymentEvents / ConfigChangeEvents

Decision logic (concept):

- If **Traffic ↑** AND **Error Rate ~ normal** → Capacity/Scaling path
- If **Traffic ~ normal** AND **Error Rate ↑** → Code/Config path
- If **Traffic ↑** AND **Error Rate ↑** → “Perfect storm” path (mixed causes)

The Gatekeeper should return:
- selected investigation path
- whether to allow LLM (yes/no)
- a short rationale (persist for audit)

---

## 1) “Viral Success” (traffic spikes)

Problem:
- CPU/memory and latency spike, but nothing changed.

Cheap check (no LLM):
- Compare **RPS change** vs **resource usage change**.
- If `RPS > +30%` at the same time as CPU spike, treat this as a likely demand/capacity event first.

Actions (infra persona):
- Check HPA events: did we hit min/max replicas?
- Check scaling lag: did replicas increase late?
- Check DB pool saturation / max connections.
- Check egress latency to critical dependencies (DB/external APIs).

LLM policy:
- Only run the Investigator if scaling checks cannot explain the symptoms.

---

## 2) “Massive Release” (50+ commits / noisy diff)

Problem:
- Too many changes overwhelm the reasoning step; high hallucination risk.
- Doing this analysis under incident pressure is slow and expensive.

Fix: **pre-compute at push time, query at incident time**

The core principle is that commit analysis is never done during an investigation. All the expensive work happens asynchronously when each commit is pushed, so by the time an incident fires, the data is already structured and ready to query.

### What is pre-computed at push time (per commit)

1. **Commit summary** — local/cheap LLM writes a 1–2 sentence plain-language summary of the commit.
2. **Per-file change type** — deterministic classification (path patterns + keyword matching): `db_migration`, `dependency`, `config`, `timeout_retry`, `http_client`, `shared_util`, `auth`, etc. No LLM needed.
3. **Per-file diff stored as text** — raw diff hunks persisted so they can be retrieved on demand without hitting the repo again.

See `../data_gathering/IDENTITY_MAPPING.md` (Section 7) for the full taxonomy and storage contract.

### What Git_Scout does at incident time (a query, not an analysis)

Git_Scout never fetches or reads raw diffs during an incident. Instead:

1. Resolve the deploy's commit range (`previous_revision..revision`).
2. Filter pre-computed `commit_files` by the `change_type` values relevant to the anomaly type:
   - p99 regression → `db_migration`, `timeout_retry`, `http_client`
   - error rate spike → `auth`, `http_client`, `shared_util`, `config`
   - CrashLoop → `config`, `dependency`
3. Rank surviving commits by `lines_changed` and `change_type` priority for the active anomaly.
4. Pass only the **commit summaries** (not raw diffs) of the top 3–5 to the Synthesizer.
5. Raw `diff_text` is only fetched if the Synthesizer or Critic explicitly requests it as a follow-up.

LLM policy:
- Expensive model (GPT-4 / Claude) only ever sees commit summaries, never raw diffs.
- If no pre-computed data exists for a commit range, Git_Scout logs a gap and falls back to infra/dependency hypotheses.

---

## 3) “Silent dependency” failures (third-party/API)

Problem:
- Your code didn’t change, but a third-party dependency is slow.

Signals:
- Egress latency increases
- timeouts to external hosts
- downstream service p99 increases before upstream

Handling:
- Add a “Third-Party Health” tool:
  - check public status pages where appropriate
  - check synthetic probes (optional)
  - check egress latency metrics per destination

LLM policy:
- If dependency regression is clearly upstream, produce a report that avoids blaming internal commits.

---

## 4) “Poison pill” request (rare input crashes pods)

Problem:
- 99.9% OK; one specific request pattern triggers OOM/crash.

Handling:
- Snapshot the last N requests/attributes before crash (where available):
  - endpoint
  - request size
  - key identifiers (user_id/tenant_id) with privacy controls
- Run lightweight clustering / grouping to find common denominators.

Outcome:
- Flag as “Poison pill” and recommend:
  - input validation
  - per-request limits
  - circuit breaking / isolation

---

## 5) “Heisenbug” (intermittent, disappears fast)

Problem:
- The anomaly is gone before deep analysis finishes.

Fix: snapshotting (“Polaroid”)

When the trigger fires:
- Store a snapshot bundle immediately:
  - metrics window slices
  - pod/container state summary
  - recent deploy/config events
  - connection pool/thread counts (where available)

Investigation should analyze the snapshot, not the live system.

---

## 6) “Cold start” delays (serverless / warm-up)

Problem:
- Latency spikes due to initialization, not a regression.

Handling:
- Check `init_duration` / cold start signals.
- If cold start explains the majority of latency, report as cold start and suggest:
  - provisioned concurrency
  - keeping warm
  - reducing init work

---

## What to implement first (practical)

1. Gatekeeper node + LLM allow/deny policy
2. Viral success capacity checks (HPA + DB pool)
3. Massive-release slicing + top-3 commit selection
4. Snapshot bundle on trigger (for heisenbugs)
