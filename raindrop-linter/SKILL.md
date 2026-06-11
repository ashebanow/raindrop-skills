---
name: raindrop-linter
description: "Periodic Raindrop.io library linter — finds duplicate URLs, near-duplicates, malformed URLs, and dead links. Creates kanban cards for review."
version: 1.0.0
author: ashebanow
license: MIT
metadata:
  hermes:
    tags: [raindrop, linter, duplicates, cleanup, kanban]
    related_skills: [raindrop-categorize]
---

# Raindrop Linter

## Overview

A periodic linter for your Raindrop.io bookmark library. Runs in phases to find quality issues and create kanban cards for you to review:

1. **Duplicate URLs** — same canonical URL bookmarked multiple times
2. **Near-duplicates** — URLs that differ only by protocol, www, tracking params, fragments
3. **Malformed URLs** — missing scheme, invalid hostname, bad encoding
4. **Dead URLs** — rolling batch scan (oldest-first, position-tracked) to find broken links

For duplicates, the **survivor** (kept bookmark) is selected by scoring each bookmark on the same quality axes used by `raindrop-categorize`: completeness (has collection + tags + note), recency, and whether it passed through the full categorization pipeline (`_categorized-v2` tag).

## Prerequisites

Same as `raindrop-categorize`:

```bash
export RAINDROP_TOKEN="your...token from https://app.raindrop.io/settings/integrations"
```

Source from `.env`:
```bash
set -a; source .env; set +a
```

### Required Script

```bash
python3 scripts/raindrop_linter.py <action>
```

## Actions

### `lint` — Run all phases

```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_linter.py lint [--limit N]
```

Runs duplicates check, malformed URL check, and dead URL batch scan.

### `dups` — Duplicates only

```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_linter.py dups [--json]
```

Finds exact duplicates (same canonical URL) and near-duplicates (different protocol/www/tracking params but same path). Outputs kanban card data.

### `malformed` — Malformed URLs only

```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_linter.py malformed [--json]
```

Scans all bookmarks for structurally invalid URLs.

### `dead` — Dead URL batch scan

```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_linter.py dead --limit 20
```

Checks N bookmarks (oldest `lastUpdate` first) via HTTP HEAD. Remembers position in `~/.hermes/cache/raindrop-lint-state.json` so each run picks up where the last left off.

### `state` — Show linter state

```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_linter.py state
```

Shows the cursor position and statistics from `raindrop-lint-state.json`.

## Scoring for Survivor Selection

When a group of duplicates is found, each bookmark is scored to pick the survivor:

| Signal | Points | Why |
|--------|--------|-----|
| Has a real Collection (not Unsorted) | +2 | Already categorized |
| Has at least one Tag | +2 | Already tagged |
| Has a Note (not empty) | +2 | Already has a description |
| Has `_categorized-v2` tag | +3 | Passed through full pipeline |
| Has a Description | +1 | Prior curation signal |
| Recency (up to +0.99) | fractional | Most recent categorization is freshest |

The bookmark with the highest score is kept; all others are flagged for deletion in kanban cards.

## Duplicate Detection Rules

### Exact duplicates
Same URL after normalization:
- Lowercase hostname
- Strip `www.` prefix
- Strip trailing slash
- Strip tracking params (`utm_*`, `fbclid`, `gclid`, etc.)
- Strip fragments

### Near-duplicates
Different canonical URLs that share the same `hostname + path`:
- Protocol variants (`http://` vs `https://`)
- `www.example.com` vs `example.com`
- `page?ref=twitter` vs `page`
- `page#section` vs `page`

### Malformed URLs
Structural problems detected by a `urlparse`-based validator:
- Missing scheme (no `http://` or `https://`)
- No hostname
- Invalid hostname (no dot, not localhost)
- Whitespace in URL
- Unusual schemes (`javascript:`, `about:`, `data:`)

## State Persistence

Linter state is stored at `~/.hermes/cache/raindrop-lint-state.json`:

```json
{
  "dead_url_cursor": 1751522131,
  "dead_url_checked": [1751522131, 1751522132, ...],
  "total_bookmarks": 2450,
  "last_run": "2026-06-10T17:30:00+00:00",
  "version": 1
}
```

The cursor ensures each run checks the oldest remaining unchecked bookmarks for dead URLs, slowly churning through the entire library without hammering the network.

## Kanban Board

Run results create cards on the **raindrop-lint** board. Columns:

- **pending-review** — new issues found this run
- **approved** — you've reviewed and want the action taken
- **done** — action completed
- **skipped** — you decided to keep as-is

### Card Types

#### Duplicate
```
Title: "dup: <bookmark title>"
Body:
  Type: exact|near-dup
  URL: https://...
  Survivor: <title> (score: 8.5) — id=12345
  Duplicates:
    - <other title> (score: 3.2) — id=67890
    - <other title> (score: 2.0) — id=13579
```

Action: delete all duplicates, keep survivor.

#### Malformed URL
```
Title: "malformed: <bookmark title>"
Body:
  URL: <raw url>
  Issue: no scheme
```

Action: fix the URL or delete the bookmark.

#### Dead URL
```
Title: "dead: <bookmark title>"
Body:
  URL: https://...
  Error: HTTP 404
  Checked: 2026-06-10
```

Action: review and either delete or update the URL.

## Cron Setup

Run weekly (or daily for aggressive linting):

```bash
hermes cron create \
  --schedule "0 9 * * 1" \
  --prompt "Run the raindrop-linter skill on the full library. Check for duplicates, near-duplicates, malformed URLs, and 20 dead URLs. Create kanban cards for all issues found on the raindrop-lint board." \
  --skills raindrop-linter
```

## Dependencies

- Python 3 stdlib only (`urllib`, `json`, `re`, `socket`)
- `RAINDROP_TOKEN` environment variable
- Hermes kanban system (for kanban board)

## Pitfalls

1. **Rate limiting** — Same ~120 req/min limit as the Raindrop API. The script paces itself with 200ms between pagination requests. The dead URL scan adds 150ms between HEAD requests.
2. **Dead URL false positives** — Some sites block HEAD requests, return 403 for bots, or require cookies. A HEAD failure doesn't always mean the URL is dead. The error message is included in the kanban card for your judgement.
3. **Dead URL state** — The cursor tracks position by `_id` order, not `lastUpdate` order. When new bookmarks are added with higher IDs, they'll be checked after the older batch completes.
4. **Large libraries** — Fetching all bookmarks (pagination) is the slowest part. For libraries with 5000+ bookmarks this takes ~20 seconds.
5. **`_categorized-v2` tag** — This tag is the strongest survivor signal. If no bookmark in a duplicate group has it, the tiebreaker favors recency. If the newer one hasn't been through the pipeline yet, the older `_categorized-v2` bookmark is preferred.
