# Raindrop Linter Skill

Periodic linter for the Raindrop.io bookmark library. See `SKILL.md` for the full process.

## Key Facts

- Shares `RAINDROP_TOKEN` env var with raindrop-categorize
- Linter state stored at `~/.hermes/cache/raindrop-lint-state.json`
- Dead URL scan uses rolling cursor (oldest-first, position-tracked)
- Duplicate survivor selected by scoring on completeness + _categorized-v2 tag
- Requires Hermes kanban system for review cards

## When to Load This Skill

- User asks about bookmark duplicates or cleanup
- User wants to check for dead/malformed URLs
- User mentions running the linter or linting their library
- User asks about raindrop-lint kanban board
