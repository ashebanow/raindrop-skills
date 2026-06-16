---
name: domain-cache
description: Implement domain fingerprint cache for raindrop-categorize
---

You are implementing Phase 5b — domain fingerprint cache.

## Context

Project root: /Users/ashebanow/Development/ai/raindrop-skills
Shared module: shared/raindrop_common.py
Cron script: raindrop-categorize/scripts/process-batch.py
Cache dir: ~/.hermes/cache/raindrop-page-cache/

Phase 5a (already done) added fetch_page_content() and should_fetch_url() to shared/raindrop_common.py.
infer_real_tags(title, domain, rich_text=None) and find_collection(title, domain, rich_text=None) both accept optional rich_text.
build_note_from_content(page_content, title) exists.

## Task

Add a domain-level text fingerprint cache that accumulates word frequencies and tag/collection assignments across runs.

### 1. Data structures

Add to shared/raindrop_common.py:

```python
DOMAIN_CACHE_DIR = os.path.expanduser("~/.hermes/cache/raindrop-page-cache")
DOMAIN_CACHE_TTL_DAYS = 90  # domains untouched this long get archived


def _domain_cache_path(domain: str) -> str:
    """Path to a domain's fingerprint JSON file."""
    safe = domain.replace(".", "_")
    return os.path.join(DOMAIN_CACHE_DIR, "domains", f"{safe}.json")


def load_domain_fingerprint(domain: str) -> dict:
    """Load domain fingerprint, or return empty defaults."""
    path = _domain_cache_path(domain)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "domain": domain,
        "total_pages": 0,
        "last_fetched": None,
        "word_frequencies": {},
        "top_tags": [],
        "top_collections": [],
    }


def save_domain_fingerprint(fingerprint: dict):
    """Save domain fingerprint."""
    os.makedirs(os.path.dirname(_domain_cache_path(fingerprint["domain"])), exist_ok=True)
    with open(_domain_cache_path(fingerprint["domain"]), "w") as f:
        json.dump(fingerprint, f, indent=2)


def update_domain_fingerprint(domain: str, body_text: str, assigned_tags: list, assigned_collection_title: str):
    """Update a domain fingerprint with content from one page fetch.

    Args:
        domain: The domain (e.g. "seriouseats.com")
        body_text: The page body text (~300 words)
        assigned_tags: List of tags assigned to this bookmark
        assigned_collection_title: Collection title assigned
    """
    fp = load_domain_fingerprint(domain)
    fp["total_pages"] += 1
    fp["last_fetched"] = datetime.now(timezone.utc).isoformat()

    # Update word frequencies
    import re
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", body_text.lower())
    stop_words = {"the", "and", "for", "are", "was", "were", "been",
                  "that", "this", "with", "from", "have", "has",
                  "not", "but", "all", "can", "you", "its", "our",
                  "their", "your", "which", "what", "when", "where",
                  "how", "who", "why", "more", "some", "about", "also"}
    for w in words:
        if w not in stop_words and len(w) > 2:
            fp["word_frequencies"][w] = fp["word_frequencies"].get(w, 0) + 1

    # Update top_tags: increment count for each assigned tag
    tag_counts = {t["tag"]: t["count"] for t in fp["top_tags"]}
    for t in assigned_tags:
        tag_counts[t] = tag_counts.get(t, 0) + 1
    # Sort and keep top 10
    sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
    fp["top_tags"] = [
        {"tag": t, "count": c, "confidence": round(c / fp["total_pages"], 3)}
        for t, c in sorted_tags[:10]
    ]

    # Update top_collections
    coll_counts = {c["collection"]: c["count"] for c in fp["top_collections"]}
    coll_counts[assigned_collection_title] = coll_counts.get(assigned_collection_title, 0) + 1
    sorted_colls = sorted(coll_counts.items(), key=lambda x: -x[1])
    fp["top_collections"] = [
        {"collection": c, "count": count, "confidence": round(count / fp["total_pages"], 3)}
        for c, count in sorted_colls[:10]
    ]

    save_domain_fingerprint(fp)


def query_domain_fingerprint(domain: str, min_pages: int = 5, min_confidence: float = 0.7):
    """Query domain fingerprint for reliable signals.

    Args:
        domain: Domain to query
        min_pages: Minimum total pages before considering the signal reliable
        min_confidence: Minimum confidence to return a suggestion

    Returns:
        dict with "tags", "collections", "top_words" keys, or None if not enough data
    """
    fp = load_domain_fingerprint(domain)
    if fp["total_pages"] < min_pages:
        return None

    result = {}
    
    # Tags with sufficient confidence
    reliable_tags = [t for t in fp["top_tags"] if t["confidence"] >= min_confidence]
    if reliable_tags:
        result["tags"] = [t["tag"] for t in reliable_tags]
    
    # Collections with sufficient confidence
    reliable_colls = [c for c in fp["top_collections"] if c["confidence"] >= min_confidence]
    if reliable_colls:
        result["collections"] = [(c["collection"], c["confidence"]) for c in reliable_colls]
    
    # Top 20 frequent words for contextual matching
    top_words = sorted(fp["word_frequencies"].items(), key=lambda x: -x[1])[:20]
    if top_words:
        result["top_words"] = [w for w, _ in top_words]
    
    return result if (reliable_tags or reliable_colls) else None
```

### 2. Wire into process-batch.py

In `process_one()` and `process_comparison()`, after fetching page content (or if fetch returned None):

```python
from urllib.parse import urlparse
domain_key = urlparse(link).netloc.lower() if link else domain

# Check domain fingerprint for cached signals
domain_signal = query_domain_fingerprint(domain_key)
if domain_signal:
    # Use domain signals to boost/suggest tags and collections
    # Tags: add domain-suggested tags if not already present
    for suggested_tag in domain_signal.get("tags", []):
        if suggested_tag not in matched_tags:
            matched_tags.append(suggested_tag)
    # Collections: if no keyword match found, use domain suggestion
    if not collection_match and domain_signal.get("collections"):
        best_coll = domain_signal["collections"][0]  # highest confidence
        collection_match = (best_coll[0], best_coll[1])  # (title, confidence)
        # Need to look up collection_id from title
        ...
```

Also, after a successful fetch with page content, call `update_domain_fingerprint()` to accumulate the signals:

```python
if page_content and page_content.get("body_text"):
    update_domain_fingerprint(
        domain_key, page_content["body_text"],
        assigned_tags, assigned_collection_title
    )
```

### 3. Import in process-batch.py

Add `load_domain_fingerprint, save_domain_fingerprint, update_domain_fingerprint, query_domain_fingerprint` to the raindrop_common import.

### Verification

Run `cd /Users/ashebanow/Development/ai/raindrop-skills/raindrop-categorize && timeout 30 python3 scripts/process-batch.py --dry-run 2>&1 | head -10` to verify no crash.

The cache will be empty on first run (no fingerprints yet), so the query will return None and fall back to existing behavior. That's expected.

Return a summary of files changed, lines added, and the cache file structure created.
