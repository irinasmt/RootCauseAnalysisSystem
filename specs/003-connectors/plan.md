# Implementation Plan: Connectors (K8s + GitHub + DB) Plug-and-Play

**Branch**: `003-connectors` | **Date**: 2026-02-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-connectors/spec.md`

## Summary

Add a connector framework and initial connectors (Kubernetes, GitHub, PostgreSQL) focused on safe-by-default data collection. The PostgreSQL connector defaults to metadata/aggregate evidence and forbids arbitrary SQL.

## Technical Context

**Language/Version**: Python 3.12
**Testing**: pytest
**Dependencies**:
- Core: pydantic (config), stdlib
- Optional extras (per-connector):
  - K8s: `kubernetes`
  - GitHub: `PyGithub` or direct REST via `httpx`
  - Postgres: `psycopg` (preferred) and/or SQLAlchemy Core

**Target Runtime**: long-running service (Kubernetes deployment)

## Constitution Check

- Safe-by-default: metadata-only DB access unless explicitly configured.
- Deterministic, testable normalization logic.
- Avoid shipping “万能 DB reader”; keep DB evidence narrow and RCA-relevant.

## Proposed Structure

```text
rca/
  connectors/
    __init__.py
    base.py            # Connector interface + registry
    config.py          # Connector config + validation
    redaction.py       # Redaction policy engine
    manifest.py        # Evidence manifest model
    kubernetes_conn.py # optional
    github_conn.py     # optional
    postgres_conn.py   # optional

tests/
  unit/
    test_connectors_config.py
    test_redaction_policy.py
    test_postgres_connector_guards.py
```

## DB Exposure Strategy (Design Decision)

### Default: metadata-only

The Postgres connector focuses on producing RCA-relevant evidence without row access:
- connection saturation indicators
- lock contention indicators
- error-rate indicators from system stats (where available)
- schema change indicators via migration tables only if explicitly allowlisted via views

### Opt-in: views

For orgs that need richer DB evidence, require a dedicated schema of allowlisted views (e.g. `rca_evidence`). This pushes PII stripping to the source and makes the connector auditable.

### Forbid

- free-form SQL strings
- schema-wide table scanning
- returning raw row payloads containing user data by default

## Milestones

1. Connector core: interfaces, registry, config validation, manifest, redaction.
2. PostgreSQL connector skeleton with strict guards + metadata-only evidence.
3. Kubernetes connector skeleton (deploy/config change evidence) and GitHub connector skeleton (commit sync contract).
4. Tests focusing on safety guarantees and deterministic outputs.

