#!/usr/bin/env python3
"""populate_lib.py - the ONE implementation of what a populate script is (R70.308 §4 / R70.315).

WHY ONE LIBRARY. PASTE 98 ran six exports inside a chat. Each one invented its own idea of "done":
one failed with no retry state, one produced counts nobody could re-derive, none could be re-run.
R70.315 makes the populate a script on the laptop; this module makes the six scripts agree about
what idempotent, incremental, resumable and counted MEAN, because six implementations of one
contract is the drift class this estate keeps paying for.

THE CONTRACT every populate_<store>.py satisfies, enforced here rather than in prose:
  1. --since / --full / --dry-run / --snapshot / --limit           `add_common_args`
  2. idempotent by sha256 - a record whose sha matches is SKIPPED  `Manifest.unchanged`
  3. resumable - the manifest IS the resume state                  `Manifest`
  4. counted at origin vs copied                                   `Counts` -> COUNTS.json
  5. secrets never; account numbers masked to last four            `mask_secrets`
  6. no file over 5 MB enters git                                  `Store.put_bulk`
  7. one store's failure never blocks another                      `run_store`

THE GRAIN IS NOT R70.308'S STATED GRAIN. PASTE 107's stress test measured a 50,000-file clone of
this container: one catalog row per record reaches 6.9 MB at 50k and breaks the estate's own 5 MB
rule at ~36k notes. So: **a record is not a note. Objects are searched; records are addressed.**
Two trees, and the split is the whole design:

    records/<store>/     TRACKED    INDEX.md · COUNTS.json · MANIFEST.tsv · the CSV indexes.
                                    Small, diffable, greppable. ONE catalog row for the whole store.
    _records/<store>/    IGNORED    full bodies, attachments, binaries. Never committed, always
                                    manifested, so nothing is lost and nothing is searched twice.

WRITTEN MEANS CHANGED. `Store.write_text` compares bytes before it touches the disk and returns
False when they match. That is what makes "the second run writes 0" a measurement instead of a
hope: a script that rewrites identical bytes still reports 0 written, and the stress test can tell
the difference between "nothing to do" and "did it all again".
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

MAX_GIT_BYTES = 5 * 1024 * 1024          # §CONTRACT 6 - nothing over 5 MB enters git
MANIFEST_COLS = ("key", "sha256", "bytes", "path", "kind", "fetched_at")


# ---------------------------------------------------------------------------------------------
# WHERE THINGS ARE.  A populate script runs from the main checkout (bev/tools/) or from a wire
# worktree (_wt/bev--<WIRE>/tools/), and those sit at DIFFERENT depths under the estate root.
# `../..` would be right in one and silently wrong in the other - it would write the container
# into `_wt/`, where cc_finish deletes it. So the root is FOUND, by what it contains.
# ---------------------------------------------------------------------------------------------
def estate_root(explicit: str | None = None) -> str:
    if explicit:
        return os.path.abspath(explicit)
    if os.environ.get("BEV_ROOT"):
        return os.path.abspath(os.environ["BEV_ROOT"])
    here = os.path.abspath(os.path.dirname(__file__))
    while True:
        if all(os.path.isdir(os.path.join(here, d)) for d in ("_reconcile", "master-brain")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            raise SystemExit("ERROR  cannot find the BEV root above %s - pass --estate"
                             % os.path.dirname(__file__))
        here = parent


def now_cdt() -> str:
    """R70.214: the stamp is taken from the clock, never estimated. Local time, named."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def now_utc_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------------------------
# MASKING.  §CONTRACT 5 says account numbers are masked to the last four and secrets never land.
# Two different jobs wearing one word, so two functions:
#   mask_account  - a number a human would call an account number, reduced to ****1234
#   mask_secrets  - a token, key or password that must never be written at all, reduced to a label
# The order matters: secrets first, because an API key that happens to contain a 10-digit run
# would otherwise be "masked" to its last four and written down as if that were safe.
# ---------------------------------------------------------------------------------------------
# A DIGIT RUN INSIDE AN IDENTIFIER IS NOT AN ACCOUNT NUMBER, and the suite is what proved it: the
# first version of this regex turned the gmail thread id `aaaa111122223333` into `aaaa****3333`,
# which silently rewrote the primary key of every record in the store. A run whose neighbour is a
# letter, digit or `_`/`-` belongs to a token (a thread id, a task id, a sha, a URL segment); only
# a run standing on its own is a number a human would call an account number.
#
# `/ = ? &` join the exclusion for the same reason one step out: a numeric URL path segment
# (`https://app.clickup.com/t/868112345678` - every ClickUp task URL) is an identifier wearing
# digits, and a masked URL is a broken URL. Nothing an account number is written after in prose
# is one of those four; it follows a space, a colon-space, a `#` or the start of a line.
_ACCOUNT_RE = re.compile(r"(?<![0-9A-Za-z*_\-/=?&])(\d[\d\- ]{7,26}\d)(?![0-9A-Za-z_\-])")

# Columns that are STRUCTURALLY keys, never money. Masking one corrupts the record it names, and
# a masked URL is a broken URL. Belt and braces with the regex above, on purpose: this class of
# bug is silent, and a silent bug in a key is unrecoverable once it is committed.
ID_COLS = ("sha256", "url", "body_path", "path", "source", "register", "doc_id")


def is_id_col(name: str) -> bool:
    return name in ID_COLS or name.endswith("_id") or name == "id"
_SECRET_RES = (
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,})"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,})"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})"),
    re.compile(r"\b(ey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})"),  # JWT
    re.compile(r"\b(AIza[A-Za-z0-9_\-]{20,})"),
    re.compile(r"(?i)\b((?:api[_\-]?key|authorization|bearer|password|secret|token)"
               r"\s*[:=]\s*)([^\s'\"]{8,})"),
)


def mask_account(text: str) -> str:
    def repl(m):
        digits = re.sub(r"\D", "", m.group(1))
        return "****" + digits[-4:] if len(digits) >= 8 else m.group(1)
    return _ACCOUNT_RE.sub(repl, text)


def mask_secrets(text: str) -> str:
    for rx in _SECRET_RES[:-1]:
        text = rx.sub("[REDACTED-SECRET]", text)
    text = _SECRET_RES[-1].sub(lambda m: m.group(1) + "[REDACTED-SECRET]", text)
    return text


def scrub(text: str) -> str:
    """Everything a populate writes goes through here. Secrets first, then accounts."""
    return mask_account(mask_secrets(text))


# ---------------------------------------------------------------------------------------------
# THE ENV.  Read-only, and deliberately dumb: it parses `.env` and hands back a dict. It never
# prints a value, never logs one, and never puts one in an exception message - a traceback is a
# log line with extra steps.
# ---------------------------------------------------------------------------------------------
def load_env(estate: str) -> dict:
    path = os.path.join(estate, "_reconcile", ".env")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


class Wall(Exception):
    """A named wall: the store could not be reached, and the reason is reportable in one line.

    This is NOT a bug and never a traceback. §CONTRACT 8: the wall is named, not hidden, and the
    script still completes against --snapshot. Raising anything else means the script is broken;
    raising this means the world is."""


# ---------------------------------------------------------------------------------------------
# THE MANIFEST.  Resume state, idempotence key and bulk index, in one TSV that a human can read.
# It is keyed by a store-chosen stable id (a gmail thread id, a clickup task id, a drive file id),
# NOT by path, because a record that moves is the same record and re-copying it would be a lie in
# the counts.
# ---------------------------------------------------------------------------------------------
class Manifest:
    def __init__(self, path: str):
        self.path = path
        self.rows: dict[str, dict] = {}
        self.dirty = False
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace", newline="") as fh:
                for row in csv.DictReader(fh, delimiter="\t"):
                    if row.get("key"):
                        self.rows[row["key"]] = row

    def unchanged(self, key: str, sha: str) -> bool:
        """§CONTRACT 2. The whole of idempotence lives in this one comparison."""
        return key in self.rows and self.rows[key].get("sha256") == sha

    def put(self, key: str, sha: str, nbytes: int, path: str, kind: str):
        self.rows[key] = {"key": key, "sha256": sha, "bytes": str(nbytes),
                          "path": path, "kind": kind, "fetched_at": now_utc_z()}
        self.dirty = True

    def save(self) -> bool:
        """Atomic, sorted, and silent when nothing changed. Returns True if the file changed."""
        buf = ["\t".join(MANIFEST_COLS)]
        for key in sorted(self.rows):
            r = self.rows[key]
            buf.append("\t".join(str(r.get(c, "")).replace("\t", " ") for c in MANIFEST_COLS))
        return _write_if_changed(self.path, "\n".join(buf) + "\n")


def _write_if_changed(path: str, text: str) -> bool:
    """WRITTEN MEANS CHANGED - see the module docstring. Also the only place that makes dirs."""
    data = text.encode("utf-8")
    if os.path.exists(path):
        with open(path, "rb") as fh:
            if fh.read() == data:
                return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return True


# ---------------------------------------------------------------------------------------------
# THE STORE.  Owns the two trees, the manifest and the counts for one source.
# ---------------------------------------------------------------------------------------------
class Store:
    def __init__(self, name: str, estate: str, dry_run: bool = False):
        self.name = name
        self.estate = estate
        self.dry_run = dry_run
        self.records = os.path.join(estate, "master-brain", "records", name)
        self.bulk = os.path.join(estate, "master-brain", "_records", name)
        self.manifest = Manifest(os.path.join(self.records, "MANIFEST.tsv"))
        self.written = 0
        self.skipped = 0
        self.failed = 0
        self.oversize: list[str] = []
        self.notes: list[str] = []

    # -- tracked side ---------------------------------------------------------------------
    def write_text(self, relpath: str, text: str) -> bool:
        """Write into records/<store>/. Scrubbed, size-gated, and counted only when it changed."""
        text = scrub(text)
        data = text.encode("utf-8")
        if len(data) > MAX_GIT_BYTES:
            # §CONTRACT 6. An oversize tracked file is a defect in the grain, not a thing to
            # shrink quietly - it goes to the bulk tree and the receipt says the grain was wrong.
            self.oversize.append(relpath)
            return self.put_bulk(relpath, data, kind="oversize-index")
        if self.dry_run:
            self.written += 1
            return True
        if _write_if_changed(os.path.join(self.records, relpath), text):
            self.written += 1
            return True
        self.skipped += 1
        return False

    def write_csv(self, relpath: str, header: list[str], rows: list[dict], key: str) -> bool:
        """MERGE a CSV index by primary key, then write only if the bytes moved.

        Merge, not append: an incremental `--since` run must be able to correct a row it already
        wrote (a thread that gained a message, a task that changed status) without duplicating it,
        and must leave every row it did not fetch exactly as it found it. That is what makes
        `--since yesterday` touch only new rows AND makes a killed run safe to repeat."""
        path = os.path.join(self.records, relpath)
        merged: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace", newline="") as fh:
                for r in csv.DictReader(fh):
                    if r.get(key):
                        merged[r[key]] = r
        for r in rows:
            merged[str(r[key])] = {c: (str(r.get(c, "")) if is_id_col(c) else scrub(str(r.get(c, ""))))
                                   for c in header}
        buf = [",".join(header)]
        for k in sorted(merged):
            r = merged[k]
            buf.append(",".join(_csv_cell(r.get(c, "")) for c in header))
        text = "\n".join(buf) + "\n"
        if self.dry_run:
            self.written += 1
            return True
        if _write_if_changed(path, text):
            self.written += 1
            return True
        self.skipped += 1
        return False

    # -- bulk side ------------------------------------------------------------------------
    def put_bulk(self, relpath: str, data: bytes, kind: str = "body") -> bool:
        """Write into _records/<store>/ - git-ignored, manifested, never searched."""
        if self.dry_run:
            self.written += 1
            return True
        path = os.path.join(self.bulk, relpath)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                if fh.read() == data:
                    self.skipped += 1
                    return False
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        self.written += 1
        return True

    def record(self, key: str, sha: str, nbytes: int, path: str, kind: str):
        self.manifest.put(key, sha, nbytes, path, kind)

    # -- closing out ----------------------------------------------------------------------
    def finish(self, at_origin: int, since: str | None, source: str, grain: str,
               walls: list[str] | None = None) -> dict:
        counts = {
            "store": self.name,
            "at_origin": at_origin,
            "copied": self.written,
            "skipped": self.skipped,
            "failed": self.failed,
            "since": since or "",
            "ran_at": now_utc_z(),
            "ran_at_local": now_cdt(),
            "source": source,
            "grain": grain,
            "walls": walls or [],
            "oversize": self.oversize,
            "manifest_rows": len(self.manifest.rows),
        }
        if not self.dry_run:
            self.manifest.save()
            _write_if_changed(os.path.join(self.records, "COUNTS.json"),
                              json.dumps(counts, indent=2, sort_keys=True) + "\n")
            _write_if_changed(os.path.join(self.records, "INDEX.md"), self._index_md(counts))
        return counts

    def _index_md(self, counts: dict) -> str:
        """ONE note per store, and it is the ONE catalog row per store (the T3 ruling).

        It deliberately holds no record rows: it holds the ADDRESS of the store, the shape of what
        was copied, and the counts. A reader who needs a record reaches it through the CSV index
        named here - never by searching the container."""
        walls = ", ".join(counts["walls"]) or "none"
        return f"""---
id: BRAIN-RECORDS-{self.name.upper()}
title: "records/{self.name} - the copied record store"
type: RECORD-STORE
domain: 11
sensitivity: PRIVATE
created: {counts['ran_at_local'][:10]}
updated: {counts['ran_at_local'][:10]}
date: {counts['ran_at_local'][:10]}
author: claude
written_by: CC-BEV
sources: [OURS]
layer: mirror
status: ACTIVE
last_refreshed: "{counts['ran_at_local']}"
location_class: LOCAL
---
# records/{self.name}

> **This is a RECORD STORE, not a note.** Objects are searched; records are addressed. It carries
> ONE catalog row for the whole store (PASTE 107 T3): a catalog with one row per record reaches
> 6.9 MB at 50k records and breaks the estate's own 5 MB rule at ~36k.

| | |
|---|---|
| grain | {counts['grain']} |
| source | {counts['source']} |
| tracked index | `master-brain\\records\\{self.name}\\` |
| bulk bodies | `master-brain\\_records\\{self.name}\\` (git-ignored, manifested) |
| refresh | `python bev\\tools\\populate_{self.name.replace('-', '_')}.py --since <date>` |
| at origin | {counts['at_origin']} |
| copied this run | {counts['copied']} |
| unchanged this run | {counts['skipped']} |
| failed | {counts['failed']} |
| manifest rows | {counts['manifest_rows']} |
| walls | {walls} |
| last run | {counts['ran_at_local']} |

Counts are generated into `COUNTS.json` by `populate_lib.Store.finish` and are never hand-written.
"""


def _csv_cell(v) -> str:
    s = str(v)
    if any(c in s for c in ',"\n\r'):
        return '"' + s.replace('"', '""') + '"'
    return s


# ---------------------------------------------------------------------------------------------
# THE SHARED COMMAND LINE, so six scripts cannot disagree about what --since means.
# ---------------------------------------------------------------------------------------------
def add_common_args(ap: argparse.ArgumentParser):
    ap.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="only records at or after this date (incremental; R70.308 §4)")
    ap.add_argument("--full", action="store_true", help="ignore --since and walk everything")
    ap.add_argument("--dry-run", action="store_true", help="count, write nothing")
    ap.add_argument("--snapshot", default=None,
                    help="read from a local export instead of the live store (the PASTE 98 snapshot)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N records (stress test 3)")
    ap.add_argument("--fail-after", type=int, default=0,
                    help="TEST ONLY: die after N records, to prove the next run resumes")
    ap.add_argument("--estate", default=None, help="BEV root; default = found by what it contains")
    ap.add_argument("--json", action="store_true", help="print COUNTS.json to stdout")
    return ap


def since_of(args) -> str | None:
    return None if args.full else args.since


def in_window(datestr: str, since: str | None) -> bool:
    """A record with no date is always IN. Dropping an undated record to satisfy a date filter
    is exactly the silent loss R70.308 §4 exists to prevent - it is copied and flagged instead."""
    if not since or not datestr:
        return True
    return str(datestr)[:10] >= since[:10]


class ResumeStop(Exception):
    """--fail-after fired. The manifest is saved first, which is what proves resume works."""


def report(counts: dict) -> str:
    """`held` is the parity number, and it is not `copied`.

    P3 asks whether the container holds at least what the 98 chat export produced. `copied` counts
    FILES WRITTEN, which at this grain is one CSV per account-month - 245 gmail threads land in 19
    files, and a receipt that compared 25 to 245 would read like a 90% loss. `held` is
    `manifest_rows`: how many RECORDS the store holds after the run. That is the number parity is
    measured on."""
    walls = ("  WALL: " + "; ".join(counts["walls"])) if counts["walls"] else ""
    return ("%-16s origin %6s  held %6s  files %5s  unchanged %5s  failed %3s%s"
            % (counts["store"], counts["at_origin"], counts.get("manifest_rows", 0),
               counts["copied"], counts["skipped"], counts["failed"], walls))


def run_store(fn, *a, **kw) -> dict:
    """§CONTRACT 7: one store's failure never blocks another.

    A Wall is a named, expected outcome and is reported as one. Anything else is a defect in the
    script, so it is caught too - the runner must not die halfway through six stores - but it is
    reported with its type and message so it reads as a bug, not as a fact about the world."""
    try:
        return fn(*a, **kw)
    except Wall as w:
        return {"store": getattr(fn, "STORE", "?"), "at_origin": 0, "copied": 0, "skipped": 0,
                "failed": 0, "walls": [str(w)], "since": "", "ran_at": now_utc_z(),
                "ran_at_local": now_cdt(), "source": "none", "grain": "-", "oversize": [],
                "manifest_rows": 0}
    except Exception as e:                                     # noqa: BLE001 - deliberate, see above
        return {"store": getattr(fn, "STORE", "?"), "at_origin": 0, "copied": 0, "skipped": 0,
                "failed": 1, "walls": ["DEFECT %s: %s" % (type(e).__name__, e)], "since": "",
                "ran_at": now_utc_z(), "ran_at_local": now_cdt(), "source": "none", "grain": "-",
                "oversize": [], "manifest_rows": 0}


def main_wrapper(store_name: str, runner, extra=None) -> int:
    """Every populate_<store>.py's __main__ is THIS, so six scripts cannot drift apart about what
    --since means, where the estate is, or what a wall does to the exit code.

    `extra` is a callable handed the parser for the one store that needs a flag of its own
    (gmail's --own-share). One escape hatch, named, beats six copies of the same eight lines."""
    ap = add_common_args(argparse.ArgumentParser(prog="populate_%s.py" % store_name))
    if extra:
        extra(ap)
    args = ap.parse_args()
    args.estate = estate_root(args.estate)
    counts = run_store(runner, args)
    print(json.dumps(counts, indent=2, sort_keys=True) if args.json else report(counts))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    print("populate_lib is a library. Run populate_all.py, or one populate_<store>.py.")
    sys.exit(2)
