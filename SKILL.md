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

## Operations Allowed vs Forbidden

The following rules apply to every run of this skill. No destructive operation runs without explicit user approval via the kanban board.

### Raindrops (Bookmarks)

| Operation | Allowed | Notes |
|---|---|---|
| Read / List | yes | Via `raindrops` and `get` commands |
| Update note & description | yes | Core purpose of the skill — consolidate description into note |
| Update collection assignment | yes | Core purpose — categorize into the right collection |
| Update tags | yes | Core purpose — assign relevant tags |
| **Delete** | **never** | Raindrops are never deleted |

### Collections

| Operation | Allowed | Notes |
|---|---|---|
| Read / List / Tree | yes | Via `collections` and `children` commands |
| Create new | yes | Implicitly creates a kanban card for user approval first |
| Rename | pending | Not yet implemented — add via `update` on collection endpoint |
| Reparent | pending | Not yet implemented — Phase 7 may suggest it |
| **Delete** | **never** | Collections are never deleted. Even if empty — they may be reused in the future. If a duplicate exists, flag it in the audit but leave it in place |

### Tags

| Operation | Allowed | Notes |
|---|---|---|
| Read / List | yes | Via `tags` command |
| Assign to bookmark | yes | Core purpose — done in Phase 3c via raindrop update |
| **Delete** | **never** | Tags are never deleted under any circumstance |
| **Merge** | **only after kanban approval** | `merge-tags <source> <target>` reassigns all bookmarks from source to target, then removes the source tag. This is the **only** destructive tag operation, and only runs after the user approves the kanban card |

### Summary of Destructive Rules

| What | Rule |
|---|---|
| Deleting a raindrop | ❌ Forbidden — never, under any circumstance |
| Deleting a collection | ❌ Forbidden — never, under any circumstance. Even if empty |
| Deleting a tag | ❌ Forbidden — never, under any circumstance |
| Merging two tags → removes source tag | ✅ Only after user kanban approval via `merge-tags` |
| Merging two collections → removes source | ❌ Forbidden — not yet implemented |

**Golden rule:** if an operation destroys data (removes a raindrop, tag, or collection), it must be explicitly approved by the user via a kanban card in the `raindrop-audit` board. The only exception is `merge-tags`, which removes the source tag after reassigning all its bookmarks, and that too requires kanban approval.

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

1. Fetch all bookmarks across all collections (paginated, up to `limit=100` per page):
   ```bash
   # Unsorted (collection 0), 50 per page
   source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py raindrops 0 50
   ```
   (Use `collection=0` for "Unsorted", or any collection ID for a specific one.)

2. **Tracking tag**: every bookmark processed by this skill gets a tracking tag `_categorized-v2`. A bookmark that has this tag has been through the pipeline before and is **not eligible** for the new pool (it may still qualify as a filler — see below).

3. A bookmark is **eligible for the new pool** if **all** of these are true:
   - It **does not** have the `_categorized-v2` tag
   - AND one or more of: no Collection (or Unsorted), tags empty (ignoring `_categorized-v2`), no note/description

4. Collect the new pool — up to 100 bookmarks.

5. **Filler queue**: if the new pool has fewer than 100 items, fill the remaining slots with bookmarks that **do** have the `_categorized-v2` tag, selected in this order:
   - **Pass 1**: bookmarks with `lastUpdate` older than 24 hours, sorted oldest first. This catches stale categorizations that would benefit from an improved pipeline, while preventing the same bookmark from cycling every run.
   - **Pass 2**: if still under 100, include bookmarks with `lastUpdate` within the last 24 hours, sorted oldest first. This ensures full batches even on small libraries.
   - **Skip any** bookmark already in the new pool to avoid duplicates.

6. **Why both signals?** `_categorized-v2` is the binary gate — has this bookmark ever gone through the pipeline? `lastUpdate` is the ageing signal — how stale is its last categorization? When the pipeline improves (new sub-collections, better tag matching, smarter notes), the most stale bookmarks get the benefit first. Together they produce a rolling reprocessing cycle without manual intervention.

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
- **Breadth heuristic**: collections with >25 bookmarks are candidates for sub-collection splitting. When possible, prefer a smaller, more specific sub-collection over a large parent collection. Ideal range is 5–25 bookmarks per collection.
- If **no suitable match** exists in the collection tree: flag the bookmark for a new collection via a kanban card (Phase 5).
- If the best match is a collection with >100 bookmarks and a more specific sub-collection could be created: create a kanban card suggesting the sub-collection split.

**Update via API:**
```bash
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py update <raindrop_id> '{"collection": {"$id": <collection_id>}}'
```

#### 3c. Process the Tags Field

- If the bookmark already has one or more Tags: evaluate each for relevance. Retain relevant ones; remove irrelevant or misapplied ones.
- If Tags are empty: infer one or more Tags from the Note and Description.
- **Match logic**: scan the existing Tag list. Tag names are flat (no hierarchy). Prefer 1–3 focused tags over 6+ scattershot ones.
- If **no suitable Tag** exists: assign a new tag name anyway — Raindrop creates tags implicitly on first assignment. The new tag will be surfaced for your review in Phase 5.
- If the taxonomy audit (Phase 7) flags two tags as synonyms, defer the merge to the kanban board (Phase 5) — never merge or remove tags without the user deciding.

**Update via API:**
```bash
# Tags are passed as a JSON array — always include _categorized-v2
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py update <raindrop_id> '{"tags": ["_categorized-v2", "tag1", "tag2"]}'
```

The `_categorized-v2` tag is always added to every processed bookmark, alongside any inferred tags.

### Phase 4 — Score Output Quality

Score quality at **three granularities**: per-raindrop, per-collection, and global. Each captures a different signal.

#### Per-Raindrop (individual bookmark)

For each bookmark in the processed list, score 1–10 on each axis. This is the finest grain — used to spot individual misassignments.

| Axis | 1–3 | 4–7 | 8–10 |
|------|-----|-----|------|
| **Completeness** | Missing 2+ of Collection/Tags/Note | Missing 1 of Collection/Tags/Note | Has all three: Collection, Tags, Note |
| **Succinctness** | Note is verbose, rambling, or padded | Note is OK but could be tighter | Note is tight, URL-relevant, no fluff |
| **Appropriate Tone** | Robotic or formal | Mixed, some awkward phrasing | Reads like you wrote it — natural, personal |
| **Relevance** | Wrong Collection or Tags | Mostly correct, 1 mismatch | Every assignment is semantically precise |

#### Per-Collection (aggregated per collection, including sub-collections)

After all bookmarks are processed, roll up scores for each **root collection** (including its descendants). This catches taxonomy-level issues:

| Metric | How it's calculated | What it signals |
|--------|-------------------|-----------------|
| **Completeness %** | % of bookmarks in this sub-tree that have all 3 fields | How well-categorised that topic area is |
| **Breadth ratio** | `bookmark_count / ideal_max(25)` — ratio >1 means oversized | Collection may need sub-collections |
| **Untagged %** | % of bookmarks with empty `tags` in this sub-tree | Is tagging being neglected in this area? |
| **Sub-collection balance** | stddev of child bookmark counts — high stddev = one child dominates | Lopsided sub-collections may need rebalancing |

#### Global (entire run)

Roll up all per-raindrop and per-collection scores into a single run summary. Written to `~/.hermes/cache/raindrop-quality.json` at the end of each run and read back at the start of the next run for trend comparison. No other persistence mechanism is needed.

| Score | What it measures |
|-------|-----------------|
| **Avg per-raindrop score** | Mean of all 4 axes across all processed bookmarks |
| **Avg completeness %** | % of all bookmarks (not just processed) that have all 3 fields |
| **Healthy collections %** | % of root collections where breadth ≤ 1.0 (≤25 bookmarks) |
| **Tagged coverage %** | % of bookmarks with at least 1 tag |

**Trend detection:** compare global scores against the last 3 runs. If avg per-raindrop score drops ≥1 point for 2 consecutive runs, the skill halts and requests human review of its process before continuing.

### Phase 5 — Create Kanban Cards for Pending Decisions

Instead of a CSV, create kanban cards in the `raindrop-audit` board. Each issue gets its own card with clear context so the user can review at their own pace. All cards go into a `pending-review` column.

**What gets a card:**
- Each bookmark needing a **new Collection** → one card per bookmark
- Each **tag merge** suggestion (synonyms found) → one card per merge
- Each **taxonomy issue** from Phase 7 audit → one card per issue
- Each bookmark that was assigned a **new tag** (created implicitly) → one summary card listing all new tags created this run

**Card body format:**
```
Title: "collection: <raindrop title>"
Body:
  URL: <url>
  Suggested: <collection name> under <parent>
  Reason: <semantic match explanation>

Title: "merge: <source> → <target>"
Body:
  Source tag: <source> (N bookmarks)
  Target tag: <target> (N bookmarks)
  Why: <reason these are synonyms>

Title: "audit: <issue description>"
Body:
  Collection/Tag: <name>
  Issue: <description>
  Suggestion: <proposed action>
```

Each card goes to the `pending-review` list on the `raindrop-audit` board.

### Phase 6 — Execute Approved Kanban Cards

1. The user reviews the `raindrop-audit` board and either **completes** cards (approves) or **blocks** them (rejects/changes needed).
2. For each completed card:
   - **New collection**: create via API using the python helper
   - **Tag merge**: run `python3 scripts/raindrop_api.py merge-tags <source> <target>`
   - **New tags**: already created implicitly on assignment in Phase 3c — no action needed
3. Re-process the bookmarks now that new Collections/Tags exist.
4. Archive completed cards with a summary of what was done.

### Phase 7 — Evaluate and Improve the Taxonomy

After all bookmarks are processed, run an **audit pass** on the full Collection tree and Tag list. Create kanban cards for each issue found (same Phase 5 format, same `raindrop-audit` board):

**Collection audit triggers:**
- **Too broad** — a collection exceeds 25 bookmarks AND groups conceptually separate things. E.g. `NixOS` at 257 bookmarks is a candidate for sub-collections.
- **Empty** — a collection has 0 bookmarks and no recent activity.
- **Redundant** — two collections have overlapping themes.
- **Ambiguous name** — the title doesn't clearly describe its contents.
- **Wrong parent** — a collection fits better under a different parent.

**Tag audit triggers:**
- **Synonym pair** — two tags with identical meaning (e.g. "nix" and "nixos").
- **Orphaned** — tag has 0 bookmarks attached.
- **Underused** — tag applied to fewer than 3 bookmarks.
- **Inconsistent casing** — tags that are clearly the same concept but cased differently.

**Collection breadth heuristic:**
When assigning a bookmark to a collection, use this signal:
```
if collection.count > 25:
    prefer  a  more  specific  sub-collection  or  flag  for  audit
  
  ideal  range: 5-25 bookmarks per collection
```
If no suitable sub-collection exists and the parent is oversized, create a kanban card suggesting one.

**Improvement actions** (all gated through kanban cards):
```bash
# Only after user approves the kanban card:
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py create-collection '{"title": "...", "parent": {"$id": ...}}'
source .env && export RAINDROP_TOKEN && python3 scripts/raindrop_api.py merge-tags <source> <target>
```

Tags are never deleted or merged without explicit user approval via the kanban board.

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
9. **Tracking tag `_categorized-v2`** — This tag is added to every processed bookmark. It should be excluded from relevance checks (it's meta-data, not a real tag). When checking if a bookmark has "no tags", ignore `_categorized-v2`. When inferring tags, never suggest removing `_categorized-v2`.
10. **Quality scores are file-only** — Scores persist in `~/.hermes/cache/raindrop-quality.json`. No supermemory dependency. The JSON file must be manually deleted to reset trend data.

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
- [ ] Kanban cards created for pending decisions (Phase 5)
- [ ] Approved Collections/Tags created via API
- [ ] Taxonomy audit completed and results recorded
- [ ] `.env` not committed to git (add `.env` to `.gitignore`)

## Related Skills

- **plan** — Use when producing a step-by-step plan for a complex multi-phase run.
- **systematic-debugging** — Use when a Raindrop API call fails and root-cause analysis is needed.
- **hermes-agent-skill-authoring** — Use when patching or extending this skill.
