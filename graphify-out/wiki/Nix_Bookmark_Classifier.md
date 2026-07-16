# Nix Bookmark Classifier

> 25 nodes

## Key Concepts

- **api_get()** (9 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **clean_note_excerpt_dupes.py** (8 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **api_put()** (7 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **main()** (7 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **get_token()** (6 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **classify-nix-bookmarks.py** (5 connections) — `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- **main()** (5 connections) — `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- **jaccard_similarity()** (5 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **fetch_nix_bookmarks()** (4 connections) — `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- **move_bookmark()** (4 connections) — `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- **bigrams()** (4 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **is_substantial_overlap()** (4 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **raindrop_api.py** (4 connections) — `raindrop-categorize/scripts/raindrop_api.py`
- **classify()** (3 connections) — `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- **looks_handwritten()** (3 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **api()** (3 connections) — `raindrop-categorize/scripts/raindrop_api.py`
- **Return the subcollection name for a bookmark.      Priority: Nix Language > Nix** (1 connections) — `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- **Fetch all bookmarks directly under Nix (not in subcollections).** (1 connections) — `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- **Move a single bookmark to a target collection. Returns True on success.** (1 connections) — `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- **Word bigrams with normalization.** (1 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **Jaccard similarity of word bigram sets.** (1 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **Check if note and excerpt share enough content to be considered duplicates.** (1 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **Heuristic: does this note look like human-written content vs template/AI?      R** (1 connections) — `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- **print_tree()** (1 connections) — `raindrop-categorize/scripts/raindrop_api.py`
- **CLI-style API call: exits on error (unlike shared module's api() which returns N** (1 connections) — `raindrop-categorize/scripts/raindrop_api.py`

## Relationships

- [Proposal Apply & Merge](Proposal_Apply_%26_Merge.md) (4 shared connections)
- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (3 shared connections)
- [Rule Suggestion Engine](Rule_Suggestion_Engine.md) (3 shared connections)
- [Gemini AI Classifier](Gemini_AI_Classifier.md) (1 shared connections)
- [Holdout Construction](Holdout_Construction.md) (1 shared connections)
- [Cron Orchestration & Quality](Cron_Orchestration_%26_Quality.md) (1 shared connections)
- [Batch Processing & Classification](Batch_Processing_%26_Classification.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/classify-nix-bookmarks.py`
- `raindrop-categorize/scripts/clean_note_excerpt_dupes.py`
- `raindrop-categorize/scripts/raindrop_api.py`

## Audit Trail

- EXTRACTED: 73 (81%)
- INFERRED: 17 (19%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*