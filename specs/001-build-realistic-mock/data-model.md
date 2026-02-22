# Data Model: Realistic Mock Incident Data Generation

## Entity: ScenarioDefinition

- Purpose: Defines deterministic generation behavior for one incident type.
- Fields:
  - `scenario_id` (string, unique)
  - `display_name` (string)
  - `trigger` (string)
  - `root_cause_label` (string)
  - `symptom_propagation` (list[string])
  - `noise_profile_defaults` (object)
  - `required_streams` (list[`ui`,`api`,`db`,`k8s`,`mesh`])
- Validation rules:
  - `scenario_id` MUST be one of the fixed v0 IDs.
  - `required_streams` MUST include all five streams.

## Entity: IncidentBundle

- Purpose: A generated fixture package for one run of one scenario.
- Fields:
  - `bundle_id` (string, unique)
  - `scenario_id` (string, FK → ScenarioDefinition)
  - `seed` (integer)
  - `time_anchor` (RFC3339 datetime)
  - `duration_minutes` (integer)
  - `resolution_seconds` (integer)
  - `created_at` (RFC3339 datetime)
  - `artifacts_path` (string)
- Validation rules:
  - Same `scenario_id + seed + time_anchor` MUST reproduce byte-identical stream artifacts.
  - `duration_minutes` >= 15 for v0.

## Entity: StreamArtifact

- Purpose: Represents each generated stream file within a bundle.
- Fields:
  - `bundle_id` (string, FK → IncidentBundle)
  - `stream_name` (enum: `ui`,`api`,`db`,`k8s`,`mesh`)
  - `format` (enum: `txt`,`jsonl`)
  - `file_name` (string)
  - `record_count` (integer)
  - `checksum` (string)
- Validation rules:
  - `ui`,`api`,`db`,`k8s` MUST use `txt`.
  - `mesh` MUST use `jsonl`.
  - Exactly one artifact per stream per bundle.

## Entity: ExpectedOutputLabelSet

- Purpose: Canonical answer key for evaluating Brain output.
- Fields:
  - `bundle_id` (string, FK → IncidentBundle, unique)
  - `root_cause` (string)
  - `trigger` (string)
  - `blast_radius` (string)
  - `expected_first_signal` (string)
  - `confidence_target_min` (number 0..1)
  - `confidence_target_max` (number 0..1)
- Validation rules:
  - Exactly one label set per bundle (`ground_truth.json`).
  - `confidence_target_min <= confidence_target_max`.

## Entity: RcaEvaluationResult

- Purpose: Result of comparing Brain prediction to expected output.
- Fields:
  - `bundle_id` (string, FK → IncidentBundle)
  - `predicted_root_cause` (string)
  - `predicted_confidence` (number 0..1)
  - `threshold_used` (number 0..1, default 0.70)
  - `pass_fail` (enum: `pass`,`fail`)
  - `reason_codes` (list[string])
- Validation rules:
  - `threshold_used` is configurable; default 0.70.
  - `pass_fail` must be deterministic from comparison rules.

## Relationships

- ScenarioDefinition 1 → N IncidentBundle
- IncidentBundle 1 → 5 StreamArtifact
- IncidentBundle 1 → 1 ExpectedOutputLabelSet
- IncidentBundle 1 → N RcaEvaluationResult

## State Transitions

- Bundle lifecycle:
  - `initialized` → `streams_generated` → `labels_generated` → `validated` → `ready_for_evaluation`
- Evaluation lifecycle:
  - `pending` → `evaluated` → `reported`
