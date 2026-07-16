# Scan Batch & Shared API

> 41 nodes

## Key Concepts

- **raindrop_common.py** (37 connections) — `shared/raindrop_common.py`
- **api()** (7 connections) — `shared/raindrop_common.py`
- **fetch_all_raindrops()** (6 connections) — `shared/raindrop_common.py`
- **api_get()** (4 connections) — `shared/raindrop_common.py`
- **compute_per_collection_metrics()** (4 connections) — `shared/raindrop_common.py`
- **_domain_cache_path()** (4 connections) — `shared/raindrop_common.py`
- **save_domain_fingerprint()** (4 connections) — `shared/raindrop_common.py`
- **fetch_page_content()** (4 connections) — `shared/raindrop_common.py`
- **main()** (3 connections) — `raindrop-categorize/scripts/clear-tracking-tags.py`
- **scan-batch.py** (3 connections) — `raindrop-categorize/scripts/scan-batch.py`
- **get_token()** (3 connections) — `shared/raindrop_common.py`
- **api_put()** (3 connections) — `shared/raindrop_common.py`
- **api_post()** (3 connections) — `shared/raindrop_common.py`
- **api_delete()** (3 connections) — `shared/raindrop_common.py`
- **detect_note_template()** (3 connections) — `shared/raindrop_common.py`
- **compute_tone_score()** (3 connections) — `shared/raindrop_common.py`
- **_build_root_tree()** (3 connections) — `shared/raindrop_common.py`
- **_collect_descendants()** (3 connections) — `shared/raindrop_common.py`
- **should_fetch_url()** (3 connections) — `shared/raindrop_common.py`
- **clear-tracking-tags.py** (2 connections) — `raindrop-categorize/scripts/clear-tracking-tags.py`
- **api()** (2 connections) — `raindrop-categorize/scripts/scan-batch.py`
- **load_rules()** (2 connections) — `shared/raindrop_common.py`
- **GET the given API path with retries and exponential backoff.      Delegates to t** (1 connections) — `raindrop-categorize/scripts/scan-batch.py`
- **Shared Raindrop.io utilities for raindrop-categorize and raindrop-linter.  Usage** (1 connections) — `shared/raindrop_common.py`
- **Return RAINDROP_TOKEN or print error and exit.** (1 connections) — `shared/raindrop_common.py`
- *... and 16 more nodes in this community*

## Relationships

- [Batch Processing & Classification](Batch_Processing_%26_Classification.md) (7 shared connections)
- [Cache Testing](Cache_Testing.md) (4 shared connections)
- [Nix Bookmark Classifier](Nix_Bookmark_Classifier.md) (3 shared connections)
- [Cron Orchestration & Quality](Cron_Orchestration_%26_Quality.md) (2 shared connections)
- [Proposal Apply & Merge](Proposal_Apply_%26_Merge.md) (2 shared connections)
- [Linter Core](Linter_Core.md) (2 shared connections)
- [Holdout Construction](Holdout_Construction.md) (1 shared connections)
- [Pipeline Runner](Pipeline_Runner.md) (1 shared connections)
- [Rule Suggestion Engine](Rule_Suggestion_Engine.md) (1 shared connections)
- [Holdout Verification](Holdout_Verification.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/clear-tracking-tags.py`
- `raindrop-categorize/scripts/scan-batch.py`
- `shared/raindrop_common.py`

## Audit Trail

- EXTRACTED: 123 (96%)
- INFERRED: 5 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*