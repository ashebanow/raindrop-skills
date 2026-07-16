# fetch_page_cached()

> God node · 11 connections · `shared/raindrop_common.py`

**Community:** [Cache Testing](Cache_Testing.md)

## Connections by Relation

### calls
- [process_comparison()](process_comparison%28%29.md) `INFERRED`
- [process_one()](process_one%28%29.md) `INFERRED`
- [main()](main%28%29.md) `INFERRED`
- test_pool_doesnt_block() `INFERRED`
- test_cache_hit() `INFERRED`
- test_cache_miss() `INFERRED`
- test_cache_miss_fail() `INFERRED`
- test_cache_dedup() `INFERRED`
- fetch_page_content() `EXTRACTED`

### contains
- raindrop_common.py `EXTRACTED`

### rationale_for
- Return page content from the shared cache; fetch on miss.      Thread-safe: back `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*