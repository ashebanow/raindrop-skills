#!/usr/bin/env python3
"""
raindrop-categorize cron orchestrator (no-agent mode).

Designed to run under Hermes's no_agent cron path, where the script's
stdout is delivered verbatim to Discord and an empty stdout is treated
as a silent success. No LLM is involved — this eliminates the broken-
pipe, idle-timeout, and RuntimeError-failed-response failure modes that
plague the agent-driven path.

What this script does:
  1. Loads RAINDROP_TOKEN from the project's .env
  2. Prunes the audit log of entries older than 7 days
  3. Runs scan-batch.py (Phase 1 + 2: collections, tags, eligible pool)
  4. Runs process-batch.py (Phase 3 + 3d: notes, tags, _categorized-v2)
  5. Writes a quality record to raindrop-quality.json (batch stats,
     completeness, compared/improvement counts, per-collection flags)
  6. Computes quality statistics (mean / median / trend over recent runs)
  7. Surfaces outstanding action items for the user (no-match backlog,
     oversized collections, new tags this run, process failures)
  8. Outputs a clean, action-focused summary suitable for Discord

Companion wrapper lives at ~/.hermes/scripts/raindrop_categorize_cron.py
(the framework requires the entry point under that directory).

Output budget: kept under ~1.5 KB so the framework's Discord wrapping
("Cronjob Response: …\n-------------\n\n" + footer) stays well under
Discord's 2000-char per-message limit.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- Configuration ---

HERMES_HOME = Path(os.path.expanduser("~/.hermes"))
CACHE = HERMES_HOME / "cache"

SKILL_DIR = HERMES_HOME / "skills" / "raindrop-categorize"
SCAN_SCRIPT = SKILL_DIR / "scripts" / "scan-batch.py"
PROCESS_SCRIPT = SKILL_DIR / "scripts" / "process-batch.py"
SUGGEST_SCRIPT = SKILL_DIR / "scripts" / "suggest-rules.py"
VERIFY_SCRIPT = SKILL_DIR / "scripts" / "verify-holdout.py"
REVERT_SCRIPT = SKILL_DIR / "scripts" / "revert-regression.py"

ENV_PATH = Path("/Users/ashebanow/Development/ai/raindrop-skills/.env")

STATE_PATH = CACHE / "raindrop-state.json"
LOG_PATH = CACHE / "raindrop-audit-log.jsonl"
QUALITY_PATH = CACHE / "raindrop-quality.json"
NO_MATCH_PATH = CACHE / "raindrop-no-match.json"

# Action-item caps (keep output under budget)
NO_MATCH_SAMPLE_LIMIT = 3
OVERSIZE_SAMPLE_LIMIT = 3
NEW_TAGS_SAMPLE_LIMIT = 5
QUALITY_WINDOW = 5

TOKEN_ENV_KEYS = ("RAINDROP_TOKEN",)

# Shared module (repo root is parent of ENV_PATH)
_REPO_ROOT = ENV_PATH.parent
sys.path.insert(0, str(_REPO_ROOT / "shared"))
from raindrop_common import load_rules as _load_rules, TRACKING_TAG

# Load thresholds from rules file
_rules = _load_rules(str(_REPO_ROOT / "raindrop-categorize" / "references" / "raindrop-rules.json"))
_thresholds = _rules.get("thresholds", {})
OVERSIZE_THRESHOLD = _thresholds.get("collection_oversize_threshold", 25)
QUALITY_WINDOW = _thresholds.get("quality_trend_window", 5)

# --------------------------------------------------------------------------- #
# Pure helpers (testable, no subprocess / network)                            #
# --------------------------------------------------------------------------- #

def load_env() -> None:
    """Source RAINDROP_TOKEN from the project .env if not already set."""
    if not ENV_PATH.exists():
        print(f"WARNING: .env not found at {ENV_PATH}", file=sys.stderr)
    else:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            if key in TOKEN_ENV_KEYS:
                os.environ.setdefault(key, val.strip().strip('"').strip("'"))
    if not os.environ.get("RAINDROP_TOKEN"):
        print("ERROR: RAINDROP_TOKEN not set", file=sys.stderr)
        sys.exit(1)


def prune_audit_log() -> tuple[int, int]:
    """Drop audit entries older than 7 days. Returns (kept, removed)."""
    if not LOG_PATH.exists():
        return 0, 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    keep: list[str] = []
    removed = 0
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            entry = json.loads(s)
            ts = datetime.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
            if ts >= cutoff:
                keep.append(s)
            else:
                removed += 1
        except (json.JSONDecodeError, ValueError):
            keep.append(s)
    LOG_PATH.write_text(("\n".join(keep) + "\n") if keep else "", encoding="utf-8")
    return len(keep), removed


def run_subprocess(cmd: list[str], timeout: int = 600) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, env=os.environ.copy(), capture_output=True,
            text=True, timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or ""), f"TIMEOUT after {timeout}s"
    except Exception as e:
        return 125, "", f"subprocess error: {e}"


def parse_scan_output(stdout: str) -> dict:
    info = {"collections": 0, "tags": 0, "eligible": 0, "batch": 0}
    for line in stdout.splitlines():
        m = re.search(r"(\d+) root \+ (\d+) children = (\d+) \| (\d+) tags", line)
        if m:
            info["collections"] = int(m.group(3))
            info["tags"] = int(m.group(4))
            continue
        m = re.search(r"Scan: \d+s \| new=(\d+) f1=(\d+) f2=(\d+) batch=(\d+)", line)
        if m:
            info["eligible"] = int(m.group(1))
            info["batch"] = int(m.group(4))
    return info


def parse_process_output(stdout: str) -> tuple[int, int, int, int]:
    """Parse the process-batch.py summary line for (tagged, deferred, compared, filler_count).

    Summary line format:
      Done in 205s | 100 batch (15 filler) | 85 new tagged, 0 deferred, 15 compared | 2.0s per bookmark

    Also handles legacy formats:
      "99 updated, 1 failed"
      "99 new tagged, 1 deferred"
    """
    for line in stdout.splitlines():
        # Full summary line: "... N batch (F filler) | X new tagged, Y deferred, Z compared ..."
        m = re.search(
            r"(\d+)\s+batch\s+\((\d+)\s+filler\)\s*\|\s*"
            r"(\d+)\s+new\s+tagged,\s+(\d+)\s+deferred,\s+(\d+)\s+compared",
            line,
        )
        if m:
            return int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(2))
        # Full summary without "new": "... N batch (F filler) | X tagged, Y deferred, Z compared ..."
        m = re.search(
            r"(\d+)\s+batch\s+\((\d+)\s+filler\)\s*\|\s*"
            r"(\d+)\s+tagged,\s+(\d+)\s+deferred,\s+(\d+)\s+compared",
            line,
        )
        if m:
            return int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(2))
        # Partial line: "N new tagged, M deferred" (no compared yet)
        m = re.search(r"(\d+)\s+new\s+tagged,\s+(\d+)\s+deferred", line)
        if m:
            return int(m.group(1)), int(m.group(2)), 0, 0
        # Partial line (no filler): "N tagged, M deferred"
        m = re.search(r"(\d+)\s+tagged,\s+(\d+)\s+deferred", line)
        if m:
            return int(m.group(1)), int(m.group(2)), 0, 0
        # Legacy format
        m = re.search(r"(\d+) updated, (\d+) failed", line)
        if m:
            return int(m.group(1)), int(m.group(2)), 0, 0
    return 0, 0, 0, 0


# --- Quality statistics ----------------------------------------------------- #

def quality_runs() -> list[float]:
    """Avg-per-raindrop scores from the most recent N runs (oldest first)."""
    if not QUALITY_PATH.exists():
        return []
    try:
        runs = json.loads(QUALITY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(runs, list):
        return []
    out: list[float] = []
    for r in runs[-QUALITY_WINDOW:]:
        v = r.get("global", {}).get("avg_per_raindrop")
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def quality_stats(runs: list[float]) -> dict | None:
    """Mean / median / stddev / trend over the recent runs."""
    if not runs:
        return None
    n = len(runs)
    mean = sum(runs) / n
    sorted_r = sorted(runs)
    if n % 2:
        median = sorted_r[n // 2]
    else:
        median = (sorted_r[n // 2 - 1] + sorted_r[n // 2]) / 2
    if n > 1:
        variance = sum((v - mean) ** 2 for v in runs) / (n - 1)
        stddev = variance ** 0.5
    else:
        stddev = 0.0
    # Trend: compare latest vs mean of prior runs
    if n >= 3:
        prior_mean = sum(runs[:-1]) / (n - 1)
        delta = runs[-1] - prior_mean
        if abs(delta) < 0.2:
            trend = "stable"
        elif delta > 0:
            trend = "rising"
        else:
            trend = "falling"
    else:
        trend = "warming"
    return {
        "n": n, "last": runs[-1], "mean": mean,
        "median": median, "stddev": stddev, "trend": trend,
    }


def latest_quality_record() -> dict | None:
    """Return the most recent entry from quality.json, or None."""
    if not QUALITY_PATH.exists():
        return None
    try:
        data = json.loads(QUALITY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, list) or not data:
        return None
    return data[-1]


def compute_quality_record(
    run_id: str,
    proc_rc: int,
    proc_out: str,
    elapsed: int,
) -> dict:
    """Build a quality record for this cron run.

    Reads state + rules to compute batch-level and per-collection scores.
    """
    timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")

    # Parse process output for batch stats
    _, _, compared_count, filler_count = parse_process_output(proc_out)

    # Count improvements from process output lines
    # Lines like: "  ✓ title... — improved (better)"
    compared_improvements = 0
    for line in proc_out.splitlines():
        if " — improved " in line:
            compared_improvements += 1

    # Read state file
    batch_size = 0
    tagged_count = 0
    empty_tags_count = 0
    empty_notes_count = 0
    collections_touched: set[int] = set()
    try:
        if STATE_PATH.exists():
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            final_list = state.get("final_list", [])
            batch_size = len(final_list)
            for bm in final_list:
                tags = bm.get("tags", []) or []
                if TRACKING_TAG in tags:
                    tagged_count += 1
                if not tags:
                    empty_tags_count += 1
                if not (bm.get("note") or "").strip():
                    empty_notes_count += 1
                coll = bm.get("collection") or {}
                cid = coll.get("$id") or coll.get("oid")
                if cid is not None and cid >= 0:
                    collections_touched.add(cid)

            # Per-collection: oversized collections from state
            colls = state.get("collections", {})
            threshold = OVERSIZE_THRESHOLD
            breadth_flagged = []
            for info in colls.values():
                if not isinstance(info, dict):
                    continue
                cnt = info.get("count", 0) or 0
                title = info.get("title", "?")
                if cnt > threshold:
                    breadth_flagged.append(f"{title} ({cnt})")
            breadth_flagged.sort(key=lambda x: -int(x.split("(")[-1].rstrip(")")))
    except (OSError, json.JSONDecodeError):
        pass

    # Compute completeness_pct: % of batch with non-empty tags AND note
    completeness_pct = 0
    if batch_size > 0:
        non_empty = batch_size - max(empty_tags_count, empty_notes_count)
        # A bookmark is "complete" if it has either tags or a note
        complete = batch_size - (empty_tags_count if empty_tags_count < empty_notes_count else empty_notes_count)
        completeness_pct = round(complete / batch_size * 100)

    # tagged_pct_delta: what % of the batch was newly tagged (vs already had tags)
    newly_tagged = batch_size - empty_tags_count - tagged_count
    if batch_size > 0:
        before_pct = round((1 - empty_tags_count / batch_size) * 100) if empty_tags_count > 0 else 0
        after_pct = round((batch_size - empty_tags_count) / batch_size * 100)
    else:
        before_pct = 0
        after_pct = 0
    tagged_delta = after_pct - before_pct
    tagged_pct_delta = f"{'+' if tagged_delta >= 0 else ''}{tagged_delta}pp"

    # note_pct_delta
    before_note_pct = round((1 - empty_notes_count / batch_size) * 100) if batch_size > 0 else 0
    after_note_pct = round((batch_size - empty_notes_count) / batch_size * 100) if batch_size > 0 else 0
    note_delta = after_note_pct - before_note_pct
    note_pct_delta = f"{'+' if note_delta >= 0 else ''}{note_delta}pp"

    # Untagged percentage average across collections
    untagged_pct_avg = round(empty_tags_count / batch_size, 4) if batch_size > 0 else 0.0

    record = {
        "run_id": run_id,
        "timestamp": timestamp,
        "pipeline": "cron",
        "batch_size": batch_size,
        "filler_count": filler_count,
        "success_rate_pct": 100 if proc_rc == 0 else 0,
        "global": {
            "avg_per_raindrop": None,
            "completeness_pct": completeness_pct,
            "tagged_pct_delta": tagged_pct_delta,
            "note_pct_delta": note_pct_delta,
            "compared_count": compared_count,
            "compared_improvements": compared_improvements,
            "compared_regressions": 0,
        },
        "per_collection": {
            "collections_touched": len(collections_touched),
            "breadth_flagged": breadth_flagged[:5],
            "untagged_pct_avg": untagged_pct_avg,
        },
        "elapsed_s": elapsed,
    }
    return record


def append_quality_record(record: dict) -> None:
    """Append a quality record to raindrop-quality.json, creating file if needed."""
    records: list[dict] = []
    if QUALITY_PATH.exists():
        try:
            data = json.loads(QUALITY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                records = data
        except (json.JSONDecodeError, OSError):
            records = []
    records.append(record)
    QUALITY_PATH.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# --- Action-item data sources ---------------------------------------------- #

def no_match_samples(n: int = NO_MATCH_SAMPLE_LIMIT) -> tuple[int, list[str]]:
    """Read the no-match file. Returns (total, sample_titles)."""
    if not NO_MATCH_PATH.exists():
        return 0, []
    try:
        data = json.loads(NO_MATCH_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0, []
    if not isinstance(data, list):
        return 0, []
    titles: list[str] = []
    for entry in data:
        if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], str):
            titles.append(entry[1])
    return len(data), titles[:n]


def oversized_collections(
    state_path: Path = STATE_PATH,
    threshold: int = OVERSIZE_THRESHOLD,
    limit: int = OVERSIZE_SAMPLE_LIMIT,
) -> list[tuple[str, int]]:
    """Top oversized collections from the most recent scan state."""
    if not state_path.exists():
        return []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    colls = state.get("collections", {})
    if not isinstance(colls, dict):
        return []
    out: list[tuple[str, int]] = []
    for info in colls.values():
        if not isinstance(info, dict):
            continue
        count = info.get("count", 0) or 0
        title = info.get("title") or "?"
        if count > threshold:
            out.append((title, count))
    out.sort(key=lambda x: -x[1])
    return out[:limit]


def new_tags_this_run(
    run_id: str | None = None,
    limit: int = NEW_TAGS_SAMPLE_LIMIT,
) -> list[str]:
    """Tags assigned by this run (excluding _categorized-v2).

    Detected by diffing tag counts in the current vs prior scan state
    via the audit log. Tags with count 1 after this run are new.
    """
    # Simplest reliable signal: entries from the most recent run_id in
    # the audit log carry the freshly-assigned tag set. We can't tell
    # *which* of those are new without the prior tag snapshot, but we
    # can still surface the set the user might want to review.
    if not LOG_PATH.exists():
        return []
    tags_in_run: set[str] = set()
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    if not lines:
        return []
    if run_id is None:
        # Find the most recent run_id with action=update_raindrop
        for line in reversed(lines):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("action") == "update_raindrop":
                run_id = e.get("run_id")
                break
        if run_id is None:
            return []
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("action") == "update_raindrop" and e.get("run_id") == run_id:
            for t in e.get("tags", []) or []:
                if t != TRACKING_TAG:
                    tags_in_run.add(t)
    return sorted(tags_in_run)[:limit]


# --------------------------------------------------------------------------- #
# Main                                                                       #
# --------------------------------------------------------------------------- #

def main() -> int:
    t0 = time.time()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    started_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    load_env()

    # 0. Safety valve — revert regressive rule changes before scanning
    revert_rc, revert_out, revert_err = run_subprocess(
        ["python3", str(REVERT_SCRIPT)], timeout=30
    )
    revert_lines = [
        l for l in revert_out.splitlines()
        if l.startswith("REVERTED:")
    ]
    revert_skips = [
        l for l in revert_out.splitlines()
        if l.startswith("REVERT_SKIP:") or l.startswith("REVERT_ERROR:")
    ]

    # 1. Prune
    _kept, removed = prune_audit_log()

    # 2. Scan (Phase 1+2)
    scan_rc, scan_out, scan_err = run_subprocess(
        ["python3", str(SCAN_SCRIPT)], timeout=600
    )
    if scan_rc != 0:
        print(
            f"## Raindrop Categorize — Run `{run_id}` (FAILED at scan)\n"
            f"**Started:** {started_iso}\n"
            f"**Scan** exited {scan_rc}.\n\n"
            f"```\n{(scan_err or scan_out)[-1500:]}\n```",
            flush=True,
        )
        return 1
    scan_info = parse_scan_output(scan_out)

    # 3. Process (Phase 3)
    proc_rc, proc_out, proc_err = run_subprocess(
        ["python3", str(PROCESS_SCRIPT)], timeout=900
    )
    ok, fail, compared_count, filler_count = parse_process_output(proc_out)

    # 3a. Quality scoring — write record to quality.json
    quality_record = compute_quality_record(
        run_id, proc_rc, proc_out, int(time.time() - t0),
    )
    append_quality_record(quality_record)

    # 4. Suggest rules from no-match clustering
    suggest_rc, suggest_out, _suggest_err = run_subprocess(
        ["python3", str(SUGGEST_SCRIPT)], timeout=60
    )
    if suggest_rc == 0:
        # Count how many new proposals were generated
        proposal_count = 0
        for line in suggest_out.splitlines():
            m = re.search(r"Saved (\d+) new proposals", line)
            if m:
                proposal_count = int(m.group(1))
                break
    else:
        proposal_count = -1  # script failed

    # --- Roll up summary inputs ---
    stats = quality_stats(quality_runs())
    nm_total, nm_samples = no_match_samples()
    oversized = oversized_collections()
    new_tags = new_tags_this_run()
    latest = latest_quality_record()
    elapsed = int(time.time() - t0)

    # --- Format pipeline line ---
    # process-batch.py now reports "tagged" (3d applied) vs "deferred"
    # (3d skipped — bookmark will be re-scanned next run). "Deferred"
    # is not a failure, so we only flag it as a warning if there were
    # also script-level failures.
    if proc_rc != 0:
        proc_status = f"⚠️ exited {proc_rc} ({ok} tagged, {fail} deferred)"
    elif fail > 0:
        proc_status = f"✅ {ok} tagged, {fail} deferred (will retry)"
    else:
        proc_status = f"✅ {ok} tagged"
    pipeline = (
        f"prune {removed} → "
        f"scan {scan_info['eligible']} eligible, batch {scan_info['batch']} → "
        f"process {proc_status}"
    )

    # --- Format quality line ---
    if latest:
        # Show batch stats from the latest record alongside trend
        batch_info = (
            f"batch: {latest.get('batch_size', 0)} total"
        )
        # Add tagged / compared breakdown if available
        g = latest.get("global", {})
        tagged_batch = latest.get("batch_size", 0) - latest.get("filler_count", 0)
        cmp_count = g.get("compared_count", 0)
        cmp_impr = g.get("compared_improvements", 0)
        parts = []
        if tagged_batch > 0:
            parts.append(f"{tagged_batch} tagged")
        if cmp_count > 0:
            impr = f" ({cmp_impr} improved)" if cmp_impr > 0 else ""
            parts.append(f"{cmp_count} compared{impr}")
        if parts:
            batch_info += " — " + ", ".join(parts)

        if stats:
            quality_line = (
                f"mean {stats['mean']:.1f} / median {stats['median']:.1f} "
                f"({stats['trend']}) — {batch_info}"
            )
        else:
            quality_line = f"{batch_info}"
    else:
        quality_line = "n/a (no quality records yet)"

    # --- Format action items ---
    items: list[str] = []

    if proc_rc != 0:
        # Script-level crash (non-zero exit) is a real failure
        tail = (proc_err or proc_out)[-400:].strip()
        items.append(
            f"⚠️ **Process script crashed (exit {proc_rc}):** check audit log for details"
            + (f" — tail: `{tail[:200]}`" if tail else "")
        )

    # 5. Holdout verification (if holdout file exists)
    verify_scores = None
    if (CACHE / "raindrop-holdout.json").exists():
        verify_rc, verify_out, _verify_err = run_subprocess(
            ["python3", str(VERIFY_SCRIPT), "--json"], timeout=120
        )
        if verify_rc == 0 and verify_out.strip():
            import json as _json
            for line in verify_out.splitlines():
                line = line.strip()
                if line and line.startswith("{"):
                    try:
                        verify_scores = _json.loads(line)
                    except _json.JSONDecodeError:
                        pass
                    break

    if nm_total > 0:
        sample = ""
        if nm_samples:
            sample = " — e.g. " + ", ".join(f"`{s[:40]}`" for s in nm_samples)
        items.append(
            f"📋 **No-match backlog ({nm_total}):** create new collections "
            f"or prune these bookmarks (`~/.hermes/cache/raindrop-no-match.json`)"
            f"{sample}"
        )

    if oversized:
        names = ", ".join(f"{t} ({c})" for t, c in oversized)
        items.append(
            f"🌳 **Oversized collections ({len(oversized)} shown, >{OVERSIZE_THRESHOLD}):** "
            f"{names} — consider sub-collection splits"
        )

    if new_tags:
        listed = ", ".join(f"`{t}`" for t in new_tags)
        more = "" if len(new_tags) <= NEW_TAGS_SAMPLE_LIMIT else "…"
        items.append(
            f"🏷️ **Tags assigned this run ({len(new_tags)}{' shown' if more else ''}):** "
            f"{listed}{more} — review for redundancy in an interactive session"
        )

    if verify_scores:
        coll_acc = verify_scores.get("collection_accuracy", 0)
        tag_f1 = verify_scores.get("tag_f1", 0)
        n = verify_scores.get("holdout_size", 0)
        bar = "✅" if coll_acc >= 0.85 else "⚠️" if coll_acc >= 0.7 else "❌"
        items.append(
            f"{bar} **Holdout verification:** {coll_acc:.0%} collection accuracy, "
            f"{tag_f1:.0%} tag F1 (n={n})"
        )

    if proposal_count > 0:
        items.append(
            f"💡 **Rule suggestions ({proposal_count} new):** "
            f"run `python3 scripts/suggest-rules.py` interactively to review "
            f"(`~/.hermes/cache/raindrop-proposals.json`)"
        )
    elif proposal_count < 0:
        items.append(
            f"⚠️ **Rule suggestion script crashed** — check suggest-rules.py output"
        )

    if not items:
        items.append("✅ None — library is in good shape.")

    # Prepend revert results to action items if any reversion occurred
    if revert_lines:
        for line in revert_lines:
            # Parse "REVERTED: coll-docker — verification dropped 92% → 78%"
            part = line[len("REVERTED: "):]
            items.insert(0, f"⏪ **Reverted 1 rule change:** {part}")
    if revert_skips:
        for line in revert_skips[:2]:  # cap at 2 to stay under Discord budget
            items.insert(0, f"⚠️  **Safety-valve skip:** {line}")

    actions_block = "\n".join(f"- {it}" for it in items)

    out = (
        f"## Raindrop Categorize — Run `{run_id}`\n"
        f"**Elapsed:** {elapsed}s · "
        f"collections {scan_info['collections']} · tags {scan_info['tags']}\n\n"
        f"**Pipeline:** {pipeline}\n"
        f"**Quality (last {stats['n'] if stats else 0} runs):** {quality_line}\n\n"
        f"**Action items:**\n{actions_block}\n"
    )

    print(out, flush=True)
    return 0 if proc_rc == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
