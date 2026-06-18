#!/usr/bin/env python3
"""
Apply rule proposals for raindrop-categorize — Phase 4a+4b.

Reads pending proposals, checks auto-approval criteria, and applies
qualifying keyword additions to raindrop-rules.json.

Modes:
  --auto-approve    Auto-approve qualifying proposals
  --dry-run         Show what would be approved without applying anything
  apply <id>        Apply a specific proposal (bypasses auto-approval checks)

Supported proposal types:
  add_keyword       Merge keywords into raindrop-rules.json
  merge_collection  Move all bookmarks from source collection into target
  move_collection   Reparent a collection under a new parent

Auto-approval criteria (ALL must be true):
  1. Proposal type is ``add_keyword``
  2. Evidence from ≥5 no-match bookmarks sharing the same domain
     (``match_count >= 5`` and domain is a real domain)
  3. Target collection has ≥20 existing bookmarks (Raindrop API)
  4. No holdout regression in the last 3 quality records with verification data

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/apply-proposals.py --dry-run
  source .env && export RAINDROP_TOKEN && python3 scripts/apply-proposals.py --auto-approve
  source .env && export RAINDROP_TOKEN && python3 scripts/apply-proposals.py apply <proposal_id>
"""
import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone

# ── Paths ────────────────────────────────────────────────────────────

CACHE = os.path.expanduser("~/.hermes/cache")
PROPOSALS_PATH = f"{CACHE}/raindrop-proposals.json"
CONFIDENCE_PATH = f"{CACHE}/raindrop-confidence.json"
NO_MATCH_PATH = f"{CACHE}/raindrop-no-match.json"
QUALITY_PATH = f"{CACHE}/raindrop-quality.json"
AUDIT_LOG_PATH = f"{CACHE}/raindrop-audit-log.jsonl"

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_PATH = os.path.join(_repo_root, "raindrop-categorize", "references", "raindrop-rules.json")
VERIFY_SCRIPT = os.path.join(_repo_root, "raindrop-categorize", "scripts", "verify-holdout.py")

sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import api_get, api_put, load_rules, fetch_all_raindrops

# How much (as fraction of previous accuracy) constitutes a "regression"
REGRESSION_THRESHOLD = 0.10  # 10%+ drop triggers regression flag


# ── I/O helpers ──────────────────────────────────────────────────────

def load_proposals() -> dict:
    """Load proposals JSON. Returns {'proposals': []} on failure."""
    if not os.path.exists(PROPOSALS_PATH):
        return {"proposals": []}
    try:
        with open(PROPOSALS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠ Could not load proposals: {e}", file=sys.stderr)
        return {"proposals": []}


def save_proposals(data: dict):
    """Write proposals JSON atomically."""
    os.makedirs(os.path.dirname(PROPOSALS_PATH), exist_ok=True)
    tmp = f"{PROPOSALS_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, PROPOSALS_PATH)


def save_rules(rules: dict):
    """Write raindrop-rules.json atomically."""
    tmp = f"{RULES_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)
    os.replace(tmp, RULES_PATH)


def load_quality() -> list:
    """Load quality records. Returns [] on failure."""
    if not os.path.exists(QUALITY_PATH):
        return []
    try:
        with open(QUALITY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def audit_log(action: str, details: dict):
    """Append a JSON line to the audit log."""
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **details,
    }
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(f"  ⚠ Could not write audit log: {e}", file=sys.stderr)


# ── Holdout regression check ─────────────────────────────────────────

def check_holdout_regression() -> bool:
    """Check if there's a regression in holdout verification scores.

    Returns True if no regression detected (criterion passes),
    False if a regression is found.

    Regression = collection_accuracy drops by >= REGRESSION_THRESHOLD (10%)
    between consecutive verification records in the last 3 such records.
    If fewer than 2 records with verification exist, returns True (pass).
    """
    quality = load_quality()
    # Collect records that have verification data with collection_accuracy
    verified = []
    for record in quality:
        v = record.get("verification")
        if v and "collection_accuracy" in v:
            verified.append({
                "run_id": record.get("run_id", "?"),
                "timestamp": record.get("timestamp", ""),
                "collection_accuracy": v["collection_accuracy"],
                "holdout_size": v.get("holdout_size", 0),
            })

    if len(verified) < 2:
        # Not enough data to detect regression — pass
        return True

    # Look at the last 3 verified records (or fewer if that's all we have)
    recent = verified[-3:] if len(verified) >= 3 else verified

    # Check for drops between consecutive records
    for i in range(1, len(recent)):
        prev_acc = recent[i - 1]["collection_accuracy"]
        curr_acc = recent[i]["collection_accuracy"]
        if prev_acc > 0 and curr_acc < prev_acc * (1 - REGRESSION_THRESHOLD):
            print(f"  ⚠ Holdout regression detected: {recent[i-1]['run_id']} "
                  f"({prev_acc:.1%}) → {recent[i]['run_id']} ({curr_acc:.1%})",
                  flush=True)
            return False  # Regression found

    return True  # No regression


# ── Collection bookmark count check ──────────────────────────────────

def get_collection_counts() -> dict:
    """Fetch all collections from Raindrop API and map collection_id -> count.

    Returns {collection_id: int, ...}. On failure returns empty dict.
    """
    try:
        roots = api_get("/collections")
        children = api_get("/collections/childrens")
        all_colls = []
        if roots and "items" in roots:
            all_colls.extend(roots["items"])
        if children and "items" in children:
            all_colls.extend(children["items"])

        return {c["_id"]: c.get("count", 0) for c in all_colls}
    except Exception as e:
        print(f"  ⚠ Failed to fetch collections: {e}", file=sys.stderr)
        return {}


def check_collection_size(collection_id: int, coll_counts: dict, min_size: int = 20) -> bool:
    """Check if a collection has at least min_size bookmarks."""
    count = coll_counts.get(collection_id, 0)
    if count >= min_size:
        return True
    print(f"  ⚠ Collection {collection_id} has only {count} bookmarks "
          f"(need ≥{min_size})", flush=True)
    return False


# ── Auto-approval evaluation ─────────────────────────────────────────

def is_real_domain(domain: str) -> bool:
    """Check if a domain string is a real internet domain (not a placeholder)."""
    if not domain:
        return False
    domain = domain.strip().lower()
    # Placeholder values used by suggest-rules.py
    if domain in ("(title keyword)", "(unknown)", ""):
        return False
    # Must contain at least one dot
    if "." not in domain:
        return False
    # Must have a TLD of at least 2 chars
    parts = domain.split(".")
    if len(parts[-1]) < 2:
        return False
    return True


def check_auto_approval(proposal: dict, coll_counts: dict) -> tuple:
    """Check if a proposal qualifies for auto-approval.

    Returns (approved: bool, reasons: list of str).
    """
    reasons = []

    # Criterion 1: type is add_keyword
    if proposal.get("type") != "add_keyword":
        reasons.append(f"type is '{proposal.get('type')}', not 'add_keyword'")
        return False, reasons

    # Criterion 2: ≥5 no-match bookmarks from the same domain
    domain = proposal.get("domain", "")
    match_count = proposal.get("match_count", 0)
    if not is_real_domain(domain):
        reasons.append(f"domain '{domain}' is not a real domain")
        return False, reasons
    if match_count < 5:
        reasons.append(f"match_count={match_count} < 5")
        return False, reasons

    # Criterion 3: target collection has ≥20 bookmarks
    target_cid = proposal.get("guessed_collection_id")
    if not target_cid:
        reasons.append("no guessed_collection_id")
        return False, reasons
    if not check_collection_size(target_cid, coll_counts):
        reasons.append(f"collection {target_cid} has <20 bookmarks")
        return False, reasons

    # Criterion 4: no holdout regression
    if not check_holdout_regression():
        reasons.append("holdout regression detected")
        return False, reasons

    return True, reasons


# ── Applying a proposal to rules ─────────────────────────────────────

def find_rule_by_collection_id(collection_id: int, rules: dict):
    """Find the rule entry in collection_keywords by collection_id.

    Returns the rule entry dict or None.
    """
    for entry in rules.get("collection_keywords", []):
        if entry.get("collection_id") == collection_id:
            return entry
    return None


def find_rule_by_id(rule_id: str, rules: dict):
    """Find the rule entry in collection_keywords by its id field."""
    for entry in rules.get("collection_keywords", []):
        if entry.get("id") == rule_id:
            return entry
    return None


def reset_confidence_for_rule(rule_id: str):
    """Reset confidence stats for a rule (if confidence file exists).

    If the file doesn't exist, this is a no-op (future-proofing).
    """
    if not os.path.exists(CONFIDENCE_PATH):
        return
    try:
        with open(CONFIDENCE_PATH, encoding="utf-8") as f:
            conf = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    # Reset per-rule stats
    by_rule = conf.get("by_rule", {})
    if rule_id in by_rule:
        by_rule[rule_id] = {
            "hits": 0,
            "misses": 0,
            "last_reset": datetime.now(timezone.utc).isoformat(),
        }
        conf["by_rule"] = by_rule
        with open(CONFIDENCE_PATH, "w", encoding="utf-8") as f:
            json.dump(conf, f, indent=2)
        print(f"  ✓ Reset confidence stats for rule '{rule_id}'", flush=True)


def apply_proposal(proposal: dict, rules: dict) -> dict:
    """Merge proposal keywords into the target rule in the rules dict.

    Modifies ``rules`` in place and returns it.
    """
    target_cid = proposal.get("guessed_collection_id")
    new_keywords = proposal.get("suggested_keywords", [])

    if not target_cid or not new_keywords:
        print(f"  ⚠ Proposal missing guessed_collection_id or suggested_keywords", flush=True)
        return rules

    # Find the target rule
    rule = find_rule_by_collection_id(target_cid, rules)
    if not rule:
        print(f"  ⚠ No rule found for collection_id={target_cid}", flush=True)
        return rules

    rule_id = rule.get("id", f"coll-{target_cid}")

    # Dedup and merge keywords
    existing_keywords = set(k.lower() for k in rule.get("keywords", []))
    added = []
    for kw in new_keywords:
        if kw.lower() not in existing_keywords:
            existing_keywords.add(kw.lower())
            added.append(kw)

    if not added:
        print(f"  ℹ All keywords already present in rule '{rule_id}'", flush=True)
        return rules

    # Update rule
    rule["keywords"] = rule.get("keywords", []) + added
    rule["version"] = rules.get("version", 1)
    rules["version"] = rules.get("version", 1) + 1
    now = datetime.now(timezone.utc).isoformat()
    rules["last_updated"] = now
    rule["last_updated"] = now

    print(f"  ✓ Added {len(added)} keywords to rule '{rule_id}' "
          f"({', '.join(added)})", flush=True)

    # Reset confidence for this rule
    reset_confidence_for_rule(rule_id)

    return rules


def run_verify_holdout() -> dict:
    """Run verify-holdout.py --json and return the parsed result.

    Returns empty dict on failure.
    """
    try:
        result = subprocess.run(
            [sys.executable, VERIFY_SCRIPT, "--json"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ},
        )
        # The output contains the JSON after status messages.
        # We need to find the last JSON block (the verification result).
        # verify-holdout.py prints messages to stdout, then the JSON.
        # Let's try to parse the entire stdout as JSON first.
        out = result.stdout.strip()
        # Find the last { ... } block
        import re as _re
        json_matches = _re.findall(r'\{.*\}', out, _re.DOTALL)
        if json_matches:
            return json.loads(json_matches[-1])

        # Fallback: try the whole output
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            print(f"  ⚠ Could not parse verify-holdout output: {out[:200]}",
                  file=sys.stderr)
            return {}
    except subprocess.TimeoutExpired:
        print("  ⚠ verify-holdout.py timed out", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"  ⚠ verify-holdout.py failed: {e}", file=sys.stderr)
        return {}


# ── Collection resolution helpers ───────────────────────────────────

def _fetch_all_collections_tree() -> dict:
    """Fetch all collections and return a tree for path resolution.

    Returns dict with:
        by_id: {cid: {title, parent_id, count}}
        by_title: {lower_title: [{cid, parent_id, title}, ...]}  # list for ambig
    """
    roots = api_get("/collections")
    children = api_get("/collections/childrens")
    all_colls = []
    if roots and "items" in roots:
        all_colls.extend(roots["items"])
    if children and "items" in children:
        all_colls.extend(children["items"])

    by_id = {}
    by_title = {}
    for c in all_colls:
        cid = c["_id"]
        title = c.get("title", "")
        parent = c.get("parent", {}) or {}
        pid = parent.get("$id")
        entry = {"cid": cid, "title": title, "parent_id": pid, "count": c.get("count", 0)}
        by_id[cid] = entry
        key = title.lower().strip()
        by_title.setdefault(key, []).append(entry)
    return {"by_id": by_id, "by_title": by_title}


def _resolve_collection_path(path: str, tree: dict) -> int:
    """Resolve a path like "Parent > Child" to a collection ID.

    The last segment is the collection title. Earlier segments
    are the parent chain used for disambiguation.

    Returns collection ID (int) or raises ValueError.
    """
    segments = [s.strip() for s in path.split(">")]
    target_title = segments[-1]
    expected_parents = segments[:-1]

    by_title = tree["by_title"]
    by_id = tree["by_id"]

    candidates = by_title.get(target_title.lower(), [])
    if not candidates:
        raise ValueError(f"No collection found with title '{target_title}'")

    if len(candidates) == 1:
        # Single match — verify parent chain if expected
        c = candidates[0]
        if expected_parents:
            _verify_parent_chain(c, expected_parents, by_id)
        return c["cid"]

    # Multiple matches — disambiguate by parent chain
    for c in candidates:
        try:
            _verify_parent_chain(c, expected_parents, by_id)
            return c["cid"]  # first match wins
        except ValueError:
            continue

    raise ValueError(
        f"Could not resolve '{path}': found {len(candidates)} collections "
        f"named '{target_title}' but none match the expected parent chain"
    )


def _verify_parent_chain(entry: dict, expected_parents: list, by_id: dict):
    """Walk up the parent chain and verify each segment matches.

    Raises ValueError on mismatch.
    """
    current = entry
    for expected in reversed(expected_parents):
        pid = current.get("parent_id")
        if pid is None:
            raise ValueError(f"Collection '{entry['title']}' has no parent, expected '{expected}'")
        parent = by_id.get(pid)
        if not parent:
            raise ValueError(f"Parent {pid} not found in tree")
        if parent["title"].lower().strip() != expected.lower().strip():
            raise ValueError(
                f"Expected parent '{expected}', got '{parent['title']}' "
                f"(id={pid})"
            )
        current = parent


def _path_parent(path: str) -> str:
    """Return the parent portion of a path, e.g.
    "Linux & Open Source > NixOS > NixOS Tutorials" -> "Linux & Open Source > NixOS"
    """
    segments = [s.strip() for s in path.split(">")]
    return " > ".join(segments[:-1])


def _path_tail(path: str) -> str:
    """Return the last segment of a path, e.g.
    "Linux & Open Source > NixOS Tutorials" -> "NixOS Tutorials"
    """
    return path.split(">")[-1].strip()


# ── Collection operation handlers ───────────────────────────────────

def do_apply_merge_collection(proposal: dict) -> bool:
    """Move all bookmarks from source_collection to target_collection.

    Does NOT delete the source collection (per SKILL.md rules).
    Returns True on success, False on failure.
    """
    source_path = proposal.get("source_collection")
    target_path = proposal.get("target_collection")

    if not source_path or not target_path:
        print(f"  ⚠ Proposal missing source_collection or target_collection", flush=True)
        return False

    print(f"  Resolving collections...", flush=True)
    tree = _fetch_all_collections_tree()

    try:
        source_id = _resolve_collection_path(source_path, tree)
        target_id = _resolve_collection_path(target_path, tree)
    except ValueError as e:
        print(f"  ❌ Could not resolve collection: {e}", flush=True)
        return False

    source_title = tree["by_id"][source_id]["title"]
    target_title = tree["by_id"][target_id]["title"]
    print(f"    Source: [{source_id}] {source_title}", flush=True)
    print(f"    Target: [{target_id}] {target_title}", flush=True)

    if source_id == target_id:
        print(f"  ⚠ Source and target are the same collection — nothing to do.", flush=True)
        return False

    # Fetch all bookmarks from source
    print(f"  Fetching bookmarks from source...", flush=True)
    bookmarks = fetch_all_raindrops(source_id)
    if not bookmarks:
        print(f"  ℹ Source collection is empty — nothing to move.", flush=True)
        return True

    ids = [b["_id"] for b in bookmarks]
    print(f"  Moving {len(ids)} bookmark(s) to target...", flush=True)

    # Individual updates (Raindrop API has no batch move endpoint)
    success = 0
    for bm in bookmarks:
        r = api_put(f"/raindrop/{bm['_id']}", {"collection": {"$id": target_id}})
        if r:
            success += 1
        time.sleep(0.1)

    if success == len(ids):
        print(f"  ✓ Moved {success} bookmark(s) from '{source_title}' to '{target_title}'", flush=True)
        audit_log("merge_collection", {
            "source_collection": source_path,
            "source_id": source_id,
            "target_collection": target_path,
            "target_id": target_id,
            "bookmarks_moved": success,
        })
        return True
    else:
        print(f"  ❌ Moved {success}/{len(ids)} bookmark(s) — some may remain in source", flush=True)
        return False


def do_apply_move_collection(proposal: dict) -> bool:
    """Reparent a collection to a new parent.

    Returns True on success, False on failure.
    """
    target_path = proposal.get("target_collection")
    new_path = proposal.get("new_path")

    if not target_path or not new_path:
        print(f"  ⚠ Proposal missing target_collection or new_path", flush=True)
        return False

    parent_path = _path_parent(new_path)
    if not parent_path:
        print(f"  ⚠ new_path '{new_path}' has no parent (can't move to root)", flush=True)
        return False

    print(f"  Resolving collections...", flush=True)
    tree = _fetch_all_collections_tree()

    try:
        coll_id = _resolve_collection_path(target_path, tree)
        parent_id = _resolve_collection_path(parent_path, tree)
    except ValueError as e:
        print(f"  ❌ Could not resolve collection: {e}", flush=True)
        return False

    coll_title = tree["by_id"][coll_id]["title"]
    parent_title = tree["by_id"][parent_id]["title"]
    print(f"    Collection to move: [{coll_id}] {coll_title}", flush=True)
    print(f"    New parent:         [{parent_id}] {parent_title}", flush=True)

    if tree["by_id"][coll_id].get("parent_id") == parent_id:
        print(f"  ℹ Collection is already under '{parent_title}' — nothing to do.", flush=True)
        return True

    # Reparent
    print(f"  Reparenting...", flush=True)
    result = api_put(f"/collection/{coll_id}", {"parent": {"$id": parent_id}})

    if result and result.get("result"):
        print(f"  ✓ Moved '{coll_title}' under '{parent_title}'", flush=True)
        audit_log("move_collection", {
            "collection": target_path,
            "collection_id": coll_id,
            "new_parent": parent_path,
            "new_parent_id": parent_id,
        })
        return True
    else:
        print(f"  ❌ Failed to reparent collection", flush=True)
        return False


# ── Main logic ───────────────────────────────────────────────────────

def do_auto_approve(dry_run: bool = False):
    """Auto-approve qualifying proposals.

    Args:
        dry_run: If True, only print what would be approved.
    """
    proposals_data = load_proposals()
    all_proposals = proposals_data.get("proposals", [])

    if not all_proposals:
        print("No proposals found.", flush=True)
        return 0

    # Fetch collection counts from API
    print("Fetching collection bookmark counts from Raindrop API...", flush=True)
    coll_counts = get_collection_counts()
    if not coll_counts:
        print("  ⚠ Could not fetch collection data from API.", flush=True)
        # Continue anyway — collection size check will fail for all proposals
        coll_counts = {}

    pending = [p for p in all_proposals if p.get("status") == "pending"]
    print(f"\nFound {len(pending)} pending proposals out of {len(all_proposals)} total.",
           flush=True)

    # Check holdout regression once
    print("Checking holdout for regression...", flush=True)
    no_regression = check_holdout_regression()
    if not no_regression:
        print("  ⚠ Holdout regression detected — no proposals will auto-approve.\n",
              flush=True)

    qualifying = []
    failing = []

    for proposal in pending:
        pid = proposal.get("id", "?")
        ptype = proposal.get("type", "?")
        approved, reasons = check_auto_approval(proposal, coll_counts)

        if approved:
            qualifying.append(proposal)
            print(f"\n  ✅ [{pid}] AUTO-APPROVE", flush=True)
        else:
            failing.append(proposal)
            if ptype == "add_keyword":
                print(f"\n  ❌ [{pid}] REJECTED: {'; '.join(reasons)}", flush=True)
            else:
                print(f"\n  ⏭️  [{pid}] SKIPPED (type '{ptype}' — auto-approve only handles 'add_keyword')", flush=True)

    print(f"\n{'='*60}", flush=True)
    print(f"Qualifying proposals: {len(qualifying)}/{len(pending)}", flush=True)

    if dry_run or not qualifying:
        if qualifying:
            print(f"\nWould auto-approve:", flush=True)
            for p in qualifying:
                print(f"  [{p['id']}] Add keywords {p.get('suggested_keywords', [])} "
                      f"to rule for collection '{p.get('guessed_collection_title')}' "
                      f"(domain: {p.get('domain')}, {p.get('match_count')} matches)",
                      flush=True)
        if dry_run:
            print("\nDry run — no changes applied.", flush=True)
        return 0

    # ── Apply qualifying proposals ──
    rules = load_rules(RULES_PATH) if os.path.exists(RULES_PATH) else {}
    if not rules:
        print("ERROR: Could not load rules file.", file=sys.stderr)
        return 1

    applied = []
    for proposal in qualifying:
        print(f"\nApplying [{proposal['id']}]...", flush=True)
        rules = apply_proposal(proposal, rules)
        # Mark proposal as auto_approved
        for p in all_proposals:
            if p["id"] == proposal["id"]:
                p["status"] = "auto_approved"
                p["applied_at"] = datetime.now(timezone.utc).isoformat()
                p["completed_at"] = datetime.now(timezone.utc).isoformat()
                p["snapshot"] = {
                    "previous_keywords": list(rule_entry.get("keywords", [])),
                    "previous_version": rules.get("version", 0),
                }
                applied.append(proposal["id"])
                break

    # Save updated rules
    save_rules(rules)
    print(f"\n✓ Saved updated rules to {RULES_PATH}", flush=True)

    # Save updated proposals
    proposals_data["proposals"] = all_proposals
    save_proposals(proposals_data)
    print(f"✓ Updated proposal statuses in {PROPOSALS_PATH}", flush=True)

    # Run verify-holdout for baseline
    print("\nRunning holdout verification for new baseline...", flush=True)
    verification = run_verify_holdout()
    if verification:
        ca = verification.get("collection_accuracy", "?")
        tf1 = verification.get("tag_f1", "?")
        print(f"  Baseline: collection_accuracy={ca:.1%}, tag_f1={tf1:.1%}",
              flush=True)

    # Audit log
    for pid in applied:
        audit_log("auto_approve", {
            "proposal_id": pid,
            "mode": "auto_approve",
        })

    print(f"\n✓ Auto-approved and applied {len(applied)} proposal(s).", flush=True)
    return 0


def do_apply_specific(proposal_id: str):
    """Apply a specific proposal by ID, bypassing auto-approval checks."""
    proposals_data = load_proposals()
    all_proposals = proposals_data.get("proposals", [])

    # Find the proposal
    proposal = None
    for p in all_proposals:
        if p["id"] == proposal_id:
            proposal = p
            break

    if not proposal:
        print(f"ERROR: No proposal found with id '{proposal_id}'", file=sys.stderr)
        return 1

    ptype = proposal.get("type")
    print(f"Applying proposal [{proposal_id}] (type: {ptype})...", flush=True)

    # ── Route by type ──

    if ptype == "add_keyword":
        rules = load_rules(RULES_PATH) if os.path.exists(RULES_PATH) else {}
        if not rules:
            print("ERROR: Could not load rules file.", file=sys.stderr)
            return 1

        rules = apply_proposal(proposal, rules)
        save_rules(rules)

        # Snapshot for revert-regression
        rule_entry = None
        for entry in rules.get("collection_keywords", []):
            if entry.get("id") == proposal.get("rule_id"):
                rule_entry = entry
                break
        snapshot = {
            "previous_keywords": list(rule_entry.get("keywords", [])) if rule_entry else [],
            "previous_version": rules.get("version", 0),
        }

        print("  Running holdout verification for baseline...", flush=True)
        verification = run_verify_holdout()
        if verification:
            snapshot["verification_before"] = verification
            print(f"  Baseline: collection_accuracy={verification.get('collection_accuracy', '?'):.1%}", flush=True)

        for p in all_proposals:
            if p["id"] == proposal_id:
                p["snapshot"] = snapshot
                break

        audit_log("apply", {
            "proposal_id": proposal_id,
            "mode": "manual_apply",
            "type": "add_keyword",
        })

    elif ptype == "merge_collection":
        if not do_apply_merge_collection(proposal):
            return 1

    elif ptype == "move_collection":
        if not do_apply_move_collection(proposal):
            return 1

    else:
        print(f"ERROR: Unknown proposal type '{ptype}'. Supported types: "
              f"add_keyword, merge_collection, move_collection", file=sys.stderr)
        return 1

    # Mark as applied
    now = datetime.now(timezone.utc).isoformat()
    for p in all_proposals:
        if p["id"] == proposal_id:
            p["status"] = "applied"
            p["applied_at"] = now
            p["completed_at"] = now
            break

    proposals_data["proposals"] = all_proposals
    save_proposals(proposals_data)

    print(f"✓ Applied proposal [{proposal_id}].", flush=True)
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 1

    mode = sys.argv[1]

    if mode == "--dry-run":
        return do_auto_approve(dry_run=True)

    if mode == "--auto-approve":
        return do_auto_approve(dry_run=False)

    if mode == "apply":
        if len(sys.argv) < 3:
            print("Usage: apply-proposals.py apply <proposal_id>", file=sys.stderr)
            return 1
        return do_apply_specific(sys.argv[2])

    print(f"Unknown mode: {mode}", file=sys.stderr)
    print(f"Use: --dry-run, --auto-approve, or apply <id>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
