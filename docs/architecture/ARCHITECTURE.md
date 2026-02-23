# Architecture

## Flow (minimal)

1. **Collectors (always on)** ingest signals from metrics, k8s, git, and optional DB stats.
2. **Sentinel + Filter (always on)** evaluate cheap rules and create incidents only when confidence is high enough.
3. **Brain (on demand)** runs only for approved incidents, gathers evidence, ranks hypotheses, and validates with critic.
4. **API + UI** expose incident status, hypotheses, and supporting evidence.

## Core point

`ApprovedIncident` is a PostgreSQL row created by the Filter stage.

- Yes, we do have constant watchers.
- No, we do **not** run the Brain constantly.
- Brain runs only when an `ApprovedIncident` exists.

## Runtime responsibilities

- **Collectors**: cheap ingestion loops (metrics/k8s/git/db)
- **Sentinel**: deterministic anomaly checks
- **Filter**: suppression + dedupe + gating
- **Brain**: investigation graph (`supervisor -> workers -> synthesizer -> critic`)

## Data stores

- **PostgreSQL**: incidents, gating decisions, reports
- **ClickHouse**: time-series and derived anomaly features
- **Neo4j**: service/dependency/deploy relationship graph
- **Qdrant**: embeddings for semantic retrieval

## Brain loop (minimal)

`ApprovedIncident -> supervisor -> (git_scout + metric_analyst) -> rca_synthesizer -> critic`

- If critic score is strong: publish report.
- If weak and attempts remain: expand evidence and retry.
- Stop after bounded retries; escalate with evidence.

## Why this split

- Keeps always-on path cheap and deterministic.
- Contains LLM cost to incident windows only.
- Produces explainable outputs backed by concrete evidence.
