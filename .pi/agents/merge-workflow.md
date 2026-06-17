---
name: merge-workflow
description: Implement merge workflow and safety-valve revert for raindrop-categorize Phase 4
---

You are implementing Phase 4d+4e — merge workflow and safety-valve revert.

## Context

Project root: /Users/ashebanow/Development/ai/raindrop-skills
Rules file: raindrop-categorize/references/raindrop-rules.json
Proposals file: ~/.hermes/cache/raindrop-proposals.json
Quality file: ~/.hermes/cache/raindrop-quality.json
Shared module: shared/raindrop_common.py
Holdout: ~/.hermes/cache/raindrop-holdout.json

## Task

Create `scripts/revert-regression.py` that checks for rule changes that caused
holdout regression and automatically reverts them.

### Safety-valve logic

1. Read `raindrop-proposals.json` — find proposals with status "auto_approved" or "user_approved"
   that were applied since the last run
2. Read `raindrop-quality.json` — find the most recent quality record that has a `verification` section
3. Compare the current holdout verification score against the baseline recorded when the
   proposal was applied
4. If collection_accuracy dropped by more than 0.1 (10 percentage points):
   a. Revert the change to `raindrop-rules.json` (remove the added keywords, restore previous state)
   b. Mark the proposal as "rejected" with reason "verification regression"
   c. Print a warning that will be picked up by cron_run.py's Discord output

### Revert logic

To revert:
1. Read `raindrop-rules.json`
2. Find the rule by `rule_id`
3. Remove `change.add_keywords` from the rule's `keywords` list
4. Bump `version` and update `last_updated`
5. Save

The proposals file should store a snapshot of the rule before the change was applied:

```json
{
  "id": "prop-...",
  "status": "auto_approved",
  "change": { "add_keywords": ["compose"] },
  "snapshot": {
    "previous_keywords": ["docker"],
    "confidence_before": 0.85,
    "verification_before": { "collection_accuracy": 0.92 }
  }
}
```

If no snapshot exists (backward compatibility), skip the revert and flag for manual review.

### Wire into cron_run.py

Add a call to `revert-regression.py` at the start of the cron run (before the scan step):

```python
# 0. Safety valve — revert regressive rule changes
revert_rc, revert_out, revert_err = run_subprocess(
    ["python3", str(REVERT_SCRIPT)], timeout=30
)
```

Add `REVERT_SCRIPT` path constant alongside the other script paths.

Include revert results in the Discord output if any reversion occurred:
```
⏪ **Reverted 1 rule change:** coll-docker — verification dropped 92% → 78%
```

### Files to modify
- Create `raindrop-categorize/scripts/revert-regression.py`
- Modify `raindrop-categorize/scripts/cron_run.py` — wire it in at the start
- Also update `auto-approve` (or the apply-proposals.py) to store snapshots

### Verification
Run `cd /Users/ashebanow/Development/ai/raindrop-skills/raindrop-categorize && timeout 15 python3 scripts/revert-regression.py 2>&1` to verify it runs without crashing (it will have nothing to revert initially).

Return a summary of the revert logic and how it integrates with the cron output.
