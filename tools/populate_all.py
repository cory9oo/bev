#!/usr/bin/env python3
"""populate_all.py - run the six populates, and let no one of them stop another (§CONTRACT 7).

    python bev/tools/populate_all.py --since 2026-09-01
    python bev/tools/populate_all.py --snapshot "C:\\Users\\fugie\\BEV\\Claude outputs" --dry-run
    python bev/tools/populate_all.py --only registers,claude-project

THIS IS THE FILE THAT REPLACES THE CHAT. PASTE 98 spent two hours and one compaction on a run that
could not be repeated; this is one command that can be run every day, forever, by a scheduler that
never reads a receipt. R70.315: a lane authors, code executes.

EVERY STORE REPORTS, INCLUDING THE ONES THAT COULD NOT RUN. A store with no credential is not an
error and not a silence - it is a row in the table reading `BUILT - NOT RUN LIVE (key absent)`.
The exit code is 0 when every store either ran or named its wall, and 1 only when a script broke,
because a scheduler needs to be able to tell a locked door from a hole in the floor.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populate_lib import add_common_args, estate_root, run_store, report, now_cdt   # noqa: E402

STORES = ["gmail", "clickup", "calendar", "drive", "registers", "claude-project"]
# The two that need no credential run first, so an unattended run always produces something real
# before it reaches the four that can be walled.
ORDER = ["registers", "claude-project", "gmail", "clickup", "calendar", "drive"]


def load(store: str):
    return importlib.import_module("populate_%s" % store.replace("-", "_"))


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(prog="populate_all.py"))
    ap.add_argument("--only", default="", help="comma list of stores; default all six")
    ap.add_argument("--own-share", type=float, default=0.05)      # consumed by populate_gmail
    a = ap.parse_args()
    a.estate = estate_root(a.estate)
    wanted = [s.strip() for s in a.only.split(",") if s.strip()] or ORDER
    unknown = [s for s in wanted if s not in STORES]
    if unknown:
        print("unknown store(s): %s   known: %s" % (", ".join(unknown), ", ".join(STORES)))
        return 2

    print("populate_all  %s  estate=%s  since=%s  %s"
          % (now_cdt(), a.estate, a.since or "(full)", "DRY RUN" if a.dry_run else ""))
    results, defects = [], 0
    for store in [s for s in ORDER if s in wanted]:
        mod = load(store)
        # Each store gets its own argv namespace so one store's --snapshot cannot leak into the
        # next one's idea of where its data lives.
        args = argparse.Namespace(**vars(a))
        args.snapshot = _snapshot_for(store, a)
        c = run_store(mod.run, args)
        results.append(c)
        defects += c.get("failed", 0)
        print("  " + report(c))

    if a.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    walled = [c["store"] for c in results if c.get("walls") and not c.get("copied")]
    if walled:
        print("\nBUILT - NOT RUN LIVE: %s" % ", ".join(walled))
    # ASCII only. This runs unattended in a Windows console whose codepage turns a middot into a
    # question mark, and a summary line nobody can read is a summary line nobody reads.
    print("\n%d store(s) | %d records held | %d files written | %d unchanged | %d defect(s)"
          % (len(results), sum(c.get("manifest_rows", 0) for c in results),
             sum(c.get("copied", 0) for c in results),
             sum(c.get("skipped", 0) for c in results), defects))
    return 1 if defects else 0


def _snapshot_for(store: str, a) -> str | None:
    """A snapshot directory belongs to a store, not to a run.

    `Claude outputs\\` is gmail's snapshot AND claude-project's; it is not clickup's, and handing
    it to clickup would make that store report `snapshot has no TASKS export` as though the
    snapshot were broken. It is not broken - PASTE 98 was paused before ClickUp landed a file.
    Per-store subdirectories win when they exist, so a future export can drop them in place."""
    if not a.snapshot:
        return None
    sub = os.path.join(a.snapshot, store)
    if os.path.isdir(sub):
        return sub
    return a.snapshot if store in ("gmail", "claude-project") else None


if __name__ == "__main__":
    sys.exit(main())
