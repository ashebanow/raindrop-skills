---
name: precision-scorer
description: Implement keyword-overlap precision scoring for raindrop-categorize
---

You are implementing Phase 2a of the raindrop-categorize self-improvement plan.

## Context

The project is at /Users/ashebanow/Development/ai/raindrop-skills. The rules file is at `raindrop-categorize/references/raindrop-rules.json`. The main processing script is `raindrop-categorize/scripts/process-batch.py`. The interactive pipeline is `raindrop-categorize/scripts/run_pipeline.py`. The shared utilities module is at `shared/raindrop_common.py`.

## Task

Replace the current relevance scoring formula with a keyword-overlap precision scorer.

### Current state

In `process-batch.py`, there is no quality scoring at all — it only processes bookmarks. Quality scoring was previously done in `run_pipeline.py` using a formulaic approach:

```python
# Relevance: based on fields changed
fc = set(rd_data["fields_changed"])
if "collection" in fc and "tags" in fc:
    relevance = 8
elif "collection" in fc or "tags" in fc:
    relevance = 7
else:
    relevance = 5
```

This doesn't measure actual quality — it measures how many fields were modified.

### What to build

Create a function `compute_precision_score(title, domain, url, assigned_collection_id, assigned_tags, rules_data)` that:

1. **Collection precision**: Check if the assigned collection's name (or its keywords from `collection_keywords` in the rules file) appears in the bookmark's title, domain, or URL.
   - If any keyword from the matching rule appears → score 1.0 for collection
   - If the collection name appears in the title → score 0.8
   - If the domain is a known fit (e.g., `github.com` → Programming) → score 0.6
   - Otherwise → score 0.0

2. **Tag precision**: For each assigned tag, check if the tag name or its keywords (from `tag_keywords` in the rules file) appear in the title/domain/URL.
   - `precision = matching_tags / total_tags`
   - If no tags assigned, score 0.0

3. **Combined score**: `(collection_precision * 0.5 + tag_precision * 0.5) * 10` mapped to 0-10 scale

### Where to put it

Add the function to `shared/raindrop_common.py` so both `process-batch.py` and `run_pipeline.py` can import it. Then:

1. In `process-batch.py`: After each bookmark is processed (in both `process_one` and `process_comparison`), compute the precision score and include it in the audit log entry under a new field `"precision_score"`.

2. In `run_pipeline.py`: Replace the hardcoded relevance scoring with a call to `compute_precision_score()`. Read the rules data from the shared `_load_rules()` function (which it already imports).

### Files to modify

- `shared/raindrop_common.py` — add `compute_precision_score()`
- `raindrop-categorize/scripts/process-batch.py` — add precision logging
- `raindrop-categorize/scripts/run_pipeline.py` — use precision in scoring

### Verification

Run `cd /Users/ashebanow/Development/ai/raindrop-skills/raindrop-categorize && timeout 10 python3 scripts/process-batch.py --dry-run 2>&1 | head -10` to verify the script still works after your changes.

Return a structured summary: files changed, lines added/removed, and a sample precision score for a bookmark from the dry-run output.
