# Cache Testing

> 24 nodes

## Key Concepts

- **test_cache.py** (12 connections) — `raindrop-categorize/scripts/test_cache.py`
- **fetch_page_cached()** (11 connections) — `shared/raindrop_common.py`
- **setup()** (9 connections) — `raindrop-categorize/scripts/test_cache.py`
- **main()** (9 connections) — `raindrop-categorize/scripts/test_cache.py`
- **test_pool_doesnt_block()** (6 connections) — `raindrop-categorize/scripts/test_cache.py`
- **start_fetcher_pool()** (6 connections) — `shared/raindrop_common.py`
- **test_cache_hit()** (5 connections) — `raindrop-categorize/scripts/test_cache.py`
- **test_cache_miss()** (5 connections) — `raindrop-categorize/scripts/test_cache.py`
- **test_cache_miss_fail()** (5 connections) — `raindrop-categorize/scripts/test_cache.py`
- **test_cache_dedup()** (5 connections) — `raindrop-categorize/scripts/test_cache.py`
- **test_fetcher_pool()** (5 connections) — `raindrop-categorize/scripts/test_cache.py`
- **test_fetcher_pool_empty()** (5 connections) — `raindrop-categorize/scripts/test_cache.py`
- **test_dry_run_pipeline()** (4 connections) — `raindrop-categorize/scripts/test_cache.py`
- **_mock_fetch()** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **fetch_page_cached returns cached content without calling fetch.** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **fetch_page_cached falls through to fetch on cache miss.** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **fetch_page_cached caches None results (dead URLs aren't retried).** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **Same URL requested twice: only one fetch, second returns cached.** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **Background fetcher pool populates the cache.** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **Empty URL list doesn't crash the pool starter.** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **Processing loop never blocks on background pool (fetch on miss).** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **Run process-batch.py --dry-run --limit 3 against actual state.      Validates th** (1 connections) — `raindrop-categorize/scripts/test_cache.py`
- **Return page content from the shared cache; fetch on miss.      Thread-safe: back** (1 connections) — `shared/raindrop_common.py`
- **Start a pool of background fetcher threads consuming a URL queue.      Each work** (1 connections) — `shared/raindrop_common.py`

## Relationships

- [Scan Batch & Shared API](Scan_Batch_%26_Shared_API.md) (4 shared connections)
- [Batch Processing & Classification](Batch_Processing_%26_Classification.md) (4 shared connections)

## Source Files

- `raindrop-categorize/scripts/test_cache.py`
- `shared/raindrop_common.py`

## Audit Trail

- EXTRACTED: 76 (78%)
- INFERRED: 22 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*