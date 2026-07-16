# Graph Report - .  (2026-07-15)

## Corpus Check
- Corpus is ~47,669 words - fits in a single context window. You may not need a graph.

## Summary
- 352 nodes · 575 edges · 17 communities (16 shown, 1 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 43 edges (avg confidence: 0.8)
- Token cost: 37,733 input · 2,036 output

## Community Hubs (Navigation)
- Proposal Apply & Merge
- Batch Processing & Classification
- Scan Batch & Shared API
- Cron Orchestration & Quality
- Holdout Construction
- Nix Bookmark Classifier
- Rule Suggestion Engine
- Cache Testing
- Linter Core
- Rules & Regression Revert
- Gemini AI Classifier
- Pipeline Runner
- Holdout Verification
- Linter Cron Entry
- Deploy Script

## God Nodes (most connected - your core abstractions)
1. `process_comparison()` - 18 edges
2. `process_one()` - 16 edges
3. `main()` - 15 edges
4. `do_auto_approve()` - 13 edges
5. `do_apply_specific()` - 12 edges
6. `main()` - 12 edges
7. `main()` - 12 edges
8. `fetch_page_cached()` - 11 edges
9. `main()` - 10 edges
10. `api_get()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `do_apply_merge_collection()` --calls--> `fetch_all_raindrops()`  [INFERRED]
  raindrop-categorize/scripts/apply-proposals.py → shared/raindrop_common.py
- `process_comparison()` --calls--> `fetch_page_cached()`  [INFERRED]
  raindrop-categorize/scripts/process-batch.py → shared/raindrop_common.py
- `process_one()` --calls--> `fetch_page_cached()`  [INFERRED]
  raindrop-categorize/scripts/process-batch.py → shared/raindrop_common.py
- `main()` --calls--> `fetch_page_cached()`  [INFERRED]
  raindrop-categorize/scripts/process-batch.py → shared/raindrop_common.py
- `main()` --calls--> `start_fetcher_pool()`  [INFERRED]
  raindrop-categorize/scripts/process-batch.py → shared/raindrop_common.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Categorization Self-Improvement Loop** — raindrop_categorize_scripts_process_batch, raindrop_categorize_scripts_suggest_rules, raindrop_categorize_scripts_apply_proposals, raindrop_categorize_scripts_verify_holdout, raindrop_categorize_scripts_revert_regression, raindrop_categorize_references_raindrop_rules [EXTRACTED 1.00]
- **Raindrop Quality Scoring System** — shared_raindrop_common, raindrop_categorize_scripts_process_batch, raindrop_categorize_scripts_cron_run [EXTRACTED 0.90]

## Communities (17 total, 1 thin omitted)

### Community 0 - "Proposal Apply & Merge"
Cohesion: 0.07
Nodes (49): apply_proposal(), audit_log(), check_auto_approval(), check_collection_size(), check_holdout_regression(), do_apply_merge_collection(), do_apply_move_collection(), do_apply_specific() (+41 more)

### Community 1 - "Batch Processing & Classification"
Cohesion: 0.09
Nodes (42): add_to_no_match(), build_note_from_content(), _classify_bookmark(), compare_assignments(), detect_note_template(), find_collection(), infer_note(), infer_real_tags() (+34 more)

### Community 2 - "Scan Batch & Shared API"
Cohesion: 0.06
Nodes (38): main(), api(), GET the given API path with retries and exponential backoff.      Delegates to t, api(), api_delete(), api_get(), api_post(), api_put() (+30 more)

### Community 3 - "Cron Orchestration & Quality"
Cohesion: 0.11
Nodes (28): append_quality_record(), compute_quality_record(), latest_quality_record(), load_env(), main(), new_tags_this_run(), no_match_samples(), oversized_collections() (+20 more)

### Community 4 - "Holdout Construction"
Cohesion: 0.12
Nodes (22): clear_line(), fetch_all_bookmarks(), fetch_collections(), find_collections_matching_name(), get_key(), infer_tags(), keyword_match_collections(), load_holdout() (+14 more)

### Community 5 - "Nix Bookmark Classifier"
Cohesion: 0.13
Nodes (21): classify(), fetch_nix_bookmarks(), main(), move_bookmark(), Fetch all bookmarks directly under Nix (not in subcollections)., Move a single bookmark to a target collection. Returns True on success., Return the subcollection name for a bookmark.      Priority: Nix Language > Nix, api_get() (+13 more)

### Community 6 - "Rule Suggestion Engine"
Cohesion: 0.12
Nodes (23): Counter, domain_clustering(), extract_domain(), extract_url(), fetch_collections(), keyword_clustering(), load_confidence_domain_suggestions(), load_no_match() (+15 more)

### Community 7 - "Cache Testing"
Cohesion: 0.16
Nodes (22): main(), Background fetcher pool populates the cache., Empty URL list doesn't crash the pool starter., Processing loop never blocks on background pool (fetch on miss)., Run process-batch.py --dry-run --limit 3 against actual state.      Validates th, fetch_page_cached returns cached content without calling fetch., fetch_page_cached falls through to fetch on cache miss., fetch_page_cached caches None results (dead URLs aren't retried). (+14 more)

### Community 8 - "Linter Core"
Cohesion: 0.14
Nodes (21): build_duplicates_report(), check_url_live(), format_kanban_card(), is_malformed_url(), load_state(), main(), near_normalize(), normalize_url() (+13 more)

### Community 9 - "Rules & Regression Revert"
Cohesion: 0.16
Nodes (20): Raindrop Rules JSON, get_current_verification(), get_rule_title(), load_proposals(), load_rules(), log(), main(), mark_proposal_rejected() (+12 more)

### Community 10 - "Gemini AI Classifier"
Cohesion: 0.20
Nodes (13): Path, _build_classification_prompt(), _build_taxonomy_text(), _call_gemini(), classify_bookmark(), load_gemini_key(), _parse_response(), Build the taxonomy portion of the prompt: hierarchical collections + tags. (+5 more)

### Community 11 - "Pipeline Runner"
Cohesion: 0.18
Nodes (6): load_quality(), paginate_raindrops(), prune_audit_log(), Fetch all raindrops in a collection with pagination., Remove entries older than 7 days., Load quality scores from cache.

### Community 12 - "Holdout Verification"
Cohesion: 0.29
Nodes (9): append_verification_to_quality(), compute_verification(), find_collection(), infer_tags(), main(), Add verification scores to the most recent quality record., First-match-wins keyword lookup (mirrors process-batch.py)., Infer tags from title + domain (mirrors run_pipeline.py tag_keywords logic). (+1 more)

### Community 13 - "Linter Cron Entry"
Cohesion: 0.29
Nodes (7): main(), parse_dup_line(), parse_malformed_line(), Run a subprocess and return (returncode, stdout, stderr)., Parse a line like '  Exact duplicates: 3 groups' into metrics., Parse '  Malformed URLs:   5, run_subprocess()

## Knowledge Gaps
- **1 isolated node(s):** `deploy-skills.sh script`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `api_get()` connect `Nix Bookmark Classifier` to `Proposal Apply & Merge`, `Cron Orchestration & Quality`, `Holdout Construction`, `Rule Suggestion Engine`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `fetch_page_cached()` connect `Cache Testing` to `Batch Processing & Classification`, `Scan Batch & Shared API`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `Raindrop Rules JSON` connect `Rules & Regression Revert` to `Proposal Apply & Merge`, `Batch Processing & Classification`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `process_comparison()` (e.g. with `compute_precision_score()` and `fetch_page_cached()`) actually correct?**
  _`process_comparison()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `process_one()` (e.g. with `compute_precision_score()` and `fetch_page_cached()`) actually correct?**
  _`process_one()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deploy-skills.sh script` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Proposal Apply & Merge` be split into smaller, more focused modules?**
  _Cohesion score 0.06693877551020408 - nodes in this community are weakly interconnected._