"""
Shared Raindrop.io utilities for raindrop-categorize and raindrop-linter.

Usage from any skill script:

    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(_root, "shared"))
    from raindrop_common import api, api_get, load_rules, TRACKING_TAG, CACHE_DIR
"""

import json
import os
import sys
import time
from typing import Optional
import urllib.error
import urllib.request

# ── Constants ────────────────────────────────────────────────────────

API_BASE = "https://api.raindrop.io/rest/v1"
TRACKING_TAG = "_categorized-v2"
CACHE_DIR = os.path.expanduser("~/.hermes/cache")


# ── Token ────────────────────────────────────────────────────────────

def get_token() -> str:
    """Return RAINDROP_TOKEN or print error and exit."""
    token = os.environ.get("RAINDROP_TOKEN", "")
    if not token:
        print("ERROR: RAINDROP_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    return token


# ── Generic API helper (GET, PUT, POST, DELETE with retries) ────────

def api(method: str, path: str, data: dict = None,
        params: dict = None, retries: int = 3, timeout: int = 15):
    """Generic Raindrop REST API call with bounded retries.

    Args:
        method: HTTP method (GET, PUT, POST, DELETE)
        path: API path starting with / (e.g. /raindrop/123)
        data: JSON-serialisable dict for PUT/POST bodies
        params: query-string params dict (e.g. {"page": 0, "perpage": 50})
        retries: max attempts on retryable errors
        timeout: per-attempt timeout in seconds

    Returns:
        Parsed JSON dict on success, or ``None`` if all retries exhausted.
        On HTTP 4xx errors (except 429) it exits early without retrying.
    """
    token = get_token()
    url = f"{API_BASE}{path}"

    # Build query string from params dict
    if params:
        qs = "&".join(
            f"{k}={urllib.request.quote(str(v), safe='')}"
            for k, v in params.items()
        )
        url = f"{url}?{qs}"

    body = json.dumps(data).encode() if data else None
    last_err = None

    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        if body:
            req.add_header("Content-Type", "application/json")

        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                err_body = e.read().decode(errors="replace")
                last_err = f"HTTP {e.code}: {err_body[:200]}"
                break  # client error, don't retry
            last_err = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            last_err = f"URLError: {e.reason}"
        except (TimeoutError, json.JSONDecodeError, ValueError) as e:
            last_err = f"{type(e).__name__}: {e}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"

        time.sleep(0.5 * (2 ** attempt))

    print(f"  ⚠ api({method} {path}) failed after {retries} attempts: {last_err}",
          flush=True)
    return None


# ── Convenience wrappers ─────────────────────────────────────────────

def api_get(path: str, params: dict = None, retries: int = 3, timeout: int = 15):
    """Convenience wrapper for GET requests."""
    return api("GET", path, params=params, retries=retries, timeout=timeout)


def api_put(path: str, data: dict, retries: int = 3, timeout: int = 15):
    """Convenience wrapper for PUT requests."""
    return api("PUT", path, data=data, retries=retries, timeout=timeout)


def api_post(path: str, data: dict, retries: int = 3, timeout: int = 15):
    """Convenience wrapper for POST requests."""
    return api("POST", path, data=data, retries=retries, timeout=timeout)


def api_delete(path: str, retries: int = 3, timeout: int = 15):
    """Convenience wrapper for DELETE requests."""
    return api("DELETE", path, retries=retries, timeout=timeout)


# ── Rules file loader ────────────────────────────────────────────────

def load_rules(rules_path: str = None) -> dict:
    """Load raindrop-rules.json. Returns dict (possibly empty on failure).

    Args:
        rules_path: explicit path to the rules JSON file. If None, looks for
                    ``references/raindrop-rules.json`` relative to the caller's
                    script directory.
    """
    if rules_path is None:
        # Walk up from the caller's frame to find the repo root
        caller_dir = os.path.dirname(os.path.abspath(sys._getframe(1).f_code.co_filename))
        rules_path = os.path.join(caller_dir, "..", "references", "raindrop-rules.json")

    if not os.path.exists(rules_path):
        print(f"WARNING: rules file not found at {rules_path}", file=sys.stderr)
        return {}

    try:
        with open(rules_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: could not load rules file: {e}", file=sys.stderr)
        return {}


# ── Pagination helper ────────────────────────────────────────────────

def fetch_all_raindrops(collection_id=0):
    """Fetch ALL bookmarks from a collection with pagination (perpage=50).

    Args:
        collection_id: Raindrop collection ID (default 0 = all bookmarks).

    Returns:
        List of raindrop dicts.
    """
    all_drops = []
    page = 0
    perpage = 50
    total_seen = 0

    while True:
        data = api_get(f"/raindrops/{collection_id}",
                       {"page": page, "perpage": perpage})
        if not data:
            break
        items = data.get("items", [])
        if not items:
            break
        all_drops.extend(items)
        total_seen += len(items)
        count = data.get("count", 0)
        if total_seen >= count:
            break
        page += 1
        time.sleep(0.2)

    return all_drops


# ── Template detection and tone scoring ────────────────────────────────


def detect_note_template(note: str, note_templates: list) -> Optional[str]:
    """Return the template id if the note matches a known template, else None.

    Checks if the note starts with the template prefix (the part before
    ``{title}`` placeholder). This catches both exact template matches and
    notes that follow the pattern with a different title.

    Args:
        note: The note text to check.
        note_templates: List of template dicts from the rules file, each with
            ``id``, ``template``, ``domain_pattern``, ``tone_penalty``.

    Returns:
        Template id string (e.g. ``"nt-github"``) or ``None``.
    """
    if not note:
        return None
    for tpl in note_templates:
        tpl_text = tpl.get("template", "")
        prefix = tpl_text.split("{title}")[0] if "{title}" in tpl_text else tpl_text[:20]
        if prefix and note.startswith(prefix):
            return tpl.get("id", "unknown")
    return None


def compute_tone_score(note_text: str, note_templates: list) -> int:
    """Score how natural / template-free a note reads.

    Template-penalized scoring:

    ==============  =====
    Condition        Score
    ==============  =====
    Empty note          0
    Generic "Bookmark"  4
    Domain template     7
    No template         9
    ==============  =====

    Args:
        note_text: The note text to evaluate.
        note_templates: List of template dicts from the rules file.

    Returns:
        Integer score 0–9.
    """
    if not note_text or not note_text.strip():
        return 0

    matched = detect_note_template(note_text, note_templates)
    if matched is None:
        return 9
    if matched == "nt-default":
        return 4
    return 7


# ── Per-collection quality metrics ────────────────────────────────────


def _build_root_tree(collections: dict) -> tuple[dict, list]:
    """Build parent-child tree from flat collections dict, return (tree, root_ids).

    Args:
        collections: Dict of ``{collection_id: {title, parent, count}}`` from
            the scan state.

    Returns:
        Tuple of (tree, root_ids) where tree is ``{cid: {title, parent, count,
        children: [cid]}}``.
    """
    tree = {}
    for cid, info in collections.items():
        tree[cid] = {
            "title": info.get("title", "?"),
            "parent": info.get("parent"),
            "count": info.get("count", 0),
            "children": [],
        }
    root_ids = []
    for cid, node in tree.items():
        pid = node["parent"]
        if pid and str(pid) in tree:
            tree[str(pid)]["children"].append(cid)
        else:
            root_ids.append(cid)
    return tree, root_ids


def _collect_descendants(tree: dict, root_id: str) -> list:
    """Return all descendant collection IDs under a root (including the root)."""
    ids = [root_id]
    for child_id in tree[root_id]["children"]:
        ids.extend(_collect_descendants(tree, child_id))
    return ids


def compute_per_collection_metrics(
    state_data: dict,
    collection_keywords: list,
) -> dict:
    """Compute per-collection quality metrics from scan state data.

    Metrics computed:
    - **Breadth ratio**: ``count / 25`` per collection, flagged when > 1.0
    - **Completeness %**: % of bookmarks in ``final_list`` (per root subtree)
      that have all 3 fields (collection != -1, non-empty tags, non-empty note)
    - **Untagged %**: % of bookmarks in ``final_list`` with empty tags

    Args:
        state_data: Dict with ``collections`` (``{id: {title, parent, count}}``)
            and ``final_list`` (list of bookmark dicts with ``tags``, ``note``,
            ``collection``).
        collection_keywords: List of collection keyword entries from the rules
            file (used only to map relevant collections).

    Returns:

    .. code-block:: python

        {
            "collections_touched": 28,
            "breadth_flagged": ["NixOS (257)", "Shopping (65)"],
            "untagged_pct_avg": 0.03,
            "completeness_pct_avg": 0.95,
        }
    """
    collections = state_data.get("collections", {}) or {}
    final_list = state_data.get("final_list", []) or []

    # Build tree
    tree, root_ids = _build_root_tree(collections)

    # Build root-title map for flagged collection display
    cid_to_title = {}
    for cid, info in collections.items():
        cid_to_title[cid] = info.get("title", "?")

    # Per-root-collection aggregators
    root_bookmarks: dict[str, list] = {}  # root_id -> list of bookmarks
    breadth_flagged = []

    for root_id in root_ids:
        descendant_ids = _collect_descendants(tree, root_id)
        # Collect bookmarks belonging to this subtree
        bk_list = []
        for bm in final_list:
            bm_coll = bm.get("collection", {}) or {}
            bm_cid = bm_coll.get("$id")
            # Also handle plain $id keys
            if bm_cid is None:
                bm_cid = bm_coll.get("$id")
            if bm_cid is None:
                bm_cid = bm_coll.get("id")
            if str(bm_cid) in descendant_ids:
                bk_list.append(bm)
        root_bookmarks[root_id] = bk_list

        # Breadth: use the collection count from state
        root_count = collections.get(root_id, {}).get("count", 0)
        if root_count > 25:
            breadth_flagged.append(
                f"{cid_to_title.get(root_id, '?')} ({root_count})"
            )

    # Compute completeness and untagged averages
    total_bookmarks = 0
    total_complete = 0
    total_untagged = 0

    for root_id, bk_list in root_bookmarks.items():
        for bm in bk_list:
            total_bookmarks += 1
            tags = bm.get("tags", []) or []
            real_tags = [t for t in tags if t != TRACKING_TAG]
            note = (bm.get("note", "") or "").strip()
            bm_coll = bm.get("collection", {}) or {}
            bm_cid = bm_coll.get("$id")
            has_coll = bm_cid not in (None, -1, 0)
            has_tags = len(real_tags) > 0
            has_note = bool(note)

            if has_coll and has_tags and has_note:
                total_complete += 1
            if not real_tags:
                total_untagged += 1

    n = total_bookmarks if total_bookmarks else 1

    return {
        "collections_touched": len(root_ids),
        "breadth_flagged": breadth_flagged,
        "untagged_pct_avg": round(total_untagged / n, 4),
        "completeness_pct_avg": round(total_complete / n, 4),
    }


# ── Precision scoring ───────────────────────────────────────────────

def compute_precision_score(title, domain, url, assigned_collection_id, assigned_tags, rules_data):
    """Compute keyword-overlap precision for an assigned collection and tags.

    Collection precision checks if the rule's keywords or collection name
    appear in the bookmark's title/domain/URL. Tag precision checks each
    assigned tag name or its keywords against the same text.

    Args:
        title: Bookmark title string.
        domain: Bookmark domain string (e.g. "github.com").
        url: Full bookmark URL string.
        assigned_collection_id: The collection ID assigned (int or None).
        assigned_tags: List of tag strings assigned.
        rules_data: Full rules dict loaded from raindrop-rules.json.

    Returns:
        dict with keys:
            collection_precision (float 0.0-1.0),
            tag_precision (float 0.0-1.0),
            combined_score (float 0.0-10.0)
    """
    # Build search text from title, domain, and URL
    text = f"{title or ''} {domain or ''} {url or ''}".lower()
    title_lower = (title or '').lower()
    domain_lower = (domain or '').lower()

    # --- Collection precision ---
    collection_precision = 0.0

    if assigned_collection_id is not None:
        # Find the matching rule entry
        rule_entry = None
        for entry in rules_data.get("collection_keywords", []):
            if entry.get("collection_id") == assigned_collection_id:
                rule_entry = entry
                break

        if rule_entry:
            keywords = rule_entry.get("keywords", [])
            collection_title = rule_entry.get("collection_title", "")

            # 1.0 if any keyword from the rule appears in title/domain/URL
            if any(kw.lower() in text for kw in keywords):
                collection_precision = 1.0
            # 0.8 if collection name appears in the title
            elif collection_title.lower() in title_lower:
                collection_precision = 0.8
            # 0.6 if domain is a known fit (keyword appears in domain)
            elif domain_lower:
                for kw in keywords:
                    kw_lower = kw.lower()
                    if kw_lower in domain_lower or domain_lower.startswith(kw_lower + "."):
                        collection_precision = 0.6
                        break
            # else 0.0 (default)

    # --- Tag precision ---
    tag_precision = 0.0
    tag_keywords_map = rules_data.get("tag_keywords", {})

    if assigned_tags:
        matching = 0
        for tag in assigned_tags:
            # Skip the tracking tag in precision evaluation
            if tag == TRACKING_TAG:
                matching += 1  # neutral — don't penalise
                continue
            # Check if tag name appears in text
            if tag.lower() in text:
                matching += 1
                continue
            # Check if tag's keywords appear in text
            tag_kws = tag_keywords_map.get(tag, [])
            if any(kw.lower() in text for kw in tag_kws):
                matching += 1
                continue
        tag_precision = matching / len(assigned_tags)

    # --- Combined score (0-10 scale) ---
    combined = (collection_precision * 0.5 + tag_precision * 0.5) * 10

    return {
        "collection_precision": round(collection_precision, 2),
        "tag_precision": round(tag_precision, 2),
        "combined_score": round(combined, 1),
    }
