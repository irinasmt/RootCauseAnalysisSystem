# Root Cause Analysis System (RCA)

## What we’re building

An open-source, Kubernetes-first Root Cause Analysis (RCA) system that:

- Detects production anomalies (CPU/memory spikes, latency regressions, error-rate increases)
- Correlates anomalies with recent changes (deployments/releases and git commits)
- Produces an evidence-backed “best explanation” of *what likely caused the incident* and *why*
- Works with minimal prerequisites (start with metrics + deploy events + git), then optionally deepens accuracy with traces/logs later

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

Most observability tools can tell you *something is wrong*. This project aims to answer:

> “Which change caused this, and what evidence supports that conclusion?”

## High-level approach

1. **Ingest signals**: metrics, Kubernetes events, deployment metadata, git commits
2. **Detect anomalies**: identify statistically significant shifts vs baseline
3. **Build context**: time window + impacted services + dependency hints
4. **Correlate causes**: match anomalies to deployments/commits and rank hypotheses
5. **Generate report**: summarize likely root cause with confidence + supporting evidence

## Roadmap

- v0: Metrics + K8s events + Git correlation, basic report output
- v1: Add service topology model (graph) and semantic search over diffs
- v2: Optional logs/traces ingestion for deeper precision and fewer false positives

## Contributing

If you’ve ever said “we deployed something and prod got weird” — you’re in the right place.

- Issues: ideas, bug reports, sample incident timelines
- PRs: collectors, detectors, correlation logic, report formatting
