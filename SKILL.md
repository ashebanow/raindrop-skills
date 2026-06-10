---
name: raindrop-categorize
description: "Use when categorizing Raindrop.io bookmarks — assign Collections, Tags, Notes, and Descriptions via the Raindrop REST API. Self-improving: scores its own output quality and flags redundant/ambiguous categories for cleanup."
version: 2.0.0
author: ashebanow
license: MIT
metadata:
  hermes:
    tags: [raindrop, bookmarks, categorization, api, self-improving]
    related_skills: [plan, systematic-debugging]
---

# Raindrop Categorize

## Overview

This skill processes Raindrop.io bookmarks through a multi-phase pipeline: reading Collections and Tags, selecting bookmarks to process, classifying each one (Collection, Tags, Notes), scoring output quality, and surfacing new Collections/Tags for user approval. It is designed to be **self-improving** — it scores its results each run and uses that feedback to detect patterns of failure, ambiguity, or redundancy.

At the end of each run it also evaluates the taxonomy itself, flagging Collections or Tags that are redundant, poorly named, or inconsistently applied.

## When to Use

- You want to auto-categorize unsorted or untagged Raindrop bookmarks
- You have a backlog of bookmarks that need Collections, Tags, and Notes
- You want to audit and clean up your existing Collection and Tag taxonomy
- You want a recurring cron job that keeps your Raindrop library organised

**Don't use for:** one-off bookmark lookups, deleting bookmarks, or bulk export.

## Prerequisites

### Required Environment Variable

```bash
export RAINDROP_TOKEN="your...nThe token is a Raindrop.io **test token** from <https://app.raindrop.io/settings/integrations>. It never expires. The files `.env` or `~/.hermes/.env` are auto-sourced if present.

### Required Script

Use the Python API helper to avoid bash `$` expansion issues with tokens:

```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py <command>
```

Copy `scripts/raindrop_api.py` from this skill's directory, or load it via `skill_view(name='raindrop-categorize', file_path='scripts/raindrop_api.py')`.

### Raindrop API Base

`https://api.raindrop.io/rest/v1`

## The Full Process

### Phase 1 — Build Collection Tree and Tag List

```bash
# Get all collections (root + children merged, with hierarchy)
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py collections

# Get all tags with counts
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py tags

# To see only child collections (those with a parent)
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py children
```

The `collections` command fetches both `GET /collections` (root) and `GET /collections/childrens` (children), then merges them into a single tree sorted by parent.

Build two data structures (keep in working memory or write to `.hermes/cache/raindrop-trees.json`):

1. **Collection tree** — map each `_id` to its `title`, `parent.$id`, and children list, forming a hierarchy.
2. **Tag list** — flat list of tag `_id` names with usage `count`.

### Phase 2 — Select Bookmarks to Process

1. Fetch all bookmarks (paginated, up to `limit=100` per page):
   ```bash
   # Unsorted (collection 0), 50 per page
   source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py raindrops 0 50
   ```
   (Use `collection=0` for "Unsorted", or any collection ID for a specific one.)

2. A bookmark is **eligible for processing** if **one or more** of:
   - No `collection` or `collection.$id` refers to the "Unsorted" collection
   - `tags` is empty or null
   - `description` and `note` are both empty/null

3. Collect the eligible list — **at most 100 bookmarks**.

4. If the eligible list has fewer than 100 items, **fill the remaining slots** with bookmarks that have the oldest `lastUpdate` (least recently processed).

### Phase 3 — Process Each Bookmark

For each bookmark in the list, apply the following three sub-processes **in order**:

#### 3a. Process the Description and Notes Fields

- **Read** existing `note` and `description` fields.
- **If `description` looks handwritten** (multi-sentence, personal voice, URL-specific commentary): preserve it verbatim as the core of the new note. You may add to and reword it as long as no substantive content is lost.
- **If `description` looks AI-generated** (Raindrop's auto-summary, generic boilerplate): discard it.
- **If `note` already has content**: merge handwritten description into the note, preserving both meaningfully. Prefer the note as the canonical location.
- **If both are empty**: write a brand-new note based on the bookmark's URL content (fetch the page to summarise, or infer from the URL/title).
- **Final result**: `note` gets the clean unified text; `description` is set to empty string.

**Update via API:**
```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py update <raindrop_id> '{"note": "...", "description": ""}'
```

#### 3b. Process the Collection Field

- If the bookmark already has a Collection and it's not "Unsorted": **skip**.
- Otherwise, use the Note (from 3a) to infer a suitable Collection from the existing tree.
- If there's no Note yet (shouldn't happen — 3a runs first), write one via 3a first.
- **Match logic**: scan the Collection tree. Look for semantic overlap between the Note/Description content and the Collection title/description. Prefer the most specific match (deepest in the tree).
- If **no suitable match** exists in the collection tree: save the bookmark to a **persistent todo list** (see "Pending Collections & Tags" below) and mark it as `needs_new_collection: true`.

**Update via API:**
```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py update <raindrop_id> '{"collection": {"$id": <collection_id>}}'
```

#### 3c. Process the Tags Field

- If the bookmark already has one or more Tags: evaluate each for relevance. Retain relevant ones; remove irrelevant or misapplied ones.
- If Tags are empty: infer one or more Tags from the Note and Description.
- **Match logic**: scan the existing Tag list. Tag names are flat (no hierarchy). Prefer 1–3 focused tags over 6+ scattershot ones.
- If **no suitable Tag** exists: assign a new tag name anyway — Raindrop creates tags implicitly on first assignment. The new tag will be surfaced for your review in Phase 5.
- If the taxonomy audit (Phase 7) flags two tags as synonyms, defer the merge to the user review CSV in Phase 5/6 — never merge or remove tags without the user deciding.

**Update via API:**
```bash
# Tags are passed as a JSON array
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py update <raindrop_id> '{"tags": ["tag1", "tag2"]}'
```

### Phase 4 — Score Output Quality

**Before** and **After** processing the list, evaluate quality on these four axes. Score 1–10 each:

| Axis | 1–3 | 4–7 | 8–10 |
|------|-----|-----|------|
| **Completeness** | Many bookmarks still missing Collection/Tags/Note | Most have 2/3 fields set | Every bookmark has Collection + Tags + Note |
| **Succinctness** | Notes are verbose or rambling | Notes are reasonably concise | Notes are tight, URL-relevant, no fluff |
| **Appropriate Tone** | Robotic or formal for personal bookmarks | Mixed, some awkward phrasing | Reads like the user wrote it themselves — natural, personal voice |
| **Relevance** | Wrong Collections or Tags assigned | Mostly correct, a few mismatches | Every assignment is semantically precise |

Store the before/after scores in `~/.hermes/cache/raindrop-quality.json` for long-run trend analysis.

### Phase 5 — Surface Pending Collections, Tags & Merges for User Review

If Phase 3 produced any bookmarks needing new Collections, or if Phase 7 flagged tags for merging:

1. Build a CSV file at `.hermes/cache/raindrop-pending.csv` with these columns:
   - `raindrop_name` — the bookmark title
   - `url` — the bookmark URL
   - `description` — the Note/Description content (for context)
   - `C-<suggested_collection>` — one column per unique suggested Collection title, prefixed with `C-`
   - `T-<suggested_tag>` — one column per unique suggested Tag name, prefixed with `T-`
   - `T-merge:<source>→<target>` — one column per suggested tag merge (e.g. `T-merge:dev->development`)

2. The CSV cells are empty — the user fills in `yes` / `no` / renames the column header.

3. Present the CSV to the user and ask them to fill it out.

### Phase 6 — Create Approved Collections & Tags

1. Read back the completed CSV.
2. For each row where the user approved a `C-<name>` column: create the Collection via API:
   ```bash
   source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py create-collection '{"title": "collection_name", "parent": {"$id": <parent_id_or_null>}}'
   ```
3. For each row where the user approved a `T-<name>` column: tags are created implicitly when first assigned to a bookmark. Assign the tag to the bookmark.
4. For each row where the user approved a `T-merge:<source>→<target>` column: reassign all bookmarks with the source tag to the target tag, then remove the source tag.
5. Re-process the bookmarks from the CSV now that the new Collection/Tag exists.
6. **Delete the CSV file** only when all rows are processed.

### Phase 7 — Evaluate and Improve the Taxonomy

After all bookmarks are processed, run an **audit pass** on the full Collection tree and Tag list:

**Collection audit:**
- Are any Collections empty (0 bookmarks)? Suggest archiving or deleting.
- Are any Collections redundant (same theme as another)? Suggest merging.
- Are any Collections names ambiguous or unclear? Suggest renaming.
- Is any Collection better suited under a different parent? Suggest reparenting.

**Tag audit:**
- Are any tags unused (count=0)? Flag as potentially orphaned.
- Are any tags synonyms (e.g. "dev", "development", "programming")? Flag for possible merge.
- Are any tags applied to fewer than 3 bookmarks? Flag as potentially too niche.
- Are any tags misspelled or inconsistently cased? Flag for standardisation.

**Improvement actions** (presented for user review in Phase 5/6):
```bash
# Delete an empty or redundant collection (only after user approval)
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py delete-collection <collection_id>
```

Tags are never deleted or merged without user approval via the Phase 5/6 CSV review process.

Record the audit findings in `~/.hermes/cache/raindrop-audit-<date>.md`.

### Quality Score Trend

The `raindrop-quality.json` file accumulates scores across runs. After each run, compare:

- **Before vs After** for this run (did improvements stick?)
- **Current vs Historical** (is quality trending up or down?)
- If quality is **trending down** for 2+ consecutive runs, flag the taxonomy audit results as a priority action.

### Recurring Run via Cron

To run this weekly:

```bash
hermes cron create \
  --schedule "0 9 * * 1" \
  --prompt "Run the raindrop-categorize skill on all eligible bookmarks (collections=0, tags=[], no note). Read scores from cache and report changes." \
  --skills raindrop-categorize
```

## Self-Improvement Logic

The skill has three built-in improvement loops:

### Loop 1 — Per-Run Scoring
Before/After scores on completeness, succinctness, tone, relevance. Stored in quality cache. If scores drop below 7 on any axis for two consecutive runs, the skill halts and requests a human review of its process.

### Loop 2 — Taxonomy Audit
After each run, full Collection and Tag audit. If >3 issues found, the skill produces a cleanup proposal and asks for confirmation before auto-executing.

### Loop 3 — Model Self-Reflection
The skill includes a reflection step where it considers:
- Were any assignments ambiguous? → Improve the prompt text.
- Were any URLs un-fetchable? → Record and skip next time.
- Were any Collections too broad? → Flag for splitting.
- Did the scoring itself change significantly? → Re-calibrate scoring rubric.

## Common Pitfalls

1. **Missing RAINDROP_TOKEN** — Without the token set as an env var, every API call returns 401. Source the `.env` file first: `set -a; source .env; set +a`.
2. **Rate limiting** — Raindrop API rate-limits at ~120 req/min. Batch updates (PUT with `raindrops` array) rather than one-at-a-time PUTs when possible.
3. **Unsorted collection is id 0** — The special "Unsorted" / "No Collection" collection has `_id=0`. Check for both null and `0` when determining if a bookmark needs a Collection.
4. **Tag creation is implicit** — Tags don't have their own create endpoint. Assign the tag name to a bookmark and it's created automatically.
5. **Parent collections** — When creating a collection, the parent is `{"$id": <parent_id>}` or `{"$id": null}` for top-level. Missing this structure causes silent failures.
6. **Description vs Note** — The `description` field is short (Raindrop auto-summary or user excerpt); `note` is the long-form field. This skill consolidates into `note` and empties `description`.
7. **CSV encoding** — Raindrop titles/URLs can contain commas. Use proper CSV quoting (Python's `csv` module handles this) to avoid parsing errors.
8. **Self-improvement doesn't mean inventing data** — If a URL is unreachable, report it. Do not synthesize page content to write a Note. Skip that bookmark and note the failure.

## Verification Checklist

- [ ] `RAINDROP_TOKEN` is set and `python3 scripts/raindrop_api.py user` returns your info
- [ ] Collections fetched and tree built correctly
- [ ] Tags fetched with usage counts
- [ ] Eligible bookmarks identified (unsorted + untagged + no note)
- [ ] At most 100 bookmarks selected; remaining slots filled by least-recently-processed
- [ ] Description consolidated into Note; description cleared
- [ ] Collections assigned from existing tree (or flagged as new)
- [ ] Tags assigned (or flagged as new)
- [ ] Before/after scores recorded in quality cache
- [ ] Pending CSV created and presented to user if needed
- [ ] Approved Collections/Tags created via API
- [ ] Taxonomy audit completed and results recorded
- [ ] `.env` not committed to git (add `.env` to `.gitignore`)

## Related Skills

- **plan** — Use when producing a step-by-step plan for a complex multi-phase run.
- **systematic-debugging** — Use when a Raindrop API call fails and root-cause analysis is needed.
- **hermes-agent-skill-authoring** — Use when patching or extending this skill.
