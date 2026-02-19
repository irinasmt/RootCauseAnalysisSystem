# Setup (Developer)

This document is for developers who want to iterate locally and validate the data contracts before connecting to real clusters.

## Recommended local dev mode

Start in **mocked mode** (fixtures) and only then connect:
1) mocked collectors → end-to-end report generation
2) local databases (optional early)
3) real Prometheus + K8s watch

## Prerequisites

- Git
- Docker Desktop (recommended for local databases)
- Optional for later:
  - a local K8s cluster (`kind` / `minikube`)
  - Prometheus (local or remote)

## Local dependencies (concept)

The architecture references:
- PostgreSQL (incidents, decisions, artifacts)
- ClickHouse (metrics + derived features)
- Neo4j (topology + relationships)
- Qdrant (embeddings + retrieval)

You can run these with Docker Compose during development.

## Environment configuration (proposed)

Use environment variables (or a `.env`, if you prefer) with the following keys:

- `POSTGRES_DSN` (example: `postgresql://rca:rca@localhost:5432/rca`)
- `CLICKHOUSE_HTTP_URL` (example: `http://localhost:8123`)
- `NEO4J_URI` (example: `bolt://localhost:7687`)
- `NEO4J_AUTH` (example: `neo4j/password`)
- `QDRANT_URL` (example: `http://localhost:6333`)

LLM (optional)
- `LLM_PROVIDER` (example: `openai|anthropic|local`)
- `LLM_API_KEY` (if applicable)
- `LLM_MODEL` (example: `gpt-4.1-mini` or equivalent)

## Fixture-first workflow

1) Choose a fixture scenario
- Keep a canonical scenario for regression-after-deploy.
- The fixture should include deploy event, metric window summary, and candidate commits.

2) Run the Brain against the fixture
- Goal: validate schemas + report format before any infra integration.

3) Store and retrieve results
- Even in mocked mode, assume the report will be persisted and later retrieved by the UI.

## Connecting to real systems (later)

### Kubernetes

- Collect DeploymentEvents via the Kubernetes API Watch.
- Normalize service identity (see `../data_gathering/IDENTITY_MAPPING.md`).

### Prometheus

- Use a small set of queries per service:
  - request rate (RPS)
  - error rate (5xx)
  - p50/p95/p99 latency
  - CPU and memory saturation
- Prefer short windows (5–15m) and pre-aggregations (recording rules) as you scale.

## Common developer pitfalls

- **Service identity drift**: relying on ad-hoc labels makes correlation fragile; standardize early.
- **Commit mapping gaps**: image tags rarely equal commit SHAs in real CI/CD; require OCI labels or annotations.
- **Evidence references**: don’t let reports inline raw data; reference stored evidence artifacts.
