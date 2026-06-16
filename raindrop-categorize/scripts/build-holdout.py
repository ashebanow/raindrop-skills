#!/usr/bin/env python3
"""
Interactive holdout set builder for raindrop-categorize.

Presents bookmarks one at a time for confirmation. Single-key input (no Enter).
Resumable — progress saved after every confirmation.

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/build-holdout.py

Controls:
  y        — confirm current assignment is correct
  n        — current assignment is wrong, show alternatives
  1-5      — pick a suggested alternative collection
  s        — skip this bookmark (leave for later)
  q        — save progress and quit (resume later)
  d        — done (mark holdout as complete)
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

# --- Paths ---
CACHE = os.path.expanduser("~/.hermes/cache")
HOLDOUT_PATH = f"{CACHE}/raindrop-holdout.json"
STATE_PATH = f"{CACHE}/raindrop-state.json"
NO_MATCH_PATH = f"{CACHE}/raindrop-no-match.json"

# --- Shared module ---
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import api_get, TRACKING_TAG, API_BASE

# --- Rules ---
_rules_path = os.path.join(_repo_root, "raindrop-categorize", "references", "raindrop-rules.json")
_rules_data = {}
if os.path.exists(_rules_path):
    with open(_rules_path) as f:
        _rules_data = json.load(f)
_COLLECTION_KEYWORDS = _rules_data.get("collection_keywords", [])
_TAG_KEYWORDS = _rules_data.get("tag_keywords", {})

TARGET = 100
MIN_PER_COLLECTION = 2


# ── Terminal helpers ────────────────────────────────────────────────

def clear_line():
    """Clear current line and move cursor to start."""
    sys.stdout.write("\033[K")


def move_up(n=1):
    sys.stdout.write(f"\033[{n}A")


def move_down(n=1):
    sys.stdout.write(f"\033[{n}B")


def get_key(prompt="") -> str:
    """Read a single keypress without Enter. Returns the key character."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    # macOS/Linux: read 1 byte from stdin
    import termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch.lower() if ch else ""


# ── Data loading ────────────────────────────────────────────────────

def load_holdout() -> dict:
    """Load existing holdout. Returns dict with 'entries' list and 'metadata'."""
    if os.path.exists(HOLDOUT_PATH):
        try:
            with open(HOLDOUT_PATH) as f:
                data = json.load(f)
            if isinstance(data, dict) and "entries" in data:
                return data
            # Legacy: list of entries
            return {"entries": data, "metadata": {"version": 1}}
        except (json.JSONDecodeError, OSError):
            pass
    return {"entries": [], "metadata": {"version": 1, "complete": False}}


def save_holdout(holdout: dict):
    os.makedirs(os.path.dirname(HOLDOUT_PATH), exist_ok=True)
    holdout["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    holdout["metadata"]["total"] = len(holdout["entries"])
    with open(HOLDOUT_PATH, "w") as f:
        json.dump(holdout, f, indent=2)


def fetch_collections():
    """Fetch all collections from Raindrop API."""
    roots = api_get("/collections") or {}
    children = api_get("/collections/childrens") or {}
    all_c = []
    for item in roots.get("items", []):
        all_c.append({
            "id": item["_id"], "title": item["title"],
            "count": item.get("count", 0), "parent": None,
        })
    for item in children.get("items", []):
        parent = item.get("parent", {})
        all_c.append({
            "id": item["_id"], "title": item["title"],
            "count": item.get("count", 0),
            "parent": parent.get("$id") if parent else None,
        })
    return all_c


def fetch_all_bookmarks():
    """Fetch ALL bookmarks via the bulk endpoint (few API calls, not per-collection)."""
    from raindrop_common import fetch_all_raindrops as _bulk_fetch
    return _bulk_fetch(collection_id=0)


def sample_for_holdout(all_bookmarks, collections, existing_ids, target=TARGET):
    """Select a diverse subset of bookmarks for confirmation."""
    # Group by collection
    by_coll = defaultdict(list)
    for r in all_bookmarks:
        coll_id = r.get("collection", {}).get("$id")
        coll_id = coll_id if coll_id else -1
        tags = [t for t in (r.get("tags") or []) if t != TRACKING_TAG]
        note = (r.get("note") or "").strip()
        by_coll[coll_id].append(r)

    # Build collection name lookup
    coll_names = {c["id"]: c["title"] for c in collections}
    coll_names[-1] = "Unsorted"

    # Pick candidates: aim for MIN_PER_COLLECTION per non-empty collection
    candidates = []
    coll_seen = defaultdict(int)
    for coll_id, items in sorted(by_coll.items(), key=lambda x: -len(x[1])):
        name = coll_names.get(coll_id, f"Collection-{coll_id}")
        needed = max(0, MIN_PER_COLLECTION - coll_seen.get(name, 0))
        pick = min(needed, len(items))
        for r in items[:pick]:
            if r["_id"] not in existing_ids:
                candidates.append(r)
                coll_seen[name] += 1
        if len(candidates) >= target:
            break

    # If we're short, top up with random from any collection
    if len(candidates) < target:
        more_needed = target - len(candidates)
        extras = [r for r in all_bookmarks if r["_id"] not in existing_ids
                  and r not in candidates][:more_needed]
        candidates.extend(extras)

    # Shuffle for variety
    import random
    random.shuffle(candidates)
    return candidates[:target]


def keyword_match_collections(title, domain, url, collections, top_n=5):
    """Find the top N collection matches by keyword overlap.

    Uses live collection names from the API (collections list) for display,
    not the potentially stale names in the rules file.
    """
    # Build live name lookup
    live_names = {}
    for c in collections:
        live_names[c["id"]] = c["title"]

    text = ((title or "") + " " + (domain or "") + " " + (url or "")).lower()
    scored = []
    for entry in _COLLECTION_KEYWORDS:
        keywords = entry.get("keywords", [])
        coll_id = entry.get("collection_id")
        # Use live name from API, fall back to rules file name
        coll_title = live_names.get(coll_id, entry.get("collection_title", "?"))
        score = sum(1 for kw in keywords if kw in text)
        # Downweight over-broad keywords that match everything
        if "github" in keywords and "github" in text and "programming" in coll_title.lower():
            score *= 0.5  # github is too broad as a signal for Programming
        if score > 0:
            scored.append((score, coll_id, coll_title))
    scored.sort(key=lambda x: -x[0])

    # Also add the current collection name if it wasn't matched
    result = [(s, cid, t) for s, cid, t in scored[:top_n]]
    return result


# ── Tag inference (mirrors verify-holdout.py) ────────────────────────

def infer_tags(title: str, domain: str):
    """Infer tags from title + domain using tag_keywords from the rules file."""
    text = ((title or "") + " " + (domain or "")).lower()
    matched = []
    for tag_name, keywords in _TAG_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                if tag_name not in matched:
                    matched.append(tag_name)
                break
        if len(matched) >= 6:
            break
    return matched


def tag_review_prompt(existing_tags: list, inferred_tags: list) -> tuple:
    """Quick tag quality check. Returns (tags_to_save, tags_need_review).

    Shows current tags and inferred suggestions, asks if tags are adequate.
    If not, marks for later tag-specific holdout pass.
    """
    inferred = [t for t in inferred_tags if t not in existing_tags]
    print(f"  Tags: {', '.join(existing_tags[:6]) or '(none)'}")
    if inferred:
        print(f"  Suggested: {', '.join(inferred[:4])}")
    key = get_key("  Tags OK? [y/1=yes, n/2=no]: ")
    print()
    if key in ("n", "2"):
        return existing_tags, True  # existing tags stored, flagged for review
    return existing_tags, False  # existing tags stored, considered correct


def find_collections_matching_name(name_fragment, collections):
    """Fuzzy find collections by name fragment."""
    frag = name_fragment.lower().strip()
    matches = []
    for c in collections:
        if frag and (frag in c["title"].lower() or c["title"].lower() in frag):
            matches.append(c)
        # Also check if the fragment matches a parent path
    return matches[:10]


# ── Main loop ───────────────────────────────────────────────────────

def main():
    holdout = load_holdout()
    existing_ids = {e["raindrop_id"] for e in holdout.get("entries", [])}

    if holdout.get("metadata", {}).get("complete"):
        print(f"Holdout already complete: {len(holdout['entries'])} entries.")
        return 0

    print("=== Raindrop Holdout Builder ===\n", flush=True)
    print(f"Existing holdout: {len(existing_ids)} entries")
    print(f"Target: {TARGET} entries\n", flush=True)
    print("Fetching collections and bookmarks...", flush=True)

    collections = fetch_collections()
    print(f"  Collections: {len(collections)}", flush=True)

    print(f"  Fetching all bookmarks via bulk endpoint...", flush=True)
    import time
    time.sleep(2)  # let rate-limit window reset
    all_bookmarks = fetch_all_bookmarks()
    print(f"  Bookmarks fetched: {len(all_bookmarks)}", flush=True)

    candidates = sample_for_holdout(all_bookmarks, collections, existing_ids)
    print(f"  Candidates for review: {len(candidates)}\n", flush=True)

    if not candidates:
        print("No candidates to review. Holdout complete?")
        return 0

    completed = len(existing_ids)
    total = min(TARGET, completed + len(candidates))

    # Build quick lookup
    coll_lookup = {}
    for c in collections:
        coll_lookup[c["id"]] = c["title"]
    coll_lookup[-1] = "Unsorted"
    coll_lookup[0] = "Unsorted"

    print("Controls: [1] quick-confirm (skip tag review)  [y] confirm + review tags", flush=True)
    print("          [2-5] alternative collection  [n] type name  [s]kip  [q]uit  [d]one\n", flush=True)

    for idx, r in enumerate(candidates):
        rid = r["_id"]
        title = r.get("title", "?")
        url = r.get("link", "")
        domain = r.get("domain", "")
        coll = r.get("collection", {}) or {}
        coll_id = coll.get("$id") if coll else -1
        coll_name = coll_lookup.get(coll_id, f"ID:{coll_id}")
        tags = [t for t in (r.get("tags") or []) if t != TRACKING_TAG]
        note = (r.get("note") or "")[:80]

        current = completed + 1
        pct = int(current / total * 10)
        bar = "█" * pct + "░" * (10 - pct)

        print(f"─── Bookmark {current}/{total}  [{bar}] ───")
        print(f"  Title: {title[:72]}")
        print(f"  URL:   {url[:72]}" if url else "")
        print(f"  Collection: {coll_name} (ID:{coll_id})")
        if tags:
            print(f"  Tags:  {', '.join(tags[:6])}")
        if note:
            print(f"  Note:  {note}")

        # Show top suggestions — always include current as [1]
        suggestions = keyword_match_collections(title, domain, url, collections)
        # Prepend current collection as option [1] if not already present
        has_current = any(sid == coll_id for _, sid, _ in suggestions[:5])
        if not has_current and coll_id:
            cur_title = coll_lookup.get(coll_id, f"ID:{coll_id}")
            suggestions.insert(0, (999, coll_id, cur_title))
        tag = "current" if not has_current else "matched"
        print(f"  Options: [1] {suggestions[0][2]} \u2190 {tag}"[:72])
        for i, (s, sid, stitle) in enumerate(suggestions[1:5], 2):
            marker = " ← current" if sid == coll_id else ""
            print(f"          [{i}] {stitle}{marker}"[:72])
        if len(suggestions) > 0:
            print(f"  ([1] keep current, [2-5] alternative, or [n] for more choices)"[:72])

        # Prompt
        while True:
            key = get_key("\n  Confirm? [1/2-5/y/n/s/q/d]: ")

            if key == "1":
                # Quick-confirm: accept current collection + tags, no tag review
                entry = {
                    "raindrop_id": rid,
                    "title": title[:200],
                    "domain": domain,
                    "confirmed_collection_id": coll_id,
                    "confirmed_collection_title": coll_name,
                    "confirmed_tags": tags,
                    "tags_need_review": False,
                    "verified_by": "user",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                }
                holdout["entries"].append(entry)
                completed += 1
                save_holdout(holdout)
                clear_line()
                print(f" ✅  ({completed}/{total})")
                break

            if key == "y":
                # Tag review before saving
                inferred = infer_tags(title, domain)
                final_tags, tags_need_review = tag_review_prompt(tags, inferred)
                entry = {
                    "raindrop_id": rid,
                    "title": title[:200],
                    "domain": domain,
                    "confirmed_collection_id": coll_id,
                    "confirmed_collection_title": coll_name,
                    "confirmed_tags": final_tags,
                    "tags_need_review": tags_need_review,
                    "verified_by": "user",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                }
                holdout["entries"].append(entry)
                completed += 1
                save_holdout(holdout)
                clear_line()
                print(f" ✅  ({completed}/{total})")
                break

            elif key == "n":
                print()  # newline after raw input
                print("  Choose alternative:")
                for i, (s, sid, stitle) in enumerate(suggestions[:5], 1):
                    print(f"    [{i}] {stitle}")
                if len(suggestions) > 5:
                    print(f"    [6-9] more...")
                print(f"    [t] type a collection name")
                print(f"    [s] skip")

                key2 = get_key("  Pick [1-5/t/s]: ")
                if key2 in "12345" and suggestions:
                    pick = int(key2) - 1
                    if pick < len(suggestions):
                        _, alt_id, alt_title = suggestions[pick]
                        # User already opted into review via 'n' — always check tags
                        inferred = infer_tags(title, domain)
                        final_tags, tags_need_review = tag_review_prompt(tags, inferred)
                        entry = {
                            "raindrop_id": rid,
                            "title": title[:200],
                            "domain": domain,
                            "confirmed_collection_id": alt_id,
                            "confirmed_collection_title": alt_title,
                            "confirmed_tags": final_tags,
                            "tags_need_review": tags_need_review,
                            "verified_by": "user",
                            "verified_at": datetime.now(timezone.utc).isoformat(),
                            "corrected": True,
                            "original_collection": coll_name,
                        }
                        holdout["entries"].append(entry)
                        completed += 1
                        save_holdout(holdout)
                        clear_line()
                        print(f" ✅ Corrected to {alt_title}  ({completed}/{total})")
                        break
                    print("  Invalid choice, skipping.")
                    break
                elif key2 == "t":
                    print()
                    name = input("  Type collection name (or Enter to skip): ").strip()
                    if name:
                        matches = find_collections_matching_name(name, collections)
                        if matches:
                            print("  Matches:")
                            for i, mc in enumerate(matches[:8], 1):
                                pid = mc.get("parent")
                                parent_name = coll_lookup.get(pid, "")
                                parent_str = f" (under {parent_name})" if parent_name else ""
                                print(f"    [{i}] {mc['title']}{parent_str}")
                            pick3 = get_key("  Pick [1-8], Enter to skip: ")
                            if pick3 in "12345678":
                                pick_i = int(pick3) - 1
                                if pick_i < len(matches):
                                    mc = matches[pick_i]
                                    inferred = infer_tags(title, domain)
                                    final_tags, tags_need_review = tag_review_prompt(tags, inferred)
                                    entry = {
                                        "raindrop_id": rid,
                                        "title": title[:200],
                                        "domain": domain,
                                        "confirmed_collection_id": mc["id"],
                                        "confirmed_collection_title": mc["title"],
                                        "confirmed_tags": final_tags,
                                        "tags_need_review": tags_need_review,
                                        "verified_by": "user",
                                        "verified_at": datetime.now(timezone.utc).isoformat(),
                                        "corrected": True,
                                        "original_collection": coll_name,
                                    }
                                    holdout["entries"].append(entry)
                                    completed += 1
                                    save_holdout(holdout)
                                    clear_line()
                                    print(f" ✅ Corrected to {mc['title']}  ({completed}/{total})")
                                    break
                        else:
                            print("  No matches found. Skipping.")
                    break
                elif key2 == "s":
                    print("  Skipped.")
                    break
                else:
                    print("  Skipped.")
                    break

            elif key in "12345" and suggestions:
                pick = int(key) - 1
                if pick < len(suggestions):
                    _, alt_id, alt_title = suggestions[pick]
                    # Tag review
                    inferred = infer_tags(title, domain)
                    final_tags, tags_need_review = tag_review_prompt(tags, inferred)
                    entry = {
                        "raindrop_id": rid,
                        "title": title[:200],
                        "domain": domain,
                        "confirmed_collection_id": alt_id,
                        "confirmed_collection_title": alt_title,
                        "confirmed_tags": final_tags,
                        "tags_need_review": tags_need_review,
                        "verified_by": "user",
                        "verified_at": datetime.now(timezone.utc).isoformat(),
                        "corrected": True,
                        "original_collection": coll_name,
                    }
                    holdout["entries"].append(entry)
                    completed += 1
                    save_holdout(holdout)
                    clear_line()
                    print(f" ✅ {alt_title}  ({completed}/{total})")
                    break
                clear_line()
                print("  Invalid, skipping.")
                break

            elif key == "s":
                print("  Skipped.")
                break

            elif key == "q":
                save_holdout(holdout)
                print(f"\n  Saved {completed} entries. Run again to resume.")
                return 0

            elif key == "d":
                holdout.setdefault("metadata", {})["complete"] = True
                save_holdout(holdout)
                print(f"\n  Holdout marked complete: {completed} entries.")
                return 0

            else:
                print("  (y/n/1-5/s/q/d)")

    print(f"\n=== Session complete. {completed} entries in holdout. ===")
    if completed >= TARGET:
        holdout.setdefault("metadata", {})["complete"] = True
        save_holdout(holdout)
        print("Holdout target reached! Marked as complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
