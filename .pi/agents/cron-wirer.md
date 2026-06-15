---
name: cron-wirer
description: Wire quality scoring into the cron orchestrator path
---

You are implementing Phase 2c of the raindrop-categorize self-improvement plan.

## Context

The project is at /Users/ashebanow/Development/ai/raindrop-skills. The cron orchestrator is at `raindrop-categorize/scripts/cron_run.py`. The quality cache is at `~/.hermes/cache/raindrop-quality.json`. The shared module is at `shared/raindrop_common.py`. The scan state is at `~/.hermes/cache/raindrop-state.json`.

## Task

Wire quality scoring into the cron path so that every cron run writes a quality record to `~/.hermes/cache/raindrop-quality.json`.

### Current state

`cron_run.py` reads `quality.json` for display in its Discord summary but **never writes** to it. Quality records are only created when someone runs `run_pipeline.py` interactively. This means:
- Trend detection ("if dropping for 2+ consecutive runs, halt") never triggers
- The Discord output shows stale quality data
- There's no way to track quality changes over time

### What to build

After the process step completes (line ~343 in cron_run.py, right after the `proc_rc, proc_out, proc_err = run_subprocess(...)` call), add a scoring phase that:

1. **Read the state file**: `~/.hermes/cache/raindrop-state.json` has `collections` and `final_list` data.
2. **Read the rules file**: Use the shared `_load_rules()` function (already imported).
3. **Compute batch-level scores**:
   - Count how many bookmarks in `final_list` have `_categorized-v2` tag (were already processed) vs new
   - Count how many have empty tags, empty notes
   - Compute a simplicity score based on the output of `process-batch.py` (parse the result line for comparison stats)
4. **Compute per-collection scores**: Read the collection tree from state to identify oversized collections
5. **Append to quality.json**: Write a new record with run_id, timestamp, batch_size, tagged/deferred/compared counts, and the computed scores.

### Quality record format

Append an entry to the array in `quality.json`:

```json
{
  "run_id": "20260614-103000",
  "timestamp": "2026-06-14T10:30:00.123456+00:00",
  "pipeline": "cron",
  "batch_size": 100,
  "filler_count": 15,
  "success_rate_pct": 100,
  "global": {
    "avg_per_raindrop": null,
    "completeness_pct": 98,
    "tagged_pct_delta": "+85pp",
    "note_pct_delta": "+45pp",
    "compared_count": 15,
    "compared_improvements": 3,
    "compared_regressions": 0
  },
  "per_collection": {
    "collections_touched": 28,
    "breadth_flagged": ["NixOS (257)", "Shopping (65)"],
    "untagged_pct_avg": 0.03
  },
  "elapsed_s": 205
}
```

Note: `avg_per_raindrop` can be `null` for cron runs since we don't have the detailed per-bookmark scoring yet (that requires the precision/tone scorers from 2a/2b, which may or may not be done yet). The cron scoring should work independently — fill in what's available, leave `null` for what's not.

### Also update the Discord output

In the `**Quality**` line of the Discord output, when the latest record is from a cron run, include batch stats (tagged vs compared vs deferred) alongside the trend. Currently it just shows:

```
**Quality (last N runs):** mean X / median Y / stddev Z (trend, n=N, last L)
```

Add something like:
```
**Quality (last N runs):** mean X / median Y (trend) — batch: 85 tagged, 15 compared (3 improved)
```

### Files to modify

- `raindrop-categorize/scripts/cron_run.py` — add scoring phase, update quality output

### Verification

Run `cd /Users/ashebanow/Development/ai/raindrop-skills && timeout 10 python3 -c "
import json
data = json.load(open('/Users/ashebanow/.hermes/cache/raindrop-quality.json'))
print(f'Current records: {len(data) if isinstance(data, list) else len(data.get(\"runs\",[]))}')
"` to check quality file state before and after.

Return a structured summary: the changes made to cron_run.py, how quality records now get written, and what the Discord output format looks like after your changes.
