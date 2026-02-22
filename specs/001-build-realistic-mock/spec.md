# Feature Specification: Realistic Mock Incident Data Generation

**Feature Branch**: `001-build-realistic-mock`  
**Created**: 2026-02-22  
**Status**: Draft  
**Input**: User description: "Build realistic mock incident data generation for a simple app with UI, API, DB, Kubernetes, and service mesh signals."

## Clarifications

### Session 2026-02-22

- Q: Which exact v0 scenario set should be required? → A: Fix v0 to exactly five scenarios: `normal_load`, `db_connection_pool_exhaustion`, `slow_query_regression`, `bad_api_rollout`, `pod_oom_restart_loop`.
- Q: What deterministic tolerance should v0 enforce? → A: Stream artifacts must be byte-identical; only bundle-level metadata timestamps may differ (`created_at`, run timestamp).
- Q: How should RCA pass threshold be defined in v0? → A: Threshold remains configurable with a global default of `0.70`.
- Q: Can Brain-based RCA evaluation be delivered in this feature iteration? → A: No. Brain integration is deferred until the Brain implementation exists.

## User Scenarios & Testing _(mandatory)_

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Generate a Basic Incident Bundle (Priority: P1)

As an RCA engineer, I can generate a deterministic mock incident bundle that contains a coherent timeline across UI, API, DB, Kubernetes, and service mesh layers.

**Why this priority**: This creates the minimum usable artifact needed to evaluate RCA logic before real production telemetry is available.

**Independent Test**: Generate one bundle twice with the same scenario and seed; both runs must produce equivalent artifacts and a single expected-output label file.

**Acceptance Scenarios**:

1. **Given** a supported scenario and seed, **When** generation is executed, **Then** one complete bundle is produced with all required stream artifacts and expected-output metadata.
2. **Given** the same scenario and seed, **When** generation is re-run, **Then** stream artifacts are byte-identical and only bundle-level metadata timestamps may differ.

---

### User Story 2 - Evaluate RCA Against Expected Output (Priority: P2)

As an RCA engineer, I can prepare expected-output metadata and threshold policy so Brain evaluation can be integrated in a later feature once Brain exists.

**Why this priority**: This prevents contract churn later and keeps mock bundles ready for future RCA scoring.

**Independent Test**: Validate every bundle contains expected-output labels and threshold metadata needed for future evaluation.

**Acceptance Scenarios**:

1. **Given** a generated bundle, **When** expected-output metadata is validated, **Then** required fields and default threshold policy are present and valid for future Brain evaluation.

---

### User Story 3 - Cover Basic v0 Scenarios (Priority: P3)

As an RCA engineer, I can generate a small set of baseline scenarios that represent common incidents in a simple app.

**Why this priority**: A basic scenario library gives immediate regression coverage while keeping v0 scope manageable.

**Independent Test**: Generate one bundle per v0 scenario and verify all bundles are complete, valid, and evaluable.

**Acceptance Scenarios**:

1. **Given** the default scenario set, **When** generation runs, **Then** one valid bundle is created per scenario with expected-output metadata.

---

### Edge Cases

- Partial outage where only a subset of pods/workloads degrade.
- Clock skew across sources causing near-misaligned timestamps.
- Background noise spikes that are unrelated to the true root cause.
- Retry storms that amplify symptoms without changing primary cause.
- Service mesh routing/policy changes causing selective request failures.

## Non-goals for this feature iteration

- Running real Brain predictions against mock bundles.
- Implementing Brain-side scoring or pass/fail execution logic.

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: System MUST generate deterministic incident bundles from scenario + seed inputs.
- **FR-002**: System MUST include coherent cross-layer evidence for UI, API, DB, Kubernetes, and service mesh signals in each bundle.
- **FR-003**: System MUST include exactly one expected-output metadata artifact per bundle describing root cause and related evaluation labels.
- **FR-004**: System MUST output logs in mixed format for v0: plain text for non-mesh streams and structured JSONL for service mesh stream.
- **FR-005**: System MUST support exactly this default v0 scenario set: `normal_load`, `db_connection_pool_exhaustion`, `slow_query_regression`, `bad_api_rollout`, `pod_oom_restart_loop`.
- **FR-006**: System MUST preserve correlation identifiers required for causal stitching across stream artifacts.
- **FR-007**: System MUST encode evaluation-ready metadata and threshold policy (configurable, default 70%) so future Brain evaluation can consume bundles without contract changes.
- **FR-008**: System MUST enforce deterministic tolerance in v0: byte-identical stream artifacts across reruns with the same scenario and seed, with variation allowed only for bundle-level metadata timestamps.

### Key Entities _(include if feature involves data)_

- **Incident Bundle**: A single generated fixture package containing timeline artifacts for all required streams and generation metadata.
- **Expected Output Label Set**: Canonical evaluation metadata for one bundle (root cause, trigger, blast radius, expected first signal, confidence band).
- **Scenario Definition**: A reusable incident profile describing trigger conditions, symptom propagation, and expected causal pattern.

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: 100% of generated v0 bundles contain all required stream artifacts plus one expected-output metadata artifact.
- **SC-002**: Repeated generation with the same scenario and seed reproduces byte-identical stream artifacts; only bundle-level metadata timestamps (`created_at`, run timestamp) may differ.
- **SC-003**: Exactly five v0 scenarios (`normal_load`, `db_connection_pool_exhaustion`, `slow_query_regression`, `bad_api_rollout`, `pod_oom_restart_loop`) are available and each can be generated successfully as a complete bundle.
- **SC-004**: 100% of generated bundles include evaluation-ready metadata with a configurable threshold policy and default of 70% confidence.
