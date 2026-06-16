# Raindrop Categorize — Self-Improvement Plan

## Progress (June 2026)

| Phase | Description | Status | Key deliverables |
|---|---|---|---|
| **0** | Consolidate rules into single JSON file + shared module | ✅ Complete | `references/raindrop-rules.json`, `shared/raindrop_common.py`. All 5 scripts updated to read from rules file and import from shared module. |
| **1a** | Activate filler queue (remove early skip) | ✅ Complete | `process-batch.py`: filler queue bookmarks now go through `process_comparison()` instead of skipping. |
| **1b** | Comparison logic (old vs new) | ✅ Complete | `compare_assignments()` scores collection stability, tag Jaccard similarity, note template improvement, note length delta. Only applies API writes on "better" verdict. |
| **1c** | Per-rule confidence tracking | ✅ Complete | `update_rule_stats()` in `process-batch.py`. Confidence file at `~/.hermes/cache/raindrop-confidence.json`. Weighted confidence = (agreements×1.0 + improvements×0.8) / total filler. Also tracks by-domain stats. |
| **1d** | No-match clustering + rule suggestions | ✅ Complete | `scripts/suggest-rules.py` clusters no-match backlog by domain and keyword, fetches live collections, proposes keyword additions. Wired into cron orchestrator. Output at `~/.hermes/cache/raindrop-proposals.json`. |
| **2a** | Keyword-overlap precision scorer | ✅ Complete | `compute_precision_score()` in `shared/raindrop_common.py`. Used in both `process-batch.py` (audit log) and `run_pipeline.py` (Phase 4 scoring). Replaced fields-changed heuristic with actual keyword overlap check. |
| **2b** | Template-penalized tone scorer + per-collection metrics | ✅ Complete | `compute_tone_score()` replaces hardcoded tone=7 (0/4/7/9 scale). `compute_per_collection_metrics()` implements breadth flags, completeness %, untagged % from SKILL.md. Both in `shared/raindrop_common.py`. `detect_note_template()` extracted from process-batch.py into shared module. |
| **2c** | Wire scoring into cron path | ✅ Complete | `cron_run.py` writes quality record after every run. Extended `parse_process_output()` for compared/filler counts. `compute_quality_record()` + `append_quality_record()` functions. Discord output now shows batch stats alongside trend. |
| **3a** | Holdout builder script | ✅ Complete | `scripts/build-holdout.py` — interactive CLI with single-key input, progress bar, resume support, alternatives from keyword matching, fuzzy collection search. |
| **3b** | Verification script | ✅ Complete | `scripts/verify-holdout.py` — re-runs inference against holdout, computes collection accuracy + tag precision/recall/F1. Wired into cron orchestrator. |
| **3c** | User curation | ⏳ **Your turn** | Run `python3 scripts/build-holdout.py` to confirm ~100 bookmarks. Resume any time. Includes tag review step — inferred tags shown alongside existing, toggle with number keys. |
| **3d** | Tag holdout flow | 📝 Planned | Future: separate tag-only verification pass. Inferred tags can be compared against confirmed tags to compute tag precision/recall independently of collection accuracy. |
| **5a** | Fetch URL content in cron path | ✅ Complete | `fetch_page_content()` in shared module. `build_note_from_content()` for real notes. `rich_text` parameter on `infer_real_tags()` and `find_collection()`. `SKIP_FETCH_DOMAINS` blacklist. |
| **5b** | Domain fingerprint cache | ✅ Complete | Domain-keyed word frequencies, tag/collection consensus. `load/save/update/query_domain_fingerprint()` in shared module. Wired into both process paths. After ~5 pages per domain, cached signals supplement keyword inference. |
| **5c** | Frequency-weighted tag scoring | ✅ Complete | `infer_real_tags()` uses `MIN_OCCURRENCES=2` on rich text: counts keyword occurrences across page body, only suggests tags exceeding threshold. Falls back to binary matching when no page content. |
| **5d** | Collection from page content | ✅ Complete | `find_collection()` uses frequency scoring on rich text: scores all 16 collection rules by total keyword occurrences, title matches get 2x bonus, minimum score of 2. Falls back to first-match-wins when no page content. |
| **5e** | Domain blacklist | ✅ Complete | Inline in `should_fetch_url()`. Wikipedia, GitHub, Reddit, YouTube, Discord, Twitter, Instagram, Facebook, TikTok — skipped for both fetching and fingerprint accumulation. |
| **4** | Rule proposal lifecycle | ⏳ Pending | Auto-approval, merge workflow, kanban integration, safety-valve auto-revert. |

## Status Quo (June 2026)

The skill has a quality scoring system that produces very little variance (scores range 7.5–8.0) and drives no actual behavioral change in the pipeline. This document outlines the root causes and a phased plan to turn it into a genuine self-improvement loop.

### Root Causes

**1. The quality score measures API success, not categorization quality**

| Axis | What it actually measures | Score range |
|---|---|---|
| Completeness | "Did the PUT succeed?" | Always 9–10 |
| Succinctness | Note character length buckets | Always 7 (300–500 chars) |
| Tone | Hardcoded constant | Always 7±1 |
| Relevance | "How many fields changed?" not "Were they correct?" | Always 7–8 |

Every run converges to 7.5–8.0 regardless of whether assignments were good or bad. The score is a proxy for API reachability, not categorization quality.

**2. The cron path never writes quality records**

`cron_run.py` reads `quality.json` for display but never appends to it. `process-batch.py` doesn't write quality either. The trend detection ("if dropping for 2+ consecutive runs, halt") never triggers because the cron path adds no new records. The five records in `quality.json` are all from interactive runs on June 10–11.

**3. No feedback loop exists**

Even if the score had variance, nothing changes as a result:
- `COLLECTION_KEYWORD_MAP` is hardcoded in `process-batch.py`
- `tag_keywords` is hardcoded in `run_pipeline.py`
- `TAG_RULES` is loaded from a markdown file but never written to
- The no-match backlog grows but never teaches the system anything
- The "Model Self-Reflection" loop described in SKILL.md has no implementation

**4. The filler queue is dead code**

`process-batch.py` immediately skips any bookmark with `_categorized-v2`, meaning the entire filler queue collected by `scan-batch.py` is never processed. The re-processing feature described in SKILL.md does not execute.

**5. Two rule implementations diverge**

`COLLECTION_KEYWORD_MAP` in `process-batch.py` and the keyword-scoring logic in `run_pipeline.py` are completely different implementations that can produce different results for the same bookmark. There is no single source of truth for categorization rules.

---

## Strategy: The Complete Self-Improvement Loop

```
  ┌──────────────────────────────────────────────────────────────┐
  │                     rules.json                               │
  │  (collection keywords, tag rules, templates, thresholds)     │
  └─────────┬─────────────────────────────────────┬──────────────┘
            │ 1. reads                             │ 5. writes proposals
            ▼                                      │
  ┌──────────────────┐     ┌──────────────────┐    │
  │  Process batch   │────→│  Filler queue    │────┘
  │  (uses rules)    │     │  comparison      │
  └──────────────────┘     │  (old vs new)     │
          │                └────────┬─────────┘
          ▼                         │ per-rule confidence
  ┌──────────────────┐              ▼
  │  Quality scoring │────→ ┌──────────────────┐
  │  (real metrics)  │      │  Rule confidence │
  └────────┬─────────┘      │  stats           │
           │                └────────┬─────────┘
           ▼                         │
  ┌──────────────────┐              │
  │  Holdout set     │              │
  │  verification    │──────────────┘
  └────────┬─────────┘              │
           ▼                        ▼
  ┌────────────────────────────────────────────┐
  │  Proposed changes.json                     │
  │  (auto-suggested rule updates)             │
  │  → user approves → merged into rules.json  │
  └────────────────────────────────────────────┘
```

The loop has three kinds of feedback:
- **Relative improvement** — filler queue comparison (old assignment vs new inference)
- **Absolute accuracy** — holdout set verification (inference vs confirmed ground truth)
- **Keyword confidence** — per-rule consistency statistics built from both sources

All three feed into proposed rule changes. The rules file is the **single actuator** — the only place changes need to happen to improve behavior.

---

## Phase 0 — Consolidate into a Single Rules File

**Goal:** Eliminate the dual implementation problem and establish the rules file as the single source of truth.

### Actions

**0a. Create `references/raindrop-rules.json`**

A JSON file containing all configurable parameters:

```jsonc
{
  "version": 1,
  "collection_keywords": [
    // Each entry: keywords → collection
    { "id": "coll-nixos", "keywords": ["nix", "nixos", "nixpkgs", "home-manager", "nix-darwin"],
      "collection_id": 70857518, "collection_title": "NixOS",
      "weight": 1.0,
      "created": "2026-06-01", "last_modified": "2026-06-01",
      "stats": { "hits": 0, "matches": 0, "confidence": null }
    },
    // ... all existing collection keyword rules
  ],
  "tag_rules": [
    // Regex → tag name (from current tag-mapping.md)
    { "id": "tag-linux", "pattern": "(?i)\\blinux\\b", "tag": "linux", "weight": 1.0, ... }
  ],
  "note_templates": [
    // Content patterns → template names (used for tone scoring)
    { "pattern": "^Git repository:", "template": "git_repo", "tone_penalty": 2 },
    { "pattern": "^Bookmark:", "template": "generic", "tone_penalty": 3 },
    { "pattern": "^Video:", "template": "video", "tone_penalty": 2 },
    { "pattern": "^Reddit post:", "template": "reddit", "tone_penalty": 2 },
    { "pattern": "^npm package:", "template": "npm", "tone_penalty": 2 },
    { "pattern": "^Rust crate:", "template": "crates", "tone_penalty": 2 }
  ],
  "thresholds": {
    "tag_max_per_bookmark": 5,
    "collection_oversize_threshold": 25,
    "match_score_minimum": 10,      // minimum keyword overlap for interactive pipeline
    "no_match_cluster_min": 3,      // min bookmarks with same domain to suggest rule
    "confidence_auto_approve": 0.95, // auto-approve rules above this confidence
    "confidence_flag_review": 0.70   // flag rules below this confidence for deprecation
  },
  "metadata": {
    "created": "2026-06-14T00:00:00Z",
    "last_updated": "2026-06-14T00:00:00Z",
    "total_runs_with_data": 0
  }
}
```

**0b. Update `process-batch.py` to read from `raindrop-rules.json`**

- Replace the hardcoded `COLLECTION_KEYWORD_MAP` with a JSON loader
- Replace the hardcoded template patterns in `infer_note()` with patterns from the rules file
- Replace the hardcoded `max(tags) = 5` with the threshold from the rules file
- Keep `TAG_RULES` loading from `tag-mapping.md` for now (it's already a file), but migrate it into `raindrop-rules.json` in a follow-up

**0c. Update `run_pipeline.py` to read from `raindrop-rules.json`**

- Replace the hardcoded keyword-scoring logic with the rules file
- Now both paths use exactly the same rules

**0d. Update `cron_run.py` to read thresholds from `raindrop-rules.json`**

- `OVERSIZE_THRESHOLD` etc. come from the rules file

### Verification

- Dry-run both `process-batch.py --dry-run` and `run_pipeline.py` against a known set of bookmarks
- They must produce identical collection/tag assignments (modulo the different inference approaches)
- Update `references/tag-mapping.md` to note it's a human-readable view; the JSON file is authoritative

---

## Phase 1 — Filler Queue Comparison + Per-Rule Confidence Tracking

**Goal:** Activate the filler queue and make it a signal source for rule quality.

### Actions

**1a. Remove the early skip for tracking-tag bookmarks in `process-batch.py`**

```python
# Current (dead code):
if TRACKING_TAG in existing_tags:
    return "skipped"

# New: branch into comparison mode
if TRACKING_TAG in existing_tags:
    return process_comparison(bookmark)  # runs inference, compares, records stats
```

**1b. Implement comparison logic**

For each filler queue bookmark:

1. Run the full inference pipeline (as if the bookmark had no existing data)
2. Compare the inference result against the current stored values:

| Axis | Comparison | Signal |
|---|---|---|
| **Collection stability** | Inferred collection ID vs current collection ID | Match = consistent rules. Mismatch = either old assignment was wrong or rules changed |
| **Tag overlap** | Jaccard similarity of inferred tags vs current tags | High = stable. Low = drift |
| **Note template** | Does the new note use the same or fewer template patterns? | Fewer templates = more specific note |
| **Note length delta** | `len(new_note) - len(old_note)` | Large positive = getting verbose. Large negative = losing information. Small = stable |
| **Keyword overlap** | Do the assigned tags/collection keywords appear in the title/URL? | Computed the same way for both old and new — higher is better |

3. For each axis, record whether the new inference is "better," "worse," or "same" vs the old value
4. Update rule statistics in `raindrop-rules.json`:

```jsonc
{
  "id": "coll-nixos",
  "stats": {
    "hits": 150,          // total times this rule matched
    "matches": 142,       // times the matching collection was confirmed correct
    "confidence": 0.947,  // matches / hits (overall)
    "filler_agreements": 23,   // filler queue: old == new
    "filler_improvements": 5,  // filler queue: new was better
    "filler_regressions": 1,   // filler queue: new was worse
    "filler_confidence": 0.96, // filler queue agreement rate
    "last_matched": "2026-06-14T10:30:00Z"
  }
}
```

**1c. Create `references/raindrop-confidence.json`**

A separate file for statistics so the rules file stays clean and diff-able. The rules file records summary stats; this file holds the full per-match history (optional, bounded to last N entries per rule).

**1d. Auto-suggestions from no-match clustering**

After each run, cluster the no-match backlog by domain. If a domain appears ≥3 times (configurable via `no_match_cluster_min`), produce a suggested rule:

```jsonc
{
  "type": "suggest_keyword",
  "domain": "hub.docker.com",
  "sample_titles": ["Deploying with Compose", "Docker Swarm Guide", "Multi-stage Builds"],
  "suggested_keywords": ["docker", "container", "compose", "swarm"],
  "possible_collections": ["Docker", "Container"],
  "match_count": 3
}
```

These go into `references/raindrop-proposals.json` for user review.

---

## Phase 2 — Real Quality Scoring

**Goal:** Replace the formulaic pseudo-score with metrics that reflect actual categorization quality, and write quality records from every run.

### Actions

**2a. Implement keyword-overlap precision**

For each processed bookmark:

```
precision_score = how_many_assigned_keywords_actually_appear_in_title_or_url
                 / total_assigned_keywords
```

If a bookmark gets tags `["linux", "nixos"]` and the title is "Getting Started with NixOS" → precision = 1.0 (1 of 2 tags present: "nixos").
If title is "Top 10 JavaScript Frameworks" and tags are `["linux", "nixos", "docker"]` → precision = 0.0.

Same calculation for collection — does the collection name (or its keywords) appear in the bookmark content?

**2b. Implement template-penalized tone scoring**

Detect which (if any) template pattern the note matches. Score decreases for each matched template:

| Condition | Score |
|---|---|
| No template detected (unique/descriptive note) | 9 |
| Matches 1 template pattern | 7 |
| Matches 2+ template patterns | 5 |
| Matches generic "Bookmark:" template | 4 |
| Auto-generated boilerplate only | 3 |

This replaces the hardcoded `tone = 7` with a score that has real variance. A bookmark whose note says "NixOS flake for setting up a PostgreSQL dev environment with Hasura and automatic migrations" scores higher than one whose note says "Git repository: dotfiles."

**2c. Implement per-collection metrics (from SKILL.md)**

After all bookmarks are processed, compute:

| Metric | Formula | What it signals |
|---|---|---|
| **Completeness %** | % of bookmarks in each root collection subtree that have all 3 fields | How well-categorised that topic area is |
| **Breadth ratio** | `bookmark_count / ideal_max(25)` | Collection may need sub-collections |
| **Untagged %** | % of bookmarks with empty `tags` in this subtree | Is tagging being neglected here? |
| **Sub-collection balance** | stddev of child bookmark counts | Lopsided = one child dominates |
| **Rule confidence** | Mean of per-rule `confidence` across all rules used this run | Are the rules themselves reliable? |

**2d. Write quality from the cron path**

Add a scoring phase to `cron_run.py` that computes all the above and appends to `quality.json`:

```jsonc
{
  "run_id": "20260614-103000",
  "timestamp": "2026-06-14T10:30:00Z",
  "pipeline": "cron",
  "batch_size": 100,
  "per_raindrop": {
    "avg_precision": 0.82,
    "avg_tone": 6.8,
    "note_nontemplate_pct": 0.45
  },
  "per_collection": {
    "collections_used": 28,
    "breadth_flagged": ["NixOS (257)", "Shopping (65)"],
    "untagged_pct_avg": 0.03
  },
  "rule_stats": {
    "rules_used": 18,
    "avg_confidence": 0.92,
    "rules_below_threshold": [],
    "total_new_suggestions": 2
  },
  "global": {
    "avg_per_raindrop": 7.3,
    "completeness_pct": 98,
    "tagged_pct": 97,
    "verification_score": null  // filled in Phase 3
  }
}
```

**2e. Update trend detection**

The trend detection currently looks at the last 3 runs. Make it look at the last 10 runs and use the precision/tone/confidence sub-scores individually — not just the aggregate — so it can flag "precision is dropping even though tone is stable" (which means the system is getting more generic/template-y).

---

## Phase 3 — Verified Holdout Set

**Goal:** Measure absolute categorization accuracy against confirmed ground truth, complementing the relative-improvement signal from Phase 1.

### Actions

**3a. Create the holdout file**

`~/.hermes/cache/raindrop-holdout.json` — 100 bookmarks with confirmed-correct assignments:

```jsonc
[
  {
    "raindrop_id": 1751522131,
    "title": "logandonley/dotfiles",
    "domain": "github.com",
    "confirmed_collection_id": 70861622,
    "confirmed_collection_title": "Dotfiles & Config",
    "confirmed_tags": ["dotfiles", "chezmoi", "config"],
    "verified_by": "user",
    "verified_at": "2026-06-14T00:00:00Z",
    "exclude_from_filler": false
  }
]
```

Selection criteria:
- At least 2-3 bookmarks per major collection (spread across the taxonomy)
- Mix of domains: github, youtube, blogs, documentation, reddit, product pages
- Mix of "easy" (obvious keyword match) and "edge case" (multi-topic, jargon-light titles)
- Exclude any bookmark the user intends to re-categorize later

**3b. Compute verification score after each run**

After every cron run and every interactive run:

1. For each holdout bookmark, run inference (ignoring existing data)
2. Compare against the confirmed values
3. Compute:

| Metric | Formula |
|---|---|
| **Collection accuracy** | % of holdout bookmarks where inferred collection == confirmed collection |
| **Tag recall** | % of confirmed tags that were inferred |
| **Tag precision** | % of inferred tags that are in the confirmed set |
| **F1 score** | Harmonic mean of tag precision and recall |
| **Overall verification** | Mean of collection accuracy and tag F1 |

**3c. Regression detection**

Since the holdout is a fixed set, any change in verification score is caused by rule changes. This is the only way to know if a "fix" was actually a fix:

- Before applying a proposed rule change: run the holdout → baseline score
- After applying: run the holdout → new score
- If new < baseline: revert the change and flag it as a regression
- Store verification scores in `quality.json` alongside per-run scores

**3d. Refresh strategy**

- When adding new rules or collections, the user should add 1-2 corresponding holdout entries
- When a bookmark is deleted from Raindrop, remove it from the holdout
- Every 50 runs, prompt the user to re-verify a random 10-bookmark subset (to catch cases where the "correct" answer has changed due to taxonomy evolution)
- Maintain at least 50 entries minimum; 100 is the target

---

## Phase 4 — Rule Proposal Lifecycle

**Goal:** Close the loop — proposals become actual changes to the rules file that improve future runs.

### Actions

**4a. Proposal file format**

`references/raindrop-proposals.json` accumulates suggestions from Phase 1 (no-match clustering) and Phase 3 (holdout regression):

```jsonc
{
  "proposals": [
    {
      "id": "prop-20260614-001",
      "type": "add_keyword",        // add_keyword | remove_keyword | adjust_weight | add_template | change_threshold
      "rule_id": "coll-docker",     // existing rule to modify, or null for new
      "change": {
        "add_keywords": ["compose", "docker-compose"],
        "reason": "3 no-match bookmarks from hub.docker.com all contain 'compose' but don't match existing 'docker' keyword because it's absent from their titles"
      },
      "evidence": {
        "filler_agreement_pct": null,
        "no_match_cluster_size": 3,
        "sample_titles": ["Deploying with Compose", "Docker Swarm vs Compose", "Compose in Production"],
        "holdout_impact": null       // computed if the holdout was tested with this change applied
      },
      "status": "pending",           // pending | auto_approved | user_approved | rejected | applied
      "created": "2026-06-14T10:30:00Z",
      "decided_at": null
    }
  ]
}
```

**4b. Auto-approval rules**

Proposals that meet ALL of these are applied automatically without user intervention:

1. The proposal would **add** keywords to an existing rule (not create a new rule, not remove anything)
2. Evidence comes from ≥5 no-match bookmarks sharing the same domain
3. The target collection has ≥20 existing bookmarks (not a new empty collection)
4. No active holdout regression was detected in the last 3 runs

Everything else goes to a kanban card.

**4c. Kanban card format**

Same `raindrop-audit` board as existing Phase 5/7 cards:

```
Title: "rule proposal: add 'compose' → Docker"
Body:
  Pattern: 3 no-match bookmarks from hub.docker.com
  Sample: "Deploying with Compose", "Docker Swarm vs Compose"
  Suggested: Add keywords ["compose", "docker-compose"] to rule "coll-docker"
  Confidence: 3 matches from single domain (medium)
  Impact: Low risk — would only trigger on books with "compose" in title
```

**4d. Merge workflow**

When a proposal is approved (auto or manual):

1. Read `raindrop-rules.json`
2. Apply the change (add keyword, increment weight, etc.)
3. Bump `version` and update `last_updated`
4. Reset affected rules' `stats.hits` and `stats.confidence` (they'll rebuild on the next run)
5. Run the holdout set with the new rules → record as baseline
6. Move the proposal to `"status": "applied"` or `"status": "rejected"`

**4e. Safety valve**

If a change causes the holdout verification score to drop by >10% in the next run, the system should:

1. Revert the change automatically
2. Mark the proposal as `"status": "rejected"` with reason "verification regression"
3. Flag in the Discord output: "Rule change for `coll-docker` reverted — verification score dropped from 92% to 78%"

---

## Implementation Order

| Phase | Depends on | Risk | Time estimate |
|---|---|---|---|
| **0** — Rules file consolidation | Nothing | Low (mechanical refactor) | Small |
| **1** — Filler queue + confidence tracking | Phase 0 | Medium (new code path for filler queue) | Medium |
| **2** — Real quality scoring | Phase 1 (uses per-rule confidence) | Low (additive, doesn't change behavior) | Medium |
| **3** — Holdout set | Phase 2 (reads verification score) | Low (new file, user curation) | Small (script) + User time (curation) |
| **4** — Proposal lifecycle | Phases 0–3 | Medium (new approval workflow, kanban integration) | Medium-Large |

Phases 0 and 2 can be partially parallelized (the rules file doesn't depend on the scoring implementation).

---

## Design Principles

1. **The rules file is the only actuator.** Scores, comparisons, and proposals are diagnostic. The rules file is where improvement is realized. If a change doesn't touch `raindrop-rules.json`, it isn't an improvement — it's just monitoring.

2. **Every rule carries its own confidence.** The system doesn't have a "global accuracy" — it has per-keyword, per-collection, per-pattern confidence scores. This lets the system retire specific bad rules without throwing out everything.

3. **Don't change rules without evidence.** Every rule change must be backed by either: (a) N no-match bookmarks with the same domain, (b) a filler queue comparison showing improvement, or (c) user confirmation. No "just try it and see" changes.

4. **Auto-revert on regression.** The holdout set is the safety net. If a change causes more harm than good, the system detects it within one run and reverts.

5. **The cron path does everything the interactive path does (except approve proposals).** Both paths process, score, and compare. The cron path just can't merge proposals — that requires user judgment.

---

## Subagent Parallelism Analysis

Each phase can be parallelized across independent subagents to reduce wall-clock time. The key constraint is the dependency chain across phases — you cannot start Phase 1 until Phase 0 is merged.

### Dependency Graph

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 4
                 │                     ↑
                 └── No-match stats ───┘
                                        
Phase 3 (independent of 0-1, feeds into 4 alongside 2)
```

### Phase 0 — 3 subagents (all parallel once schema is agreed)

Precondition: Define the `raindrop-rules.json` schema (~15 min design).

| Subagent | File to modify | What to do |
|---|---|---|
| A | `process-batch.py` | Replace hardcoded `COLLECTION_KEYWORD_MAP`, template patterns, and max-tag limit with JSON loader |
| B | `run_pipeline.py` | Replace hardcoded keyword-scoring and `tag_keywords` dicts with JSON loader |
| C | `cron_run.py` + create `raindrop-rules.json` | Write the rules file with existing rules migrated in; make cron read thresholds from it |

These three are truly independent — the contract is just "read this JSON file."

### Phase 1 — 2 subagents (both start after Phase 0 merged)

| Subagent | What to do | Key deliverable |
|---|---|---|
| A | Remove early skip in `process-batch.py`, implement filler queue comparison logic, per-rule confidence tracking, write to confidence file | Code changes to `process-batch.py`, confidence tracking data structures |
| B | No-match backlog clustering by domain / suggested rules, write to proposals file | New utility or inline code, `raindrop-proposals.json` format |

Agent A touches the main processing path. Agent B is a pure-data post-processing step. They share no memory — Agent B just reads the no-match file and writes proposals.

### Phase 2 — 3 subagents (all start after Phase 1 merged)

| Subagent | What to do |
|---|---|
| A | Keyword-overlap precision scorer (replaces current relevance formula) |
| B | Template-penalized tone scorer (replaces hardcoded tone=7) + per-collection metrics from SKILL.md |
| C | Wire scoring into `cron_run.py` so it writes quality records on every run |

A and B are independent formula implementations. C depends on at least one scoring function existing, but the integration is straightforward — call scorers and append to `quality.json`.

### Phase 3 — 1 subagent (starts after Phase 2 merged)

The holdout verification script is a single file. Curation (selecting 100 bookmarks) is manual user work. No parallelism possible here.

### Phase 4 — 3 subagents (all start after Phases 1-3 merged)

| Subagent | What to do |
|---|---|
| A | Proposal accumulation logic + auto-approval rules (reads confidence data, writes proposals, auto-approves high-confidence changes) |
| B | Merge workflow (apply proposals to `raindrop-rules.json`) + safety-valve auto-revert on regression |
| C | Kanban card integration for non-auto-approved proposals |

A and B share the proposals file format but modify different fields (A writes proposals, B reads them). C is fully independent — it is a rendering concern.

### Summary

| Phase | Subagents | Max parallelism | Can start when |
|---|---|---|---|
| 0 | 3 | 3 | Rules file schema is designed (~15 min)
| 1 | 2 | 2 | Phase 0 merged (rules file exists)
| 2 | 3 | 3 | Phase 1 merged (confidence data exists)
| 3 | 1 | 1 | Phase 2 merged (scoring exists)
| 4 | 3 | 3 | Phases 1-3 merged (all signals exist)

**Maximum parallelism at any point:** 3 subagents (during Phase 0, 2, or 4).

**Total subagents across all phases if fully parallelized:** ~10-12 (sequential across phases).

**Cannot be parallelized:**
- Defining the rules file schema (must be sequential to provide the contract)
- The pipeline scripts themselves (single-threaded by nature — one bookmark at a time for rate limiting)
- User curation of the holdout set (manual work)

---

## Phase 5 — Content-Driven Inference with Domain Caching (Planned)

**Status:** Not started. Hold until Phase 3 holdout curation is complete.

### The Problem

Tag and collection inference currently runs against **title + domain only** (5-20 words). This is insufficient signal, producing three failure modes:

1. **Substring false positives** — `"ai"` matches `"maintenance"`, `"retainer"`, `"Brazil"` (present in many words)
2. **Topic-blind matches** — A food recipe page suggested as `"AI"` because a sidebar or footer mentioned "AI"
3. **False negatives** — A page about "Rustic Sourdough Bread" won't match the keyword `"recipe"` even though the page is a recipe, because "recipe" isn't in the title

The interactive path (`run_pipeline.py`) already fetches URL page content — the cron path (`process-batch.py`) does not, leaving the cron runs with the poorest signal.

### Solution Overview

Bring URL content fetching into the cron path and introduce a **domain-level text fingerprint cache** that compounds over time, turning the cron path from the weakest inferencer into the strongest.

---

### Phase 5a — Fetch URL Content in the Cron Path

**Goal:** Give the cron path the same real page content the interactive path has.

**Implementation:**

1. Add `fetch_page_content(url, timeout=5)` to `shared/raindrop_common.py`:
   - Fetch the URL with a short timeout (5s)
   - Extract: `<title>`, `<meta name="description">`, `<meta name="keywords">`, `<meta property="og:*">`
   - Strip HTML tags from `<body>`, keeping ~300 words of clean text
   - Return dict: `{"title", "meta_description", "meta_keywords", "body_text", "og_type"}`
   - On failure (timeout, DNS, 4xx/5xx): return `None` — never crash, just fall back

2. Call `fetch_page_content()` in both `process_one()` and `process_comparison()` before inference:
   - If content available → feed page body into `infer_real_tags()`, `find_collection()`, AND note generation
   - If content unavailable → fall back to current title+domain matching

3. **Cache the raw page text** per-URL with 7-day TTL in `~/.hermes/cache/raindrop-page-cache/pages/`:
   - Keyed by URL (normalised: strip tracking params, fragments)
   - TTL avoids stale content; at 7 days the entry is evicted
   - Hit rate on this alone is low (~10-15%) because the pipeline intentionally avoids recently-processed bookmarks

4. **Domain blacklist** — skip URL fetch for known user-content aggregators where page content adds no signal:

```
SKIP_FETCH_DOMAINS = {
    "wikipedia.org", "github.com", "gitlab.com", "bitbucket.org",
    "discord.com", "discord.gg", "twitter.com", "x.com",
    "reddit.com", "youtube.com", "youtu.be",
    "instagram.com", "facebook.com", "tiktok.com",
}
```

**Tradeoff:** Each URL fetch adds ~3-5s. For a batch of 100 bookmarks, ~60-70 will be fetchable (excluding blacklist + unreachable), adding ~3-5 min to the batch. Acceptable within the cron window.

---

### Phase 5b — Domain Fingerprint Cache

**Goal:** Turn the cost of URL fetching into a lasting asset that compounds over runs.

**Concept:**

Instead of caching per-URL, maintain **domain-level text fingerprints** that accumulate word frequencies across every page fetched on that domain. After a few runs, most common domains will have enough data for reliable inference without fetching at all.

**Data structure** (`~/.hermes/cache/raindrop-page-cache/domains/{domain}.json`):

```json
{
  "domain": "seriouseats.com",
  "total_pages": 47,
  "last_fetched": "2026-06-16T10:30:00Z",
  "word_frequencies": {
    "recipe": 42, "ingredients": 38, "cook": 35,
    "cup": 18, "bake": 15, "heat": 12, "oven": 10
  },
  "top_tags": [
    {"tag": "food", "count": 40, "confidence": 0.85},
    {"tag": "cooking", "count": 12, "confidence": 0.26}
  ],
  "top_collections": [
    {"collection": "Food & Drink", "count": 38, "confidence": 0.81}
  ]
}
```

**Workflow:**

1. Before fetching a URL → check domain fingerprint. If the fingerprint has ≥5 pages and ≥80% consensus on a collection/tag, **skip the fetch** and use the fingerprint directly.
2. On page fetch → update the domain fingerprint: increment word frequencies, update top_tags/top_collections with the assigned values from this run.
3. On unreachable URL → fall back to the domain fingerprint as the sole signal source.
4. On blacklisted domain → skip fetch AND skip fingerprint accumulation (these domains produce no consistent signal).

**Hit rate over time:**

| After | Domains accumulated | New-bookmark hit rate | Batch time |
|---|---|---|---|
| Run 1 | ~40 | ~5% | ~5-6 min (mostly fetches) |
| Run 7 | ~200 | ~40-50% | ~3-4 min |
| Run 30 | ~600 | ~65-75% | ~1.5-2.5 min |
| Run 90 | ~1200 | ~80-85% | ~1-2 min |

The system gets **faster over time**, not slower — the opposite of a naive per-URL cache.

**Garbage collection:**
- Page-level entries: purge >7 days old each run
- Domain fingerprints: persist indefinitely. Old entries decay via a recency weight: fingerprints from the last 30 days get full weight, older ones are halved.
- Domains with 0 hits in 90 days: archive.

---

### Phase 5c — Frequency-Weighted Tag Scoring

**Goal:** Replace binary keyword matching (`if kw in text`) with frequency-based scoring, eliminating substring false positives.

**Implementation:**

Instead of:
```python
if kw in text:  # matches "ai" in "maintenance", "recipe" in title even if page isn't a recipe
    suggest_tag(tag)
```

Use:
```python
count = text.lower().count(kw)  # actual occurrence count
if count >= MIN_OCCURRENCES:     # e.g. 2, or in the top-N frequent words
    score = count / max_freq    # normalised 0-1
    if score > threshold:
        suggest_tag(tag, score)
```

**`MIN_OCCURRENCES`** starts at 2 for page-body text (eliminates single-occurrence false positives like "ai" in "maintenance"). For title-only (fallback when page unreachable), keep the current binary match.

**Word frequency analysis:** After extracting body text, compute the top 15-20 most frequent non-stop words. Any tag keyword appearing in the top 15 is a strong signal. Keywords appearing below that threshold are weak.

---

### Phase 5d — Collection Inference from Page Content

**Goal:** Use the same page content to improve collection assignment, not just tags.

**Implementation:**

Currently `find_collection()` matches keywords against title + domain (~20 words). With page content (~300 words), the match surface is 15x larger.

1. Run keyword matching against the full page text (title + meta description + body text)
2. Score each collection rule by the **frequency** of its keywords in the page text (not just presence)
3. A recipe page mentioning "recipe" 15x, "ingredients" 10x, "cook" 8x scores much higher on "Food & Drink" than a page mentioning "computer" once

This directly addresses the "AI suggested for a recipe" problem — even if "ai" appears once in a sidebar, it won't out-score "recipe" × 15 occurrences.

---

### Phase 5e — Domain Blacklist

Domains where URL content provides no consistent categorization signal (user-generated content aggregators).

```
SKIP_FETCH_DOMAINS = {
    "wikipedia.org",       # Encyclopedic — no single topic signal
    "github.com",          # All topics, all languages
    "gitlab.com",
    "bitbucket.org",
    "discord.com",
    "discord.gg",
    "twitter.com",
    "x.com",
    "reddit.com",          # All topics, comments are the content
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",
    "tiktok.com",
}
```

Bookmarks from these domains still get tag/collection inference — from title + domain only (current behavior). No fetch attempt, no fingerprint accumulation.

---

### Implementation Order (Post-Holdout)

| Sub-phase | Depends on | What it delivers | Batch time impact |
|---|---|---|---|
| **5a** — Fetch content in cron path | Nothing new (adds to shared module) | Real notes + page text for inference | +3-5 min (first run) |
| **5b** — Domain fingerprint cache | 5a (needs fetch to build fingerprints) | Compounding speed: ~80% hit rate after 90 runs | -2-3 min (steadily improves) |
| **5c** — Frequency-weighted scoring | 5a (needs page body text) | Eliminates substring false positives | No change |
| **5d** — Collection from page content | 5a (needs page body text) | Better collection assignment from 15x signal | No change |
| **5e** — Domain blacklist | 5a (needs the fetch function) | Avoid wasted fetches on noisy domains | Improves immediately |

**Recommended order:** 5a + 5e together (parallel — both add to shared module), then 5b, then 5c + 5d (parallel — both consume page text).
