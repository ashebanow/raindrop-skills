# Batch Processing & Classification

> 43 nodes

## Key Concepts

- **process-batch.py** (25 connections) — `raindrop-categorize/scripts/process-batch.py`
- **process_comparison()** (18 connections) — `raindrop-categorize/scripts/process-batch.py`
- **process_one()** (16 connections) — `raindrop-categorize/scripts/process-batch.py`
- **main()** (12 connections) — `raindrop-categorize/scripts/process-batch.py`
- **update_domain_fingerprint()** (7 connections) — `shared/raindrop_common.py`
- **query_domain_fingerprint()** (6 connections) — `shared/raindrop_common.py`
- **infer_real_tags()** (5 connections) — `raindrop-categorize/scripts/process-batch.py`
- **build_note_from_content()** (5 connections) — `raindrop-categorize/scripts/process-batch.py`
- **find_collection()** (5 connections) — `raindrop-categorize/scripts/process-batch.py`
- **update_rule_stats()** (5 connections) — `raindrop-categorize/scripts/process-batch.py`
- **compare_assignments()** (5 connections) — `raindrop-categorize/scripts/process-batch.py`
- **_try_gemini_classification()** (5 connections) — `raindrop-categorize/scripts/process-batch.py`
- **load_domain_fingerprint()** (5 connections) — `shared/raindrop_common.py`
- **infer_note()** (4 connections) — `raindrop-categorize/scripts/process-batch.py`
- **_is_handwritten()** (4 connections) — `raindrop-categorize/scripts/process-batch.py`
- **compute_precision_score()** (4 connections) — `shared/raindrop_common.py`
- **log_entry()** (3 connections) — `raindrop-categorize/scripts/process-batch.py`
- **add_to_no_match()** (3 connections) — `raindrop-categorize/scripts/process-batch.py`
- **load_confidence()** (3 connections) — `raindrop-categorize/scripts/process-batch.py`
- **_rule_key_for_collection()** (3 connections) — `raindrop-categorize/scripts/process-batch.py`
- **detect_note_template()** (3 connections) — `raindrop-categorize/scripts/process-batch.py`
- **jaccard_similarity()** (3 connections) — `raindrop-categorize/scripts/process-batch.py`
- **_classify_bookmark()** (2 connections) — `raindrop-categorize/scripts/process-batch.py`
- **save_confidence()** (2 connections) — `raindrop-categorize/scripts/process-batch.py`
- **load_state()** (2 connections) — `raindrop-categorize/scripts/process-batch.py`
- *... and 18 more nodes in this community*

## Relationships

- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (7 shared connections)
- [Cache Testing](Cache_Testing.md) (4 shared connections)
- [Cron Orchestration & Quality](Cron_Orchestration_%26_Quality.md) (1 shared connections)
- [Gemini AI Classifier](Gemini_AI_Classifier.md) (1 shared connections)
- [Rules & Regression Revert](Rules_%26_Regression_Revert.md) (1 shared connections)
- [Nix Bookmark Classifier](Nix_Bookmark_Classifier.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/process-batch.py`
- `shared/raindrop_common.py`

## Audit Trail

- EXTRACTED: 152 (88%)
- INFERRED: 21 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*