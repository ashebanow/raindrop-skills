#!/usr/bin/env python3
"""
Deterministic cron orchestrator for raindrop-linter.

Wraps raindrop_linter.py and outputs a clean, compact summary
suitable for Discord delivery via no_agent cron mode.

Usage (cron):
  source .env && export RAINDROP_TOKEN && python3 scripts/cron_run.py

Output format:
  ## Raindrop Linter — <date>
  Pipeline: <one-liner stats>
  Action items:
  - Duplicates: <N> groups, keep <N>, remove <N>
  - Dead URLs: <N> checked, <N> dead (cursor at <id>)
  - Malformed URLs: <N>
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

# ── Paths ────────────────────────────────────────────────────────────

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINTER_SCRIPT = os.path.join(_repo_root, "raindrop-linter", "scripts", "raindrop_linter.py")
STATE_PATH = os.path.expanduser("~/.hermes/cache/raindrop-lint-state.json")


# ── Subprocess helper ────────────────────────────────────────────────

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


# ── Output parsers ───────────────────────────────────────────────────

def parse_dup_line(line: str) -> dict:
    """Parse a line like '  Exact duplicates: 3 groups' into metrics."""
    m = __import__("re").search(r"(Exact|Near) duplicates:\s+(\d+)\s+groups?", line)
    if m:
        return {"type": m.group(1).lower(), "groups": int(m.group(2))}
    return {}


def parse_malformed_line(line: str) -> int:
    """Parse '  Malformed URLs:   5'"""
    m = __import__("re").search(r"Malformed URLs:\s+(\d+)", line)
    return int(m.group(1)) if m else 0


# ── Main ─────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    started_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"## Raindrop Linter — Run `{run_id}`", flush=True)
    print(f"**Started:** {started_iso}", flush=True)
    print(file=sys.stderr)

    # ── Run linter ──
    rc, out, err = run_subprocess(
        ["python3", LINTER_SCRIPT, "lint", "--limit", "50"],
        timeout=900,
    )

    elapsed = int(time.time() - t0)

    # ── Parse results ──
    exact_groups = 0
    near_groups = 0
    malformed_count = 0
    total_dups = 0
    dead_checked = 0
    dead_found = 0
    dead_cursor = 0

    for line in out.splitlines():
        m = __import__("re").search(r"Exact duplicates:\s+(\d+)\s+groups?", line)
        if m:
            exact_groups = int(m.group(1))
        m = __import__("re").search(r"Near-duplicates:\s+(\d+)\s+groups?", line)
        if m:
            near_groups = int(m.group(1))
        m = __import__("re").search(r"Malformed URLs:\s+(\d+)", line)
        if m:
            malformed_count = int(m.group(1))
        m = __import__("re").search(r"Total duplicates to remove:\s+(\d+)", line)
        if m:
            total_dups = int(m.group(1))
        m = __import__("re").search(r"Checked (\d+) URLs, (\d+) dead", line)
        if m:
            dead_checked = int(m.group(1))
            dead_found = int(m.group(2))

    # Read state for cursor position
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                state = json.load(f)
                dead_cursor = state.get("dead_url_cursor", 0)
        except (json.JSONDecodeError, OSError):
            pass

    # ── Summarise ──
    total_groups = exact_groups + near_groups
    status = "✅ ok" if rc == 0 else "❌ failed"
    pipeline = (
        f"dups {total_groups} groups ({total_dups} to remove), "
        f"malformed {malformed_count}, "
        f"dead {dead_checked} checked ({dead_found} dead, cursor {dead_cursor})"
    )

    print(f"\n**Pipeline:** {pipeline}  ·  {elapsed}s  ·  {status}", flush=True)

    if rc != 0:
        print(f"\n**Stderr:**\n```\n{(err or '')[-800:]}\n```", flush=True)
        print(f"\n---\n_raindrop-linter exited {rc}_", flush=True)
        return rc

    # ── Action items ──
    items = []

    if total_groups > 0:
        items.append(
            f"**Duplicates:** {total_groups} groups ({total_dups} bookmarks "
            f"to remove). Review on the kanban board."
        )

    if malformed_count > 0:
        # Show first 3 malformed URLs
        malformed_samples = []
        capture = False
        for line in out.splitlines():
            if "malformed URLs found" in line:
                capture = True
                continue
            if capture and line.startswith("    [") and len(malformed_samples) < 3:
                malformed_samples.append(line.strip())
            elif capture and not line.startswith("    ["):
                break
        samples = "\n".join(malformed_samples) if malformed_samples else ""
        items.append(
            f"**Malformed URLs:** {malformed_count} found."
            + (f"\n{samples}" if samples else "")
        )

    if dead_found > 0:
        # Show first 3 dead URLs
        dead_samples = []
        capture = False
        for line in out.splitlines():
            if "dead" in line and "checked" in line:
                capture = True
                continue
            if capture and line.startswith("    DEAD") and len(dead_samples) < 3:
                dead_samples.append(line.strip())
            elif capture and line.startswith("    DEAD"):
                continue
            elif capture and not line.startswith("    DEAD") and dead_samples:
                break
        samples = "\n".join(dead_samples) if dead_samples else ""
        items.append(
            f"**Dead URLs:** {dead_found} dead (out of {dead_checked} checked)."
            + (f"\n{samples}" if samples else "")
        )

    if not items:
        items.append("No issues found. Library is clean.")

    print("\n**Action items:**", flush=True)
    for item in items:
        for line in item.split("\n"):
            print(f"- {line}" if not line.startswith("  ") else line, flush=True)

    print(f"\n---\n_raindrop-linter completed in {elapsed}s_", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
