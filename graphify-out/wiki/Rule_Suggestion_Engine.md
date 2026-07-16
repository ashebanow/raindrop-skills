# Rule Suggestion Engine

> 24 nodes

## Key Concepts

- **suggest-rules.py** (13 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **main()** (10 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Counter** (4 connections)
- **domain_clustering()** (4 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **keyword_clustering()** (4 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **fetch_collections()** (4 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **suggest_from_domain_clusters()** (4 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **extract_domain()** (3 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **load_no_match()** (3 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **load_proposals()** (3 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **suggest_from_keyword_clusters()** (3 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **load_confidence_domain_suggestions()** (3 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **extract_url()** (2 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **save_proposals()** (2 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Extract domain from a no-match entry (which may be [id, title] or [id, title, do** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Extract URL from a no-match entry.** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Load no-match backlog. Returns list of entries (lists).** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Load existing proposals file.** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Group no-match entries by extracted domain.      Returns: {domain: {"entries": [** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Group no-match entries by common significant words in titles.      Returns: {key** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Fetch the live collection tree from Raindrop API for display.** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Generate rule suggestions from domain clusters.** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Generate rule suggestions from keyword clusters (entries without domains).** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`
- **Read the confidence file for high-volume domains that lack a rule.** (1 connections) — `raindrop-categorize/scripts/suggest-rules.py`

## Relationships

- [Nix Bookmark Classifier](Nix_Bookmark_Classifier.md) (3 shared connections)
- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/suggest-rules.py`

## Audit Trail

- EXTRACTED: 66 (92%)
- INFERRED: 6 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*