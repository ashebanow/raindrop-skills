# Raindrop Skills — Monorepo

This repo contains Hermes skills for working with Raindrop.io:

- `raindrop-categorize/` — Auto-categorize bookmarks (Collection, Tags, Notes)
- `raindrop-linter/` — Find duplicates, near-duplicates, malformed URLs, and dead links

## Development Workflow

```bash
# Install/update a skill locally
cp -r raindrop-linter ~/.hermes/skills/raindrop-linter

# Or symlink for live development (if skills dir supports it)
ln -s "$(pwd)/raindrop-linter" ~/.hermes/skills/raindrop-linter
```

## Structure

```
raindrop-skills/
├── .env                          # Shared env vars (RAINDROP_TOKEN)
├── .gitignore
├── AGENTS.md                     # This file
├── raindrop-categorize/
│   ├── SKILL.md
│   ├── AGENTS.md
│   └── scripts/
│       └── raindrop_api.py
└── raindrop-linter/
    ├── SKILL.md
    └── scripts/
        └── raindrop_linter.py
```
