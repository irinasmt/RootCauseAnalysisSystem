# Implementation Plan (Phased)

This plan is written for developers. It turns the architecture into an executable sequence of milestones with clear deliverables and “definition of done”.

## Guiding constraints

- **DB-first**: spin up the full data layer with realistic seed data before writing any Brain or collector code.
- **Brain before plumbing**: validate the reasoning engine against seeded data before building ingestion pipelines.
- **Evidence-first**: every report claim must trace to a stored evidence reference.
- **Bounded cost**: investigation steps are gated and loop-bounded (see Brain + Edge Cases docs).
- **Language**: Python 3.12+ throughout. See `../../.github/github_instructions.md` for tooling, standards, and project layout.

---

## Phase 0 — Local databases + seed data (Week 1)

Goal: an end-to-end “incident → investigation → report” loop using mocked collectors and deterministic evidence bundles.

Deliverables

- A single canonical **Incident Scenario** (fixture):
  - Service `checkout`
  - Deployment at `T0`
  - Error rate spike at `T0+6m`
  - Candidate commit SHA + diff summary
  - Output report with citations (evidence refs)
- Documented **contracts** (schemas) for:
  - `TriggerCandidate` → `ApprovedIncident`
  - `EvidenceBundle`
  - `RCAReport`

Definition of done

- The pipeline can produce the same report from the same fixture (deterministic mode).
- Every hypothesis line includes at least one evidence reference.

---

## Phase 1 — Data model + Brain API contracts (Week 2)

Goal: lock storage shapes and API shapes early to avoid thrash.

Deliverables

- Data model spec: see `../data_structure/DATA_MODELS.md`
- Human feedback spec: see `../human_feedback/HUMAN_FEEDBACK.md`
- API contract spec (minimal):
  - Incidents list
  - Incident detail (timeline + evidence)
  - Trigger decision (approve/suppress)
  - Run investigation (manual or auto)
  - Add feedback events (confirm/reject/root-cause/note)

Definition of done

- All major entities have stable IDs, timestamps, and referential links.
- A report can be stored and retrieved strictly from storage references.

---

## Phase 2 — Collectors v1 (Week 3)

Goal: ingest “just enough” signal to catch the most common case: deploy caused regression.

Deliverables

- K8s deploy watcher design (events → normalized `DeploymentEvent`)
- Git change fetcher design (commit/PR metadata → normalized `Commit`)
- Metrics fetcher design (Prometheus query plan → normalized `MetricPoint`)

Definition of done

- For a single service, you can obtain:
  - deploy timestamps + image metadata
  - a best-effort commit revision
  - RED metrics around the anomaly window

---

## Phase 3 — Sentinel + Filter gating (Week 4)

Goal: open incidents cheaply and reliably; only investigate when it’s worth it.

Deliverables

- Trigger candidate rules:
  - p99 regression and/or error-rate spike
  - deploy proximity rule
- Filter heuristics (no LLM):
  - persistence window
  - low-traffic suppression
  - rate limit / dedupe
  - known-flaky suppression

Definition of done

- Incidents are created with clear “why triggered” rationale.
- False positives are suppressed with a recorded reason.

---

## Phase 4 — Investigator graph v0 (Week 5)

Goal: a minimal LangGraph flow that produces ranked hypotheses with citations.

Deliverables

- Brain graph spec aligned to `../brain/BRAIN.md`:
  - Supervisor → Git_Scout + Metric_Analyst → Synthesizer → Critic
- Critic “disprove first” checklist (documented) and loop bounds.

Definition of done

- Investigator produces:
  - ranked hypotheses + confidence
  - narrative report
  - evidence references (query IDs, event IDs, timestamps)

---

## Phase 5 — UI integration contract (Week 6)

Goal: the UI can render incidents, hypotheses, and evidence without bespoke logic.

Deliverables

- UI data requirements finalized:
  - timeline objects
  - evidence cards
  - report sections
  - feedback actions + audit log view

Definition of done

- UI can be built against stable API contracts and sample JSON from fixtures.

---

## Parallelizable work (safe to do anytime)

- Add additional incident scenarios (fixtures):
  - traffic spike (“viral success”)
  - dependency slowdown
  - crashloop/config drift
- Expand EvidenceBundle formats (charts, snapshots, diffs)
- Document privacy/security requirements by evidence type (what can contain secrets)
