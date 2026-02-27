# Root Cause Analysis System (RCA)

## Overview

An open-source, Kubernetes-first Root Cause Analysis (RCA) system that:

- Detects production anomalies (CPU/memory spikes, latency regressions, error-rate increases)
- Correlates anomalies with recent changes (deployments/releases and git commits)
- Produces an evidence-backed “best explanation” of _what likely caused the incident_ and _why_
- Works with minimal prerequisites (start with metrics + deploy events + git), then optionally deepens accuracy with traces/logs later

## Why this exists

Most observability tools can tell you _something is wrong_. This project aims to answer:

> “Which change caused this, and what evidence supports that conclusion?”

## Current focus (v0)



## Fixture pipeline runner

Run one command to ingest a scenario fixture into Neo4j (mesh + logs + diff index)
and execute the Brain:

```bash
python run_fixture_pipeline.py tests/fixtures/shoe_store/order_slow_due_to_payment
```

Requirements:

- Neo4j running and reachable via `NEO4J_URL`
- `NEO4J_USERNAME`, `NEO4J_PASSWORD` set (in `.env` is fine)

What it does:

1. Clears Neo4j (unless `--no-reset` is passed)
2. Inserts service mesh events as `:MESH_CALL` relationships
3. Inserts logs as `:LogLine` nodes linked from `:Service`
4. Indexes all mock-diff bundles under `<fixture>/diffs/*`
5. Runs `BrainEngine` with graph index wired into `git_scout`

- Multi-cloud / multi-cluster federation
- Full distributed tracing requirements
- “Perfect attribution” for every incident

## How we work (SDD + Spec Kit)

This repository uses Spec-Driven Development (SDD) with Spec Kit.

- Spec Kit repo: https://github.com/github/spec-kit
- SDD project guide: [specs/README.md](specs/README.md)
- Project constitution: [.specify/memory/constitution.md](.specify/memory/constitution.md)

Recommended feature flow:

1. `/speckit.constitution`
2. `/speckit.specify`
3. `/speckit.clarify` (if needed)
4. `/speckit.plan`
5. `/speckit.tasks`
6. `/speckit.analyze` and `/speckit.checklist`
7. `/speckit.implement`

Active feature artifacts live in numbered folders under `specs/` (for example `specs/001-build-realistic-mock/`).

## Docs (start here)

- Architecture overview: [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)
- Brain (LangGraph engine): [docs/brain/BRAIN.md](docs/brain/BRAIN.md)
- Setup (developer): [docs/setup/SETUP.md](docs/setup/SETUP.md)
- Testing strategy: [docs/testing/TESTING.md](docs/testing/TESTING.md)
- GitHub & development instructions: [.github/github_instructions.md](.github/github_instructions.md)

For the full documentation set, browse:

- [docs/](docs)
- [specs/](specs)

## High-level approach

1. Ingest signals (K8s + metrics + git + optional DB)
2. Detect anomalies (cheap always-on)
3. Trigger a bounded investigation (only on incidents)
4. Correlate deploys/commits/config to the anomaly window
5. Generate an evidence-backed RCA report for humans

## Roadmap

See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for the current phased plan.

## Contributing

If you’ve ever said “we deployed something and prod got weird” — you’re in the right place.

- Issues: ideas, bug reports, sample incident timelines
- PRs: collectors, detectors, correlation logic, report formatting
