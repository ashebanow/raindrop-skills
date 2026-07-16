# Holdout Verification

> 10 nodes

## Key Concepts

- **verify-holdout.py** (7 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **compute_verification()** (5 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **find_collection()** (3 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **infer_tags()** (3 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **append_verification_to_quality()** (3 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **main()** (3 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **First-match-wins keyword lookup (mirrors process-batch.py).** (1 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **Infer tags from title + domain (mirrors run_pipeline.py tag_keywords logic).** (1 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **Run inference against all holdout entries and compute scores.** (1 connections) — `raindrop-categorize/scripts/verify-holdout.py`
- **Add verification scores to the most recent quality record.** (1 connections) — `raindrop-categorize/scripts/verify-holdout.py`

## Relationships

- [Cron Orchestration & Quality](Cron_Orchestration_%26_Quality.md) (1 shared connections)
- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/verify-holdout.py`

## Audit Trail

- EXTRACTED: 28 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*