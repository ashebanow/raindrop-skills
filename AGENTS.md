# Raindrop Skills Monorepo

This repo contains Hermes Agent skills for managing a [Raindrop.io](https://raindrop.io) bookmark library.

## Skills

- **raindrop-categorize/** — Auto-categorize bookmarks: assign Collections, Tags, and Notes via the Raindrop REST API. Self-improving pipeline that scores output quality and flags taxonomy issues.
- **raindrop-linter/** — Periodic library linter: finds duplicate URLs, near-duplicates, malformed URLs, and dead links. Creates kanban cards for review.

## Usage

Each skill has its own `SKILL.md` with full instructions. Skills are installed to `~/.hermes/skills/` and loaded by name.

```bash
# Install/update a skill
cp -r raindrop-categorize ~/.hermes/skills/raindrop-categorize
cp -r raindrop-linter ~/.hermes/skills/raindrop-linter
```

## Structure

```
raindrop-skills/
├── .env                     # RAINDROP_TOKEN (gitignored)
├── .gitignore
├── AGENTS.md                # This file
├── raindrop-categorize/
│   ├── SKILL.md
│   ├── ORIGINAL_PROMPT.md   # Original task spec (historical)
│   └── scripts/
│       └── raindrop_api.py
└── raindrop-linter/
    ├── SKILL.md
    └── scripts/
        └── raindrop_linter.py
```
