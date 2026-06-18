#!/usr/bin/env python3
"""
One-shot classifier for top-level Nix bookmarks.

Fetches bookmarks directly in the Nix collection (id=70861985) and
classifies each into one of three new subcollections based on
title/domain/tag keyword matching.

Collections:
  Nix Language  (id=72134536) — Nix expression language, syntax, evaluation
  Nix Tools     (id=72134538) — Build tools, flakes, CI, dev tools, deployments
  NixOS         (id=72134539) — OS config, modules, hardware, systemd (default)

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/classify-nix-bookmarks.py
  source .env && export RAINDROP_TOKEN && python3 scripts/classify-nix-bookmarks.py --apply
  source .env && export RAINDROP_TOKEN && python3 scripts/classify-nix-bookmarks.py --apply --dry-run
"""
import json
import os
import sys
import time
import re
from collections import Counter

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
from raindrop_common import api_get, api_put

NIX_COLLECTION_ID = 70861985
SUBCOLLECTIONS = {
    "Nix Language": 72134536,
    "Nix Tools": 72134538,
    "NixOS": 72134539,
}
ID_TO_NAME = {v: k for k, v in SUBCOLLECTIONS.items()}


# ── Keyword rules ────────────────────────────────────────────────────

def classify(bookmark: dict) -> str:
    """Return the subcollection name for a bookmark.

    Priority: Nix Language > Nix Tools > NixOS (fallback).
    """
    title = (bookmark.get("title") or "").lower()
    domain = (bookmark.get("domain") or "").lower()
    tags = [t.lower() for t in (bookmark.get("tags") or [])]
    url = (bookmark.get("link") or "").lower()

    combined = f"{title} {domain} {url}"
    title_lower = title

    # ── Nix Language ──
    # Signals about the Nix expression language itself
    lang_signals = [
        # Direct language references
        r"\bnix expression", r"\bnix language", r"\bnix syntax",
        r"\bnix evaluation", r"\bnix evaluator",
        r"\bnix language server", r"\bnil\b",
        # Derivations / the language model
        r"\bderivation", r"\bbuilt-in", r"\bbuiltin",
        r"\bnixpkgs manual", r"\bnixpkgs reference",
        r"\breference manual",
        # Language-specific tools
        r"\bnixfmt", r"\bnixpkgs-fmt", r"\bstatix\b", r"\bdeadnix\b",
        r"\bnixd\b",  # Nix language server
        r"\bnix eval\b",
    ]
    for pattern in lang_signals:
        if re.search(pattern, combined):
            # Exclude: OS-level context overrides
            if re.search(r"\bnixos\b.*(?:module|config|systemd|kernel|hardware|boot|install)", combined):
                continue
            if "nix-language" in tags or "language" in tags and "nix" in tags:
                return "Nix Language"
            # Only return Language if there's a strong signal, not just {"nix", "language"} in tags
            if re.search(pattern, title_lower):
                return "Nix Language"

    # ── Nix Tools ──
    # Build/deploy/dev tools, flakes, CI
    tools_signals = [
        # Flakes and build tools
        r"\bflake\b", r"\bflake-parts", r"\bflake\.parts",
        r"\bnix build\b", r"\bnix shell\b", r"\bnix develop\b",
        r"\bnix profile\b", r"\bnix store\b", r"\bnix flake\b",
        r"\bnix run\b", r"\bnix edit\b",
        r"\bnix-collect-garbage", r"\bnix-store",
        # Dev environments
        r"\bdevenv", r"\bdevbox\b", r"\blorri\b",
        r"\bdirenv\b", r"\bnix-direnv",
        # Deployment
        r"\bdeploy", r"\bdeploy-rs", r"\bnixos-anywhere",
        r"\bcolmena\b", r"\bnixinate\b",
        # CI / caching
        r"\bci\b", r"\bnixci\b", r"\bgithub actions.*nix",
        r"\bcachix\b", r"\battic\b", r"\bnix cache\b",
        # Indices / search
        r"\bnix-index", r"\bcomma\b", r"\bnix-locate",
        r"\bnoogle\b", r"\bhome-manager",
        # Other tools
        r"\bnixpacks\b", r"\bnix-bundle",
        r"\bnix flake check\b",
        # Tool-specific domains
        r"flake\.parts", r"devenv\.sh", r"colmena\.cli\.rs",
        r"determinate\.systems", r"numtide",
    ]
    for pattern in tools_signals:
        if re.search(pattern, combined):
            # Exclude: NixOS config repos that happen to use flakes
            if re.search(r"\bnixos\b.*(?:config|configuration|dotfiles)", title_lower):
                return "NixOS"
            return "Nix Tools"

    if any(t in ("tool", "cli", "devtool", "flake", "ci", "deploy") for t in tags):
        return "Nix Tools"

    # ── NixOS (default catch-all) ──
    # Any bookmark with "nixos" or OS-level context goes here
    os_signals = [
        r"\bnixos\b", r"\bnixos\b",
        r"\blinux\b", r"\bsystemd\b", r"\bkernel\b",
        r"\bmodule\b", r"\bhardware\b",
        r"\bconfiguration\.nix",
        r"\bdesktop\b", r"\bserver\b", r"\bboot\b",
        r"\bwpa_supplicant", r"\bnetworkmanager",
        r"\bxfce\b", r"\bgnome\b", r"\bkde\b", r"\bhyprland",
        r"\bwayland\b", r"\bxorg\b",
    ]
    for pattern in os_signals:
        if re.search(pattern, combined):
            return "NixOS"

    # Domain-based fallbacks
    if "nixos.wiki" in domain or "wiki.nixos.org" in domain:
        return "NixOS"
    if "nixos.org" in domain or "nix.dev" in domain:
        return "Nix Language"  # official docs are language-reference heavy
    if "discourse.nixos.org" in domain:
        return "NixOS"  # forum topics are mostly OS/config

    # Tag-based fallback: if tagged "nixos" or "linux", it's NixOS
    if "nixos" in tags:
        return "NixOS"

    # Default: NixOS is the broadest category
    return "NixOS"


def fetch_nix_bookmarks() -> list:
    """Fetch all bookmarks directly under Nix (not in subcollections)."""
    all_drops = []
    page = 0
    perpage = 50
    while True:
        data = api_get(f"/raindrops/{NIX_COLLECTION_ID}", {"page": page, "perpage": perpage})
        if not data:
            break
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            coll = item.get("collection", {}) or {}
            if coll.get("$id") == NIX_COLLECTION_ID:
                all_drops.append(item)
        if len(items) < perpage:
            break
        page += 1
        time.sleep(0.2)
    return all_drops


def move_bookmark(rid: int, target_id: int) -> bool:
    """Move a single bookmark to a target collection. Returns True on success."""
    result = api_put(f"/raindrop/{rid}", {"collection": {"$id": target_id}})
    if result:
        time.sleep(0.1)
        return True
    return False


def main():
    apply_mode = "--apply" in sys.argv
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        apply_mode = True  # --dry-run implies --apply context

    print("=== Classify Nix Bookmarks ===", flush=True)
    print(f"  Collections: {', '.join(f'{k} (id={v})' for k, v in SUBCOLLECTIONS.items())}",
          flush=True)

    bookmarks = fetch_nix_bookmarks()
    print(f"\nFetched {len(bookmarks)} bookmarks directly in Nix.\n", flush=True)

    # Classify
    assignments = Counter()
    details = []
    for bm in bookmarks:
        label = classify(bm)
        assignments[label] += 1
        details.append((bm, label))

    # Summary
    print(f"{'='*60}", flush=True)
    print(f"{'Collection':<20} {'Count':>6}", flush=True)
    print(f"{'-'*26}", flush=True)
    for name in ["Nix Language", "Nix Tools", "NixOS"]:
        print(f"{name:<20} {assignments[name]:>6}", flush=True)
    print(f"{'─'*26}", flush=True)
    print(f"{'Total':<20} {len(bookmarks):>6}", flush=True)
    print()

    # Show samples
    for name in ["Nix Language", "Nix Tools", "NixOS"]:
        samples = [d for d in details if d[1] == name][:5]
        if samples:
            print(f"\n  {name} samples:", flush=True)
            for bm, _ in samples:
                title = (bm.get("title") or "?")[:65]
                domain = bm.get("domain", "") or ""
                print(f"    [{bm['_id']}] {title}", flush=True)
                print(f"            {domain}", flush=True)

    if not apply_mode:
        print(f"\n{'='*60}", flush=True)
        print("Dry run — classification only. Run with --apply to move bookmarks.",
              flush=True)
        return 0

    if dry_run:
        print(f"\n{'='*60}", flush=True)
        print("Dry run — would move bookmarks as shown above.", flush=True)
        return 0

    # ── Apply ──
    print(f"\n{'='*60}", flush=True)
    print(f"Applying classifications...", flush=True)

    moved = {name: 0 for name in SUBCOLLECTIONS}
    failed = 0
    for bm, label in details:
        target_id = SUBCOLLECTIONS[label]
        if move_bookmark(bm["_id"], target_id):
            moved[label] += 1
        else:
            failed += 1
            print(f"  ❌ Failed to move [{bm['_id']}] {bm.get('title','?')[:50]}",
                  flush=True)

    print(f"\nResults:", flush=True)
    for name in ["Nix Language", "Nix Tools", "NixOS"]:
        print(f"  {name:<20} {moved[name]:>4} moved", flush=True)
    if failed:
        print(f"  {'Failed':<20} {failed:>4}", flush=True)
    print(f"\n✓ Done.", flush=True)


if __name__ == "__main__":
    main()
