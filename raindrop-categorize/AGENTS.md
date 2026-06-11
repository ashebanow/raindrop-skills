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
