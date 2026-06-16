# Raindrop Skills Monorepo

This repo contains Hermes Agent skills for managing a [Raindrop.io](https://raindrop.io) bookmark library.

## Skills

- **raindrop-categorize/** — Auto-categorize bookmarks: assign Collections, Tags, and Notes via the Raindrop REST API. Self-improving pipeline that scores output quality and flags taxonomy issues.
- **raindrop-linter/** — Periodic library linter: finds duplicate URLs, near-duplicates, malformed URLs, and dead links. Creates kanban cards for review.

## Usage

Each skill has its own `SKILL.md` with full instructions. Skills are installed to `~/.hermes/skills/` and loaded by name.

### Deploy changes to Hermes

After making changes to any skill script, deploy to the Hermes skills directory:

```bash
./deploy-skills.sh
```

This copies scripts, the shared module, and the rules file to `~/.hermes/skills/`.

### Manual install (first time)

```bash
cp -r raindrop-categorize ~/.hermes/skills/raindrop-categorize
cp -r raindrop-linter ~/.hermes/skills/raindrop-linter
```

### Structure

After deploy, the skills directory mirrors the repo:

```
~/.hermes/skills/
├── raindrop-categorize/
│   ├── scripts/
│   ├── references/
│   │   └── raindrop-rules.json
│   └── SKILL.md
├── raindrop-linter/
│   └── scripts/
└── shared/
    ├── raindrop_common.py
    └── __init__.py
```

## Cron Jobs

- **raindrop-categorize-daily** — twice daily (7am/7pm), categorizes bookmarks, notifies Discord
- **raindrop-linter-weekly** — Mondays 10am, checks duplicates + dead URLs, silent if nothing found

## Structure

```
raindrop-skills/
├── .env                     # RAINDROP_TOKEN (gitignored)
├── .gitignore
├── AGENTS.md                # This file
├── deploy-skills.sh          # Deploy to ~/.hermes/skills/
├── shared/                  # Shared module (both skills import this)
│   ├── raindrop_common.py
│   └── __init__.py
├── raindrop-categorize/
│   ├── SKILL.md
│   ├── IMPROVEMENT_PLAN.md  # Self-improvement roadmap
│   ├── ORIGINAL_PROMPT.md   # Original task spec (historical)
│   ├── references/
│   │   └── raindrop-rules.json  # All categorization rules
│   └── scripts/
│       ├── raindrop_api.py
│       ├── process-batch.py
│       ├── scan-batch.py
│       ├── cron_run.py
│       ├── build-holdout.py
│       ├── verify-holdout.py
│       └── suggest-rules.py
└── raindrop-linter/
    ├── SKILL.md
    └── scripts/
        └── raindrop_linter.py
```
