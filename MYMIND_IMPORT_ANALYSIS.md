# MyMind Import Analysis

## Mapping

| Raindrop | → MyMind | Notes |
|---|---|---|
| URL (`link`) | `url` on `POST /objects` | Auto-deduplicates — same URL returns 200 (bumped) not 201 |
| Title | `title` | |
| Note | `notes[]` — single entry, `text/markdown` | |
| Description (legacy) | Merged into note body before import | We no longer use descriptions; any remaining are appended |
| Tags | `tags[]` | Strip `_categorized-v2` tracking tag |
| Root collection | `spaces[]` — one space per bookmark | ~12-15 spaces total |
| Child collection name | Additional tag | e.g. "Italy", "Florence" become tags |
| Cover image | Screenshot (auto-captured at import) | MyMind generates these; we don't use custom covers |
| Excerpt | `summary` (AI-generated) | MyMind generates this; we don't use Raindrop's excerpt |
| Highlights | — | Not used |
| Created date | Lost | MyMind assigns current timestamp on import |

## Losses

| What | Severity | Mitigation |
|---|---|---|
| **Created dates** | Medium | All bookmarks show import day. 15 years of history flattened. Just eat it. |
| **Collection hierarchy** | Low | Top-level → spaces, child → tags. Search still works. |
| **Broken link flag** | Low | MyMind saves full content at creation time, so dead links later don't lose content. No proactive dead-link detection though. |

## What We Don't Use (No Loss)

- Custom cover images (MyMind generates screenshots — a win)
- Raindrop excerpt (MyMind generates AI `summary` — a win)
- Highlights (not used)

## Space Strategy

~12-15 spaces, one per top-level Raindrop collection:

```
Homelab & Self-Hosting
AI & LLMs
Desktop & UI
Programming
NixOS
Travel
Food & Cooking
...
```

Child collections (e.g. "Italy", "Florence" under Travel) become tags on the objects.

## Import Flow

```
1. Create ~15 spaces via POST /spaces → capture space IDs
2. Paginate through all Raindrop bookmarks
3. For each bookmark:
   a. Map root collection → space ID
   b. Map child collection → extra tag
   c. Merge description (if any) into note body
   d. Strip _categorized-v2 tracking tag
   e. POST /objects with url, title, tags, notes, spaces
   f. Duplicate URLs → 200 OK (safe to restart if interrupted)
```

## API Credit Budget

MyMind plans: Guest (500/5K), Bookmarker (2.5K/25K), Student of Life (5K/50K), Mastermind (10K/100K).
Sustained = 30-day window. Burst = short spike window.

| Operation | Count | Cost | Total |
|---|---|---|---|
| Create spaces | ~15 | 100 each | 1,500 |
| Create objects (URL) | ~5,563 | 10 each | 55,630 |
| **Total** | | | **~57,130** |

- **Mastermind**: Comfortable (100K sustained)
- **Student of Life**: Tight but possible if staggered across months (50K sustained + 5K burst)
- **Bookmarker**: Not viable without multistage batching

## Idempotency

MyMind auto-deduplicates by URL. `POST /objects` with the same URL returns `200 OK` (bumped timestamp) instead of `201 Created`. This means:

- Script can be safely restarted if interrupted or rate-limited
- No risk of creating duplicates
- Can run in batches across multiple days/months if needed

## Rate Limiting (Dynamic)

MyMind sends rate limit state in every response header. Instead of fixed-delay pacing, the import script should parse these headers and adjust on the fly:

```
RateLimit-Policy: "burst";q=10000;w=300, "sustained";q=100000;w=2592000
RateLimit:        "burst";r=9990;t=300, "sustained";r=99641;t=2589945
RateLimit-Cost:   10
```

- `r` = credits remaining in window
- `t` = seconds until window resets

**Strategy:** after each request, check remaining credits. If either `burst` or `sustained` is nearing exhaustion (r < 100), sleep until that window's `t` resets. Otherwise, compute a dynamic delay proportional to remaining burst budget — fast when headroom is plentiful, gentle when it's tight. On `429 Too Many Requests`, parse the `RateLimit` header for every policy with `r=0` and sleep until the slowest exhausted window resets.

This approach eliminates the need for a fixed `REQUEST_DELAY` constant and adapts to plan tier, concurrent usage, and window timing automatically.

## Objects Created One at a Time

No batch endpoint. Each bookmark is a separate `POST /objects` call. With dynamic rate limiting, full import throughput depends on plan and current usage rather than a fixed pacing delay.
