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
  5. Computes quality statistics (mean / median / stddev over recent runs)
  6. Surfaces outstanding action items for the user (no-match backlog,
     oversized collections, new tags this run, process failures)
  7. Outputs a clean, action-focused summary suitable for Discord

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

ENV_PATH = Path("/Users/ashebanow/Development/ai/raindrop-skills/.env")

STATE_PATH = CACHE / "raindrop-state.json"
LOG_PATH = CACHE / "raindrop-audit-log.jsonl"
QUALITY_PATH = CACHE / "raindrop-quality.json"
NO_MATCH_PATH = CACHE / "raindrop-no-match.json"

# Breadth heuristic: collections above this size are flagged for splits
OVERSIZE_THRESHOLD = 25
# Action-item caps (keep output under budget)
NO_MATCH_SAMPLE_LIMIT = 3
OVERSIZE_SAMPLE_LIMIT = 3
NEW_TAGS_SAMPLE_LIMIT = 5
QUALITY_WINDOW = 5
TRACKING_TAG = "_categorized-v2"

TOKEN_ENV_KEYS = ("RAINDROP_TOKEN",)


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


def parse_process_output(stdout: str) -> tuple[int, int]:
    for line in stdout.splitlines():
        m = re.search(r"(\d+) updated, (\d+) failed", line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 0, 0


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
    ok, fail = parse_process_output(proc_out)

    # --- Roll up summary inputs ---
    stats = quality_stats(quality_runs())
    nm_total, nm_samples = no_match_samples()
    oversized = oversized_collections()
    new_tags = new_tags_this_run()
    elapsed = int(time.time() - t0)

    # --- Format pipeline line ---
    if proc_rc != 0:
        proc_status = f"⚠️ exited {proc_rc} ({ok} ok, {fail} failed)"
    elif fail > 0:
        proc_status = f"⚠️ {ok} ok, {fail} failed"
    else:
        proc_status = f"✅ {ok} ok"
    pipeline = (
        f"prune {removed} → "
        f"scan {scan_info['eligible']} eligible, batch {scan_info['batch']} → "
        f"process {proc_status}"
    )

    # --- Format quality line ---
    if stats:
        quality_line = (
            f"mean {stats['mean']:.1f} / median {stats['median']:.1f} / "
            f"stddev {stats['stddev']:.2f} "
            f"({stats['trend']}, n={stats['n']}, last {stats['last']:.1f})"
        )
    else:
        quality_line = "n/a (no quality records yet)"

    # --- Format action items ---
    items: list[str] = []

    if proc_rc != 0 or fail > 0:
        # Failures are always an action item
        tail = (proc_err or proc_out)[-400:].strip()
        items.append(
            f"⚠️ **Process failures ({fail}):** check audit log for details"
            + (f" — tail: `{tail[:200]}`" if tail else "")
        )

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

    if not items:
        items.append("✅ None — library is in good shape.")

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
