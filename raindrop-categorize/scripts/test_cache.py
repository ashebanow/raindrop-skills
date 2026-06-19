#!/usr/bin/env python3
"""
Tests for the page content cache and background fetcher pool.

Run:  source .env && export RAINDROP_TOKEN && python3 scripts/test_cache.py

The cache/fetcher tests mock fetch_page_content so no real HTTP.
The dry-run test runs process-batch.py --dry-run --limit 3 as a
subprocess to verify the full pipeline integration.
"""
import os
import subprocess
import sys
import time
from typing import Optional

# ── Path setup ──────────────────────────────────────────────────────
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_repo_root, "shared"))
_script_dir = os.path.join(_repo_root, "raindrop-categorize", "scripts")

# ── Mock fetch_page_content and import the shared module ────────────
# We monkey-patch *before* importing raindrop_common so the mock is in place.

_fetch_log: list[str] = []  # tracks which URLs were actually fetched
_fetch_delay = 0.0

def _mock_fetch(url: str, timeout: int = 3) -> Optional[dict]:
    _fetch_log.append(url)
    if _fetch_delay > 0:
        time.sleep(_fetch_delay)
    if "fail" in url:
        return None
    return {
        "success": True,
        "title": f"Test: {url}",
        "meta_description": "test description with keywords for matching",
        "body_text": "test body content for keyword matching and analysis",
    }

import raindrop_common

# Monkey-patch fetch_page_content *before* importing the cache wrappers
# so they use our mock at function-call time (Python looks up names in
# the module global scope at call time, so this works).
raindrop_common.fetch_page_content = _mock_fetch

from raindrop_common import (
    PAGE_CACHE,
    fetch_page_cached,
    start_fetcher_pool,
)


def setup():
    PAGE_CACHE.clear()
    _fetch_log.clear()


# ═══════════════════════════════════════════════════════════════════ #
# Unit tests — cache infrastructure                                  #
# ═══════════════════════════════════════════════════════════════════ #

def test_cache_hit():
    """fetch_page_cached returns cached content without calling fetch."""
    setup()
    PAGE_CACHE["https://example.com"] = {"cached": True}
    _fetch_log.clear()

    result = fetch_page_cached("https://example.com")
    assert result == {"cached": True}, f"Expected cached dict, got {result}"
    assert len(_fetch_log) == 0, f"Expected 0 fetches on hit, got {len(_fetch_log)}"
    print("  ✅ test_cache_hit")


def test_cache_miss():
    """fetch_page_cached falls through to fetch on cache miss."""
    setup()
    result = fetch_page_cached("https://example.com/miss")
    assert result is not None, "Expected a result from mock fetch"
    assert result.get("title") == "Test: https://example.com/miss"
    assert PAGE_CACHE.get("https://example.com/miss") is result, "Result should be cached"
    assert len(_fetch_log) == 1, f"Expected 1 fetch on miss, got {len(_fetch_log)}"
    print("  ✅ test_cache_miss")


def test_cache_miss_fail():
    """fetch_page_cached caches None results (dead URLs aren't retried)."""
    setup()
    result = fetch_page_cached("https://fail.example.com")
    assert result is None, "Expected None for failed URL"
    assert PAGE_CACHE.get("https://fail.example.com") is None, "None should be cached"
    print("  ✅ test_cache_miss_fail")


def test_cache_dedup():
    """Same URL requested twice: only one fetch, second returns cached."""
    setup()
    r1 = fetch_page_cached("https://example.com/dedup")
    r2 = fetch_page_cached("https://example.com/dedup")
    assert r1 is r2, "Both calls should return the same dict object"
    assert len(_fetch_log) == 1, f"Expected 1 fetch for dedup, got {len(_fetch_log)}"
    print("  ✅ test_cache_dedup")


def test_fetcher_pool():
    """Background fetcher pool populates the cache."""
    setup()
    urls = [
        "https://example.com/pool/1",
        "https://example.com/pool/2",
        "https://example.com/pool/3",
        "https://fail.example.com/pool/4",
    ]
    start_fetcher_pool(urls, num_workers=3)
    time.sleep(0.5)  # wait for workers

    for url in urls:
        assert url in PAGE_CACHE, f"URL {url} should be cached after pool fetch"
    assert PAGE_CACHE["https://fail.example.com/pool/4"] is None, "Failed URL should cache as None"
    for url in urls:
        count = _fetch_log.count(url)
        assert count == 1, f"URL {url} fetched {count} times (expected 1)"
    print("  ✅ test_fetcher_pool")


def test_fetcher_pool_empty():
    """Empty URL list doesn't crash the pool starter."""
    setup()
    start_fetcher_pool([], num_workers=5)
    print("  ✅ test_fetcher_pool_empty")


def test_pool_doesnt_block():
    """Processing loop never blocks on background pool (fetch on miss)."""
    setup()
    # Start pool on some URLs, but processing needs a *different* URL
    start_fetcher_pool(["https://example.com/slow/1"], num_workers=1)
    time.sleep(0.02)  # give worker a moment

    # Processing needs a URL the pool isn't working on
    result = fetch_page_cached("https://example.com/different")
    assert result is not None, "Should get result even though pool is busy elsewhere"
    assert len(_fetch_log) == 2, "Should have 2 fetches: pool's + sync"
    print("  ✅ test_pool_doesnt_block")


# ═══════════════════════════════════════════════════════════════════ #
# Integration — dry-run pipeline                                      #
# ═══════════════════════════════════════════════════════════════════ #

def test_dry_run_pipeline():
    """Run process-batch.py --dry-run --limit 3 against actual state.

    Validates the full import chain, rule loading, and per-bookmark
    logic without making any API calls.
    """
    setup()
    script = os.path.join(_script_dir, "process-batch.py")
    if not os.path.exists(script):
        print("  ⚠  test_dry_run_pipeline: script not found, skipping")
        return

    result = subprocess.run(
        ["python3", script, "--dry-run", "--limit", "3"],
        capture_output=True, text=True, timeout=120,
        env={**os.environ},
    )
    stdout = result.stdout
    stderr = result.stderr

    # Should exit 0
    assert result.returncode == 0, (
        f"Dry-run exited {result.returncode}\n"
        f"STDERR: {stderr[:500]}\n"
        f"STDOUT: {stdout[:500]}"
    )

    # Should mention the limit
    assert "Processing 3 bookmarks" in stdout, f"Expected 'Processing 3', got:\n{stdout[:300]}"

    # Should have a "Done in" summary line
    assert "Done in " in stdout, f"Expected 'Done in' summary, got:\n{stdout[-300:]}"

    # Should have per-bookmark lines with tags
    assert "tags:" in stdout, f"Expected tag inference output:\n{stdout[:500]}"

    # Should have the prefetch info
    assert "Background fetcher" not in stdout or "workers" in stdout, (
        "Should mention background pool if it ran"
    )

    # No API errors in stderr
    if stderr.strip():
        # Some WARNING about rules is OK, but no ERROR
        assert "ERROR" not in stderr.upper(), f"Unexpected stderr:\n{stderr}"

    print(f"  ✅ test_dry_run_pipeline  ({result.returncode}, {len(stdout)} chars)")


# ═══════════════════════════════════════════════════════════════════ #
# Main                                                               #
# ═══════════════════════════════════════════════════════════════════ #

def main():
    print("🚀 Cache & fetcher pool tests")
    test_cache_hit()
    test_cache_miss()
    test_cache_miss_fail()
    test_cache_dedup()
    test_fetcher_pool()
    test_fetcher_pool_empty()
    test_pool_doesnt_block()

    print("\n🚀 Pipeline integration test")
    test_dry_run_pipeline()

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    main()
