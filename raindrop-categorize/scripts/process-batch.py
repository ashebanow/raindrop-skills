#!/usr/bin/env python3
"""
Process saved bookmark batch from scan-batch.py — full Phase 3 pipeline:

  Phase 3a — Update note (and clear description)
  Phase 3b — Assign collection (if currently Unsorted, using keyword map)
  Phase 3c — Update tags (without the tracking tag)
  Phase 3d — Add _categorized-v2 tracking tag (ONLY if 3a, 3b, 3c all
             succeeded; otherwise the bookmark stays in the pool for
             next run)

If any of 3a/3b/3c fails to write to the API — or if 3b has no keyword
match — the tracking tag is NOT applied. The bookmark will be picked up
again on the next run (it's still missing whatever the failed phase was
supposed to write, so it remains eligible per scan-batch.py's filter).

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/process-batch.py [--dry-run]

State file (from scan-batch.py): ~/.hermes/cache/raindrop-state.json
Audit log: ~/.hermes/cache/raindrop-audit-log.jsonl
No-match file: ~/.hermes/cache/raindrop-no-match.json
Tag mapping: references/tag-mapping.md
Collection keyword map: references/collection-keyword-mapping.md
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

CACHE = os.path.expanduser("~/.hermes/cache")
STATE_PATH = f"{CACHE}/raindrop-state.json"
LOG_PATH = f"{CACHE}/raindrop-audit-log.jsonl"
NO_MATCH_PATH = f"{CACHE}/raindrop-no-match.json"
DRY_RUN = "--dry-run" in sys.argv

BASE = "https://api.raindrop.io/rest/v1"
TRACKING_TAG = "_categorized-v2"
TRACKING_TAG_VERSION = "v2"

token = os.environ.get("RAINDROP_TOKEN", "")
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")

# --- Tag mapping (loaded from references/tag-mapping.md) --------------------- #

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TAG_MAPPING_PATH = os.path.join(SCRIPT_DIR, "..", "references", "tag-mapping.md")


def load_tag_rules():
    """Load (regex_pattern, tag_name) pairs from references/tag-mapping.md."""
    """Load (regex_pattern, tag_name) pairs from references/tag-mapping.md."""
    rules = []
    if not os.path.exists(TAG_MAPPING_PATH):
        return rules
    with open(TAG_MAPPING_PATH, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^\| `([^`]+)` \| `([^`]+)` \|$", line)
            if m:
                rules.append((m.group(1), m.group(2)))
    return rules


TAG_RULES = load_tag_rules()
print(f"Loaded {len(TAG_RULES)} tag rules", flush=True)

# --- Collection keyword map (Phase 3b) -------------------------------------- #
# Mirrors references/collection-keyword-mapping.md. Hardcoded here so the
# script doesn't depend on the markdown parsing at runtime, and so the
# map is reviewed alongside the script in code review.

COLLECTION_KEYWORD_MAP = [
    (["nix", "nixos", "nixpkgs", "home-manager", "nix-darwin"], 70857518, "NixOS"),
    (["programming", "code", "git", "github", "golang", "rust", "python", "javascript"], 70857519, "Programming"),
    (["homelab", "self-host", "proxmox", "docker", "kubernetes", "k8s"], 70857516, "Homelab & Self-Hosting"),
    (["recipe", "cooking", "food", "kitchen", "cuisine"], 70857521, "Food & Drink"),
    (["health", "fitness", "exercise", "nutrition", "doctor", "medical", "wellness"], 70857523, "Health & Wellness"),
    (["travel", "hotel", "flight", "vacation", "trip", "destination"], 41357283, "Travel"),
    (["linux", "os", "firmware", "openwrt", "gl-inet", "router"], 70857517, "Firmware & OS"),
    (["home", "living", "house", "garden", "furniture", "decor", "renovation"], 70857525, "Home & Living"),
    (["shopping", "deal", "buy", "amazon", "product"], 70857522, "Shopping & Lifestyle"),
    (["desktop", "ui", "gtk", "hyprland", "sway", "i3", "wayland", "ricing", "theme", "dotfile"], 70861622, "Desktop & UI"),
    (["macos", "mac", "apple", "homebrew", "brew"], 70864186, "macOS"),
    (["security", "privacy", "vpn", "encrypt", "password", "firewall", "auth"], 70864189, "Security & Privacy"),
    (["ai", "llm", "gpt", "claude", "openai", "machine.learning", "ml"], 70864187, "AI"),
    (["music", "song", "spotify", "band", "album", "audio", "podcast"], 70864185, "Music"),
    (["frontend", "css", "tailwind", "react", "vue", "web.design", "svelte"], 70864184, "Frontend"),
    (["database", "sql", "postgres", "mysql", "sqlite", "redis", "mongo"], 70859700, "Database"),
]


# --- Raindrop API helper ---------------------------------------------------- #

def api(method, path, data=None, retries=3):
    """PUT/POST/GET against the Raindrop API with bounded retries.

    Returns the parsed JSON dict on success, or ``None`` if the call
    failed after exhausting retries. Callers should treat ``None`` as
    a failed write and skip any dependent phases.
    """
    """PUT/POST/GET against the Raindrop API with bounded retries.

    Returns the parsed JSON dict on success, or ``None`` if the call
    failed after exhausting retries. Callers should treat ``None`` as
    a failed write and skip any dependent phases.
    """
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data else None
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                last_err = f"HTTP {e.code}"
                break
            last_err = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            last_err = f"URLError: {e.reason}"
        except (TimeoutError, json.JSONDecodeError, ValueError) as e:
            last_err = f"{type(e).__name__}: {e}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(0.5 * (2 ** attempt))
    if last_err:
        print(f"  ⚠ api({method} {path}) failed after {retries} attempts: {last_err}", flush=True)
    return None


# --- Inference helpers ------------------------------------------------------ #

def infer_real_tags(title: str, domain: str) -> list[str]:
    """Infer real (non-tracking) tags from title + domain via tag-mapping.md."""
    text = (title + " " + (domain or "")).lower()
    matched: list[str] = []
    for pattern, tag in TAG_RULES:
        if re.search(pattern, text) and tag not in matched:
            matched.append(tag)
            if len(matched) >= 4:
                break
    return matched


def infer_note(title: str, domain: str, link: str) -> str:
    d = (domain or "").lower()
    if "github" in d or "gitlab" in d or "codeberg" in d:
        return f"Git repository: {title}."
    if "youtube" in d:
        return f"Video: {title}."
    if "reddit" in d:
        return f"Reddit post: {title}."
    if "npmjs" in d:
        return f"npm package: {title}."
    if "crates.io" in d:
        return f"Rust crate: {title}."
    return f"Bookmark: {title}."


def find_collection(title: str, domain: str):
    """First-match-wins keyword lookup against the root collection map.

    Returns (collection_id, collection_title) tuple, or None.
    """
    """First-match-wins keyword lookup against the root collection map."""
    text = (title + " " + (domain or "")).lower()
    for keywords, coll_id, coll_title in COLLECTION_KEYWORD_MAP:
        if any(kw in text for kw in keywords):
            return (coll_id, coll_title)
    return None


# --- Persistence helpers ---------------------------------------------------- #

def log_entry(action, fields):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN_ID,
        "action": action,
        **fields,
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def add_to_no_match(rid, title):
    """Add a (rid, title) pair to the no-match file. Returns True if added."""
    data = []
    if os.path.exists(NO_MATCH_PATH):
        try:
            data = json.loads(open(NO_MATCH_PATH, encoding="utf-8").read())
        except (json.JSONDecodeError, OSError):
            data = []
    if not isinstance(data, list):
        data = []
    if any(isinstance(e, list) and len(e) >= 1 and e[0] == rid for e in data):
        return False
    data.append([rid, title])
    os.makedirs(os.path.dirname(NO_MATCH_PATH), exist_ok=True)
    with open(NO_MATCH_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True


# --- Main pipeline ---------------------------------------------------------- #

def load_state():
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def process_one(bookmark: dict):
    """Process a single bookmark through Phases 3a → 3d.

    Returns one of:
      "tagged"   — 3a, 3b (or skipped), 3c, 3d all succeeded
      "deferred" — at least one phase failed; tracking tag NOT applied
      "skipped"  — bookmark already has the tracking tag (defensive)
    """
    """Process a single bookmark through Phases 3a → 3d.

    Returns one of:
      "tagged"   — 3a, 3b (or skipped), 3c, 3d all succeeded
      "deferred" — at least one phase failed; tracking tag NOT applied
      "skipped"  — bookmark already has the tracking tag (defensive)
    """
    rid = bookmark["_id"]
    title = bookmark.get("title", "?")
    domain = bookmark.get("domain", "")
    link = bookmark.get("link", "")
    existing_tags = bookmark.get("tags", []) or []

    if TRACKING_TAG in existing_tags:
        return "skipped"

    note = infer_note(title, domain, link)
    real_tags = infer_real_tags(title, domain)

    current_coll = bookmark.get("collection") or {}
    current_coll_id = current_coll.get("$id")
    is_unsorted = current_coll_id in (None, -1, 0)

    # Track per-phase outcomes
    phase_3a_ok = False
    # 3b: "skipped" if bookmark is already in a real collection,
    #     "matched" / "no_match" / "failed" if currently unsorted
    phase_3b_state = "skipped"
    phase_3c_ok = False

    # --- Phase 3a: note + clear description ---
    result = api("PUT", f"/raindrop/{rid}", {"note": note, "description": ""})
    if result and result.get("result"):
        phase_3a_ok = True
        if not DRY_RUN:
            log_entry("update_raindrop", {
                "raindrop_id": rid,
                "title": title[:80],
                "fields_changed": ["note", "description"],
                "note_preview": note[:100],
            })
    else:
        # Without 3a succeeding, 3b has no semantic content to match
        # against, and tracking the failure is moot. Bail early.
        return "deferred"

    # --- Phase 3b: assign collection (only if currently Unsorted) ---
    if is_unsorted:
        match = find_collection(title, domain)
        if match is None:
            phase_3b_state = "no_match"
            if not DRY_RUN:
                added = add_to_no_match(rid, title)
                if added:
                    log_entry("no_match", {
                        "raindrop_id": rid,
                        "title": title[:80],
                        "domain": domain,
                    })
        else:
            coll_id, coll_title = match
            result = api("PUT", f"/raindrop/{rid}", {"collection": {"$id": coll_id}})
            if result and result.get("result"):
                phase_3b_state = "matched"
                if not DRY_RUN:
                    log_entry("update_raindrop", {
                        "raindrop_id": rid,
                        "title": title[:80],
                        "fields_changed": ["collection"],
                        "collection_id": coll_id,
                        "collection_title": coll_title,
                    })
            else:
                phase_3b_state = "failed"

    # --- Phase 3c: real tags (without _categorized-v2) ---
    result = api("PUT", f"/raindrop/{rid}", {"tags": real_tags})
    if result and result.get("result"):
        phase_3c_ok = True
        if not DRY_RUN:
            log_entry("update_raindrop", {
                "raindrop_id": rid,
                "title": title[:80],
                "fields_changed": ["tags"],
                "tags": real_tags,
            })

    # --- Phase 3d: tracking tag (only if 3a, 3b-or-skipped, 3c all succeeded) ---
    if phase_3a_ok and phase_3b_state in ("skipped", "matched") and phase_3c_ok:
        final_tags = real_tags + [TRACKING_TAG]
        result = api("PUT", f"/raindrop/{rid}", {"tags": final_tags})
        if result and result.get("result"):
            if not DRY_RUN:
                log_entry("update_raindrop", {
                    "raindrop_id": rid,
                    "title": title[:80],
                    "fields_changed": ["tags"],
                    "tags": final_tags,
                    "tracking_tag_added": True,
                })
            return "tagged"

    return "deferred"


def main() -> int:
    state = load_state()
    final = state.get("final_list", [])[:100]
    total = len(final)

    t0 = time.time()
    counts = {"tagged": 0, "deferred": 0, "skipped": 0}

    mode = " (DRY RUN)" if DRY_RUN else ""
    print(f"Processing {total} bookmarks{mode}...", flush=True)

    for i, r in enumerate(final):
        if DRY_RUN:
            # In dry-run, only do the inference; never call the API
            real = infer_real_tags(r.get("title", ""), r.get("domain", ""))
            note = infer_note(r.get("title", ""), r.get("domain", ""), r.get("link", ""))
            current_coll = r.get("collection") or {}
            is_unsorted = current_coll.get("$id") in (None, -1, 0)
            match = find_collection(r.get("title", ""), r.get("domain", "")) if is_unsorted else None
            coll_str = f" → {match[1]}" if match else (" → (no match)" if is_unsorted else " → (already in collection)")
            print(f"  [{i+1}/{total}] {r.get('title', '?')[:50]}{coll_str}  tags: {real}")
            counts["tagged" if match or not is_unsorted else "deferred"] += 1
        else:
            outcome = process_one(r)
            counts[outcome] += 1
            # Light progress line
            if (i + 1) % 10 == 0:
                print(
                    f"  [{i+1}/{total}] tagged={counts['tagged']} "
                    f"deferred={counts['deferred']} skipped={counts['skipped']}",
                    flush=True,
                )

        time.sleep(0.25)  # Pacing: 4 req/sec worst case (4 PUTs per bookmark)

    elapsed = time.time() - t0
    print(
        f"\nDone in {elapsed:.0f}s | "
        f"{counts['tagged']} tagged, "
        f"{counts['deferred']} deferred, "
        f"{counts['skipped']} skipped | "
        f"{elapsed/max(1, sum(counts.values())):.1f}s per bookmark",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
