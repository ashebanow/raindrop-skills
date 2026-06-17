#!/usr/bin/env python3
"""
Remove _categorized-v2 tracking tags from all bookmarks.

This resets the tracking state so all previously-processed bookmarks
will be re-processed from scratch with the current improved pipeline.

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/clear-tracking-tags.py [--dry-run]
"""
import sys, os, time

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import fetch_all_raindrops, api_put, TRACKING_TAG

DRY_RUN = "--dry-run" in sys.argv

def main():
    print(f"{'DRY RUN: ' if DRY_RUN else ''}Fetching all bookmarks...", flush=True)
    drops = fetch_all_raindrops()
    print(f"Total: {len(drops)}", flush=True)

    tagged = [d for d in drops if TRACKING_TAG in (d.get("tags") or [])]
    print(f"With {TRACKING_TAG}: {len(tagged)}", flush=True)

    if not tagged:
        print("Nothing to do.")
        return 0

    removed = 0
    errors = 0
    for i, d in enumerate(tagged):
        rid = d["_id"]
        title = (d.get("title") or "?")[:40]
        tags = [t for t in (d.get("tags") or []) if t != TRACKING_TAG]

        if DRY_RUN:
            print(f"  [{i+1}/{len(tagged)}] #{rid} {title} — would remove tag", flush=True)
            removed += 1
        else:
            result = api_put(f"/raindrop/{rid}", {"tags": tags})
            if result and result.get("result"):
                removed += 1
                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(tagged)}] {removed} removed, {errors} errors", flush=True)
            else:
                errors += 1
                print(f"  ✗ #{rid} {title} — API error", flush=True)

        time.sleep(0.25)

    print(f"\nDone. {removed} removed, {errors} errors.", flush=True)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
