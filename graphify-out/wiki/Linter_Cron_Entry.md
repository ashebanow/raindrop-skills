# Linter Cron Entry

> 8 nodes

## Key Concepts

- **cron_run.py** (5 connections) — `raindrop-linter/scripts/cron_run.py`
- **run_subprocess()** (3 connections) — `raindrop-linter/scripts/cron_run.py`
- **parse_dup_line()** (2 connections) — `raindrop-linter/scripts/cron_run.py`
- **parse_malformed_line()** (2 connections) — `raindrop-linter/scripts/cron_run.py`
- **main()** (2 connections) — `raindrop-linter/scripts/cron_run.py`
- **Run a subprocess and return (returncode, stdout, stderr).** (1 connections) — `raindrop-linter/scripts/cron_run.py`
- **Parse a line like '  Exact duplicates: 3 groups' into metrics.** (1 connections) — `raindrop-linter/scripts/cron_run.py`
- **Parse '  Malformed URLs:   5** (1 connections) — `raindrop-linter/scripts/cron_run.py`

## Relationships

- [Linter Core](Linter_Core.md) (1 shared connections)

## Source Files

- `raindrop-linter/scripts/cron_run.py`

## Audit Trail

- EXTRACTED: 17 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*