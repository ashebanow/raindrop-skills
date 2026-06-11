# Raindrop Linter Skill

Periodic linter for the Raindrop.io bookmark library. See `SKILL.md` for the full process.

## Key Facts

- Shares `RAINDROP_TOKEN` env var with raindrop-categorize
- Linter state stored at `~/.hermes/cache/raindrop-lint-state.json`
- Dead URL scan uses rolling cursor (oldest-first, position-tracked)
- Duplicate survivor selected by scoring on completeness + _categorized-v2 tag
- Requires Hermes kanban system for review cards

## Cron Jobs

- **raindrop-linter-weekly** (`0 10 * * 1`) — runs every Monday at 10am. Checks duplicates, 100 dead URLs. Only notifies Discord if new issues are found (otherwise silent).

## When to Load This Skill

- User asks about bookmark duplicates or cleanup
- User wants to check for dead/malformed URLs
- User mentions running the linter or linting their library
- User asks about raindrop-lint kanban board
