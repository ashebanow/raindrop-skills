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
  source .env && export RAINDROP_TOKEN && python3 scripts/process-batch.py [--dry-run] [--limit N]

  --dry-run   Log inferences without making any API calls.
  --limit N   Process at most N bookmarks (default: from rules thresholds.batch_limit or 50).

State file (from scan-batch.py): ~/.hermes/cache/raindrop-state.json
Audit log: ~/.hermes/cache/raindrop-audit-log.jsonl
No-match file: ~/.hermes/cache/raindrop-no-match.json
Rules: references/raindrop-rules.json
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Optional

# --- Shared Raindrop utilities -------------------------------------------- #
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import (
    api as _api,
    compute_precision_score,
    detect_note_template as _detect_note_template_shared,
    fetch_page_cached,
    fetch_page_content,
    load_rules as _load_rules,
    query_domain_fingerprint,
    should_fetch_url,
    start_fetcher_pool,
    TRACKING_TAG,
    update_domain_fingerprint,
)



# Re-export api for local use (preserves backward compat within this file)
api = _api

CACHE = os.path.expanduser("~/.hermes/cache")
STATE_PATH = f"{CACHE}/raindrop-state.json"
LOG_PATH = f"{CACHE}/raindrop-audit-log.jsonl"
NO_MATCH_PATH = f"{CACHE}/raindrop-no-match.json"
CONFIDENCE_PATH = f"{CACHE}/raindrop-confidence.json"
DRY_RUN = "--dry-run" in sys.argv

# Parse optional --limit N argument (default: _BATCH_LIMIT from rules)
_BATCH_LIMIT_OVERRIDE = None
for i, arg in enumerate(sys.argv):
    if arg == "--limit" and i + 1 < len(sys.argv):
        try:
            _BATCH_LIMIT_OVERRIDE = int(sys.argv[i + 1])
        except ValueError:
            pass
        break

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")

# --- Rules loaded from references/raindrop-rules.json ---------------------- #
_rules_data = _load_rules()

# Collection keyword map: list of (keywords, collection_id, collection_title)
COLLECTION_KEYWORD_MAP = [
    (entry["keywords"], entry["collection_id"], entry["collection_title"])
    for entry in _rules_data.get("collection_keywords", [])
]

# Reverse map for domain fingerprint collection lookup
COLLECTION_TITLE_TO_ID = {
    entry["collection_title"]: entry["collection_id"]
    for entry in _rules_data.get("collection_keywords", [])
}

# Tag rules: list of (regex_pattern, tag_name) from tag_rules
TAG_RULES = [
    (entry["pattern"], entry["tag"])
    for entry in _rules_data.get("tag_rules", [])
]

# Tag keywords: dict of tag_name → [keyword, ...]
TAG_KEYWORDS = _rules_data.get("tag_keywords", {})

# Note templates: list of dicts with domain_pattern, template, tone_penalty
NOTE_TEMPLATES = _rules_data.get("note_templates", [])

# Thresholds
thresholds = _rules_data.get("thresholds", {})
MAX_TAGS = thresholds.get("max_tags_per_bookmark", 5)
API_RETRIES = thresholds.get("api_retries", 3)
API_TIMEOUT = thresholds.get("api_timeout_s", 15)
RATE_LIMIT_DELAY = thresholds.get("rate_limit_delay_s", 0.25)
MIN_OCCURRENCES = thresholds.get("min_occurrences", 2)  # min keyword occurrences in rich text to suggest a tag

# Default batch limit (overridable via --limit N)
_BATCH_LIMIT = thresholds.get("batch_limit", 50)

print(f"Loaded {len(COLLECTION_KEYWORD_MAP)} collection rules, "
      f"{len(TAG_KEYWORDS)} tag keyword groups, "
      f"{len(TAG_RULES)} regex tag rules, "
      f"{len(NOTE_TEMPLATES)} note templates, "
      f"max_tags={MAX_TAGS}", flush=True)





# --- Inference helpers ------------------------------------------------------ #

def infer_real_tags(title: str, domain: str, rich_text: Optional[str] = None) -> list[str]:
    """Infer real (non-tracking) tags from title + domain + optional rich_text.

    When rich_text is provided (page body text), uses frequency-weighted
    scoring: all keywords for a tag are counted across the full text
    (title + domain + rich_text), and a tag is assigned only if the total
    occurrence count meets MIN_OCCURRENCES (default 2). This avoids
    false positives from sidebar/nav text where a keyword appears once.

    When rich_text is NOT available (fetch failed or blacklisted domain),
    falls back to binary matching against title + domain only. This
    preserves existing behavior for unreachable URLs.

    After keyword matching, falls back to regex tag_rules if defined.
    """
    text = ((title or "") + " " + (domain or "")).lower()
    matched: list[str] = []

    if rich_text:
        # Frequency-weighted scoring against full text
        match_text = (text + " " + rich_text.lower())
        for tag_name, keywords in TAG_KEYWORDS.items():
            total_count = sum(match_text.count(kw) for kw in keywords)
            if total_count >= MIN_OCCURRENCES:
                matched.append(tag_name)
                if len(matched) >= MAX_TAGS:
                    break
    else:
        # Binary matching with word-boundary awareness
        # Short keywords like "nix" (3 chars) should not match inside
        # "nixos" or "nixpkgs". Use word-boundary regex to ensure the
        # keyword appears as a standalone word, not as a substring.
        for tag_name, keywords in TAG_KEYWORDS.items():
            for kw in keywords:
                if tag_name in matched:
                    break
                # Multi-word keywords (e.g. "open source") use substring match
                if " " in kw:
                    if kw in text:
                        matched.append(tag_name)
                        break
                else:
                    # Word-boundary match — prevents "nix" matching "nixos"
                    pattern = r"(?<![a-zA-Z])" + re.escape(kw) + r"(?![a-zA-Z])"
                    if re.search(pattern, text):
                        matched.append(tag_name)
                        break
            if len(matched) >= MAX_TAGS:
                break

    # Fallback: regex rules (if any are configured)
    if not matched:
        for pattern, tag in TAG_RULES:
            if re.search(pattern, text) and tag not in matched:
                matched.append(tag)
                if len(matched) >= MAX_TAGS:
                    break

    return matched


def infer_note(title: str, domain: str, link: str) -> str:
    d = (domain or "").lower()
    for template in NOTE_TEMPLATES:
        pat = template.get("domain_pattern", "")
        if pat and re.search(pat, d):
            return template["template"].replace("{title}", title)
    return f"Bookmark: {title}."


def build_note_from_content(page_content: dict, title: str) -> str:
    """Build a human-readable note from fetched page content.

    Priority:
    1. meta_description (truncated to 200 chars)
    2. body_text first 150 chars
    3. Fall back to template-driven infer_note()
    """
    meta_desc = (page_content.get("meta_description") or "").strip()
    if meta_desc:
        return meta_desc[:200]
    body_text = (page_content.get("body_text") or "").strip()
    if body_text:
        return body_text[:150]
    # No usable content from page
    return f"Bookmark: {title}."


def find_collection(title: str, domain: str, rich_text: Optional[str] = None):
    """Find the best-matching collection via keyword scoring.

    When rich_text is available, uses frequency-based scoring across all
    rule keywords in title + domain + rich_text.  Highest cumulative score
    wins, with title/domain matches getting a 2x bonus.  Requires a minimum
    cumulative score of 2 to return a result.

    When rich_text is NOT available, falls back to first-match-wins keyword
    lookup against title + domain only (original behavior).

    Returns (collection_id, collection_title) tuple, or None.
    """
    text = ((title or "") + " " + (domain or "")).lower()

    if rich_text:
        # Frequency-weighted scoring: highest total keyword frequency wins
        match_text = text + " " + rich_text.lower()
        best_score = 0
        best_match = None
        for keywords, coll_id, coll_title in COLLECTION_KEYWORD_MAP:
            score = sum(match_text.count(kw) for kw in keywords)
            # Bonus: keyword in title/domain is stronger than in body
            title_bonus = sum(2 for kw in keywords if kw in text)
            score += title_bonus
            if score > best_score:
                best_score = score
                best_match = (coll_id, coll_title)

        # Minimum cumulative score of 2 to avoid noise
        if best_score >= 2:
            return best_match
        return None
    else:
        # First-match-wins against title+domain only (existing behavior)
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


def add_to_no_match(rid, title, domain=None, url=None):
    """Add a bookmark to the no-match file. Returns True if added (new entry).

    Stores [rid, title, domain, url] tuple for richer clustering.
    Old-format entries (2 items) are preserved during migration.
    """
    data = []
    if os.path.exists(NO_MATCH_PATH):
        try:
            with open(NO_MATCH_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = []
    if not isinstance(data, list):
        data = []
    if any(isinstance(e, list) and len(e) >= 1 and e[0] == rid for e in data):
        return False
    entry = [rid, title]
    if domain:
        entry.append(domain)
        if url:
            entry.append(url)
    data.append(entry)
    os.makedirs(os.path.dirname(NO_MATCH_PATH), exist_ok=True)
    with open(NO_MATCH_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True


# --- Confidence tracking ---------------------------------------------------- #

def load_confidence() -> dict:
    """Load per-rule confidence stats from cache file."""
    if os.path.exists(CONFIDENCE_PATH):
        try:
            with open(CONFIDENCE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "rules": {}, "by_domain": {}}


def save_confidence(data: dict):
    os.makedirs(os.path.dirname(CONFIDENCE_PATH), exist_ok=True)
    with open(CONFIDENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _rule_key_for_collection(coll_id: int) -> str:
    """Find the rule id for a collection ID from the rules data."""
    for entry in _rules_data.get("collection_keywords", []):
        if entry.get("collection_id") == coll_id:
            return entry.get("id", f"coll-{coll_id}")
    return f"coll-{coll_id}"


def update_rule_stats(rule_key: str, result: str, domain: str = None):
    """Update per-rule confidence with a match result.

    Args:
        rule_key: rule identifier (e.g. "coll-nixos")
        result: one of "match", "agreement", "improvement", "regression", "miss"
        domain: optional domain for by_domain tracking
    """
    conf = load_confidence()
    if rule_key not in conf["rules"]:
        conf["rules"][rule_key] = {
            "hits": 0, "matches": 0,
            "filler_agreements": 0, "filler_improvements": 0, "filler_regressions": 0,
            "last_matched": None, "confidence": None,
        }
    r = conf["rules"][rule_key]
    r["hits"] += 1
    r["last_matched"] = datetime.now(timezone.utc).isoformat()

    if result == "match":
        r["matches"] += 1
    elif result == "agreement":
        r["filler_agreements"] += 1
        r["matches"] += 1
    elif result == "improvement":
        r["filler_improvements"] += 1
        r["matches"] += 1
    elif result == "regression":
        r["filler_regressions"] += 1
    # "miss" — no match, do not increment matches

    # Recompute confidence
    total_filler = r["filler_agreements"] + r["filler_improvements"] + r["filler_regressions"]
    if total_filler > 0:
        # Weighted: agreements=1.0, improvements=0.8, regressions=0.0
        weighted = (r["filler_agreements"] * 1.0 + r["filler_improvements"] * 0.8)
        r["confidence"] = round(weighted / total_filler, 4)
    elif r["hits"] > 0:
        r["confidence"] = round(r["matches"] / r["hits"], 4)
    else:
        r["confidence"] = None

    # Domain tracking
    if domain:
        if domain not in conf["by_domain"]:
            conf["by_domain"][domain] = {"hits": 0, "matched_collections": {}}
        conf["by_domain"][domain]["hits"] += 1
        coll_title = None
        for entry in _rules_data.get("collection_keywords", []):
            if entry.get("id") == rule_key:
                coll_title = entry.get("collection_title", "?")
                break
        if coll_title:
            d = conf["by_domain"][domain]["matched_collections"]
            d[coll_title] = d.get(coll_title, 0) + 1

    conf["last_run_id"] = RUN_ID
    conf["last_run_timestamp"] = datetime.now(timezone.utc).isoformat()
    save_confidence(conf)


# --- Filler queue comparison helpers ---------------------------------------- #

def detect_note_template(note: str) -> Optional[str]:
    """Return the template id if the note matches a known template, else None.

    Delegates to the shared implementation in raindrop_common.
    """
    return _detect_note_template_shared(note, NOTE_TEMPLATES)


def jaccard_similarity(a: list, b: list) -> float:
    """Jaccard index of two tag lists, ignoring tracking tag."""
    set_a = {t for t in a if t != TRACKING_TAG}
    set_b = {t for t in b if t != TRACKING_TAG}
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 1.0


def compare_assignments(
    existing_note: str, existing_tags: list, existing_coll_id: Optional[int],
    inferred_note: str, inferred_tags: list, inferred_coll_id: Optional[int],
    title: str, domain: str,
) -> dict:
    """Compare existing vs inferred assignments. Returns a verdict dict.

    Verdict axes:
      "collection_stability": "stable" | "changed"
      "tag_jaccard": 0.0-1.0
      "note_template_improved": Optional[bool]
      "note_length_delta": int (positive = new is longer)
      "overall_verdict": "better" | "worse" | "same"
    """
    # Collection stability
    collection_stability = "stable" if existing_coll_id == inferred_coll_id else "changed"

    # Tag overlap
    tag_jaccard = jaccard_similarity(existing_tags, inferred_tags)

    # Note comparison
    old_template = detect_note_template(existing_note)
    new_template = detect_note_template(inferred_note)

    # Template improved: new note is NOT a template when old note WAS
    # (or new uses a less-penalized template)
    note_template_improved = None
    if old_template and not new_template:
        note_template_improved = True
    elif not old_template and new_template:
        note_template_improved = False
    elif old_template and new_template:
        # Both are templates — compare tone_penalty if available
        old_penalty = 3
        new_penalty = 3
        for tpl in NOTE_TEMPLATES:
            if tpl.get("id") == old_template:
                old_penalty = tpl.get("tone_penalty", 3)
            if tpl.get("id") == new_template:
                new_penalty = tpl.get("tone_penalty", 3)
        note_template_improved = new_penalty < old_penalty

    note_length_delta = len(inferred_note) - len(existing_note)

    # Overall verdict
    signals = []
    if collection_stability == "stable":
        signals.append("same_coll")
    else:
        signals.append("diff_coll")

    if tag_jaccard >= 0.7:
        signals.append("tags_stable")
    elif tag_jaccard >= 0.3:
        signals.append("tags_drift")
    else:
        signals.append("tags_changed")

    if note_template_improved is True:
        signals.append("note_better")
    elif note_template_improved is False:
        signals.append("note_worse")

    # Short-ish notes (<150 chars) that aren't template are good
    if len(inferred_note) < 150 and not new_template:
        signals.append("note_concise")
    if len(existing_note) < 150 and not old_template:
        signals.append("old_concise")

    # Assign verdict
    if collection_stability == "changed":
        overall = "better"  # Assume change is intentional until we have holdout data
    elif signals.count("note_better") > signals.count("note_worse"):
        overall = "better"
    elif signals.count("note_worse") > signals.count("note_better"):
        overall = "worse"
    elif "tags_changed" in signals and tag_jaccard < 0.3:
        overall = "worse"  # Big tag drift without collection change = unstable
    else:
        overall = "same"

    return {
        "collection_stability": collection_stability,
        "tag_jaccard": round(tag_jaccard, 3),
        "note_template_improved": note_template_improved,
        "note_length_delta": note_length_delta,
        "overall_verdict": overall,
    }


def process_comparison(bookmark: dict) -> str:
    """Process a filler-queue bookmark: infer, compare, conditionally apply.

    Returns "compared" (inference ran, stats recorded) or "skipped" (no change needed).
    """
    rid = bookmark["_id"]
    title = bookmark.get("title", "?")
    domain = bookmark.get("domain", "")
    link = bookmark.get("link", "")
    existing_tags = bookmark.get("tags", []) or []
    existing_note = bookmark.get("note", "") or ""
    existing_coll = bookmark.get("collection") or {}
    existing_coll_id = existing_coll.get("$id")

    # Fetch page content for richer inference (cached per URL)
    page_content = fetch_page_cached(link)
    rich_text = None
    if page_content and page_content.get("body_text"):
        rich_text = (title + " " + (domain or "") + " "
                     + page_content.get("meta_description", "") + " "
                     + page_content.get("body_text", ""))

    # Run inference (same as for new bookmarks)
    inferred_tags = infer_real_tags(title, domain, rich_text=rich_text)
    if page_content and page_content.get("body_text"):
        inferred_note = build_note_from_content(page_content, title)
    else:
        inferred_note = infer_note(title, domain, link)
    inferred_coll_id = None
    inferred_coll_title = None

    current_coll_id = existing_coll.get("$id")
    is_unsorted = current_coll_id in (None, -1, 0)
    if is_unsorted:
        match = find_collection(title, domain, rich_text=rich_text)
        if match:
            inferred_coll_id, inferred_coll_title = match
    else:
        inferred_coll_id = current_coll_id  # keep existing

    # Domain fingerprint cache: supplement tags & collection with cached signals
    domain_key = urlparse(link).netloc.lower() if link else domain
    domain_signal = query_domain_fingerprint(domain_key)
    if domain_signal:
        for suggested_tag in domain_signal.get("tags", []):
            if suggested_tag not in inferred_tags:
                inferred_tags.append(suggested_tag)
        if not inferred_coll_id and domain_signal.get("collections"):
            best_coll = domain_signal["collections"][0]
            coll_id = COLLECTION_TITLE_TO_ID.get(best_coll[0])
            if coll_id:
                inferred_coll_id = coll_id
                inferred_coll_title = best_coll[0]

    # Update domain fingerprint with fetched content (only with a real collection)
    if page_content and page_content.get("body_text"):
        _assigned_coll_title = inferred_coll_title if inferred_coll_id else (existing_coll.get("title", "") if not is_unsorted else "")
        if _assigned_coll_title:
            update_domain_fingerprint(domain_key, page_content["body_text"], inferred_tags, _assigned_coll_title)

    # Compare
    verdict = compare_assignments(
        existing_note, existing_tags, existing_coll_id,
        inferred_note, inferred_tags, inferred_coll_id,
        title, domain,
    )

    if DRY_RUN:
        # Just report, don't apply
        print(f"  [comparison] {title[:50]} verdict={verdict['overall_verdict']} "
              f"coll={verdict['collection_stability']} "
              f"tags_j={verdict['tag_jaccard']}", flush=True)
        return "compared"

    # Update rule stats (collection rule)
    if inferred_coll_id:
        rule_key = _rule_key_for_collection(inferred_coll_id)
        if verdict["overall_verdict"] == "better":
            update_rule_stats(rule_key, "improvement", domain)
        elif verdict["overall_verdict"] == "same":
            update_rule_stats(rule_key, "agreement", domain)
        else:
            update_rule_stats(rule_key, "regression", domain)

    # Compute precision score for audit logging
    _precision_result = compute_precision_score(
        title, domain, link,
        inferred_coll_id,
        inferred_tags,
        _rules_data,
    )
    _precision_score = _precision_result["combined_score"]

    # Apply update only if verdict is "better"
    if verdict["overall_verdict"] != "better":
        # Still clear the description field even if note/tags/collection
        # are unchanged — avoids stale descriptions lingering on filler
        # bookmarks that were categorized before description-clearing was
        # part of the pipeline.
        if not DRY_RUN:
            api("PUT", f"/raindrop/{rid}", {"description": ""})
            log_entry("update_raindrop", {
                "raindrop_id": rid,
                "title": title[:80],
                "fields_changed": ["description"],
                "note_preview": "",
                "phase": "comparison",
                "precision_score": _precision_score,
            })
        return "compared"  # Stats recorded, no API call for other fields

    # Apply the improvements
    phase_ok = True

    # 3a: Note update
    note_result = api("PUT", f"/raindrop/{rid}", {"note": inferred_note, "description": ""})
    if note_result and note_result.get("result"):
        log_entry("update_raindrop", {
            "raindrop_id": rid,
            "title": title[:80],
            "fields_changed": ["note", "description"],
            "note_preview": inferred_note[:100],
            "phase": "comparison",
            "precision_score": _precision_score,
        })
    else:
        phase_ok = False

    # 3b: Collection update (only if unsorted and inferred differs)
    if inferred_coll_id and is_unsorted and inferred_coll_id != existing_coll_id:
        coll_result = api("PUT", f"/raindrop/{rid}", {"collection": {"$id": inferred_coll_id}})
        if coll_result and coll_result.get("result"):
            log_entry("update_raindrop", {
                "raindrop_id": rid,
                "title": title[:80],
                "fields_changed": ["collection"],
                "collection_id": inferred_coll_id,
                "collection_title": inferred_coll_title,
                "phase": "comparison",
                "precision_score": _precision_score,
            })
        else:
            phase_ok = False

    # 3c: Tag merge (never remove existing tags)
    existing_real = [t for t in existing_tags if t != TRACKING_TAG]
    merged_tags = list(existing_real)
    for t in inferred_tags:
        if t not in merged_tags and len(merged_tags) < MAX_TAGS:
            merged_tags.append(t)

    if set(merged_tags) != set(existing_real):
        tag_result = api("PUT", f"/raindrop/{rid}", {"tags": merged_tags})
        if tag_result and tag_result.get("result"):
            log_entry("update_raindrop", {
                "raindrop_id": rid,
                "title": title[:80],
                "fields_changed": ["tags"],
                "tags": merged_tags,
                "phase": "comparison",
                "precision_score": _precision_score,
            })
        else:
            phase_ok = False

    if phase_ok:
        print(f"  ✓ {title[:50]} — improved ({verdict['overall_verdict']})", flush=True)
    else:
        print(f"  ⚠ {title[:50]} — comparison succeeded but partial API failure", flush=True)

    return "compared"


# --- Main pipeline ---------------------------------------------------------- #

def load_state():
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def process_one(bookmark: dict):
    """Process a single bookmark through Phases 3a → 3d.

    For new bookmarks (no tracking tag): runs the full pipeline and applies
    _categorized-v2 on success.

    For filler queue bookmarks (has tracking tag): runs inference, compares
    against existing values, and only applies if the new inference is better.
    Records per-rule confidence stats in both cases.

    Returns one of:
      "tagged"    — new bookmark fully processed
      "deferred"  — at least one phase failed; tracking tag NOT applied
      "compared"  — filler bookmark evaluated and stats recorded
    """
    rid = bookmark["_id"]
    title = bookmark.get("title", "?")
    domain = bookmark.get("domain", "")
    link = bookmark.get("link", "")
    existing_tags = bookmark.get("tags", []) or []

    if TRACKING_TAG in existing_tags:
        return process_comparison(bookmark)

    # Fetch page content for richer inference (cached per URL)
    page_content = fetch_page_cached(link)
    rich_text = None
    if page_content and page_content.get("body_text"):
        rich_text = (title + " " + (domain or "") + " "
                     + page_content.get("meta_description", "") + " "
                     + page_content.get("body_text", ""))

    real_tags = infer_real_tags(title, domain, rich_text=rich_text)
    if page_content and page_content.get("body_text"):
        note = build_note_from_content(page_content, title)
    else:
        note = infer_note(title, domain, link)

    current_coll = bookmark.get("collection") or {}
    current_coll_id = current_coll.get("$id")
    is_unsorted = current_coll_id in (None, -1, 0)

    # Determine assigned collection (if any)
    _assigned_coll_id = None
    _match = find_collection(title, domain, rich_text=rich_text) if is_unsorted else None
    if _match:
        _assigned_coll_id = _match[0]

    # Domain fingerprint cache: supplement tags & collection with cached signals
    domain_key = urlparse(link).netloc.lower() if link else domain
    domain_signal = query_domain_fingerprint(domain_key)
    if domain_signal:
        for suggested_tag in domain_signal.get("tags", []):
            if suggested_tag not in real_tags:
                real_tags.append(suggested_tag)
        if not _match and domain_signal.get("collections"):
            best_coll = domain_signal["collections"][0]
            coll_id = COLLECTION_TITLE_TO_ID.get(best_coll[0])
            if coll_id:
                _match = (coll_id, best_coll[0])
                _assigned_coll_id = coll_id

    # Compute precision score for audit logging
    _precision_result = compute_precision_score(
        title, domain, link,
        _assigned_coll_id,
        real_tags,
        _rules_data,
    )
    _precision_score = _precision_result["combined_score"]

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
                "precision_score": _precision_score,
            })
    else:
        # Without 3a succeeding, 3b has no semantic content to match
        # against, and tracking the failure is moot. Bail early.
        return "deferred"

    # --- Phase 3b: assign collection (only if currently Unsorted) ---
    if is_unsorted:
        match = _match
        if match is None:
            phase_3b_state = "no_match"
            if not DRY_RUN:
                added = add_to_no_match(rid, title, domain=domain, url=link)
                if added:
                    log_entry("no_match", {
                        "raindrop_id": rid,
                        "title": title[:80],
                        "domain": domain,
                        "precision_score": _precision_score,
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
                        "precision_score": _precision_score,
                    })
            else:
                phase_3b_state = "failed"

    # Update domain fingerprint with fetched content (only with a real collection)
    if page_content and page_content.get("body_text"):
        _assigned_coll_title = _match[1] if _match else (current_coll.get("title", "") if not is_unsorted else "")
        if _assigned_coll_title:
            update_domain_fingerprint(domain_key, page_content["body_text"], real_tags, _assigned_coll_title)

    # --- Phase 3c: merge tags (never remove existing tags) ---
    # Merge existing real tags with inferred tags. Existing tags are
    # always preserved — the pipeline only adds missing tags, it never
    # removes human-curated tags.
    existing_real = [t for t in existing_tags if t != TRACKING_TAG]
    merged_tags = list(existing_real)
    for t in real_tags:
        if t not in merged_tags and len(merged_tags) < MAX_TAGS:
            merged_tags.append(t)

    # Only write if the merged set actually differs (avoids unnecessary PUTs)
    if set(merged_tags) != set(existing_real):
        result = api("PUT", f"/raindrop/{rid}", {"tags": merged_tags})
        if result and result.get("result"):
            phase_3c_ok = True
            if not DRY_RUN:
                log_entry("update_raindrop", {
                    "raindrop_id": rid,
                    "title": title[:80],
                    "fields_changed": ["tags"],
                    "tags": merged_tags,
                    "precision_score": _precision_score,
                })
        else:
            phase_3c_ok = False
    else:
        # Tags unchanged — no API call needed, but still passes the gate
        phase_3c_ok = True

    # --- Phase 3d: tracking tag (only if 3a, 3b-or-skipped, 3c all succeeded) ---
    if phase_3a_ok and phase_3b_state in ("skipped", "matched") and phase_3c_ok:
        final_tags = merged_tags + [TRACKING_TAG]
        if result and result.get("result"):
            # Actually PUT the tracking tag (was only logging before — bug fix)
            tag_result = api("PUT", f"/raindrop/{rid}", {"tags": final_tags})
            if tag_result and tag_result.get("result"):
                if not DRY_RUN:
                    log_entry("update_raindrop", {
                        "raindrop_id": rid,
                        "title": title[:80],
                        "fields_changed": ["tags"],
                        "tags": final_tags,
                        "tracking_tag_added": True,
                        "precision_score": _precision_score,
                    })
                return "tagged"

    return "deferred"


def main() -> int:
    state = load_state()
    limit = _BATCH_LIMIT_OVERRIDE if _BATCH_LIMIT_OVERRIDE is not None else _BATCH_LIMIT
    final = state.get("final_list", [])[:limit]
    total = len(final)

    t0 = time.time()
    counts = {"tagged": 0, "deferred": 0, "compared": 0}
    filler_count = 0

    mode = " (DRY RUN)" if DRY_RUN else ""
    print(f"Processing {total} bookmarks{mode}...", flush=True)

    # Background fetcher pool: 5 workers keep ahead of the processing loop
    all_urls = [r.get("link", "") for r in final if r.get("link")]
    if all_urls:
        start_fetcher_pool(all_urls, num_workers=5)

    for i, r in enumerate(final):
        is_filler = TRACKING_TAG in (r.get("tags", []) or [])
        if is_filler:
            filler_count += 1

        if DRY_RUN:
            if is_filler:
                # Dry-run comparison
                process_comparison(r)
                counts["compared"] += 1
            else:
                # Dry-run inference for new bookmarks (include page content, cached)
                link = r.get("link", "")
                page_content = fetch_page_cached(link)
                rich_text = None
                if page_content and page_content.get("body_text"):
                    rich_text = (r.get("title", "") + " " + (r.get("domain", "") or "") + " "
                                 + page_content.get("meta_description", "") + " "
                                 + page_content.get("body_text", ""))
                real = infer_real_tags(r.get("title", ""), r.get("domain", ""), rich_text=rich_text)
                if page_content and page_content.get("body_text"):
                    note = build_note_from_content(page_content, r.get("title", ""))
                else:
                    note = infer_note(r.get("title", ""), r.get("domain", ""), link)
                current_coll = r.get("collection") or {}
                is_unsorted = current_coll.get("$id") in (None, -1, 0)
                match = find_collection(r.get("title", ""), r.get("domain", ""), rich_text=rich_text) if is_unsorted else None
                # Domain fingerprint cache: supplement tags & collection with cached signals
                domain_key = urlparse(link).netloc.lower() if link else r.get("domain", "")
                domain_signal = query_domain_fingerprint(domain_key)
                if domain_signal:
                    for suggested_tag in domain_signal.get("tags", []):
                        if suggested_tag not in real:
                            real.append(suggested_tag)
                    if not match and domain_signal.get("collections"):
                        best_coll = domain_signal["collections"][0]
                        coll_id = COLLECTION_TITLE_TO_ID.get(best_coll[0])
                        if coll_id:
                            match = (coll_id, best_coll[0])
                # Update domain fingerprint with fetched content (only with a real collection)
                if page_content and page_content.get("body_text"):
                    _assigned_coll_title = match[1] if match else (current_coll.get("title", "") if not is_unsorted else "")
                    if _assigned_coll_title:
                        update_domain_fingerprint(domain_key, page_content["body_text"], real, _assigned_coll_title)
                coll_str = f" → {match[1]}" if match else (" → (no match)" if is_unsorted else " → (already in collection)")
                print(f"  [{i+1}/{total}] {r.get('title', '?')[:50]}{coll_str}  tags: {real}", flush=True)
                counts["tagged" if match or not is_unsorted else "deferred"] += 1
        else:
            outcome = process_one(r)
            counts[outcome] = counts.get(outcome, 0) + 1
            # Light progress line
            if (i + 1) % 10 == 0:
                print(
                    f"  [{i+1}/{total}] new_tagged={counts.get('tagged', 0)} "
                    f"deferred={counts.get('deferred', 0)} "
                    f"compared={counts.get('compared', 0)}",
                    flush=True,
                )

        time.sleep(RATE_LIMIT_DELAY)  # Pacing: rate_limit_delay_s from rules

    elapsed = time.time() - t0
    total_processed = sum(counts.values())
    print(
        f"\nDone in {elapsed:.0f}s | "
        f"{total} batch ({filler_count} filler) | "
        f"{counts.get('tagged', 0)} new tagged, "
        f"{counts.get('deferred', 0)} deferred, "
        f"{counts.get('compared', 0)} compared | "
        f"{elapsed/max(1, total_processed):.1f}s per bookmark",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
