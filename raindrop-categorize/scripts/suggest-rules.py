#!/usr/bin/env python3
"""
Post-processing suggestion engine for raindrop-categorize.

Reads the no-match backlog and clustering by domain / common title keywords,
then produces proposed additions to the collection keyword map.

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/suggest-rules.py

Output: ~/.hermes/cache/raindrop-proposals.json
"""
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

# --- Paths ---
CACHE = os.path.expanduser("~/.hermes/cache")
NO_MATCH_PATH = f"{CACHE}/raindrop-no-match.json"
PROPOSALS_PATH = f"{CACHE}/raindrop-proposals.json"
CONFIDENCE_PATH = f"{CACHE}/raindrop-confidence.json"

# --- Shared module ---
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import load_rules, api_get

# --- Config from rules ---
_rules_data = load_rules()
_thresholds = _rules_data.get("thresholds", {})
CLUSTER_MIN = _thresholds.get("no_match_cluster_min", 3)
OVERSIZE_THRESHOLD = _thresholds.get("collection_oversize_threshold", 25)

# Known domains rarely worth suggesting (they're too generic)
SKIP_DOMAINS = {
    "google.com", "youtube.com", "reddit.com", "twitter.com", "x.com",
    "linkedin.com", "facebook.com", "instagram.com", "github.com",
    "gitlab.com", "bitbucket.org",
}


def extract_domain(entry) -> str:
    """Extract domain from a no-match entry (which may be [id, title] or [id, title, domain] or [id, title, domain, url])."""
    if len(entry) >= 3 and entry[2] and isinstance(entry[2], str) and "." in entry[2]:
        return entry[2].lower().strip()
    # Fallback: try to extract from title (if it looks like a URL)
    title = entry[1] if len(entry) >= 2 else ""
    if title.startswith("http"):
        from urllib.parse import urlparse
        try:
            parsed = urlparse(title)
            return parsed.netloc.lower()
        except Exception:
            pass
    return ""


def extract_url(entry) -> str:
    """Extract URL from a no-match entry."""
    if len(entry) >= 4 and entry[3] and isinstance(entry[3], str) and entry[3].startswith("http"):
        return entry[3]
    title = entry[1] if len(entry) >= 2 else ""
    if title.startswith("http"):
        return title
    return ""


def load_no_match() -> list:
    """Load no-match backlog. Returns list of entries (lists)."""
    if not os.path.exists(NO_MATCH_PATH):
        return []
    try:
        with open(NO_MATCH_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        # Old dict format
        return data.get("bookmarks", data.get("items", []))
    except (json.JSONDecodeError, OSError):
        return []


def load_proposals() -> dict:
    """Load existing proposals file."""
    if os.path.exists(PROPOSALS_PATH):
        try:
            with open(PROPOSALS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"proposals": []}


def save_proposals(data: dict):
    os.makedirs(os.path.dirname(PROPOSALS_PATH), exist_ok=True)
    with open(PROPOSALS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def domain_clustering(entries: list) -> dict:
    """Group no-match entries by extracted domain.

    Returns: {domain: {"entries": [...], "titles": [...]}}
    """
    clusters = defaultdict(list)
    for entry in entries:
        domain = extract_domain(entry)
        if not domain:
            continue
        title = entry[1] if len(entry) >= 2 else "?"
        clusters[domain].append({"entry": entry, "title": title})
    return dict(clusters)


def keyword_clustering(entries: list) -> dict:
    """Group no-match entries by common significant words in titles.

    Returns: {keyword: {"entries": [...], "count": N}}
    """
    # Words to ignore when clustering
    STOP_WORDS = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
        "is", "it", "with", "from", "by", "be", "as", "that", "this", "are",
        "was", "were", "been", "get", "not", "you", "your", "our", "their",
        "its", "all", "how", "why", "what", "when", "where", "who",
        "install", "setup", "guide", "review", "new", "free", "best", "top",
        # URL protocol / browser noise — never useful for categorization
        "https", "http", "www", "com", "html", "php",
    }
    word_counts = Counter()
    entry_map = defaultdict(list)
    for entry in entries:
        title = entry[1] if len(entry) >= 2 else ""
        if not title:
            continue
        # Skip entries where the title is a raw URL — they have no real keywords
        if title.startswith("http"):
            continue
        words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", title.lower()))
        significant = words - STOP_WORDS
        for w in significant:
            word_counts[w] += 1
            entry_map[w].append(entry)

    # Return only words appearing in 2+ entries (not single matches)
    return {
        w: {"entries": es, "count": c}
        for w, es in entry_map.items()
        if (c := len(es)) >= 2
    }


def fetch_collections() -> list:
    """Fetch the live collection tree from Raindrop API for display."""
    try:
        roots = api_get("/collections")
        children = api_get("/collections/childrens")
        all_c = (roots.get("items", []) if roots else []) + \
                (children.get("items", []) if children else [])
        return [{"id": c["_id"], "title": c["title"], "count": c.get("count", 0)}
                for c in all_c]
    except Exception as e:
        print(f"  ⚠ Could not fetch collections: {e}", file=sys.stderr)
        return []


def suggest_from_domain_clusters(clusters: dict, collections: list) -> list:
    """Generate rule suggestions from domain clusters."""
    proposals = []
    for domain, entries_list in sorted(clusters.items()):
        count = len(entries_list)
        if count < CLUSTER_MIN:
            continue
        if domain in SKIP_DOMAINS:
            continue
        titles = [e["title"] for e in entries_list]

        # Extract likely keywords from titles (words that appear in multiple entries)
        word_counter = Counter()
        for t in titles:
            words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", t.lower()))
            word_counter.update(words)

        # Suggest the 3 most common meaningful words as keywords
        common_words = [w for w, _ in word_counter.most_common(6)
                        if w not in ("for", "the", "and", "with", "from")]
        suggested_keywords = common_words[:4] if common_words else domain.split(".")[0]

        # Guess a target collection by looking for keyword overlap
        guessed_collection = None
        if collections and suggested_keywords:
            best_score = 0
            for c in collections:
                c_title_lower = c["title"].lower()
                score = sum(1 for kw in suggested_keywords if kw in c_title_lower)
                if score > best_score:
                    best_score = score
                    guessed_collection = c

        proposal = {
            "id": f"prop-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{domain.replace('.','-')}",
            "type": "add_keyword",
            "domain": domain,
            "match_count": count,
            "sample_titles": titles[:5],
            "suggested_keywords": suggested_keywords,
            "guessed_collection_id": guessed_collection["id"] if guessed_collection else None,
            "guessed_collection_title": guessed_collection["title"] if guessed_collection else f"Collection with '{suggested_keywords[0]}' in name",
            "status": "pending",
            "completed_at": None,
            "source": "no_match_domain_cluster",
            "created": datetime.now(timezone.utc).isoformat(),
        }
        proposals.append(proposal)
    return proposals


def suggest_from_keyword_clusters(clusters: dict) -> list:
    """Generate rule suggestions from keyword clusters (entries without domains).

    NOTE: These proposals use "(title keyword)" as a placeholder domain, which
    means they can never pass auto-approval (is_real_domain check in
    apply-proposals.py). They are informational only — a human must review
    and either reject them or convert them into proper domain-based proposals.
    """
    proposals = []
    for word, info in sorted(clusters.items(), key=lambda x: -x[1]["count"]):
        count = info["count"]
        if count < CLUSTER_MIN:
            continue
        titles = [e[1] if len(e) >= 2 else "?" for e in info["entries"]]

        proposal = {
            "id": f"prop-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{word}",
            "type": "add_keyword",
            "domain": "(title keyword)",
            "match_count": count,
            "sample_titles": titles[:5],
            "suggested_keywords": [word],
            "guessed_collection_id": None,
            "guessed_collection_title": None,
            "status": "pending",
            "completed_at": None,
            "source": "no_match_keyword_cluster",
            "created": datetime.now(timezone.utc).isoformat(),
        }
        proposals.append(proposal)
    return proposals


def load_confidence_domain_suggestions() -> list:
    """Read the confidence file for high-volume domains that lack a rule."""
    proposals = []
    if not os.path.exists(CONFIDENCE_PATH):
        return proposals
    try:
        with open(CONFIDENCE_PATH, encoding="utf-8") as f:
            conf = json.load(f)
    except (json.JSONDecodeError, OSError):
        return proposals

    by_domain = conf.get("by_domain", {})
    for domain, info in by_domain.items():
        if domain in SKIP_DOMAINS:
            continue
        hits = info.get("hits", 0)
        matched_collections = info.get("matched_collections", {})
        if hits >= CLUSTER_MIN and len(matched_collections) <= 2:
            # Domain consistently maps to 1-2 collections — may need a more specific rule
            proposals.append({
                "id": f"prop-domain-{domain.replace('.','-')}",
                "type": "refine_keyword",
                "domain": domain,
                "match_count": hits,
                "matched_collections": matched_collections,
                "status": "pending",
                "completed_at": None,
                "source": "confidence_file_domain",
                "created": datetime.now(timezone.utc).isoformat(),
            })
    return proposals


def main():
    print("=== Suggest Rules ===", flush=True)
    entries = load_no_match()
    if not entries:
        print("No no-match entries found. Nothing to suggest.", flush=True)
        return 0

    print(f"Loaded {len(entries)} no-match entries.", flush=True)

    # 1. Domain clustering
    domain_clusters = domain_clustering(entries)
    print(f"Found {len(domain_clusters)} unique domains.", flush=True)

    collections = fetch_collections()
    if collections:
        print(f"Fetched {len(collections)} collections for matching.", flush=True)

    domain_proposals = suggest_from_domain_clusters(domain_clusters, collections)
    print(f"  → {len(domain_proposals)} domain-based suggestions.", flush=True)

    # 2. Keyword clustering (for entries without extractable domains)
    keyword_clusters = keyword_clustering(entries)
    keyword_proposals = suggest_from_keyword_clusters(keyword_clusters)
    print(f"  → {len(keyword_proposals)} keyword-based suggestions.", flush=True)

    # 3. Confidence file suggestions
    confidence_proposals = load_confidence_domain_suggestions()
    print(f"  → {len(confidence_proposals)} confidence-based suggestions.", flush=True)

    # 4. Merge with existing proposals (deduplicate by ID and by semantic fingerprint)
    all_proposals = domain_proposals + keyword_proposals + confidence_proposals
    existing = load_proposals()
    existing_ids = {p["id"] for p in existing.get("proposals", [])}
    # Build a fingerprint set from existing proposals to catch semantically
    # identical suggestions that get different IDs (e.g., same keyword from
    # different runs). Fingerprint = (source, domain, suggested_keywords tuple)
    existing_fingerprints = set()
    for p in existing.get("proposals", []):
        fp = (
            p.get("source"),
            p.get("domain"),
            tuple(sorted(p.get("suggested_keywords", []))),
        )
        existing_fingerprints.add(fp)
    new_count = 0
    skipped_dupes = 0
    for p in all_proposals:
        if p["id"] in existing_ids:
            continue
        fp = (
            p.get("source"),
            p.get("domain"),
            tuple(sorted(p.get("suggested_keywords", []))),
        )
        if fp in existing_fingerprints:
            skipped_dupes += 1
            continue
        existing.setdefault("proposals", []).append(p)
        existing_ids.add(p["id"])
        existing_fingerprints.add(fp)
        new_count += 1
    if skipped_dupes:
        print(f"  → {skipped_dupes} duplicate suggestions skipped (already exist in proposals).", flush=True)

    if new_count > 0:
        save_proposals(existing)
        print(f"\nSaved {new_count} new proposals to {PROPOSALS_PATH}", flush=True)
    else:
        print("\nNo new proposals.", flush=True)

    # 5. Print summary
    for p in all_proposals:
        print(f"\n  [{p['id']}]", flush=True)
        print(f"    Domain: {p.get('domain', '?')} ({p.get('match_count', 0)} matches)", flush=True)
        print(f"    Sample: {', '.join(p.get('sample_titles', [])[:3])}", flush=True)
        print(f"    Keywords: {p.get('suggested_keywords', [])}", flush=True)
        if p.get("guessed_collection_title"):
            print(f"    Target: {p['guessed_collection_title']}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
