#!/usr/bin/env python3
"""populate_registers.py - the registers, copied as-is, because they are already the right shape.

GRAIN (PASTE 107 T3): "registers | CSV as-is | 13 files/yr". There is nothing to re-grain here:
a register IS a CSV index of objects, which is precisely the shape the stress test says a record
store should have. So this script copies rather than transforms - and copying is still a populate,
because it is idempotent, counted, manifested and resumable like every other.

NO CREDENTIAL. The registers are local files in `life-taxonomy\\registers\\`, so this store runs
LIVE on this laptop today, key or no key. Same for `claude-project`. That is worth saying out loud:
two of the six stores never needed the chat at all.

AS-IS DOES NOT MEAN UNSCRUBBED. §CONTRACT 5 masks account numbers to the last four on the way in
(`populate_lib.scrub`). A register that carries a full account number into a second repo is a leak
that git remembers forever, and "as-is" is not a reason to make one.
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populate_lib import estate_path                                     # noqa: E402
from populate_lib import (Store, Wall, sha256, since_of, ResumeStop,      # noqa: E402
                          main_wrapper, in_window)

STORE = "registers"
GRAIN = "CSV as-is (already the right shape), masked; one INDEX row per register"
HEADER = ["register", "rows", "bytes", "sha256", "modified", "source"]
TAKE = (".csv", ".yaml", ".yml", ".tsv")


def source_dir(estate: str, override: str | None) -> str:
    d = override or os.path.join(estate_path(estate, "life-taxonomy"), "registers")
    if not os.path.isdir(d):
        raise Wall("no registers directory at %s" % d)
    return d


def run(args) -> dict:
    st = Store(STORE, args.estate, args.dry_run)
    since = since_of(args)
    src = source_dir(args.estate, args.snapshot)
    walls: list[str] = []

    names = sorted(n for n in os.listdir(src) if os.path.isfile(os.path.join(src, n)))
    at_origin = len(names)
    index_rows, n = [], 0
    try:
        for name in names:
            path = os.path.join(src, name)
            # `issues.csv.pre-bev-home-1-h5` and friends: a backup of a register is not a register.
            # Copying it would double every issue row in the container's own count. This test runs
            # BEFORE the extension test, or a backup gets reported as "not a register format" -
            # true, but not the reason, and a reason that misleads is worse than none.
            if ".pre-" in name or name.endswith("~"):
                st.notes.append("skipped %s (a backup, not a register)" % name)
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in TAKE:
                st.notes.append("skipped %s (not a register format)" % name)
                continue
            with open(path, "rb") as fh:
                raw = fh.read()
            text = raw.decode("utf-8", "replace")
            sha = sha256(text)
            if st.manifest.unchanged(name, sha):
                st.skipped += 1
                index_rows.append(_row(name, text, raw, path))
                continue
            st.write_text(name, text)
            st.record(name, sha, len(raw), name, "register")
            index_rows.append(_row(name, text, raw, path))
            n += 1
            if args.fail_after and n >= args.fail_after:
                raise ResumeStop("--fail-after %d" % args.fail_after)
    except ResumeStop as stop:
        walls.append("stopped early (%s) - the manifest is saved, the next run resumes" % stop)

    # The INDEX is the one place a reader learns how big each register is without opening it.
    index_rows = [r for r in index_rows if in_window(r["modified"], since)] or index_rows
    st.write_csv("INDEX.csv", HEADER, index_rows, key="register")
    return st.finish(at_origin, since, "local:life-taxonomy/registers", GRAIN, walls)


def _row(name: str, text: str, raw: bytes, path: str) -> dict:
    import datetime
    rows = max(0, sum(1 for _ in csv.reader(text.splitlines())) - 1) if name.endswith((".csv", ".tsv")) else ""
    return {"register": name, "rows": str(rows), "bytes": str(len(raw)), "sha256": sha256(text)[:16],
            "modified": datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d"),
            "source": "life-taxonomy/registers/%s" % name}


run.STORE = STORE


if __name__ == "__main__":
    sys.exit(main_wrapper(STORE, run))
