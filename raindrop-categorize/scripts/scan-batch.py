#!/usr/bin/env python3
"""
Scan all collections for eligible bookmarks, build the new + filler pools,
and save state for the processing script.

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/scan-batch.py

IMPORTANT: The Raindrop API silently caps perpage at 50, NOT 200.
           The pagination check must compare against 50, not 200.

Output:
  ~/.hermes/cache/raindrop-state.json  — collections, tags, and final bookmark list
"""
import json, os, sys, time
from datetime import datetime, timezone, timedelta
from collections import Counter
from pathlib import Path

# Shared module with retry-capable API
_repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_repo_root / "shared"))
from raindrop_common import api_get as _api_get

CACHE = os.path.expanduser("~/.hermes/cache")
STATE_PATH = f"{CACHE}/raindrop-state.json"
CUTOFF_24H = datetime.now(timezone.utc) - timedelta(hours=24)

PERPAGE = 50  # Raindrop API caps at 50; do not change to 200


def api(path):
    """GET the given API path with retries and exponential backoff.

    Delegates to the shared ``api_get()`` which already handles 3 retries
    with exponential backoff, eliminating the single-timeout-kills-scan
    failure mode.
    """
    # Split path and params for the shared api_get signature
    if "?" in path:
        path_part, qs = path.split("?", 1)
        params = dict(p.split("=", 1) for p in qs.split("&"))
        return _api_get(path_part, params=params)
    return _api_get(path)

t0 = time.time()

# Phase 1: Collections + Tags
print("Fetching collections...", flush=True)
try:
    roots = api("/collections").get("items", [])
except Exception as e:
    print(f"  ERROR fetching root collections: {e}", flush=True)
    roots = []
try:
    children = api("/collections/childrens").get("items", [])
except Exception as e:
    print(f"  ERROR fetching child collections: {e}", flush=True)
    children = []
try:
    tags_data = api("/tags/0").get("items", [])
except Exception as e:
    print(f"  ERROR fetching tags: {e}", flush=True)
    tags_data = []
all_colls = roots + children
print(f"  {len(roots)} root + {len(children)} children = {len(all_colls)} | {len(tags_data)} tags", flush=True)

# Phase 2: Scan collections sequentially (parallel causes 429 rate limits)
non_empty = [c for c in all_colls if c.get("count", 0) > 0]
non_empty.insert(0, {"_id": 0, "title": "Unsorted"})
print(f"Scanning {len(non_empty)} collections sequentially...", flush=True)

seen = set()
new_pool, filler_p1, filler_p2 = [], [], []

# Collection 0 (/raindrops/0) returns ALL bookmarks in the library, so we
# only need to scan it once. Subsequent collections would just return
# already-seen bookmarks — skipping them saves ~200 API calls and avoids
# the 600s timeout on slow API days.
for idx, c in enumerate(non_empty):
    cid = c["_id"]
    page = 0
    while True:
        try:
            data = api(f"/raindrops/{cid}?perpage={PERPAGE}&page={page}")
            if data is None:
                print(f"  ⚠ col[{cid}] page {page}: API returned None after retries", flush=True)
                break
            items = data.get("items", [])
            if not items:
                break
            for r in items:
                rid = r["_id"]
                if rid in seen:
                    continue
                seen.add(rid)
                tags = r.get("tags", [])
                has_tracking = "_categorized-v2" in tags
                real_tags = [t for t in tags if t != "_categorized-v2"]
                coll = r.get("collection", {})
                cid_val = coll.get("$id", -1) if coll else -1
                needs = (cid_val in (0, -1)) or (not real_tags) or (not (r.get("note") or r.get("description")))

                if not has_tracking and needs:
                    new_pool.append(r)
                elif has_tracking:
                    lu_str = r.get("lastUpdate", "")
                    try:
                        lu = datetime.fromisoformat(lu_str.replace("Z", "+00:00"))
                    except:
                        lu = datetime.now(timezone.utc)
                    pool = filler_p1 if lu < CUTOFF_24H else filler_p2
                    pool.append(r)

            page += 1
            if len(items) < PERPAGE:
                break
        except Exception as e:
            print(f"  ⚠ col[{cid}]: {str(e)[:60]}", flush=True)
            time.sleep(2)
            break
    # After scanning collection 0 (all bookmarks), skip remaining collections
    if cid == 0:
        print(f"  (scanned {len(non_empty) - 1} collections skipped — all bookmarks already seen via _id=0)", flush=True)
        break
    time.sleep(0.3)

filler_p1.sort(key=lambda r: r.get("lastUpdate", ""))
filler_p2.sort(key=lambda r: r.get("lastUpdate", ""))

final = new_pool[:100]
if len(final) < 100:
    final.extend(filler_p1[:100 - len(final)])
if len(final) < 100:
    final.extend(filler_p2[:100 - len(final)])

domains = Counter(r.get("domain", "") for r in final)
print(f"\nScan: {time.time()-t0:.0f}s | new={len(new_pool)} f1={len(filler_p1)} f2={len(filler_p2)} batch={len(final)}", flush=True)
print(f"Top domains: {', '.join(f'{d}({c})' for d,c in domains.most_common(5))}", flush=True)

os.makedirs(CACHE, exist_ok=True)
state = {
    "collections": {str(c["_id"]): {"title": c["title"],
        "parent": c.get("parent", {}).get("$id") if c.get("parent") else None,
        "count": c.get("count", 0)} for c in all_colls},
    "tags": [t["_id"] for t in tags_data],
    "tag_counts": {t["_id"]: t.get("count", 0) for t in tags_data},
    "final_list": [{"_id": r["_id"], "title": r.get("title",""), "link": r.get("link",""),
        "domain": r.get("domain",""), "tags": r.get("tags",[]), "note": r.get("note",""),
        "description": r.get("description",""), "collection": r.get("collection"),
        "lastUpdate": r.get("lastUpdate","")} for r in final],
}
with open(STATE_PATH, "w") as f:
    json.dump(state, f, indent=2)
print(f"State: {STATE_PATH}")
