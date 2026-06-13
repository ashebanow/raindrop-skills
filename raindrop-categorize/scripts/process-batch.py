#!/usr/bin/env python3
"""
Process saved bookmark batch from scan-batch.py — write notes, add tags,
add _categorized-v2 tracking tag. Runs in batch mode, pacing updates to
avoid rate limits. Updates audit log on each change.

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/process-batch.py [--dry-run]

State file (from scan-batch.py): ~/.hermes/cache/raindrop-state.json
Audit log: ~/.hermes/cache/raindrop-audit-log.jsonl
Tag mapping: references/tag-mapping.md
"""
import json, os, urllib.request, re, time, sys
from datetime import datetime, timezone

CACHE = os.path.expanduser("~/.hermes/cache")
STATE_PATH = f"{CACHE}/raindrop-state.json"
LOG_PATH = f"{CACHE}/raindrop-audit-log.jsonl"
DRY_RUN = "--dry-run" in sys.argv

token = os.environ.get("RAINDROP_TOKEN", "")
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")

# Load state
with open(STATE_PATH) as f:
    state = json.load(f)

# Load tag mapping from reference file
TAG_RULES = []
mapping_path = os.path.join(os.path.dirname(__file__), "..", "references", "tag-mapping.md")
if os.path.exists(mapping_path):
    with open(mapping_path) as f:
        for line in f:
            m = re.match(r'^\| `([^`]+)` \| `([^`]+)` \|$', line)
            if m:
                TAG_RULES.append((m.group(1), m.group(2)))
print(f"Loaded {len(TAG_RULES)} tag rules", flush=True)

def api(method, path, data=None, retries=3):
    """PUT/POST/GET against the Raindrop API with bounded retries.

    Returns the parsed JSON dict on success, or ``None`` if the call
    failed after exhausting retries (HTTP error, network error, timeout,
    or malformed JSON). Callers should treat ``None`` as a failed update
    and continue with the next bookmark — the audit log will not be
    touched for failed items.
    """
    url = f"https://api.raindrop.io/rest/v1{path}"
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
            # 4xx (except 429) is a deterministic client error — don't retry
            if 400 <= e.code < 500 and e.code != 429:
                last_err = f"HTTP {e.code}"
                break
            last_err = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            last_err = f"URLError: {e.reason}"
        except (TimeoutError, json.JSONDecodeError, ValueError) as e:
            last_err = f"{type(e).__name__}: {e}"
        except Exception as e:
            # Catch-all so a single bad bookmark never aborts the batch
            last_err = f"{type(e).__name__}: {e}"
        # Exponential backoff before retrying
        time.sleep(0.5 * (2 ** attempt))
    if last_err:
        print(f"  ⚠ api({method} {path}) failed after {retries} attempts: {last_err}", flush=True)
    return None

def infer_tags(title, domain):
    text = (title + " " + (domain or "")).lower()
    matched = []
    for pattern, tag in TAG_RULES:
        if re.search(pattern, text):
            if tag not in matched:
                matched.append(tag)
    return ["_categorized-v2"] + matched[:4]

def infer_note(title, domain, link):
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

def log_entry(action, fields):
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "run_id": RUN_ID, "action": action, **fields}
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

final = state["final_list"][:100]
total = len(final)

t0 = time.time()
ok, fail = 0, 0

print(f"Processing {total} bookmarks{' (DRY RUN)' if DRY_RUN else ''}...", flush=True)

for i, r in enumerate(final):
    rid = r["_id"]
    title = r.get("title", "?")
    domain = r.get("domain", "")
    link = r.get("link", "")

    tags = infer_tags(title, domain)
    note = infer_note(title, domain, link)
    payload = {"note": note, "description": "", "tags": tags}

    if DRY_RUN:
        print(f"  [{i+1}/{total}] {title[:60]} → tags: {[t for t in tags if t != '_categorized-v2']}")
        ok += 1
    else:
        result = api("PUT", f"/raindrop/{rid}", payload)
        if result and result.get("result"):
            log_entry("update_raindrop", {
                "raindrop_id": rid, "title": title[:80],
                "fields_changed": ["note", "description", "tags"],
                "note_preview": note[:100], "tags": tags,
            })
            ok += 1
        else:
            fail += 1

    time.sleep(0.15)  # Pacing: ~6-7 updates/sec

    if (i + 1) % 25 == 0:
        print(f"  [{i+1}/{total}] {ok} ok, {fail} fail", flush=True)

t = time.time() - t0
print(f"\nDone in {t:.0f}s | {ok} updated, {fail} failed | {t/max(ok,1):.1f}s per bookmark", flush=True)
