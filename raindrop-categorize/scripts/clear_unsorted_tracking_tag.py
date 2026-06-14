#!/usr/bin/env python3
"""
One-shot cleanup: remove the _categorized-v2 tracking tag from bookmarks
in the Unsorted collection that were marked "complete" by an older
version of process-batch.py but never actually moved out of Unsorted
(it never did collection assignment — see SKILL.md Phase 3b).

The corrected process-batch.py now gates the tracking tag on all three
phases succeeding (note, collection, tags), so it can re-process these
bookmarks from scratch on the next run.

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/clear_unsorted_tracking_tag.py [--dry-run]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.raindrop.io/rest/v1"
TRACKING_TAG = "_categorized-v2"
DRY_RUN = "--dry-run" in sys.argv

token = os.environ.get("RAINDROP_TOKEN", "")
if not token:
    print("ERROR: RAINDROP_TOKEN not set", file=sys.stderr)
    sys.exit(1)


def api(method, path, data=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"HTTP {e.code}: {err}", file=sys.stderr)
        return None


# Fetch all Unsorted bookmarks (collection -1)
print("Fetching Unsorted bookmarks...", flush=True)
all_items = []
# (api() is defined above)


# Fetch all Unsorted bookmarks (collection -1)
print("Fetching Unsorted bookmarks...", flush=True)
all_items: list = []
page = 0
while True:
    result = api("GET", f"/raindrops/-1?perpage=50&page={page}")
    if not result:
        break
    items = result.get("items", [])
    if not items:
        break
    all_items.extend(items)
    page += 1
    if len(items) < 50:
        break

print(f"  Found {len(all_items)} bookmarks in Unsorted", flush=True)

with_tag = [b for b in all_items if TRACKING_TAG in b.get("tags", [])]
print(f"  Of which {len(with_tag)} carry the stale {TRACKING_TAG} tag", flush=True)

if not with_tag:
    print("Nothing to clean up.")
    sys.exit(0)

if DRY_RUN:
    print("\nDRY RUN — would clear tracking tag from:", flush=True)
    for b in with_tag:
        print(f"  [{b['_id']}] {b.get('title', '?')[:60]}", flush=True)
    sys.exit(0)

# Clear the tag (preserving other tags)
ok = 0
fail = 0
for b in with_tag:
    rid = b["_id"]
    new_tags = [t for t in b.get("tags", []) if t != TRACKING_TAG]
    result = api("PUT", f"/raindrop/{rid}", {"tags": new_tags})
    if result and result.get("result"):
        print(f"  ✅ [{rid}] {b.get('title', '?')[:50]}", flush=True)
        ok += 1
    else:
        print(f"  ❌ [{rid}] {b.get('title', '?')[:50]}", flush=True)
        fail += 1
    time.sleep(0.2)  # pacing — 5 req/sec, well under Raindrop's ~120 req/min

print(f"\nDone: {ok} cleared, {fail} failed")
sys.exit(0 if fail == 0 else 1)
