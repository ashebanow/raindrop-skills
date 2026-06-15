#!/usr/bin/env python3
"""
Raindrop.io API helper — avoids bash $expansion issues with tokens.
Usage: python3 raindrop_api.py <action> [args]

Actions:
  user                    Get current user info
  collections             List all collections
  tags                    List all tags with counts
  raindrops <collection>  List raindrops in a collection (default: 0 = Unsorted)
  get <id>                Get a single raindrop
  update <id> <json>      Update a raindrop (JSON body)
  create-collection <json> Create a new collection (JSON body)
  merge-tags <source> <target>  Reassign all bookmarks from source tag to target tag

Environment:
  RAINDROP_TOKEN — set in .env or shell (sourced automatically via `set -a; source .env; set +a`)
"""

import json, os, sys, urllib.request, urllib.error

# Import shared constants
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import API_BASE, get_token

def api(method, path, data=None):
    """CLI-style API call: exits on error (unlike shared module's api() which returns None)."""
    url = f"{API_BASE}{path}"
    token = get_token()

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
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]

    if action == "user":
        result = api("GET", "/user")
        u = result["user"]
        print(f"User: {u['fullName']} ({u['email']})")
        print(f"  ID: {u['_id']}")
        print(f"  Pro: {u.get('pro', False)}")
        for g in u.get("groups", []):
            print(f"  Group '{g['title']}': {len(g.get('collections', []))} root collections")
            for cid in g.get("collections", []):
                print(f"    - root collection ID: {cid}")

    elif action == "children":
        """Get all child collections (those with parent.$id set)."""
        result = api("GET", "/collections/childrens")
        items = result.get("items", [])
        print(f"Child collections: {len(items)}")
        for c in sorted(items, key=lambda x: x.get("title", "")):
            parent = c.get("parent", {})
            pid = parent.get("$id", "?") if parent else "?"
            print(f"  [{c['_id']}] '{c['title']}' parent=[{pid}] ({c.get('count', 0)} bookmarks)")

    elif action == "collections":
        # Fetch root + children separately, then merge
        root_result = api("GET", "/collections")
        child_result = api("GET", "/collections/childrens")
        
        # Merge all into one tree
        all_items = root_result.get("items", []) + child_result.get("items", [])
        
        tree = {}
        for c in all_items:
            parent = c.get("parent", {})
            pid = parent.get("$id") if parent else None
            tree[c["_id"]] = {
                "title": c["title"],
                "parent": pid,
                "count": c.get("count", 0),
                "children": []
            }
        
        # Build parent-child links
        root_ids = []
        for cid, info in tree.items():
            if info["parent"] and info["parent"] in tree:
                tree[info["parent"]]["children"].append(cid)
            else:
                root_ids.append(cid)

        def print_tree(node_ids, indent=0):
            for cid in node_ids:
                info = tree.get(cid, {})
                prefix = "  " * indent
                print(f"{prefix}[{cid}] {info.get('title', '?')} ({info.get('count', 0)} bookmarks)")
                if info.get("children"):
                    print_tree(info["children"], indent + 1)

        print(f"Total collections: {len(tree)} (root: {len(root_ids)}, total items: {len(all_items)})")
        print_tree(root_ids)

    elif action == "tags":
        result = api("GET", "/tags/0")
        items = result.get("items", [])
        print(f"{'Tag':<30} {'Count':>6}")
        print("-" * 38)
        for t in sorted(items, key=lambda x: -x.get("count", 0)):
            print(f"{t.get('_id', '?'):<30} {t.get('count', 0):>6}")
        print(f"\nTotal: {len(items)} tags")

    elif action == "raindrops":
        collection_id = sys.argv[2] if len(sys.argv) > 2 else "0"
        perpage = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        page = 0
        all_items = []
        while True:
            result = api("GET", f"/raindrops/{collection_id}?perpage={perpage}&page={page}")
            items = result.get("items", [])
            if not items:
                break
            all_items.extend(items)
            page += 1
            if len(items) < perpage:
                break
        print(json.dumps(all_items, indent=2))

    elif action == "get":
        rid = sys.argv[2]
        result = api("GET", f"/raindrop/{rid}")
        print(json.dumps(result.get("item", {}), indent=2))

    elif action == "update":
        rid = sys.argv[2]
        data = json.loads(sys.argv[3])
        result = api("PUT", f"/raindrop/{rid}", data)
        print(json.dumps(result, indent=2))

    elif action == "create-collection":
        data = json.loads(sys.argv[2])
        result = api("POST", "/collection", data)
        print(json.dumps(result, indent=2))

    elif action == "merge-tags":
        """Reassign all bookmarks tagged with <source> to use <target> instead, then remove <source>."""
        source_tag = sys.argv[2]
        target_tag = sys.argv[3]
        
        # Find all bookmarks with the source tag
        # Raindrop's /raindrops endpoint doesn't filter by tag directly in the API,
        # so we iterate all collections and check tags client-side
        print(f"Searching for bookmarks tagged '{source_tag}'...")
        collections = api("GET", "/collections").get("items", [])
        
        affected = 0
        for coll in collections:
            cid = coll["_id"]
            page = 0
            while True:
                result = api("GET", f"/raindrops/{cid}?perpage=50&page={page}")
                items = result.get("items", [])
                if not items:
                    break
                for rd in items:
                    tags = rd.get("tags", [])
                    if source_tag in tags:
                        new_tags = [t for t in tags if t != source_tag]
                        if target_tag not in new_tags:
                            new_tags.append(target_tag)
                        api("PUT", f"/raindrop/{rd['_id']}", {"tags": new_tags})
                        affected += 1
                        print(f"  [{rd['_id']}] {rd.get('title','?')[:50]} — '{source_tag}' → '{target_tag}'")
                page += 1
                if len(items) < 50:
                    break
        
        print(f"\nDone. {affected} bookmark(s) updated.")
        if affected > 0:
            # Clean up: remove the source tag entirely
            api("DELETE", f"/tag/{source_tag}")
            print(f"Tag '{source_tag}' removed.")

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)
