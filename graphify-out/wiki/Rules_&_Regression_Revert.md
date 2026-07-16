# Rules & Regression Revert

> 21 nodes

## Key Concepts

- **revert-regression.py** (12 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **main()** (9 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **load_rules()** (7 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **log()** (6 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **revert_rule_change()** (6 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **load_proposals()** (4 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **save_proposals()** (3 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **save_rules()** (3 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **get_current_verification()** (3 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **get_rule_title()** (3 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **mark_proposal_rejected()** (3 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Raindrop Rules JSON** (3 connections) — `raindrop-categorize/references/raindrop-rules.json`
- **Emit one line of machine-parseable output for cron_run.py.** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Load proposals from raindrop-proposals.json. Returns list of proposal dicts.** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Write proposals back to disk.** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Load raindrop-rules.json. Returns dict.** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Write rules back to disk.** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Return the verification section from the most recent quality record, or None.** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Get the human-readable collection title for a rule, or the rule_id itself.** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Remove add_keywords from the rule's keywords list, bump version, save.      Retu** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`
- **Update a proposal's status to 'rejected' with reason and timestamp.** (1 connections) — `raindrop-categorize/scripts/revert-regression.py`

## Relationships

- [Proposal Apply & Merge](Proposal_Apply_%26_Merge.md) (3 shared connections)
- [Cron Orchestration & Quality](Cron_Orchestration_%26_Quality.md) (1 shared connections)
- [Batch Processing & Classification](Batch_Processing_%26_Classification.md) (1 shared connections)

## Source Files

- `raindrop-categorize/references/raindrop-rules.json`
- `raindrop-categorize/scripts/revert-regression.py`

## Audit Trail

- EXTRACTED: 69 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*