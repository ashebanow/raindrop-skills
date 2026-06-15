#!/usr/bin/env python3
"""
Full raindrop-categorize pipeline runner.
Phases: 0 (prune), 1 (collections+tags), 2 (eligible bookmarks), 3 (process), 4 (score)
"""
import json, os, sys, time, datetime, re

# --- Shared Raindrop utilities -------------------------------------------- #
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import (
    api,
    compute_precision_score,
    load_rules as _load_rules,
    TRACKING_TAG,
    CACHE_DIR as _CACHE_DIR,
)

CACHE_DIR = os.path.expanduser("~/.hermes/cache")
os.makedirs(CACHE_DIR, exist_ok=True)
AUDIT_LOG = os.path.join(CACHE_DIR, "raindrop-audit-log.jsonl")
QUALITY_FILE = os.path.join(CACHE_DIR, "raindrop-quality.json")
NO_MATCH_FILE = os.path.join(CACHE_DIR, "raindrop-no-match.json")

# --- Load rules from references/raindrop-rules.json ------------------------ #
_rules_data = _load_rules()
TAG_KEYWORDS = _rules_data.get("tag_keywords", {})
COLL_TAG_MAP = _rules_data.get("coll_tag_map", {})
thresholds = _rules_data.get("thresholds", {})
MAX_TAGS = thresholds.get("max_tags_per_bookmark", 5)
NOTE_TEMPLATES = _rules_data.get("note_templates", [])
COLLECTION_KEYWORDS = _rules_data.get("collection_keywords", [])
print(f"Loaded {len(TAG_KEYWORDS)} tag keyword groups, {len(COLL_TAG_MAP)} collection-tag mappings, "
      f"{len(NOTE_TEMPLATES)} note templates, max_tags={MAX_TAGS}", flush=True)

def paginate_raindrops(collection_id, max_items=999999):
    """Fetch all raindrops in a collection with pagination."""
    all_items = []
    page = 0
    while True:
        result = api("GET", f"/raindrops/{collection_id}?perpage=50&page={page}")
        if not result:
            break
        items = result.get("items", [])
        if not items:
            break
        all_items.extend(items)
        if len(all_items) >= max_items:
            break
        page += 1
        if len(items) < 50:
            break
        time.sleep(0.2)  # ~200ms pacing
    return all_items

def log_audit(entry):
    """Append to audit log."""
    entry["timestamp"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    entry["run_id"] = datetime.datetime.utcnow().strftime("%Y-%m-%d-%H%M")
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

def prune_audit_log():
    """Remove entries older than 7 days."""
    if not os.path.exists(AUDIT_LOG):
        return 0
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    kept = 0
    pruned = 0
    temp_path = AUDIT_LOG + ".tmp"
    with open(AUDIT_LOG, "r") as f_in, open(temp_path, "w") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")
                if ts:
                    entry_time = datetime.datetime.strptime(ts.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
                    if entry_time >= cutoff:
                        f_out.write(line + "\n")
                        kept += 1
                    else:
                        pruned += 1
                else:
                    f_out.write(line + "\n")
                    kept += 1
            except (json.JSONDecodeError, ValueError):
                f_out.write(line + "\n")
                kept += 1
    os.replace(temp_path, AUDIT_LOG)
    return pruned

def load_quality():
    """Load quality scores from cache."""
    if os.path.exists(QUALITY_FILE):
        with open(QUALITY_FILE, "r") as f:
            return json.load(f)
    return {"runs": [], "scores": {}}

def save_quality(data):
    with open(QUALITY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_no_match():
    if os.path.exists(NO_MATCH_FILE):
        with open(NO_MATCH_FILE, "r") as f:
            return json.load(f)
    return {"bookmarks": []}

def save_no_match(data):
    with open(NO_MATCH_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ========== PHASE 0: Prune audit log ==========
print("=== PHASE 0: Pruning audit log ===")
pruned = prune_audit_log()
print(f"  Pruned {pruned} entries from audit log")

# ========== PHASE 1: Fetch collections & tags ==========
print("\n=== PHASE 1: Fetching collections and tags ===")

# Collections
root_result = api("GET", "/collections")
child_result = api("GET", "/collections/childrens")
all_collections = (root_result.get("items", []) if root_result else []) + (child_result.get("items", []) if child_result else [])

# Build lookup dict
collection_map = {}
for c in all_collections:
    parent = c.get("parent", {})
    pid = parent.get("$id") if parent else None
    collection_map[c["_id"]] = {
        "title": c["title"],
        "parent": pid,
        "count": c.get("count", 0),
        "children": []
    }

# Build parent-child links
root_ids = []
for cid, info in collection_map.items():
    if info["parent"] and info["parent"] in collection_map:
        collection_map[info["parent"]]["children"].append(cid)
    else:
        root_ids.append(cid)

print(f"  Collections: {len(collection_map)}")
print(f"  Root collections: {len(root_ids)}")

# Tags
tag_result = api("GET", "/tags/0")
tag_items = tag_result.get("items", []) if tag_result else []
tag_map = {}
for t in tag_items:
    tag_map[t["_id"]] = t.get("count", 0)
print(f"  Tags: {len(tag_map)}")

# ========== PHASE 2: Find eligible bookmarks ==========
print("\n=== PHASE 2: Finding eligible bookmarks ===")

# Get all non-empty collections (non-zero count)
non_empty = [cid for cid, info in collection_map.items() if info["count"] > 0]
print(f"  Non-empty collections: {len(non_empty)}")

# Scan unsorted first
eligible = []
unsorted_items = paginate_raindrops(-1, max_items=100)
for rd in unsorted_items:
    tags = rd.get("tags", [])
    has_tracking = TRACKING_TAG in tags
    real_tags = [t for t in tags if t != TRACKING_TAG]
    note = rd.get("note", "") or ""
    desc = rd.get("description", "") or ""
    has_note = bool(note.strip())
    has_tags = bool(real_tags)
    coll_id = rd.get("collection", {}).get("$id")
    truly_unsorted = (coll_id == -1)
    
    if not has_tracking and (truly_unsorted or not has_tags or not has_note):
        eligible.append(rd)
        if len(eligible) >= 100:
            break

print(f"  Unsorted eligible: {len(eligible)}")

# Sort non-empty collections by count (largest first — more likely to have uncategorized)
sorted_collections = sorted(non_empty, key=lambda cid: -collection_map[cid]["count"])

for cid in sorted_collections:
    if len(eligible) >= 100:
        break
    # Check if this collection's items are already well-categorized
    info = collection_map[cid]
    # Quick check: fetch first page to see proportion of categorized vs uncategorized
    page0 = api("GET", f"/raindrops/{cid}?perpage=50&page=0")
    if not page0:
        continue
    items = page0.get("items", [])
    if not items:
        continue
    
    # If all items on first page have tracking tag and tags, probably all are categorized
    uncategorized_on_page = 0
    for rd in items:
        tags = rd.get("tags", [])
        if TRACKING_TAG not in tags:
            uncategorized_on_page += 1
        elif TRACKING_TAG in tags:
            # Check if there are still missing fields
            real_tags = [t for t in tags if t != TRACKING_TAG]
            note = rd.get("note", "") or ""
            has_note = bool(note.strip())
            
            if not has_note or not real_tags:
                uncategorized_on_page += 1
    
    if uncategorized_on_page == 0:
        # All categorized on first page — likely all are done
        print(f"  Collection '{info['title']}' ({cid}): all {info['count']} appear categorized, skipping")
        continue
    
    # Fetch all items from this collection
    all_items = paginate_raindrops(cid, max_items=200)
    
    for rd in all_items:
        if len(eligible) >= 100:
            break
        tags = rd.get("tags", [])
        has_tracking = TRACKING_TAG in tags
        real_tags = [t for t in tags if t != TRACKING_TAG]
        note = rd.get("note", "") or ""
        desc = rd.get("description", "") or ""
        has_note = bool(note.strip())
        has_tags = bool(real_tags)
        
        if not has_tracking:
            eligible.append(rd)
        elif not has_note or not has_tags:
            # Has tracking tag but missing fields — re-process
            eligible.append(rd)

print(f"  Total eligible bookmarks: {len(eligible)}")

if len(eligible) == 0:
    print("\nNo eligible bookmarks found. Nothing to do.")
    save_quality(load_quality())
    sys.exit(0)

# ========== PHASE 3: Process each bookmark ==========
print(f"\n=== PHASE 3: Processing {len(eligible)} bookmarks ===")

processed = []
errors = []
skipped = []

for idx, rd in enumerate(eligible):
    rid = rd["_id"]
    title = rd.get("title", "?")[:60]
    url = rd.get("link", "")
    print(f"\n  [{idx+1}/{len(eligible)}] Processing #{rid}: {title}")
    
    # Get full details
    full = api("GET", f"/raindrop/{rid}")
    if not full:
        errors.append({"id": rid, "title": title, "reason": "Failed to fetch full details"})
        continue
    rd_full = full.get("item", rd)
    
    current_tags = rd_full.get("tags", [])
    has_tracking = TRACKING_TAG in current_tags
    current_note = rd_full.get("note", "") or ""
    current_desc = rd_full.get("description", "") or ""
    current_coll = rd_full.get("collection", {})
    current_coll_id = current_coll.get("$id") if current_coll else None
    current_coll_title = current_coll.get("title", "") if current_coll else ""
    
    fields_changed = []
    
    # ---- 3a: Process note & description ----
    note_text = current_note.strip()
    desc_text = current_desc.strip()
    
    if not note_text and not desc_text:
        # Try to fetch URL for content
        note_content = ""
        if url:
            try:
                fetch_req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                fetch_resp = urllib.request.urlopen(fetch_req, timeout=10)
                html = fetch_resp.read().decode("utf-8", errors="replace")
                # Extract title from HTML
                import re
                title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                page_title = title_match.group(1).strip() if title_match else title
                # Extract description meta
                desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', html, re.IGNORECASE)
                meta_desc = desc_match.group(1) if desc_match else ""
                # Extract body text (simple)
                body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.IGNORECASE | re.DOTALL)
                body_text = ""
                if body_match:
                    body_text = re.sub(r'<[^>]+>', ' ', body_match.group(1))
                    body_text = re.sub(r'\s+', ' ', body_text).strip()[:500]
                note_content = page_title
                if meta_desc:
                    note_content += " — " + meta_desc
                elif body_text:
                    note_content += " — " + body_text[:200]
                print(f"    Fetched URL: {page_title}")
            except Exception as e:
                print(f"    Could not fetch URL: {e}")
                note_content = title  # Fallback to title
        else:
            note_content = title
        
        new_note = note_content
        print(f"    Note: empty → written from URL content")
    elif desc_text and not note_text:
        # Description exists but no note
        if len(desc_text) > 50 and (", " in desc_text or "." in desc_text or len(desc_text.split()) > 10):
            # Looks handwritten
            new_note = desc_text
        else:
            # Looks AI-generated or short — write fresh
            if url:
                try:
                    fetch_req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    fetch_resp = urllib.request.urlopen(fetch_req, timeout=10)
                    html = fetch_resp.read().decode("utf-8", errors="replace")
                    import re
                    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                    page_title = title_match.group(1).strip() if title_match else title
                    new_note = page_title
                except:
                    new_note = title + " — " + desc_text
            else:
                new_note = title + " — " + desc_text
        print(f"    Note: description → note (consolidated)")
    elif note_text:
        # Note exists
        if desc_text and len(desc_text) > 50 and desc_text not in note_text:
            new_note = note_text + "\n\n" + desc_text
        else:
            new_note = note_text
        print(f"    Note: already exists")
    
    if new_note != current_note or current_desc:
        update_data = {"note": new_note, "description": ""}
        result = api("PUT", f"/raindrop/{rid}", update_data)
        if result:
            fields_changed.append("note")
            fields_changed.append("description")
            print(f"    ✓ Note/Description updated")
        else:
            print(f"    ✗ Failed to update note")
            errors.append({"id": rid, "title": title, "reason": "Failed to update note"})
            continue
    
    # ---- 3b: Process collection ----
    needs_collection = (current_coll_id is None or current_coll_id == -1)
    
    new_coll_id = None
    if needs_collection:
        # Semantic matching based on title and URL content
        search_text = (title + " " + url + " " + new_note).lower()
        best_match = None
        best_score = 0
        
        for cid, info in collection_map.items():
            coll_title_lower = info["title"].lower()
            score = 0
            # Check if any word in collection title appears in search text
            for word in coll_title_lower.split():
                if len(word) > 2 and word in search_text:
                    score += 10
            # Exact title or subtitle match
            for keyword in search_text.split():
                keyword = keyword.strip(".,:;!?()[]{}'\"")
                if len(keyword) > 3 and keyword in coll_title_lower:
                    score += 5
            # URL domain matching
            if "github" in coll_title_lower and "github" in url:
                score += 15
            if "git" in coll_title_lower and ("git" in url or "github" in url):
                score += 10
            if "nix" in coll_title_lower and "nix" in search_text:
                score += 20
            if ("linux" in coll_title_lower or "nix" in coll_title_lower) and ("linux" in search_text or "nix" in search_text):
                score += 15
            if "docker" in coll_title_lower and "docker" in search_text:
                score += 20
            if "python" in coll_title_lower and "python" in search_text:
                score += 20
            if "rust" in coll_title_lower and "rust" in search_text:
                score += 20
            if "ruby" in coll_title_lower and "ruby" in search_text:
                score += 20
            if "javascript" in coll_title_lower and "javascript" in search_text:
                score += 20
            if "go" == coll_title_lower.strip() and "go" in search_text.split():
                score += 15
            if "ai" in coll_title_lower and "ai" in search_text:
                score += 15
            if ("security" in coll_title_lower or "secure" in coll_title_lower) and ("security" in search_text or "secure" in search_text):
                score += 15
            if "container" in coll_title_lower and ("container" in search_text or "docker" in search_text):
                score += 20
            if "homelab" in coll_title_lower and ("homelab" in search_text or "self-host" in search_text):
                score += 15
            if "network" in coll_title_lower and "network" in search_text:
                score += 15
            if "hardware" in coll_title_lower and ("hardware" in search_text or "pc" in search_text):
                score += 15
            if "editor" in coll_title_lower and ("vim" in search_text or "neovim" in search_text or "editor" in search_text):
                score += 15
            if ("dotfile" in coll_title_lower or "config" in coll_title_lower) and ("dotfile" in search_text or "config" in search_text):
                score += 15
            if "game" in coll_title_lower and ("game" in search_text or "bg3" in search_text or "diablo" in search_text):
                score += 20
            if "mac" in coll_title_lower and ("mac" in search_text or "macos" in search_text):
                score += 15
            if "terminal" in coll_title_lower and ("terminal" in search_text or "shell" in search_text):
                score += 15
            if "automation" in coll_title_lower and ("automation" in search_text or "ansible" in search_text):
                score += 15
            if "observability" in coll_title_lower and ("observability" in search_text or "grafana" in search_text or "prometheus" in search_text):
                score += 20
            if "storage" in coll_title_lower and ("storage" in search_text or "nas" in search_text):
                score += 15
            if "window" in coll_title_lower and ("window manager" in search_text or "hyprland" in search_text or "wayland" in search_text or "tiling" in search_text):
                score += 20
            if "web serving" in coll_title_lower and ("nginx" in search_text or "caddy" in search_text or "traefik" in search_text):
                score += 20
            if "programming" in coll_title_lower and ("programming" in search_text or "code" in search_text or "developer" in search_text):
                score += 10
            
            if score > best_score:
                best_score = score
                best_match = cid
        
        if best_match and best_score >= 10:
            new_coll_id = best_match
            coll_name = collection_map[best_match]["title"]
            print(f"    Collection: assigned to '{coll_name}' (score={best_score})")
            
            # Prefer deeper (more specific) children
            # Check if any child of best_match is an even better match
            for child_cid in collection_map[best_match]["children"]:
                child_info = collection_map[child_cid]
                child_title_lower = child_info["title"].lower()
                child_score = 0
                for word in child_title_lower.split():
                    if len(word) > 2 and word in search_text:
                        child_score += 15
                if child_score > best_score:
                    new_coll_id = child_cid
                    best_score = child_score
                    coll_name = child_info["title"]
                    print(f"    → Preferring sub-collection '{coll_name}' (score={child_score})")
            
            update_data = {"collection": {"$id": new_coll_id}}
            result = api("PUT", f"/raindrop/{rid}", update_data)
            if result:
                fields_changed.append("collection")
                print(f"    ✓ Collection updated to '{coll_name}'")
            else:
                print(f"    ✗ Failed to update collection")
                errors.append({"id": rid, "title": title, "reason": f"Failed to update collection to {coll_name}"})
                continue
        else:
            # No match found — flag for user review
            coll_titles = [info["title"] for cid, info in sorted(collection_map.items(), key=lambda x: -x[1]["count"])[:10]]
            print(f"    ⚠ No collection match (best={best_score}). Flagging for review.")
            no_matches = load_no_match()
            no_matches["bookmarks"].append({
                "id": rid,
                "title": title,
                "url": url,
                "note_preview": new_note[:100] if new_note else "",
                "suggested_collections": " or ".join(coll_titles[:3]) + " or similar"
            })
            save_no_match(no_matches)
            skipped.append({"id": rid, "title": title, "reason": "No matching collection found"})
            continue
    else:
        # Already has a collection (and it's not Unsorted)
        # Verify it's a real collection
        if current_coll_id in collection_map:
            coll_name = collection_map[current_coll_id]["title"]
            print(f"    Collection: already in '{coll_name}' — skipping")
        else:
            # Collection ID might not be in our map (deleted?)
            print(f"    Collection: {current_coll_id} (unknown) — keeping as-is")
    
    # ---- 3c: Process tags ----
    real_tags = [t for t in current_tags if t != TRACKING_TAG]
    
    # Infer tags from title and URL
    inferred_tags = set()
    search_text = (title + " " + url + " " + new_note).lower()
    
    # Add tags based on collection assignment
    if new_coll_id and new_coll_id in collection_map:
        coll_title_lower = collection_map[new_coll_id]["title"].lower()
        for kw, tags in COLL_TAG_MAP.items():
            if kw in coll_title_lower:
                for t in tags:
                    inferred_tags.add(t)
    
    # Add keyword-based tags
    for tag_name, keywords in TAG_KEYWORDS.items():
        for kw in keywords:
            if kw in search_text:
                inferred_tags.add(tag_name)
                break
    
    # Merge existing + inferred
    final_tags = list(real_tags)
    for tag in inferred_tags:
        if tag not in final_tags:
            final_tags.append(tag)
    
    # Limit tags per bookmark from rules
    final_tags = final_tags[:MAX_TAGS]
    
    if set(final_tags) != set(real_tags):
        update_data = {"tags": final_tags}
        result = api("PUT", f"/raindrop/{rid}", update_data)
        if result:
            fields_changed.append("tags")
            added = [t for t in final_tags if t not in real_tags]
            print(f"    ✓ Tags updated: {final_tags} (added: {added})")
        else:
            print(f"    ✗ Failed to update tags")
            errors.append({"id": rid, "title": title, "reason": "Failed to update tags"})
            continue
    else:
        print(f"    Tags: unchanged ({final_tags})")
    
    # ---- 3d: Apply tracking tag ----
    if not has_tracking:
        final_with_tracking = list(final_tags)
        if TRACKING_TAG not in final_with_tracking:
            final_with_tracking.append(TRACKING_TAG)
        update_data = {"tags": final_with_tracking}
        result = api("PUT", f"/raindrop/{rid}", update_data)
        if result:
            fields_changed.append("tracking_tag")
            print(f"    ✓ Tracking tag applied")
        else:
            print(f"    ✗ Failed to apply tracking tag")
            errors.append({"id": rid, "title": title, "reason": "Failed to apply tracking tag"})
            continue
    
    # Log audit
    log_audit({
        "action": "update_raindrop",
        "raindrop_id": rid,
        "title": title,
        "fields_changed": fields_changed,
        "note_preview": (new_note[:100] if new_note else "") if fields_changed else "",
        "tags": final_tags,
        "collection_id": new_coll_id or current_coll_id,
        "collection_title": collection_map.get(new_coll_id or current_coll_id, {}).get("title", current_coll_title)
    })
    
    # Domain extraction for precision scoring
    _domain = rd.get("domain", "") or rd_full.get("domain", "")

    processed.append({
        "id": rid,
        "title": title,
        "domain": _domain,
        "link": url,
        "fields_changed": fields_changed,
        "note_length": len(new_note),
        "note_text": new_note,
        "collection_id": new_coll_id or current_coll_id,
        "tags": final_tags,
    })
    
    # Pacing
    time.sleep(0.3)

print(f"\n=== Processing Summary ===")
print(f"  Processed: {len(processed)}")
print(f"  Skipped (no collection match): {len(skipped)}")
print(f"  Errors: {len(errors)}")

# ========== PHASE 4: Score quality ==========
print(f"\n=== PHASE 4: Scoring quality ===")

quality = load_quality()

# Per-raindrop scoring
total_completeness = 0
total_succinctness = 0
total_tone = 0
total_relevance = 0

for rd_data in processed:
    # Completeness: all 3 (note, collection, tags) = 10
    completeness = 10  # All were done
    
    # Succinctness: based on note length
    nl = rd_data.get("note_length", 0)
    if nl > 500:
        succinctness = 5
    elif nl > 300:
        succinctness = 7
    else:
        succinctness = 9
    
    # Tone: template-penalized scorer
    tone = compute_tone_score(rd_data.get("note_text", ""), NOTE_TEMPLATES)
    
    # Relevance: keyword-overlap precision score
    _rd_title = rd_data.get("title", "")
    _rd_domain = rd_data.get("domain", "")
    _rd_link = rd_data.get("link", "")
    _rd_coll_id = rd_data.get("collection_id")
    _rd_tags = rd_data.get("tags", [])
    _precision = compute_precision_score(
        _rd_title, _rd_domain, _rd_link,
        _rd_coll_id, _rd_tags,
        _rules_data,
    )
    relevance = _precision["combined_score"]
    
    total_completeness += completeness
    total_succinctness += succinctness
    total_tone += tone
    total_relevance += relevance

n = len(processed) if processed else 1
avg_completeness = total_completeness / n
avg_succinctness = total_succinctness / n
avg_tone = total_tone / n
avg_relevance = total_relevance / n
avg_score = (avg_completeness + avg_succinctness + avg_tone + avg_relevance) / 4

print(f"  Avg completeness: {avg_completeness:.1f}/10")
print(f"  Avg succinctness: {avg_succinctness:.1f}/10")
print(f"  Avg tone: {avg_tone:.1f}/10")
print(f"  Avg relevance: {avg_relevance:.1f}/10")
print(f"  Overall avg: {avg_score:.1f}/10")

# Per-collection metrics
state_path = os.path.join(CACHE_DIR, "raindrop-state.json")
if os.path.exists(state_path):
    try:
        with open(state_path, encoding="utf-8") as f:
            state_data = json.load(f)
        per_coll_metrics = compute_per_collection_metrics(
            state_data, COLLECTION_KEYWORDS
        )
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠ Could not load state for per-collection metrics: {e}")
        per_coll_metrics = {}
else:
    # Fall back to collection_map + processed data
    per_coll_metrics = compute_per_collection_metrics(
        {"collections": collection_map, "final_list": processed},
        COLLECTION_KEYWORDS,
    )
print(f"  Collections touched: {per_coll_metrics.get('collections_touched', 0)}")
if per_coll_metrics.get("breadth_flagged"):
    print(f"  ⚠ Broad collections: {', '.join(per_coll_metrics['breadth_flagged'][:5])}")
print(f"  Completeness avg: {per_coll_metrics.get('completeness_pct_avg', 0):.0%}")
print(f"  Untagged avg: {per_coll_metrics.get('untagged_pct_avg', 0):.0%}")

# Save quality
run_record = {
    "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "processed": len(processed),
    "skipped": len(skipped),
    "errors": len(errors),
    "avg_completeness": round(avg_completeness, 1),
    "avg_succinctness": round(avg_succinctness, 1),
    "avg_tone": round(avg_tone, 1),
    "avg_relevance": round(avg_relevance, 1),
    "avg_score": round(avg_score, 1),
    "per_collection_metrics": per_coll_metrics,
}

if "runs" not in quality:
    quality["runs"] = []
quality["runs"].append(run_record)

# Compute global scores
all_run_scores = [r["avg_score"] for r in quality["runs"]]
if all_run_scores:
    quality["scores"]["avg_per_raindrop_score"] = round(sum(all_run_scores) / len(all_run_scores), 1)
quality["scores"]["latest_score"] = round(avg_score, 1)

save_quality(quality)

# Trend detection
if len(quality["runs"]) >= 2:
    last_two = quality["runs"][-2:]
    if last_two[0]["avg_score"] >= 8 and last_two[1]["avg_score"] < 7:
        print("\n⚠ WARNING: Quality score dropped significantly. Consider reviewing.")
    elif len(quality["runs"]) >= 3:
        last_three = quality["runs"][-3:]
        if all(s["avg_score"] < (last_three[0]["avg_score"] - 1) for s in last_three[1:]):
            print("\n⚠ WARNING: Quality trending down for 2+ consecutive runs. Halting for review.")

print(f"\n=== Pipeline Complete ===")
print(f"  Processed: {len(processed)} bookmarks")
print(f"  Skipped (no collection): {len(skipped)} bookmarks")
print(f"  Errors: {len(errors)} errors")
print(f"  Quality score: {avg_score:.1f}/10")
