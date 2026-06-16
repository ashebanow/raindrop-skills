---
name: freq-scorer
description: Implement frequency-weighted tag scoring for raindrop-categorize
---

You are implementing Phase 5c — frequency-weighted tag scoring.

## Context

Project root: /Users/ashebanow/Development/ai/raindrop-skills
Shared module: shared/raindrop_common.py
Cron script: raindrop-categorize/scripts/process-batch.py

Phase 5a (already done) added:
- fetch_page_content() in shared/raindrop_common.py
- infer_real_tags(title, domain, rich_text=None) with optional rich_text parameter
- find_collection(title, domain, rich_text=None) with optional rich_text parameter
- build_note_from_content(page_content, title)

Currently infer_real_tags() uses simple `if kw in text` matching regardless of whether text is rich or not.

## Task

Modify `infer_real_tags()` to use frequency-based scoring when rich_text is available.

### The problem

```
if kw in text:
    matched.append(tag_name)
    break
```

This matches on first occurrence. For a page body with 300 words, a keyword like "ai" appearing once in a sidebar triggers the match even if the page is about cooking.

### The fix

When `rich_text` is provided (page body text), use occurrence counting:

```python
def infer_real_tags(title, domain, rich_text=None):
    text = ((title or "") + " " + (domain or "")).lower()
    
    if rich_text:
        # Frequency-weighted scoring against rich text
        match_text = (text + " " + rich_text.lower())
        matched = []
        for tag_name, keywords in TAG_KEYWORDS.items():
            # Count total occurrences of all keywords for this tag in the full text
            total_count = sum(match_text.count(kw) for kw in keywords)
            if total_count >= MIN_OCCURRENCES:  # default 2 for rich text
                matched.append(tag_name)
                if len(matched) >= MAX_TAGS:
                    break
        return matched
    else:
        # Binary matching against title+domain only (existing behavior)
        matched = []
        for tag_name, keywords in TAG_KEYWORDS.items():
            for kw in keywords:
                if kw in text and tag_name not in matched:
                    matched.append(tag_name)
                    break
            if len(matched) >= MAX_TAGS:
                break
        return matched
```

### Define MIN_OCCURRENCES

Add to the thresholds section of process-batch.py (loaded from rules file or hardcoded):

```python
MIN_OCCURRENCES = 2  # minimum occurrences in rich text to suggest a tag
```

If not in the rules file, hardcode as 2.

When rich_text is NOT available (fetch failed or blacklisted domain), fall back to the existing binary match against title+domain. That way, existing behavior is preserved for unreachable URLs.

### Files to modify

- `raindrop-categorize/scripts/process-batch.py` — update `infer_real_tags()` to use frequency scoring

### Verification

Run `cd /Users/ashebanow/Development/ai/raindrop-skills/raindrop-categorize && timeout 30 python3 scripts/process-batch.py --dry-run 2>&1 | head -10` to verify no crash.

Return a summary of the change and how the tag inference behavior differs when rich_text is vs isn't available.
