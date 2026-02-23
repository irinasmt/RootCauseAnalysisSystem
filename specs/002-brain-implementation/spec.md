# Feature Specification: Brain Investigator MVP

**Feature Branch**: `002-brain-implementation`  
**Created**: 2026-02-22  
**Status**: Draft  
**Input**: User description: "implement the brain"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Investigate Approved Incident (Priority: P1)

As an on-call engineer, I want the Brain to process an approved incident and return ranked RCA hypotheses with evidence.

**Why this priority**: This is the core product value and MVP path.

**Independent Test**: Provide a synthetic `ApprovedIncident` and verify Brain returns a deterministic RCA report with hypotheses and confidence.

**Acceptance Scenarios**:

1. **Given** an `ApprovedIncident`, **When** Brain runs, **Then** it returns report status `completed` with at least one ranked hypothesis.
2. **Given** evidence is weak, **When** critic score is below threshold, **Then** Brain retries up to max iterations and returns escalation if still weak.

---

### User Story 2 - Persist and Retrieve Report (Priority: P2)

As an operator, I want Brain reports persisted and retrievable by incident id.

**Why this priority**: Enables UI/API integration and debugging.

**Independent Test**: Save report to repository storage and fetch by incident id.

**Acceptance Scenarios**:

1. **Given** a completed report, **When** persisted, **Then** it can be retrieved by incident id with identical payload.

---

### User Story 3 - Fail-Safe Execution (Priority: P3)

As an operator, I want Brain failures captured as structured errors without crashing the worker.

**Why this priority**: Keeps pipeline stable in production.

**Independent Test**: Force worker failure and verify Brain returns terminal `failed` with error details.

**Acceptance Scenarios**:

1. **Given** an internal node exception, **When** Brain executes, **Then** error is captured in report and execution terminates safely.

### Edge Cases

- Incident references unknown service.
- No deployment evidence exists in window.
- Metrics evidence list is empty.
- Critic remains below threshold after max iterations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept an `ApprovedIncident` input object and execute Brain investigation flow.
- **FR-002**: System MUST execute nodes in order: `supervisor -> workers -> synthesizer -> critic`.
- **FR-003**: System MUST support bounded retry loop when critic score is below threshold.
- **FR-004**: System MUST emit a deterministic `RcaReport` payload containing hypotheses, confidence, evidence references, and terminal status.
- **FR-005**: System MUST persist report by incident id and allow retrieval.
- **FR-006**: System MUST return structured error payload when execution fails.

### Key Entities

- **ApprovedIncident**: Gated incident record containing incident id, service, start time, and optional deployment metadata.
- **BrainState**: Mutable execution state shared across graph nodes.
- **Hypothesis**: Candidate root cause with evidence and confidence.
- **RcaReport**: Final investigation output with status, ranked hypotheses, and diagnostics.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Brain processes a valid `ApprovedIncident` to terminal state in < 2 seconds in local tests.
- **SC-002**: 100% of Brain test fixtures produce deterministic output with fixed seed/input.
- **SC-003**: Critic gating behavior is validated by tests for pass, retry, and escalation paths.
- **SC-004**: Report persistence and retrieval pass integration tests for all MVP statuses (`completed`, `escalated`, `failed`).
