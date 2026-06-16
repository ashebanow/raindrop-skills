---
name: content-fetcher
description: Implement URL page content fetching for raindrop-categorize cron path
---

You are implementing Phase 5a of the raindrop-categorize self-improvement plan.

## Context

Project root: /Users/ashebanow/Development/ai/raindrop-skills
Shared module: shared/raindrop_common.py
Rules file: raindrop-categorize/references/raindrop-rules.json
Cron script: raindrop-categorize/scripts/process-batch.py

## Task

Add URL page content fetching to the shared module, then wire it into process-batch.py so the cron path has real page text for tag inference, collection matching, and note generation.

### 1. Add fetch_page_content() to shared/raindrop_common.py

```python
SKIP_FETCH_DOMAINS = {
    "wikipedia.org", "github.com", "gitlab.com", "bitbucket.org",
    "discord.com", "discord.gg", "twitter.com", "x.com",
    "reddit.com", "youtube.com", "youtu.be",
    "instagram.com", "facebook.com", "tiktok.com",
}


def should_fetch_url(url: str) -> bool:
    """Check if a URL should be fetched (not blacklisted)."""
    from urllib.parse import urlparse
    try:
        domain = urlparse(url).netloc.lower()
        for skip in SKIP_FETCH_DOMAINS:
            if skip in domain:
                return False
        return True
    except Exception:
        return False


def fetch_page_content(url: str, timeout: int = 5, max_body_words: int = 300) -> dict | None:
    """Fetch a URL and extract readable text content.

    Returns dict with keys: title, meta_description, meta_keywords,
    body_text, og_type, success.

    Returns None on any failure (timeout, DNS, 4xx/5xx).
    Never raises an exception — always returns None on failure.
    """
    import urllib.request
    import urllib.error
    import re

    if not should_fetch_url(url):
        return None

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; raindrop-categorize/1.0)",
            "Accept": "text/html",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Check content type — skip non-HTML
            ct = resp.headers.get("Content-Type", "")
            if "text/html" not in ct and "application/xhtml" not in ct:
                return None
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    result = {"success": True}
    
    # Extract <title>
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    result["title"] = m.group(1).strip() if m else ""

    # Extract <meta name="description">
    m = re.search(
        r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE
    )
    result["meta_description"] = m.group(1).strip() if m else ""
    if not result["meta_description"]:
        # Try og:description
        m = re.search(
            r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']*)["\']',
            html, re.IGNORECASE
        )
        result["meta_description"] = m.group(1).strip() if m else ""

    # Extract <meta name="keywords">
    m = re.search(
        r'<meta[^>]*name=["\']keywords["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE
    )
    result["meta_keywords"] = m.group(1).strip() if m else ""

    # Extract og:type
    m = re.search(
        r'<meta[^>]*property=["\']og:type["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE
    )
    result["og_type"] = m.group(1).strip() if m else ""

    # Extract body text (strip tags, collapse whitespace)
    m = re.search(r'<body[^>]*>(.*?)</body>', html, re.IGNORECASE | re.DOTALL)
    if m:
        body = m.group(1)
        # Remove script and style blocks
        body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.IGNORECASE | re.DOTALL)
        # Strip tags
        body = re.sub(r'<[^>]+>', ' ', body)
        # Collapse whitespace
        body = re.sub(r'\s+', ' ', body).strip()
        # Truncate to max_body_words
        words = body.split()
        if len(words) > max_body_words:
            words = words[:max_body_words]
        result["body_text"] = ' '.join(words)
    else:
        result["body_text"] = ""

    return result
```

### 2. Wire into process-batch.py

In both `process_one()` and `process_comparison()`:

Before running inference (infer_real_tags, find_collection, infer_note), call fetch_page_content(url).

```python
page_content = fetch_page_content(link)
if page_content and page_content.get("body_text"):
    # Combine title + meta description + body text for rich inference text
    rich_text = (title + " " + (domain or "") + " "
                 + page_content.get("meta_description", "") + " "
                 + page_content.get("body_text", ""))
    # Use rich_text as input to infer_real_tags and find_collection
    # instead of just title + domain
    # For note generation, use the fetched content to write a real note
    new_note = build_note_from_content(page_content, title)
else:
    # Fall back to current behavior
    new_note = infer_note(title, domain, link)
```

Create a `build_note_from_content(page_content, title)` helper that:
- If page has meta_description: use it (truncated to 200 chars)
- If not, use body_text first 150 chars
- Fall back to current infer_note()

For tag and collection inference, modify the inference functions to accept an optional `rich_text` parameter. When present, use it instead of `title + domain`.

### 3. Import in process-batch.py

Add `fetch_page_content, should_fetch_url` to the import from raindrop_common.

### 4. Update infer_real_tags() and find_collection()

Both currently accept `(title, domain)`. Add an optional `rich_text=None` parameter. When rich_text is provided, concatenate `title + " " + domain + " " + rich_text` for matching instead of just `title + " " + domain`.

### 5. Update infer_note()

Keep the existing template logic as fallback. When page content is available, use `build_note_from_content()` instead.

### Verification

Run `cd /Users/ashebanow/Development/ai/raindrop-skills/raindrop-categorize && timeout 30 python3 scripts/process-batch.py --dry-run 2>&1 | head -15` to verify no crash.

Return a summary of files changed, lines added, and a sample of what notes/tags look like with page content.
