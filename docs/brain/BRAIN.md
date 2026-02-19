# Brain (RCA Engine)

This document describes the **Brain**: the customer-installed RCA engine that runs the investigation only when a trigger fires.

The Brain is designed to avoid the “commodity trap” by being **self-correcting**: every hypothesis must survive cross-validation before a human sees it.

## Design principles

- **Supervisor–Worker–Critic** (SWC) architecture
- **Evidence-first**: every claim must reference concrete evidence (metrics window, deploy event, commit SHA, timestamps)
- **Guardrails everywhere**: schema validation + evidence checks + confidence thresholds
- **Cost-aware**: loops are bounded; early exits avoid unnecessary LLM calls

---

## High-level graph: Supervisor–Worker–Critic

### Core nodes (SRE teammates)

1. **Supervisor (Orchestrator)**

- Input: `ApprovedIncident` (service, trigger type, anomaly window, severity, deploy proximity)
- Responsibility: pick the next best worker(s) to run, based on the trigger and what evidence is missing.
- Output: a `TaskPlan` (which workers to run and in what order)

2. **Git_Scout (Code worker)**

- Resolves the deployment's commit range (`previous_revision..revision`) from the pre-computed store.
- Does **not** fetch or analyze raw diffs at incident time — that work is already done at push time.
- Queries pre-computed `commit_files`, filtered by the `change_type` values most relevant to the active anomaly type (e.g., `db_migration` + `timeout_retry` for a p99 regression).
- Ranks the filtered commits and selects the top 3–5 by relevance.
- Passes commit **summaries** (not raw diffs) to the Synthesizer.
- Fetches raw `diff_text` on demand only if the Synthesizer or Critic explicitly requests it.
- Handles the rollback case: if `is_rollback = true`, reports what code was removed, not what was added.

3. **Metric_Analyst (Live metrics worker)**

- Queries ClickHouse (and/or Prometheus for near-real-time) for:
  - RED metrics (rate, errors, duration)
  - CPU/memory saturation signals
  - downstream dependency signals (if known)
- Characterizes anomaly “shape” (step spike vs slow creep) and correlates with deploy timestamps.

4. **RCA_Synthesizer (Reasoner)**

- Combines outputs from Git_Scout + Metric_Analyst.
- Produces a ranked set of hypotheses:
  - “Release X caused regression in service Y”
  - “Traffic spike + CPU saturation (capacity issue)”
  - “DB lock/slow query after schema change”
- Outputs: `HypothesisSet` with confidence + evidence references.

5. **The_Critic (Validation node)**

- Primary job: **disprove** the Synthesizer.
- Checks for simpler explanations and evidence gaps:
  - “Are metrics normal for the accused service?”
  - “Did the regression start before the deployment?”
  - “Is there a correlated downstream dependency?”
- Outputs: `CriticReview` with a score + action recommendation.

---

## Self-correcting behavior (conditional edges + loops)

### The “Loop of Truth”

- Synthesizer proposes: “Commit `A12B` in User-Svc caused the incident.”
- Critic evaluates: “User-Svc metrics are normal; evidence is weak.”
- Conditional edge:
  - If `critic_score < 0.80`, loop back to Metric_Analyst (expand scope: dependencies, infra signals, DB signals).
  - If `critic_score >= 0.80`, proceed to final report.

### Loop bounds (cost + safety)

- `max_iterations = 3`
- If unresolved after max iterations:
  - produce a “conflicting evidence” escalation report for a human
  - do not spam alerts

---

## Guardrails (“Guardian patterns”)

### 1) Pydantic Guard (schema validation)

Every node output is parsed/validated against a schema.

Purpose:

- prevents malformed outputs from breaking the pipeline
- enforces required fields for downstream steps

Examples of enforced fields:

- commit SHA must match a valid pattern
- timestamps must be present and parseable
- evidence references must include source + query id

### 2) Evidence Check (anti-handwaving)

Critic verifies that the report contains at least:

- 1+ **DeploymentEvent** IDs/timestamps (if using the “deploy proximity” trigger)
- 1+ **Commit SHA** (when claiming code change)
- 1+ metrics snapshot reference (ClickHouse query ID or materialized view)

If not, the hypothesis is downgraded or rejected.

### 3) Confidence Threshold (alert fatigue control)

- If final confidence `< 0.70`:
  - do not page/Slack by default
  - persist as a “silent” incident for review

---

## Exit ramps (save time + money)

- **Empty Search Exit**: no deployments found within the last hour
  - outcome: stop code-correlation path
  - message: “No recent changes detected; investigating infra-only causes.”

- **Iteration Limit Exit**: hit `max_iterations`
  - outcome: human escalation with structured evidence bundle
  - message: “Conflicting evidence; unable to resolve automatically.”

- **Low traffic exit** (optional): if request rate is below a minimum threshold
  - outcome: avoid interpreting noise as incident

---

## Inputs and outputs (contracts)

### Brain input (from Trigger system)

`ApprovedIncident` should minimally include:

- `service_id`
- `trigger_type` (e.g., `error_rate_spike`, `p99_regression`, `crashloop`)
- `started_at`, `window_start`, `window_end`
- `severity`
- `deployment_event_ids` (if known)

### Brain output

- `incident_hypotheses` (ranked list with confidence)
- `rca_report` (human-readable summary)
- `evidence_refs` (pointers into ClickHouse / Neo4j / Qdrant)
- `next_actions` (rollback, revert, scale, add index, etc.)

Persisted to PostgreSQL for UI consumption.

---

Store responsibilities are defined in ../architecture/ARCHITECTURE.md.

---

## Implementation notes (practical MVP)

- Start with a single LangGraph graph for the three main scenarios:
  1. Bad code push (5xx spike)
  2. Silent slowdown (p99 regression)
  3. Config drift (CrashLoopBackOff)

- Keep workers deterministic where possible:
  - Git_Scout: mostly API calls + diff summarization
  - Metric_Analyst: mostly ClickHouse queries

- Use the LLM primarily for:
  - synthesizing a narrative
  - ranking ambiguous hypotheses
  - generating “next steps” suggestions

- Always store intermediate artifacts so humans can audit the reasoning.
