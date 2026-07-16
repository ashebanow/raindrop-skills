# Gemini AI Classifier

> 14 nodes

## Key Concepts

- **gemini_classifier.py** (7 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **classify_bookmark()** (6 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **load_gemini_key()** (4 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **_build_classification_prompt()** (4 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **Path** (3 connections)
- **_build_taxonomy_text()** (3 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **_call_gemini()** (3 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **_parse_response()** (3 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **Resolve the Gemini API key from environment or .env files.** (1 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **Build the taxonomy portion of the prompt: hierarchical collections + tags.** (1 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **Build the full classification prompt for Gemini.** (1 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **Send prompt to Gemini, return raw text response or None on failure.** (1 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **Parse Gemini's JSON response into {collection, tags}.      Handles:     - Clean** (1 connections) — `raindrop-categorize/scripts/gemini_classifier.py`
- **Classify a bookmark using Gemini.      Args:         title: Bookmark title** (1 connections) — `raindrop-categorize/scripts/gemini_classifier.py`

## Relationships

- [Nix Bookmark Classifier](Nix_Bookmark_Classifier.md) (1 shared connections)
- [Cron Orchestration & Quality](Cron_Orchestration_%26_Quality.md) (1 shared connections)
- [Batch Processing & Classification](Batch_Processing_%26_Classification.md) (1 shared connections)

## Source Files

- `raindrop-categorize/scripts/gemini_classifier.py`

## Audit Trail

- EXTRACTED: 36 (92%)
- INFERRED: 3 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*