# Root Cause Analysis System (RCA)

## What we’re building

An open-source, Kubernetes-first Root Cause Analysis (RCA) system that:

- Detects production anomalies (CPU/memory spikes, latency regressions, error-rate increases)
- Correlates anomalies with recent changes (deployments/releases and git commits)
- Produces an evidence-backed “best explanation” of _what likely caused the incident_ and _why_
- Works with minimal prerequisites (start with metrics + deploy events + git), then optionally deepens accuracy with traces/logs later

## Docs

- Architecture overview: [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)
- Brain (LangGraph engine): [docs/brain/BRAIN.md](docs/brain/BRAIN.md)
- Edge cases (production readiness): [docs/production_readiness/EDGE_CASES.md](docs/production_readiness/EDGE_CASES.md)
- Futuristic development (advanced moats): [docs/future_development/FUTURISTIC_DEVELOPMENT.md](docs/future_development/FUTURISTIC_DEVELOPMENT.md)
- Implementation plan (phased): [docs/planning/IMPLEMENTATION_PLAN.md](docs/planning/IMPLEMENTATION_PLAN.md)
- Setup (developer): [docs/setup/SETUP.md](docs/setup/SETUP.md)
- Data models (schemas): [docs/data_structure/DATA_MODELS.md](docs/data_structure/DATA_MODELS.md)
- Testing strategy: [docs/testing/TESTING.md](docs/testing/TESTING.md)
- Identity mapping (service↔deploy↔commit): [docs/data_gathering/IDENTITY_MAPPING.md](docs/data_gathering/IDENTITY_MAPPING.md)
- Human feedback loop: [docs/human_feedback/HUMAN_FEEDBACK.md](docs/human_feedback/HUMAN_FEEDBACK.md)
- GitHub & development instructions: [.github/github_instructions.md](.github/github_instructions.md)
- Spec-Driven Development (SDD): [specs/README.md](specs/README.md)

## Initial scope (v0)

- Kubernetes only (single cluster)
- Metrics-based anomaly detection (Prometheus-style signals)
- Release/commit correlation (deployment timeline + git history)
- Human-readable RCA report with citations to:
  - the anomaly window
  - the deployment/release involved
  - likely-impacting commits/files

## Non-goals (for now)

- Multi-cloud / multi-cluster federation
- Full distributed tracing requirements
- “Perfect attribution” for every incident (we’ll prioritize high-confidence, evidence-backed conclusions)

## Why this exists

Most observability tools can tell you _something is wrong_. This project aims to answer:

> “Which change caused this, and what evidence supports that conclusion?”

## High-level approach

1. Ingest signals (K8s + metrics + git + optional DB)
2. Detect anomalies (cheap always-on)
3. Trigger a bounded investigation (only on incidents)
4. Correlate deploys/commits/config to the anomaly window
5. Generate an evidence-backed RCA report for humans

## Roadmap

See docs/architecture/ARCHITECTURE.md for the current phased plan.

## Contributing

If you’ve ever said “we deployed something and prod got weird” — you’re in the right place.

- Issues: ideas, bug reports, sample incident timelines
- PRs: collectors, detectors, correlation logic, report formatting
