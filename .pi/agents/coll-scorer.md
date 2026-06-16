---
name: coll-scorer
description: Implement collection inference from page content in raindrop-categorize
---

You are implementing Phase 5d — collection inference from page content.

## Context

Project root: /Users/ashebanow/Development/ai/raindrop-skills
Cron script: raindrop-categorize/scripts/process-batch.py

Phase 5a (already done) added:
- fetch_page_content() in shared/raindrop_common.py
- find_collection(title, domain, rich_text=None) with optional rich_text parameter
- infer_real_tags(title, domain, rich_text=None) with optional rich_text parameter

Currently find_collection() uses first-match-wins keyword matching regardless of input:

```python
def find_collection(title, domain, rich_text=None):
    text = ((title or "") + " " + (domain or "")).lower()
    for keywords, coll_id, coll_title in COLLECTION_KEYWORD_MAP:
        if any(kw in text for kw in keywords):
            return (coll_id, coll_title)
    return None
```

## Task

Modify `find_collection()` to use frequency-based scoring when rich_text is available, selecting the BEST match rather than the FIRST match.

### The fix

When `rich_text` is provided, score each collection rule by keyword frequency in the rich text:

```python
def find_collection(title, domain, rich_text=None):
    text = ((title or "") + " " + (domain or "")).lower()
    
    if rich_text:
        # Frequency-weighted: score each collection by total keyword occurrences in rich text
        match_text = (text + " " + rich_text.lower())
        best_score = 0
        best_match = None
        for keywords, coll_id, coll_title in COLLECTION_KEYWORD_MAP:
            score = sum(match_text.count(kw) for kw in keywords)
            # Bonus: if any keyword appears in the title, boost significantly
            title_bonus = sum(2 for kw in keywords if kw in text)
            score += title_bonus
            if score > best_score:
                best_score = score
                best_match = (coll_id, coll_title, score)
        
        if best_match and best_match[2] >= 2:  # minimum cumulative score
            return (best_match[0], best_match[1])
        return None
    else:
        # First-match-wins against title+domain only (existing behavior)
        for keywords, coll_id, coll_title in COLLECTION_KEYWORD_MAP:
            if any(kw in text for kw in keywords):
                return (coll_id, coll_title)
        return None
```

Key differences from the rich-text tag scorer:
1. Uses **total score** across all keywords, not a threshold per tag
2. Highest-scoring collection wins (not first-match)
3. Title matches get a **2x bonus** (keyword in title is stronger than keyword in body)
4. Minimum cumulative score of 2 to avoid noise from single low-frequency matches

When rich_text is NOT available, fall back to the existing first-match-wins behavior unchanged.

### Files to modify

- `raindrop-categorize/scripts/process-batch.py` — update `find_collection()` to use frequency scoring

### Verification

Run `cd /Users/ashebanow/Development/ai/raindrop-skills/raindrop-categorize && timeout 30 python3 scripts/process-batch.py --dry-run 2>&1 | head -10` to verify no crash.

Return a summary of the change.
