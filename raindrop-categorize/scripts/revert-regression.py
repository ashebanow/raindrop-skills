#!/usr/bin/env python3
"""
Safety-valve: revert rule changes that caused holdout verification regression.

Reads proposals and quality files, checks each approved proposal against
the current holdout verification scores, and reverts any change that caused
collection_accuracy to drop by more than 0.1 (10 percentage points).

Output (machine-parseable, one line per event):
  REVERT_OK                                    — nothing to revert
  REVERTED: <rule_title> — verification dropped X% → Y%
  REVERT_SKIP: <prop_id> — <reason>
  REVERT_ERROR: <message>

These lines are captured by cron_run.py and formatted into Discord output.

Usage:
  python3 scripts/revert-regression.py

Expected proposal snapshot format (populated when proposal is applied):

  {
    "id": "prop-...",
    "rule_id": "coll-docker",
    "status": "auto_approved",
    "change": { "add_keywords": ["compose"] },
    "snapshot": {
      "previous_keywords": ["docker"],
      "confidence_before": 0.85,
      "verification_before": { "collection_accuracy": 0.92 }
    }
  }
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────

CACHE = Path(os.path.expanduser("~/.hermes/cache"))
PROPOSALS_PATH = CACHE / "raindrop-proposals.json"
QUALITY_PATH = CACHE / "raindrop-quality.json"

# Rules file: this script lives at raindrop-categorize/scripts/revert-regression.py
_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPTS_DIR.parent
RULES_PATH = _SKILL_DIR / "references" / "raindrop-rules.json"

# ── Output collection ───────────────────────────────────────────────

_OUTPUT_LINES: list[str] = []


def log(line: str):
    """Emit one line of machine-parseable output for cron_run.py."""
    _OUTPUT_LINES.append(line)
    print(line, flush=True)


# ── Data loading ────────────────────────────────────────────────────


def load_proposals() -> list[dict]:
    """Load proposals from raindrop-proposals.json. Returns list of proposal dicts."""
    if not PROPOSALS_PATH.exists():
        return []
    try:
        data = json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log(f"REVERT_ERROR: could not read proposals file: {e}")
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("proposals", [])
    return []


def save_proposals(proposals: list[dict]):
    """Write proposals back to disk."""
    PROPOSALS_PATH.write_text(
        json.dumps({"proposals": proposals}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_rules() -> dict:
    """Load raindrop-rules.json. Returns dict."""
    if not RULES_PATH.exists():
        log(f"REVERT_ERROR: rules file not found at {RULES_PATH}")
        return {}
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log(f"REVERT_ERROR: could not read rules file: {e}")
        return {}


def save_rules(rules: dict):
    """Write rules back to disk."""
    RULES_PATH.write_text(
        json.dumps(rules, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_current_verification() -> Optional[dict]:
    """Return the verification section from the most recent quality record, or None."""
    if not QUALITY_PATH.exists():
        return None
    try:
        data = json.loads(QUALITY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, list):
        return None

    # Scan from most recent backward for a record with a verification section
    for record in reversed(data):
        verification = record.get("verification")
        if verification and isinstance(verification, dict):
            return verification
    return None


def get_rule_title(rules: dict, rule_id: str) -> str:
    """Get the human-readable collection title for a rule, or the rule_id itself."""
    for entry in rules.get("collection_keywords", []):
        if entry.get("id") == rule_id:
            return entry.get("collection_title", rule_id)
    return rule_id


# ── Revert logic ────────────────────────────────────────────────────


def revert_rule_change(rule_id: str, add_keywords: list[str]) -> bool:
    """Remove add_keywords from the rule's keywords list, bump version, save.

    Returns True on success, False if the rule was not found.
    """
    rules = load_rules()
    if not rules:
        return False

    found = False
    for entry in rules.get("collection_keywords", []):
        if entry.get("id") == rule_id:
            keywords = entry.get("keywords", [])
            original_len = len(keywords)

            # Remove each added keyword (all occurrences, idempotent)
            for kw in add_keywords:
                while kw in keywords:
                    keywords.remove(kw)

            if len(keywords) == original_len and add_keywords:
                log(f"REVERT_WARN: no keywords were removed from rule {rule_id} "
                    f"(add_keywords={add_keywords!r} not found in {keywords!r})")

            entry["keywords"] = keywords

            # Bump version and update timestamp
            rules["version"] = rules.get("version", 0) + 1
            rules["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            save_rules(rules)
            found = True
            break

    if not found:
        log(f"REVERT_ERROR: rule '{rule_id}' not found in raindrop-rules.json")
        return False

    return True


def mark_proposal_rejected(proposal: dict, reason: str = "verification regression"):
    """Update a proposal's status to 'rejected' with reason and timestamp."""
    proposal["status"] = "rejected"
    proposal["rejected_at"] = datetime.now(timezone.utc).isoformat()
    proposal["rejection_reason"] = reason


# ── Main ────────────────────────────────────────────────────────────


def main() -> int:
    # 1. Load proposals
    proposals = load_proposals()
    if not proposals:
        log("REVERT_OK")
        return 0

    # 2. Get current holdout verification
    current_verification = get_current_verification()
    if not current_verification:
        log("REVERT_OK  (no verification data yet)")
        return 0

    current_accuracy = current_verification.get("collection_accuracy", 0.0)

    # 3. Find approved proposals (applied changes) that have snapshots
    approved_with_snapshots = []
    for p in proposals:
        status = p.get("status", "")
        if status in ("auto_approved", "user_approved"):
            snapshot = p.get("snapshot")
            rule_id = p.get("rule_id")
            change = p.get("change", {})
            add_keywords = change.get("add_keywords", [])

            if not snapshot:
                log(f"REVERT_SKIP: {p.get('id', '?')} — missing snapshot (manual review needed)")
                continue
            if not rule_id or not add_keywords:
                log(f"REVERT_SKIP: {p.get('id', '?')} — missing rule_id or change.add_keywords "
                    f"(manual review needed)")
                continue

            approved_with_snapshots.append(p)

    if not approved_with_snapshots:
        log("REVERT_OK")
        return 0

    # 4. Load rules once for title lookups
    rules = load_rules()
    if not rules:
        return 1

    # 5. Check each approved proposal for regression
    reverted: list[str] = []  # human-readable messages

    for proposal in approved_with_snapshots:
        snapshot = proposal["snapshot"]
        rule_id = proposal["rule_id"]
        add_keywords = proposal["change"]["add_keywords"]
        verification_before = snapshot.get("verification_before", {})

        baseline_accuracy = verification_before.get("collection_accuracy", 0.0)

        # Skip if no baseline to compare against
        if baseline_accuracy <= 0:
            log(f"REVERT_SKIP: {proposal['id']} — verification_before has no collection_accuracy")
            continue

        # Regression check
        drop = baseline_accuracy - current_accuracy
        if drop > 0.1:  # more than 10 percentage points drop
            # Revert the rule change
            success = revert_rule_change(rule_id, add_keywords)
            if not success:
                continue

            # Mark proposal as rejected
            mark_proposal_rejected(proposal)

            # Build human-readable message
            rule_title = get_rule_title(rules, rule_id)
            pct_before = round(baseline_accuracy * 100)
            pct_current = round(current_accuracy * 100)
            msg = (
                f"REVERTED: {rule_title} ({rule_id}) — "
                f"verification dropped {pct_before}% → {pct_current}%"
            )
            log(msg)
            reverted.append(msg)

    # 6. Save updated proposals
    save_proposals(proposals)

    if not reverted:
        log("REVERT_OK")

    return 0


if __name__ == "__main__":
    sys.exit(main())
