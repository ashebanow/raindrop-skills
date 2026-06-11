# Raindrop Skills

Hermes Agent skills for managing a [Raindrop.io](https://raindrop.io) bookmark library — categorization, linting, and quality assurance.

## Skills

### raindrop-categorize

Auto-categorizes unsorted, untagged, or un-described bookmarks. Runs a multi-phase pipeline:

1. Build a collection tree and tag list from Raindrop
2. Select eligible bookmarks (unsorted, untagged, no note/description)
3. For each bookmark: write a note, assign a collection, assign tags
4. Score output quality on completeness, succinctness, tone, and relevance
5. Surface new collections/tags for user approval via kanban board
6. Audit the taxonomy for redundancy, ambiguous names, and mis-parented collections

Self-improving — scores are tracked across runs and the pipeline halts for human review if quality trends downward.

### raindrop-linter

Periodic library quality checker. Runs weekly via cron (Mondays at 10am) and reports issues to a kanban board:

- **Duplicate URLs** — same bookmark saved multiple times (exact duplicates and near-duplicates)
- **Malformed URLs** — structurally invalid bookmarks
- **Dead URLs** — rolling batch scan (100 per run, oldest first) for broken links

For duplicates, the best-quality bookmark is kept as the survivor using a scoring system based on completeness and categorization history.

## Getting Started

```bash
# Install a skill
cp -r raindrop-categorize ~/.hermes/skills/raindrop-categorize
cp -r raindrop-linter ~/.hermes/skills/raindrop-linter

# Set up your Raindrop API token
echo "RAINDROP_TOKEN=your_token_here" > .env
```

Each skill has its own `SKILL.md` with full usage instructions.

## License

MIT
