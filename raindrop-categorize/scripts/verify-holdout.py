#!/usr/bin/env python3
"""
Holdout set verifier for raindrop-categorize.

Reads the holdout file and re-runs inference against each entry,
comparing inferred values against confirmed ground truth.

Outputs verification scores and appends them to the quality record.

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/verify-holdout.py [--json]

  --json   Output scores as JSON (for programmatic consumption)
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

# --- Paths ---
CACHE = os.path.expanduser("~/.hermes/cache")
HOLDOUT_PATH = f"{CACHE}/raindrop-holdout.json"
QUALITY_PATH = f"{CACHE}/raindrop-quality.json"

# --- Shared module ---
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import TRACKING_TAG

# --- Rules ---
_rules_path = os.path.join(_repo_root, "raindrop-categorize", "references", "raindrop-rules.json")
_rules_data = {}
if os.path.exists(_rules_path):
    with open(_rules_path) as f:
        _rules_data = json.load(f)
_COLLECTION_KEYWORDS = _rules_data.get("collection_keywords", [])
_TAG_KEYWORDS = _rules_data.get("tag_keywords", {})


# ── Inference (same logic as process-batch.py) ─────────────────────

def find_collection(title: str, domain: str):
    """First-match-wins keyword lookup (mirrors process-batch.py)."""
    text = ((title or "") + " " + (domain or "")).lower()
    for entry in _COLLECTION_KEYWORDS:
        keywords = entry.get("keywords", [])
        if any(kw in text for kw in keywords):
            return (entry["collection_id"], entry["collection_title"])
    return None


def infer_tags(title: str, domain: str):
    """Infer tags from title + domain (mirrors run_pipeline.py tag_keywords logic)."""
    text = ((title or "") + " " + (domain or "")).lower()
    matched = []
    for tag_name, keywords in _TAG_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                if tag_name not in matched:
                    matched.append(tag_name)
                break
        if len(matched) >= 5:
            break
    return matched


# ── Scoring ─────────────────────────────────────────────────────────

def compute_verification(holdout_entries: list) -> dict:
    """Run inference against all holdout entries and compute scores."""
    coll_correct = 0
    coll_total = 0
    tag_true_positives = 0
    tag_false_positives = 0
    tag_false_negatives = 0

    per_collection = defaultdict(lambda: {"correct": 0, "total": 0})

    for entry in holdout_entries:
        title = entry.get("title", "")
        domain = entry.get("domain", "")
        confirmed_coll_id = entry.get("confirmed_collection_id")
        confirmed_tags = set(entry.get("confirmed_tags", []))

        # Run inference
        match = find_collection(title, domain)
        inferred_tags = set(infer_tags(title, domain))

        # Collection accuracy
        if match:
            inferred_coll_id = match[0]
            coll_total += 1
            is_correct = inferred_coll_id == confirmed_coll_id
            if is_correct:
                coll_correct += 1
            coll_name = entry.get("confirmed_collection_title", "?")
            per_collection[coll_name]["total"] += 1
            if is_correct:
                per_collection[coll_name]["correct"] += 1
        elif confirmed_coll_id is None:
            # No inference and no confirmed collection — skip
            pass
        else:
            # No inference but confirmed collection exists — miss
            coll_total += 1
            coll_name = entry.get("confirmed_collection_title", "?")
            per_collection[coll_name]["total"] += 1

        # Tag metrics
        for t in inferred_tags:
            if t in confirmed_tags:
                tag_true_positives += 1
            else:
                tag_false_positives += 1
        for t in confirmed_tags:
            if t not in inferred_tags:
                tag_false_negatives += 1

    # Aggregate scores
    collection_accuracy = coll_correct / coll_total if coll_total > 0 else 0.0
    tag_precision = tag_true_positives / (tag_true_positives + tag_false_positives) if (tag_true_positives + tag_false_positives) > 0 else 0.0
    tag_recall = tag_true_positives / (tag_true_positives + tag_false_negatives) if (tag_true_positives + tag_false_negatives) > 0 else 0.0
    tag_f1 = 2 * (tag_precision * tag_recall) / (tag_precision + tag_recall) if (tag_precision + tag_recall) > 0 else 0.0

    # Per-collection breakdown
    coll_breakdown = {}
    for name, counts in sorted(per_collection.items()):
        coll_breakdown[name] = {
            "accuracy": round(counts["correct"] / counts["total"], 3) if counts["total"] > 0 else 0,
            "count": counts["total"],
        }

    return {
        "collection_accuracy": round(collection_accuracy, 3),
        "tag_precision": round(tag_precision, 3),
        "tag_recall": round(tag_recall, 3),
        "tag_f1": round(tag_f1, 3),
        "holdout_size": len(holdout_entries),
        "collection_correct": coll_correct,
        "collection_total": coll_total,
        "by_collection": coll_breakdown,
    }


# ── Quality file integration ───────────────────────────────────────

def append_verification_to_quality(verification: dict):
    """Add verification scores to the most recent quality record."""
    if not os.path.exists(QUALITY_PATH):
        print("  ⚠ No quality file to update.", flush=True)
        return
    try:
        with open(QUALITY_PATH) as f:
            quality = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    if isinstance(quality, list) and quality:
        quality[-1]["verification"] = verification
        with open(QUALITY_PATH, "w") as f:
            json.dump(quality, f, indent=2)
        print(f"  ✓ Verification appended to most recent quality record.", flush=True)
    elif isinstance(quality, dict) and quality.get("runs"):
        quality["runs"][-1]["verification"] = verification
        with open(QUALITY_PATH, "w") as f:
            json.dump(quality, f, indent=2)
        print(f"  ✓ Verification appended to most recent quality record.", flush=True)
    else:
        print(f"  ⚠ Unknown quality file format.", flush=True)


# ── Main ───────────────────────────────────────────────────────────

def main():
    import_json = "--json" in sys.argv

    if not os.path.exists(HOLDOUT_PATH):
        print("No holdout file found. Run build-holdout.py first.", flush=True)
        return 1

    with open(HOLDOUT_PATH) as f:
        holdout = json.load(f)

    if isinstance(holdout, dict):
        entries = holdout.get("entries", [])
    elif isinstance(holdout, list):
        entries = holdout
    else:
        print("Unknown holdout format.", flush=True)
        return 1

    if not entries:
        print("Holdout is empty.", flush=True)
        return 0

    print(f"Verifying against {len(entries)} holdout entries...", flush=True)
    verification = compute_verification(entries)

    if import_json:
        print(json.dumps(verification, indent=2))
    else:
        print(f"\n  Collection accuracy: {verification['collection_accuracy']:.1%} "
              f"({verification['collection_correct']}/{verification['collection_total']})")
        print(f"  Tag precision:       {verification['tag_precision']:.1%}")
        print(f"  Tag recall:          {verification['tag_recall']:.1%}")
        print(f"  Tag F1:              {verification['tag_f1']:.1%}")
        print(f"  Samples:             {verification['holdout_size']}")
        if verification.get("by_collection"):
            print(f"\n  Per collection:")
            for name, stats in sorted(verification["by_collection"].items()):
                bar_len = int(stats["accuracy"] * 20)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                print(f"    [{bar}] {name}: {stats['accuracy']:.0%} ({stats['count']} samples)")

    # Append to quality file
    append_verification_to_quality(verification)

    # Regression detection
    if verification["collection_accuracy"] < 0.7 and verification["holdout_size"] >= 10:
        print(f"\n⚠ WARNING: Collection accuracy below 70% ({verification['collection_accuracy']:.1%}). "
              f"Consider reviewing the taxonomy or keyword rules.", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
