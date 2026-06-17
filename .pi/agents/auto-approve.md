---
name: auto-approve
description: Implement proposal auto-approval logic for raindrop-categorize Phase 4
---

You are implementing Phase 4a+4b — proposal accumulation and auto-approval.

## Context

Project root: /Users/ashebanow/Development/ai/raindrop-skills
Rules file: raindrop-categorize/references/raindrop-rules.json
Proposals file: ~/.hermes/cache/raindrop-proposals.json
Confidence file: ~/.hermes/cache/raindrop-confidence.json
No-match file: ~/.hermes/cache/raindrop-no-match.json
Shared module: shared/raindrop_common.py
Holdout: ~/.hermes/cache/raindrop-holdout.json

## Task

Create `scripts/apply-proposals.py` that:

### Mode 1: `--auto-approve`
Reads all pending proposals, checks auto-approval criteria, applies qualifying ones.

Auto-approval criteria (ALL must be true):
1. Proposal type is `add_keyword` (adding keywords to an existing rule)
2. Evidence comes from ≥5 no-match bookmarks sharing the same domain (no_match_cluster_size >= 5)
3. The target collection has ≥20 existing bookmarks (query from Raindrop API)
4. No holdout regression was detected in the last 3 quality records

Approved proposals get applied to `raindrop-rules.json`:
- Find the rule by `rule_id` in `collection_keywords`
- Add `change.add_keywords` to the rule's `keywords` list (dedup)
- Bump `version` and update `last_updated`
- Reset affected rule's confidence stats
- Move proposal status to "auto_approved"

After applying, run `verify-holdout.py --json` to get a baseline score.
Log the change in the audit log.

### Mode 2: `apply <proposal_id>`
Apply a specific proposal regardless of auto-approval criteria (for user-initiated approvals).

Same merge logic as auto-approve.

### Mode 3: `--dry-run`
Show what would be auto-approved without applying anything.

### Evidence sources
- Read `raindrop-proposals.json` for pending proposals
- Read `raindrop-confidence.json` for per-rule confidence stats (to verify the target rule exists and has hits)
- Read holdout via `verify-holdout.py --json` for regression detection
- Fetch collections from Raindrop API via shared `api_get("/collections")` to check bookmark counts

### Files to modify
- Create `raindrop-categorize/scripts/apply-proposals.py`
- The script should work independently — import from shared module

### Verification
Run `cd /Users/ashebanow/Development/ai/raindrop-skills/raindrop-categorize && timeout 15 python3 scripts/apply-proposals.py --dry-run 2>&1` to verify it runs without crashing.

Return a summary of the script structure, auto-approval criteria, and what the dry-run output shows.
