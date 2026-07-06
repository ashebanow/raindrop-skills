#!/usr/bin/env python3
"""
Gemini classifier for raindrop-categorize — assigns collection + tags using
Google's Gemini Flash-Lite free tier (1,000 request/day, zero cost).

Called by process-batch.py when page content is available. Falls back to
keyword matching on failure (network errors, rate limits, bad JSON).

Gemini 2.5 Flash-Lite free tier:
  - 30 RPM, 1,000 RPD, 1M token context
  - Model: gemini-2.5-flash-lite
  - Endpoint: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

Usage:
  from gemini_classifier import classify_bookmark
  result = classify_bookmark(title, url, body_text, meta_description,
                              collections, tags, api_key)
  # → {"collection": "Food & Drink", "tags": ["food", "recipe"]} or None on failure
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# --- Configuration ---

MODEL = "gemini-2.5-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
ENDPOINT = f"{API_BASE}/{MODEL}:generateContent"

# ENV keys to search for the Gemini API key (in order)
_GEMINI_KEY_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

# Max body text chars to include in the prompt (keeps token count low)
MAX_BODY_CHARS = 2000

# Max collections to describe in the taxonomy prompt
MAX_COLLECTIONS = 50

# Max tags to list in the taxonomy prompt
MAX_TAGS = 60

# LLM call timeout (seconds)
TIMEOUT_S = 15

# Retry config
MAX_RETRIES = 2
RETRY_DELAY_S = 1.0


# --- API key loading ----------------------------------------------------------

def load_gemini_key() -> Optional[str]:
    """Resolve the Gemini API key from environment or .env files."""
    # 1. Already in environment
    for var in _GEMINI_KEY_ENV_VARS:
        val = os.environ.get(var)
        if val and not val.startswith("your_") and len(val) > 10:
            return val

    # 2. Project .env (same dir as this script, or cwd)
    for base in [Path(__file__).resolve().parent.parent.parent,
                 Path.cwd(),
                 Path.home()]:
        env_path = base / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in _GEMINI_KEY_ENV_VARS and v and len(v) > 10:
                    os.environ[k] = v
                    return v

    # 3. ~/.hermes/.env
    hermes_env = Path.home() / ".hermes" / ".env"
    if hermes_env.exists():
        for line in hermes_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in _GEMINI_KEY_ENV_VARS and v and len(v) > 10:
                os.environ[k] = v
                return v

    return None


# --- Taxonomy prompt builder --------------------------------------------------

def _build_taxonomy_text(
    collections: dict[str, dict],
    tags: list[tuple[str, str]],  # [(tag_name, description), ...]
) -> str:
    """Build the taxonomy portion of the prompt: hierarchical collections + tags."""

    lines: list[str] = []
    lines.append("## Available Collections (hierarchical — dots show nesting depth)")
    lines.append("Assign the bookmark to ONE collection from this tree:")
    lines.append("")

    # Build a parent → children tree for hierarchy display
    children_of: dict[str | None, list[tuple[str, dict]]] = {}
    title_by_id: dict[str, str] = {}
    for cid, info in collections.items():
        if not isinstance(info, dict):
            continue
        parent = info.get("parent")
        if parent is not None:
            parent = str(parent)
        children_of.setdefault(parent, []).append((cid, info))
        title_by_id[cid] = info.get("title", cid)

    # Build paths from root
    def _build_path(cid: str, info: dict) -> str:
        parts = [info.get("title", cid)]
        parent = info.get("parent")
        while parent is not None:
            parent_str = str(parent)
            parent_info = collections.get(parent_str, {})
            if isinstance(parent_info, dict) and parent_info.get("title"):
                parts.insert(0, parent_info["title"])
                parent = parent_info.get("parent")
            else:
                break
        return " > ".join(parts)

    # Collect all entries with their paths
    entries: list[tuple[str, int]] = []  # [(path, count), ...]
    for cid, info in collections.items():
        if not isinstance(info, dict):
            continue
        path = _build_path(cid, info)
        cnt = info.get("count", 0) or 0
        entries.append((path, cnt))

    # Sort alphabetically within parent groups (keeps related topics together)
    entries.sort(key=lambda e: e[0].lower())

    for path, cnt in entries:
        depth = path.count(" > ")
        indent = "  " * depth
        detail = f" ({cnt})" if cnt else ""
        lines.append(f"{indent}- {path}{detail}")

    lines.append("")
    lines.append("## Available Tags")
    lines.append("Select 1-4 relevant tags:")
    lines.append("")

    sorted_tags = sorted(tags, key=lambda t: t[0].lower())
    for tag_name, desc in sorted_tags:
        if desc:
            lines.append(f"- {tag_name}: {desc}")
        else:
            lines.append(f"- {tag_name}")

    lines.append("")
    return "\n".join(lines)


def _build_classification_prompt(
    title: str,
    url: str,
    body_text: str,
    meta_description: str,
    collections: dict[str, dict],
    tags: list[tuple[str, str]],
) -> str:
    """Build the full classification prompt for Gemini."""

    taxonomy = _build_taxonomy_text(collections, tags)

    body_snippet = body_text[:MAX_BODY_CHARS].strip()
    meta_snippet = meta_description[:500] if meta_description else ""

    prompt = f"""You are a precise content classification agent for a bookmarking system.

Analyze the provided bookmark and classify it according to the taxonomy below.

{taxonomy}

## Bookmark to Classify

**Title:** {title}
**URL:** {url}
**Meta Description:** {meta_snippet if meta_snippet else "(none)"}
**Page Content Preview:** {body_snippet if body_snippet else "(not available)"}

## Instructions

Respond with ONLY a JSON object on a single line (no markdown, no explanation):

{{"collection": "<exact collection name from the list above>", "tags": ["tag1", "tag2"]}}

Rules:
- The collection MUST be an exact hierarchical path shown in the tree (e.g., "Travel > Italy")
- Tags MUST come from the Available Tags list
- If no specific sub-collection fits, use a broader parent path
- Choose 1-3 most relevant tags (NOT 5+)

Domain discrimination (IMPORTANT — avoid obvious mismatches):
- "citizenship", "visa", "passport", "immigration", "embassy", "consulate" → Travel > <country>
- "language classes", "language school", "learn <language>", "language courses" → NOT Technology; prefer country-based Travel path or broad general collection
- "voice recognition", "speech to text", "ASR", "speaker diarization" → Technology > Voice Recognition
- Food, recipes, cooking, restaurants → Food & Drink path
- Travel, vacations, hotels → Travel path
- Health, fitness, exercise → Health & Wellness path
- Music, bands, albums → Entertainment & Media > Music
- Be conservative: don't force-fit non-technical content into technical categories
"""

    return prompt


# --- API call ----------------------------------------------------------------

def _call_gemini(prompt: str, api_key: str) -> Optional[str]:
    """Send prompt to Gemini, return raw text response or None on failure."""

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,       # Low temp for deterministic classification
            "maxOutputTokens": 800,    # Flash verbose; JSON + potential explanation
            "topP": 0.95,
        },
    }

    url = f"{ENDPOINT}?key={api_key}"
    data = json.dumps(payload).encode("utf-8")

    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")

        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT_S)
            body = json.loads(resp.read().decode())

            # Navigate Gemini response structure:
            # candidates[0].content.parts[0].text
            candidates = body.get("candidates", [])
            if not candidates:
                print(f"  ⚠ Gemini: no candidates in response", flush=True)
                return None

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                print(f"  ⚠ Gemini: no parts in content", flush=True)
                return None

            text = parts[0].get("text", "")
            if text:
                return text.strip()
            else:
                print(f"  ⚠ Gemini: empty text in response", flush=True)
                return None

        except urllib.error.HTTPError as e:
            status = e.code
            if status == 429:
                # Rate limit — back off and retry
                if attempt < MAX_RETRIES:
                    wait = RETRY_DELAY_S * (2 ** attempt)
                    print(f"  ⚠ Gemini rate limited, retrying in {wait:.0f}s...", flush=True)
                    time.sleep(wait)
                    continue
                else:
                    print(f"  ⚠ Gemini: rate limit exhausted after {MAX_RETRIES} retries", flush=True)
                    return None
            else:
                print(f"  ⚠ Gemini HTTP {status}: {e.reason}", flush=True)
                return None

        except (urllib.error.URLError, OSError) as e:
            print(f"  ⚠ Gemini network error: {e}", flush=True)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)
                continue
            return None

        except json.JSONDecodeError as e:
            print(f"  ⚠ Gemini: bad JSON in response body: {e}", flush=True)
            return None

    return None


# --- Response parsing --------------------------------------------------------

def _parse_response(text: str, collection_names: list[str]) -> Optional[dict]:
    """Parse Gemini's JSON response into {collection, tags}.

    Handles:
    - Clean JSON: {"collection": "...", "tags": [...]}
    - Markdown code blocks: ```json ... ```
    - Trailing commas or other minor parse errors
    """

    # Strip markdown code fences
    text = text.strip()
    if text.startswith("```"):
        # Find the opening fence end
        nl = text.find("\n")
        if nl > 0:
            text = text[nl + 1:]
        else:
            text = text[3:]
        # Find the closing fence
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    # Try direct parse
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Try stripping trailing commas
        import re
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            print(f"  ⚠ Gemini: could not parse JSON response: {text[:200]}", flush=True)
            return None

    if not isinstance(result, dict):
        return None

    collection = result.get("collection", "")
    tags = result.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    # Validate collection exists in our taxonomy.
    # Try: exact match → leaf-only match → fuzzy substring match
    if collection and collection not in collection_names:
        # Try extracting leaf (last segment of path)
        if " > " in collection:
            leaf = collection.rsplit(" > ", 1)[-1]
            if leaf in collection_names:
                collection = leaf
            else:
                # Fuzzy match: case-insensitive substring in any collection name
                found = None
                for name in collection_names:
                    if leaf.lower() in name.lower() or name.lower() in leaf.lower():
                        found = name
                        break
                if found:
                    collection = found
                    print(f"  🤖 Gemini fuzzy-matched collection: {collection}", flush=True)
                else:
                    print(f"  ⚠ Gemini suggested unknown collection: {collection}", flush=True)
                    collection = ""
        else:
            # Single-word collection: try fuzzy match
            found = None
            for name in collection_names:
                if collection.lower() in name.lower() or name.lower() in collection.lower():
                    found = name
                    break
            if found:
                collection = found
                print(f"  🤖 Gemini fuzzy-matched collection: {collection}", flush=True)
            else:
                print(f"  ⚠ Gemini suggested unknown collection: {collection}", flush=True)
                collection = ""

    # Filter tags to only known ones
    valid_tags = [t for t in tags if isinstance(t, str) and t.strip()]
    valid_tags = valid_tags[:4]  # Max 4 tags

    if not collection and not valid_tags:
        return None

    return {
        "collection": collection,
        "tags": valid_tags,
    }


# --- Public API --------------------------------------------------------------

def classify_bookmark(
    title: str,
    url: str,
    body_text: str,
    meta_description: str,
    collections: dict[str, dict],
    tags: list[tuple[str, str]],
    api_key: Optional[str] = None,
) -> Optional[dict]:
    """Classify a bookmark using Gemini.

    Args:
        title: Bookmark title
        url: Bookmark URL
        body_text: Page body text (from fetch_page_cached)
        meta_description: Page meta description
        collections: {title: {count, description}, ...} dict
        tags: [(tag_name, description), ...] list
        api_key: Gemini API key (loaded from env if not provided)

    Returns:
        {"collection": "...", "tags": ["...", "..."]} or None on any failure
    """

    if api_key is None:
        api_key = load_gemini_key()

    if not api_key:
        print("  ⚠ Gemini: no API key configured — falling back to keyword rules", flush=True)
        return None

    if not body_text and not meta_description:
        return None  # No content to classify

    # Build a lookup map for collection validation — includes dict keys,
    # collection titles, AND hierarchical paths the LLM sees in the prompt.
    coll_lookup = set(collections.keys())
    for cid, info in collections.items():
        if not isinstance(info, dict):
            continue
        title = info.get("title", "")
        if title:
            coll_lookup.add(title)
        # Build hierarchical path (e.g., "Travel > Italy")
        parts = [title]
        parent = info.get("parent")
        while parent is not None:
            parent_str = str(parent)
            parent_info = collections.get(parent_str, {})
            if isinstance(parent_info, dict) and parent_info.get("title"):
                parts.insert(0, parent_info["title"])
                parent = parent_info.get("parent")
            else:
                break
        if len(parts) > 1:
            coll_lookup.add(" > ".join(parts))

    prompt = _build_classification_prompt(
        title, url, body_text, meta_description,
        collections, tags,
    )

    raw = _call_gemini(prompt, api_key)
    if raw is None:
        return None

    result = _parse_response(raw, list(coll_lookup))

    if result:
        coll_str = result.get('collection', '(none)')
        tag_str = ', '.join(result.get('tags', []))
        print(f"  🤖 Gemini: collection={coll_str} tags=[{tag_str}]", flush=True)

    return result


# --- CLI test mode -----------------------------------------------------------

if __name__ == "__main__":
    import sys
    print("Gemini Classifier — test mode")
    key = load_gemini_key()
    if key:
        print(f"API key: {key[:12]}...")
    else:
        print("No API key found. Set GEMINI_API_KEY in .env or environment.")
        sys.exit(1)

    # Quick test with sample data
    test_collections = {
        "Food & Drink": {"count": 174},
        "Programming": {"count": 230},
        "NixOS": {"count": 257},
        "Travel": {"count": 45},
    }
    test_tags = [
        ("food", "recipes, cooking, restaurants"),
        ("programming", "code, software development"),
        ("ai", "artificial intelligence, ML, LLMs"),
        ("travel", "vacations, trips, hotels"),
    ]

    result = classify_bookmark(
        title="Traditional Palestinian Hummus Recipe",
        url="https://waleedasadi.com/p/traditional-palestinian-hummus",
        body_text="Cook the chickpeas until tender. Add tahini, lemon juice, garlic, and salt. Blend until smooth. Serve with olive oil and paprika.",
        meta_description="The best authentic Palestinian hummus recipe.",
        collections=test_collections,
        tags=test_tags,
        api_key=key,
    )

    print(f"\nResult: {json.dumps(result, indent=2)}")
