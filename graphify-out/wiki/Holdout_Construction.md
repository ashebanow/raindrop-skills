# Holdout Construction

> 25 nodes

## Key Concepts

- **build-holdout.py** (15 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **main()** (12 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **get_key()** (4 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **fetch_collections()** (4 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **tag_review_prompt()** (4 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **clear_line()** (3 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **load_holdout()** (3 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **fetch_all_bookmarks()** (3 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **sample_for_holdout()** (3 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **keyword_match_collections()** (3 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **infer_tags()** (3 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **find_collections_matching_name()** (3 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **save_holdout()** (2 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **move_up()** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **move_down()** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Clear current line and move cursor to start.** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Read a single keypress without Enter. Returns the key character.** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Load existing holdout. Returns dict with 'entries' list and 'metadata'.** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Fetch all collections from Raindrop API.** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Fetch ALL bookmarks via the bulk endpoint (few API calls, not per-collection).** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Select a diverse subset of bookmarks for confirmation.** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Find the top N collection matches by keyword overlap.      Uses live collection** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Infer tags from title + domain using tag_keywords from the rules file.** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Quick tag quality check. Returns (tags_to_save, tags_need_review).      Shows cu** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`
- **Fuzzy find collections by name fragment.** (1 connections) — `raindrop-categorize/scripts/build-holdout.py`

## Relationships

- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (1 shared connections)
- [Nix Bookmark Classifier](Nix_Bookmark_Classifier.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/build-holdout.py`

## Audit Trail

- EXTRACTED: 73 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*