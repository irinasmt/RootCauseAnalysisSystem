# Human Feedback Loop

This system must capture human feedback so it can:
- improve accuracy over time (reduce wrong blame)
- provide auditability (“why did we believe this?”)
- turn incidents into reusable knowledge (future retrieval)

This doc defines **what feedback is captured**, **how it is stored**, and **how it is used**.

## Design goals

- **Append-only**: feedback is a timeline of events, not mutable state.
- **Audit-friendly**: every feedback event has an actor, timestamp, and reason.
- **Low friction**: 3-click workflows for common actions.
- **Safe learning**: never silently “train in prod”; treat feedback as data for evaluation + future improvements.

---

## Feedback UX (UI actions)

### Minimal actions (must-have)

1) **Confirm a hypothesis**
- “Yes, this is the root cause”
- Links the incident to a chosen `hypothesis_id`.

2) **Reject a hypothesis**
- “No, this is not the root cause”
- Requires a short reason (free-text or a small taxonomy).

3) **Set final resolution**
- Choose one:
  - selected hypothesis
  - “Other” (free-text)
  - “Unknown”
- Optional: link to postmortem URL.

4) **Add human notes**
- Free text notes for context.
- Optional: attach supporting evidence pointers (dashboard URL, log link).

### Helpful (next)

- Labeling/tagging (e.g., `capacity`, `db-lock`, `bad-release`, `dependency`, `config`)
- “Report quality” rating (helpful / misleading / missing evidence)
- Mark evidence as “relevant” or “irrelevant”

---

## Storage model (append-only events)

Feedback is stored as a timeline of `feedback_events` linked to an incident.

Key properties
- **All feedback is an event**.
- “Final state” (resolved, root cause) can be **derived** from events, or stored as a convenience field on `incidents`.

### Event types (recommended taxonomy)

- `hypothesis_confirmed`
  - payload: `{ hypothesis_id, confidence_override?, note? }`
- `hypothesis_rejected`
  - payload: `{ hypothesis_id, reason_code?, note? }`
- `root_cause_set`
  - payload: `{ root_cause_kind: "hypothesis"|"other"|"unknown", hypothesis_id?, summary? }`
- `incident_status_changed`
  - payload: `{ from, to, reason? }`
- `human_note_added`
  - payload: `{ note_markdown }`
- `evidence_attached`
  - payload: `{ kind, source, ref, metadata? }` (must be convertible to `evidence_artifacts`)
- `identity_mapping_corrected`
  - payload: `{ service_key?, deployment_event_id?, revision? }`

---

## How the Brain should use feedback

### Immediate (v0/v1)

- Show feedback in the UI alongside the report (audit).
- If a hypothesis is rejected, the Brain must avoid presenting the same exact conclusion as “high confidence” without new evidence.

### Evaluation and iteration

- Use feedback to compute offline metrics:
  - top-1 accuracy on confirmed incidents
  - false attribution rate
  - “insufficient evidence” frequency
- Use feedback to improve:
  - gating heuristics (reduce noisy investigations)
  - evidence retrieval (what was missing)
  - Critic checks (what contradictions were missed)

### Learning policy (safety)

- Treat feedback as data that can inform future model/prompt updates.
- Do not automatically update prompts/models in-cluster without explicit operator action.

---

## Privacy and access control

- Feedback may include sensitive context (links to dashboards, customer impact notes).
- The API should enforce:
  - RBAC for who can add/edit feedback events
  - immutable event log (no deletion by default)
  - redaction support for accidental secret leakage
