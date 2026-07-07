#!/usr/bin/env python3
"""
One-shot: find and clear notes that duplicate or closely match
Raindrop's auto-generated excerpt field.

Uses Jaccard similarity on word bigrams to catch near-duplicates
(e.g., notes that share most of their phrasing with the excerpt).

Rate-limited to ~2 req/s (~120 req/min Raindrop API cap).

Usage:
  source .env && export RAINDROP_TOKEN && python3 scripts/clean_note_excerpt_dupes.py [--dry-run] [--threshold 0.5]

  --dry-run     Report matches without making changes.
  --threshold N Jaccard similarity threshold (default 0.45).
  --limit N     Stop after processing N bookmarks (for testing).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from collections import Counter

# --- Config ---

API_BASE = "https://api.raindrop.io/rest/v1"
PERPAGE = 50
REQUEST_DELAY = 0.5  # seconds between API calls (~2 req/s)
THRESHOLD = 0.45     # Jaccard similarity threshold

DRY_RUN = "--dry-run" in sys.argv
LIMIT = None

for i, arg in enumerate(sys.argv):
    if arg == "--threshold" and i + 1 < len(sys.argv):
        try:
            THRESHOLD = float(sys.argv[i + 1])
        except ValueError:
            pass
    if arg == "--limit" and i + 1 < len(sys.argv):
        try:
            LIMIT = int(sys.argv[i + 1])
        except ValueError:
            pass

# --- Token helpers ---


def get_token() -> str:
    token = os.environ.get("RAINDROP_TOKEN", "")
    if not token:
        # Try sourcing .env
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("RAINDROP_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["RAINDROP_TOKEN"] = token
                    break
    if not token:
        print("ERROR: RAINDROP_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    return token


# --- Similarity ---


def bigrams(text: str) -> Counter:
    """Word bigrams with normalization."""
    words = text.lower().split()
    return Counter(zip(words, words[1:]))


def jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity of word bigram sets."""
    ba = bigrams(a)
    bb = bigrams(b)
    if not ba and not bb:
        return 0.0
    intersection = sum((ba & bb).values())
    union = sum((ba | bb).values())
    return intersection / union if union else 0.0


def is_substantial_overlap(note: str, excerpt: str, threshold: float) -> bool:
    """Check if note and excerpt share enough content to be considered duplicates."""
    note = note.strip()
    excerpt = excerpt.strip()
    if not note or not excerpt:
        return False

    # Exact match
    if note == excerpt:
        return True

    # One is fully contained in the other
    if note in excerpt or excerpt in note:
        return True

    # Bigram Jaccard
    sim = jaccard_similarity(note, excerpt)
    return sim >= threshold


def looks_handwritten(note: str) -> bool:
    """Heuristic: does this note look like human-written content vs template/AI?

    Returns True if the note appears to be hand-typed by a user.
    We only clear template/AI-generated notes, not user content.
    """
    note = note.strip()
    if not note:
        return False

    # Template patterns: these are clearly auto-generated, safe to clear
    template_patterns = [
        "Git repository: ",
        "GitHub - ",
        "Bookmark: ",
    ]
    for pat in template_patterns:
        if note.startswith(pat):
            return False  # template note, safe to clear

    # Multi-sentence notes with personal voice are likely hand-written
    sentences = [s.strip() for s in note.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    if len(sentences) >= 2:
        return True

    # Long notes are likely hand-written (even if single-sentence)
    if len(note) > 200:
        return True

    # Short notes that are exact matches: safe to clear (they're excerpt copies)
    # Medium notes: borderline — default to keeping them
    return False


# --- API helpers ---


def api_get(path: str, params: dict = None) -> dict | None:
    """GET with retries."""
    token = get_token()
    url = f"{API_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"

    for attempt in range(3):
        try:
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {token}")
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                return None
            time.sleep(0.5 * (2 ** attempt))
        except Exception:
            time.sleep(0.5 * (2 ** attempt))
    return None


def api_put(path: str, data: dict) -> dict | None:
    """PUT with retries."""
    token = get_token()
    url = f"{API_BASE}{path}"
    body = json.dumps(data).encode()

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, method="PUT")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                return None
            time.sleep(0.5 * (2 ** attempt))
        except Exception:
            time.sleep(0.5 * (2 ** attempt))
    return None


# --- Main ---


def main() -> int:
    token = get_token()
    dry = " (DRY RUN)" if DRY_RUN else ""
    print(f"Scanning bookmarks for note≈excerpt duplicates{dry}...")
    print(f"  threshold={THRESHOLD}  delay={REQUEST_DELAY}s  limit={LIMIT or 'all'}")
    print()

    page = 0
    total_scanned = 0
    matches = 0
    cleared = 0

    while True:
        data = api_get("/raindrops/0", {"perpage": str(PERPAGE), "page": str(page)})
        if not data:
            print(f"  ERROR: failed to fetch page {page}")
            break

        items = data.get("items", [])
        if not items:
            break

        for r in items:
            total_scanned += 1
            rid = r["_id"]
            title = r.get("title", "")[:60]
            note = (r.get("note") or "").strip()
            excerpt = (r.get("excerpt") or "").strip()

            if not note or not excerpt:
                continue

            if not is_substantial_overlap(note, excerpt, THRESHOLD):
                continue

            # Skip notes that look hand-written — only clear template/AI content
            if looks_handwritten(note):
                continue

            matches += 1
            sim = jaccard_similarity(note, excerpt)
            print(
                f"  #{matches} id={rid} sim={sim:.3f}\n"
                f"    note:    {note[:120]}\n"
                f"    excerpt: {excerpt[:120]}",
                flush=True,
            )

            if DRY_RUN:
                continue

            result = api_put(f"/raindrop/{rid}", {"note": ""})
            if result and result.get("result"):
                cleared += 1
                print(f"    ✓ cleared", flush=True)
            else:
                print(f"    ✗ API error", flush=True)

            time.sleep(REQUEST_DELAY)

            if LIMIT and total_scanned >= LIMIT:
                break

            # Periodic progress
            if matches % 20 == 0:
                print(
                    f"  ... progress: scanned={total_scanned} matches={matches} "
                    f"cleared={cleared}",
                    flush=True,
                )

        if LIMIT and total_scanned >= LIMIT:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    print()
    print(
        f"Done. Scanned {total_scanned} bookmarks, "
        f"found {matches} note≈excerpt matches"
        + (f", cleared {cleared}" if not DRY_RUN else "")
        + "."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
