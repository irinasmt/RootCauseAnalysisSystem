---
description: Run Brain against the current fixture and explain what the RCA report means.
---

Run the RCA Brain engine against the fixture in the current directory (or the path below) and explain the output.

**Fixture path:** ${input:fixture_path:Path to the fixture directory, e.g. tests/fixtures/shoe_store/order_slow_due_to_payment}

Do the following:

1. Read the fixture's `manifest.json` and `ground_truth.json` to understand what the expected root cause is.
2. Run the Brain engine:
   ```bash
   python run_brain.py ${input:fixture_path:tests/fixtures/shoe_store/order_slow_due_to_payment}
   ```
3. Parse the RCA report output and explain:
   - **What Brain identified as the root cause** — and whether it matches `ground_truth.json`
   - **Which Brain nodes contributed evidence** (mesh_scout, git_scout, metric_analyst)
   - **The confidence score** — and whether it met the `threshold` in `manifest.json`
   - **The fix recommendations** from fix_advisor
   - **Any critic loop iterations** — did Brain self-correct, and why?
4. If the confidence score is below threshold, suggest which stream file likely has insufficient signal and how to improve the fixture.
