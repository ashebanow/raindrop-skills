# Cron Orchestration & Quality

> 29 nodes

## Key Concepts

- **cron_run.py** (20 connections) — `raindrop-categorize/scripts/cron_run.py`
- **main()** (15 connections) — `raindrop-categorize/scripts/cron_run.py`
- **prune_no_match()** (4 connections) — `raindrop-categorize/scripts/cron_run.py`
- **parse_process_output()** (4 connections) — `raindrop-categorize/scripts/cron_run.py`
- **compute_quality_record()** (4 connections) — `raindrop-categorize/scripts/cron_run.py`
- **oversized_collections()** (4 connections) — `raindrop-categorize/scripts/cron_run.py`
- **load_env()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **prune_audit_log()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **run_subprocess()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **quality_runs()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **quality_stats()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **latest_quality_record()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **append_quality_record()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **no_match_samples()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **new_tags_this_run()** (3 connections) — `raindrop-categorize/scripts/cron_run.py`
- **parse_scan_output()** (2 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Source RAINDROP_TOKEN from the project .env if not already set.** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Drop audit entries older than 7 days. Returns (kept, removed).** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Remove no-match entries whose bookmarks are no longer unsorted.      Checks each** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Run a subprocess and return (returncode, stdout, stderr).** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Parse the process-batch.py summary line for (tagged, deferred, compared, filler_** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Avg-per-raindrop scores from the most recent N runs (oldest first).** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Mean / median / stddev / trend over the recent runs.** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Return the most recent entry from quality.json, or None.** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- **Build a quality record for this cron run.      Reads state + rules to compute ba** (1 connections) — `raindrop-categorize/scripts/cron_run.py`
- *... and 4 more nodes in this community*

## Relationships

- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (2 shared connections)
- [Batch Processing & Classification](Batch_Processing_%26_Classification.md) (1 shared connections)
- [Rules & Regression Revert](Rules_%26_Regression_Revert.md) (1 shared connections)
- [Holdout Verification](Holdout_Verification.md) (1 shared connections)
- [Nix Bookmark Classifier](Nix_Bookmark_Classifier.md) (1 shared connections)
- [Gemini AI Classifier](Gemini_AI_Classifier.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/cron_run.py`

## Audit Trail

- EXTRACTED: 92 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*