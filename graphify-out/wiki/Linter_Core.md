# Linter Core

> 22 nodes

## Key Concepts

- **raindrop_linter.py** (13 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **main()** (8 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **build_duplicates_report()** (6 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **normalize_url()** (4 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **near_normalize()** (4 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **score_raindrop()** (4 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **pick_survivor()** (4 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **format_kanban_card()** (4 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **is_malformed_url()** (3 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **check_url_live()** (3 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **load_state()** (3 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **save_state()** (3 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Normalize a URL for duplicate detection. Returns canonical form or None if malfo** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Softer normalization for near-duplicate detection: keep non-tracking query param** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Check if a URL is structurally malformed.** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Check if a URL is reachable. Tries HEAD first; falls back to GET on 405 (Method** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Score a raindrop for survivor selection. Higher = better quality.          Uses** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Analyse bookmarks for duplicates.** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Pick the best raindrop from a group. Returns (survivor, [others]).** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Build a kanban card dict for a duplicate group.** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Load linter state from cache file.** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`
- **Save linter state to cache file.** (1 connections) — `raindrop-linter/scripts/raindrop_linter.py`

## Relationships

- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (2 shared connections)
- [Linter Cron Entry](Linter_Cron_Entry.md) (1 shared connections)

## Source Files

- `raindrop-linter/scripts/raindrop_linter.py`

## Audit Trail

- EXTRACTED: 68 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*