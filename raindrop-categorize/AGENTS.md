# Raindrop Categorize Skill

Primary Raindrop bookmark categorization pipeline. See `SKILL.md` for the full process.

## Key Facts

- Uses Raindrop REST API (`https://api.raindrop.io/rest/v1`)
- Requires `RAINDROP_TOKEN` env var
- API pagination cap: `perpage=50` (higher values silently capped)
- Rate limit: ~120 req/min
- Tracking tag: `_categorized-v2` (applied only after all 3 phases succeed)
- Collections are never deleted; Tags are never deleted (merge-tags is the only destructive tag op)
- Audit log at `~/.hermes/cache/raindrop-audit-log.jsonl`
- Quality scores at `~/.hermes/cache/raindrop-quality.json`

## When to Load This Skill

- User asks about categorizing bookmarks
- User mentions running the raindrop pipeline
- User asks about Raindrop API quirks or collection/tag management
- User asks to review the categorization quality or taxonomy health

## Cron Jobs

- **raindrop-categorize-daily** (`0 7,19 * * *`) — runs twice daily, categorizes eligible bookmarks, creates kanban cards for new collections/tags. Delivers summary to Discord (origin).

## Notes for Future Agents

- **The skill has been assigning collections correctly over multiple runs** (verified by the user). The `references/collection-keyword-mapping.md` is a **fallback** keyword map for when other collection-assignment methods don't produce a match — not evidence that the script never did collection assignment. Earlier agents should not infer "never worked" from the line *"it was never designed to"* in that file; the original author of that comment has acknowledged the wording is unclear.
- **The audit log is not a complete record of collection writes.** Low counts in `fields_changed` do not mean the system has been failing — the script was historically doing the work in ways that weren't all logged in that field. Always cross-check against Discord delivery summaries (the LLM-driven cron's messages confirmed successful collection assignments) before drawing conclusions from a small `fields_changed` count alone.
