# Pipeline Runner

> 11 nodes

## Key Concepts

- **run_pipeline.py** (8 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **paginate_raindrops()** (2 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **prune_audit_log()** (2 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **load_quality()** (2 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **log_audit()** (1 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **save_quality()** (1 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **load_no_match()** (1 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **save_no_match()** (1 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **Fetch all raindrops in a collection with pagination.** (1 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **Remove entries older than 7 days.** (1 connections) — `raindrop-categorize/scripts/run_pipeline.py`
- **Load quality scores from cache.** (1 connections) — `raindrop-categorize/scripts/run_pipeline.py`

## Relationships

- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/run_pipeline.py`

## Audit Trail

- EXTRACTED: 21 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*