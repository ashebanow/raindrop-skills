---
name: tone-scorer
description: Implement template-penalized tone scoring and per-collection metrics for raindrop-categorize
---

You are implementing Phase 2b of the raindrop-categorize self-improvement plan.

## Context

The project is at /Users/ashebanow/Development/ai/raindrop-skills. The rules file is at `raindrop-categorize/references/raindrop-rules.json`. The main processing script is `raindrop-categorize/scripts/process-batch.py` and the interactive pipeline is `raindrop-categorize/scripts/run_pipeline.py`. The quality cache is at `~/.hermes/cache/raindrop-quality.json`.

## Task

Replace the hardcoded tone score and implement per-collection quality metrics as described in SKILL.md.

### Current state

In `run_pipeline.py`, tone is hardcoded:
```python
# Tone: always 7 (passable — automated)
tone = 7
```

Per-collection metrics from SKILL.md (Breadth ratio, Sub-collection balance, Untagged %) are not implemented at all.

### What to build

#### 1. Template-penalized tone scorer

Create a function `compute_tone_score(note_text, note_templates)` that:
- Reads the `note_templates` from the rules file (already in `raindrop-rules.json`)
- Checks if the note matches each template using `detect_note_template()` (already exists in `process-batch.py` — move it to shared or duplicate it)
- Score decreases for each matched template:

| Condition | Score |
|---|---|
| No template detected (unique/descriptive note) | 9 |
| Matches 1 domain-specific template (e.g., "Git repository: ...") | 7 |
| Matches generic "Bookmark: ..." template | 4 |
| Empty note | 0 |

The `detect_note_template()` function from `process-batch.py` does most of this already. Extract it into `shared/raindrop_common.py`.

#### 2. Per-collection metrics

Create a function `compute_per_collection_metrics(state_data, collection_keywords)` that computes:

| Metric | Formula | What it signals |
|---|---|---|
| Completeness % | % of bookmarks in each root collection subtree that have all 3 fields (collection, tags, note) | How well-categorised that topic area is |
| Breadth ratio | `bookmark_count / ideal_max(25)` | Collection may need sub-collections |
| Untagged % | % of bookmarks with empty `tags` in this subtree | Is tagging being neglected? |

Input is the scan state from `~/.hermes/cache/raindrop-state.json` (which has `collections` dict with title/parent/count, and `final_list` with bookmarks).

Output is a dict like:
```python
{
  "collections_touched": 28,
  "breadth_flagged": ["NixOS (257)", "Shopping (65)"],
  "untagged_pct_avg": 0.03,
  "completeness_pct_avg": 0.95
}
```

#### 3. Where to put it

Add both functions to `shared/raindrop_common.py` so both pipelines can use them.

In `run_pipeline.py`: Replace the hardcoded `tone = 7` with a call to `compute_tone_score()`. Add the per-collection metrics to the quality run record.

### Files to modify

- `shared/raindrop_common.py` — add `compute_tone_score()`, `compute_per_collection_metrics()`, and `detect_note_template()`
- `raindrop-categorize/scripts/run_pipeline.py` — use new scoring functions

### Verification

Run `cd /Users/ashebanow/Development/ai/raindrop-skills/raindrop-categorize && timeout 10 python3 scripts/process-batch.py --dry-run 2>&1 | head -10` to verify no breakage.

Return a structured summary: files changed, lines added/removed, and what tone scores a sample of notes would get.
