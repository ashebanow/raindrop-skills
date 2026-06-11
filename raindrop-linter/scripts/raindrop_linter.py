#!/usr/bin/env python3
"""Raindrop Linter — checks for duplicate URLs, malformed URLs, and dead links.

Phases:
  1. Fetch all bookmarks, normalize URLs, build lookup
  2. Find exact duplicates & near-duplicates, score survivors
  3. Find malformed URLs
  4. Dead URL batch scan (rolling cursor, oldest-first)

State persisted to ~/.hermes/cache/raindrop-lint-state.json
"""

import json, os, sys, time, re, socket
import urllib.request
import urllib.error
from collections import defaultdict
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from datetime import datetime, timezone

HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
CACHE_DIR = os.path.join(HERMES_HOME, "cache")
STATE_FILE = os.path.join(CACHE_DIR, "raindrop-lint-state.json")
API_BASE = "https://api.raindrop.io/rest/v1"

# ── API helpers ──────────────────────────────────────────────────────

def api_get(path, params=None):
    import urllib.request
    token = os.environ.get("RAINDROP_TOKEN", "")
    if not token:
        raise RuntimeError("RAINDROP_TOKEN not set")
    url = f"{API_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={urllib.request.quote(str(v), safe='')}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "raindrop-linter/1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_all_raindrops():
    """Fetch ALL bookmarks (paginated, perpage=50). Returns list of raindrops."""
    all_drops = []
    page = 0
    perpage = 50
    total_seen = 0
    while True:
        data = api_get("/raindrops/0", {"page": page, "perpage": perpage})
        items = data.get("items", [])
        if not items:
            break
        all_drops.extend(items)
        total_seen += len(items)
        count = data.get("count", 0)
        if total_seen >= count:
            break
        page += 1
        time.sleep(0.2)  # rate limit pacing
    return all_drops


# ── URL normalization ────────────────────────────────────────────────

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid",
    "msclkid", "mc_cid", "mc_eid",
    "_ga", "_gl",
    "ref", "src", "source",
    "tab", "pli", "sca_esv", "sxsrf", "ei", "ved", "rlz",
}

_REMOVE_FRAGMENTS = True


def normalize_url(url: str) -> str:
    """Normalize a URL for duplicate detection. Returns canonical form or None if malformed."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    # Skip non-HTTP schemes
    if url.startswith("javascript:") or url.startswith("about:") or url.startswith("data:"):
        return None
    # Add scheme if missing
    if not url.startswith(("http://", "https://", "ftp://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    # Normalize hostname: lowercase, strip www
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    # Normalize path: lowercase, strip trailing slash
    path = parsed.path.rstrip("/") or "/"
    # Strip tracking params
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    clean_params = {k: v for k, v in query_params.items() if k.lower() not in _TRACKING_PARAMS}
    query_str = urlencode(clean_params, doseq=True) if clean_params else ""
    # Rebuild
    normalized = urlunparse(("https", hostname, path, parsed.params, query_str, ""))
    return normalized


def near_normalize(url: str) -> str:
    """Softer normalization for near-duplicate detection: keep non-tracking query params."""
    norm = normalize_url(url)
    if not norm:
        return None
    parsed = urlparse(norm)
    # hostname + path + non-tracking query params (sorted)
    clean_params = parse_qs(parsed.query, keep_blank_values=True)
    query_str = urlencode(clean_params, doseq=True) if clean_params else ""
    return f"{parsed.hostname}{parsed.path.rstrip('/')}?{query_str}".rstrip("?")


# ── URL validation ───────────────────────────────────────────────────

_MALFORMED_PATTERNS = [
    re.compile(r"^https?://$"),                     # empty host
    re.compile(r"^https?://\s+"),                   # whitespace in host
    re.compile(r"[%\s]"),                           # unencoded spaces
    re.compile(r"^https?://[^:]+:[^@]+@"),          # credentials in URL
]


def is_malformed_url(url: str) -> bool:
    """Check if a URL is structurally malformed."""
    if not url or not isinstance(url, str):
        return True, "empty or None"
    url = url.strip()
    if not url:
        return True, "empty"
    if any(p.search(url) for p in _MALFORMED_PATTERNS):
        return True, "malformed pattern"
    try:
        parsed = urlparse(url)
    except Exception as e:
        return True, f"parse error: {e}"
    if not parsed.scheme:
        return True, "no scheme"
    if parsed.scheme not in ("http", "https", "ftp"):
        return True, f"unusual scheme: {parsed.scheme}"
    if not parsed.hostname:
        return True, "no hostname"
    if "." not in parsed.hostname and parsed.hostname != "localhost":
        return True, "invalid hostname (no dot)"
    return False, ""


# ── Dead URL check (HEAD) ────────────────────────────────────────────

def check_url_live(url: str, timeout: float = 8.0) -> tuple:
    """Check if a URL is reachable. Tries HEAD first; falls back to GET on 405 (Method Not Allowed).
    Returns (live: bool, status: int or None, error: str or None)."""
    import urllib.request
    methods = ["HEAD", "GET"]
    for method in methods:
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, method=method)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return True, resp.status, None
            except urllib.error.HTTPError as e:
                status = e.code
                if status == 405 and method == "HEAD":
                    break  # server doesn't support HEAD, try GET
                if status < 500:
                    return False, status, f"HTTP {status}"
                # 5xx — retry once within this method
                if attempt == 0:
                    time.sleep(1)
                    continue
                return False, status, f"HTTP {status} (after retry)"
            except urllib.error.URLError as e:
                return False, None, str(e.reason)
            except (ConnectionRefusedError, ConnectionResetError) as e:
                return False, None, str(e)
            except socket.timeout:
                if attempt == 0:
                    time.sleep(1)
                    continue
                return False, None, "timeout"
            except Exception as e:
                return False, None, str(e)
    return False, None, "max retries"


# ── Scoring ──────────────────────────────────────────────────────────

def score_raindrop(drop: dict) -> int:
    """Score a raindrop for survivor selection. Higher = better quality.
    
    Uses the same quality axes as raindrop-categorize.
    """
    score = 0
    tags = drop.get("tags", []) or []
    note = drop.get("note", "") or ""
    desc = drop.get("description", "") or ""
    collection = drop.get("collection", {}) or {}
    
    # Completeness
    if collection.get("$id") and collection["$id"] not in (0, -1):
        score += 2
    if tags:
        score += 2
    if note.strip():
        score += 2
    
    # _categorized-v2 is a strong signal
    if "_categorized-v2" in tags:
        score += 3
    
    # Has description (but we consolidate it — having one shows prior curation)
    if desc.strip():
        score += 1
    
    # Tiebreaker: most recently updated
    # (added as fractional point so it doesn't override quality signals)
    last_update = drop.get("lastUpdate", "")
    if last_update:
        try:
            ts = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
            # Score up to +0.99 for recency
            age_days = (datetime.now(timezone.utc) - ts).days
            score += max(0, min(99, 100 - age_days)) / 100
        except (ValueError, AttributeError):
            pass
    
    return score


# ── Main lint pipeline ───────────────────────────────────────────────

def build_duplicates_report(drops: list) -> dict:
    """Analyse bookmarks for duplicates."""
    # Canonical URL → drops
    canon_map = defaultdict(list)
    near_map = defaultdict(list)
    malformed = []
    
    for drop in drops:
        url = drop.get("link", "")
        canon = normalize_url(url)
        
        if canon:
            canon_map[canon].append(drop)
            near_key = near_normalize(url)
            if near_key:
                near_map[near_key].append(drop)
        else:
            # Couldn't normalize — check if malformed
            is_bad, reason = is_malformed_url(url)
            if is_bad:
                malformed.append((drop, reason, url))
    
    # Exact duplicates: canonical URL with 2+ drops
    exact_dups = {url: group for url, group in canon_map.items() if len(group) > 1}
    
    # Near-duplicates: different canonical URLs but same near-key
    # Exclude the ones already caught as exact dups
    near_dups = {}
    canon_urls_set = set(canon_map.keys())
    for near_key, group in near_map.items():
        if len(group) > 1:
            # Check if they're NOT all the same canonical URL
            canons_in_group = {normalize_url(d.get("link", "")) for d in group}
            if len(canons_in_group) > 1:
                # Filter to only the ones that aren't already exact-dup pairs
                extra = [d for d in group if normalize_url(d.get("link", "")) in canons_in_group]
                if extra:
                    near_dups[near_key] = extra
    
    return {
        "exact_duplicates": exact_dups,
        "near_duplicates": near_dups,
        "malformed": malformed,
    }


def pick_survivor(drops: list) -> tuple:
    """Pick the best raindrop from a group. Returns (survivor, [others])."""
    scored = [(score_raindrop(d), d) for d in drops]
    scored.sort(key=lambda x: (-x[0], x[1].get("_id", 0)))
    survivor = scored[0][1]
    others = [d for _, d in scored[1:]]
    return survivor, others


def format_kanban_card(survivor: dict, others: list, dup_type: str) -> dict:
    """Build a kanban card dict for a duplicate group."""
    url = survivor.get("link", "")
    title = survivor.get("title", "Untitled")[:80]
    surv_score = score_raindrop(survivor)
    
    others_lines = []
    for d in others:
        s = score_raindrop(d)
        t = d.get("title", "Untitled")[:60]
        others_lines.append(f"  - {t} (score: {s:.1f}) — id={d.get('_id')}")
    
    body = (
        f"Type: {dup_type}\n"
        f"URL: {url}\n"
        f"Survivor: {title} (score: {surv_score:.1f}) — id={survivor.get('_id')}\n"
        f"Duplicates:\n" + "\n".join(others_lines)
    )
    return {
        "title": f"dup: {title[:60]}",
        "body": body,
    }


def load_state() -> dict:
    """Load linter state from cache file."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "dead_url_cursor": 0,       # raindrop _id to start from
            "dead_url_checked": [],     # raindrop _ids already checked
            "total_bookmarks": 0,
            "last_run": None,
            "version": 1,
        }


def save_state(state: dict):
    """Save linter state to cache file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ── CLI entry point ──────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Raindrop Linter")
    parser.add_argument("action", nargs="?", default="lint",
                        choices=["lint", "dead", "dups", "malformed", "state"],
                        help="Action to perform")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max dead URLs to check per run (default: 100)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON (for kanban card creation)")
    args = parser.parse_args()
    
    state = load_state()
    
    if args.action == "state":
        print(json.dumps(state, indent=2, default=str))
        return
    
    print(f"Fetching all bookmarks...", file=sys.stderr)
    drops = fetch_all_raindrops()
    state["total_bookmarks"] = len(drops)
    print(f"  {len(drops)} bookmarks loaded", file=sys.stderr)
    
    if args.action in ("lint", "dups"):
        print(f"\nChecking for duplicates...", file=sys.stderr)
        report = build_duplicates_report(drops)
        
        exact = report["exact_duplicates"]
        near = report["near_duplicates"]
        malformed = report["malformed"]
        
        print(f"  Exact duplicates: {len(exact)} groups", file=sys.stderr)
        print(f"  Near-duplicates:  {len(near)} groups", file=sys.stderr)
        print(f"  Malformed URLs:   {len(malformed)}", file=sys.stderr)
        
        cards = []
        total_dups = 0
        
        # Process exact duplicates
        for canon_url, group in exact.items():
            survivor, others = pick_survivor(group)
            cards.append(format_kanban_card(survivor, others, "exact"))
            total_dups += len(others)
        
        # Process near-duplicates
        for near_key, group in near.items():
            survivor, others = pick_survivor(group)
            cards.append(format_kanban_card(survivor, others, "near-dup"))
            total_dups += len(others)
        
        if args.json:
            print(json.dumps({"cards": cards, "total_duplicates": total_dups}, indent=2))
        else:
            print(f"\nTotal duplicates to remove: {total_dups}", file=sys.stderr)
            for card in cards:
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"  {card['title']}", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)
                print(card['body'], file=sys.stderr)
    
    if args.action in ("lint", "malformed"):
        print(f"\nChecking for malformed URLs...", file=sys.stderr)
        malformed = build_duplicates_report(drops)["malformed"]
        if args.json:
            malformed_data = [{"id": d.get("_id"), "title": d.get("title"), "url": url, "reason": reason}
                              for d, reason, url in malformed]
            print(json.dumps({"malformed": malformed_data}, indent=2))
        else:
            print(f"  {len(malformed)} malformed URLs found", file=sys.stderr)
            for drop, reason, url in malformed[:10]:
                print(f"    [{drop.get('_id')}] {drop.get('title','?')[:50]} — {reason}", file=sys.stderr)
            if len(malformed) > 10:
                print(f"    ... and {len(malformed)-10} more", file=sys.stderr)
    
    if args.action in ("lint", "dead"):
        print(f"\nDead URL batch scan (limit={args.limit})...", file=sys.stderr)
        
        # Sort drops by lastUpdate ascending (oldest first), skip already checked
        cursor = state.get("dead_url_cursor", 0)
        checked = set(state.get("dead_url_checked", []))
        
        # Find the oldest unchecked drops
        unchecked = []
        for d in drops:
            did = d.get("_id", 0)
            if did <= cursor or did in checked:
                continue
            unchecked.append(d)
        
        # Sort by lastUpdate ascending
        unchecked.sort(key=lambda d: d.get("lastUpdate", ""))
        
        batch = unchecked[:args.limit]
        dead_urls = []
        for i, drop in enumerate(batch):
            url = drop.get("link", "")
            did = drop.get("_id", 0)
            print(f"  [{i+1}/{len(batch)}] {drop.get('title','?')[:40]}... ", end="", file=sys.stderr)
            live, status, error = check_url_live(url)
            if live:
                print(f"OK ({status})", file=sys.stderr)
            else:
                print(f"DEAD — {error}", file=sys.stderr)
                dead_urls.append((drop, error, url))
            checked.add(did)
            time.sleep(0.15)  # rate limit pacing
        
        # Update cursor to the last bookmark we checked
        if batch:
            state["dead_url_cursor"] = max(d.get("_id", 0) for d in batch)
        state["dead_url_checked"] = list(checked)
        
        if args.json:
            dead_data = [{"id": d.get("_id"), "title": d.get("title"), "url": url, "error": error}
                         for d, error, url in dead_urls]
            print(json.dumps({"dead_urls": dead_data, "checked": len(batch)}, indent=2))
        else:
            print(f"\n  Checked {len(batch)} URLs, {len(dead_urls)} dead", file=sys.stderr)
            for drop, error, url in dead_urls:
                print(f"    DEAD [{drop.get('_id')}] {drop.get('title','?')[:50]} — {error}", file=sys.stderr)
    
    # Save state
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
