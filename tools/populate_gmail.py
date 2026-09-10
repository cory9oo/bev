#!/usr/bin/env python3
"""populate_gmail.py - mail into the container at the grain the stress test ruled.

GRAIN (PASTE 107 T3, which overrides R70.308's stated grain and PASTE 108 P2 says so):
    records/gmail/<account>/YYYY-MM.csv     one row per THREAD          ~132 files/yr
    _records/gmail/threads/<id>.md          a body, git-ignored, only when one exists
A thread body becomes a NOTE only when an object links it. Until then it is a record: addressed
through the CSV, never searched. At R70.308's stated grain this store alone produced 18,250 md/yr.

SOURCES, in the order tried:
    --snapshot <dir>   the PASTE 98 in-chat export: INDEX.tsv + <thread_id>.md bodies
    live               Composio GMAIL_FETCH_EMAILS against the connected account

WHOSE ACCOUNT IS IT. The snapshot names no account list and the mirror note names none either, so
this script does not invent one: an address is "ours" when it appears on at least `--own-share` of
threads (5% by default), measured over the corpus. That is derived from the data and reported in
COUNTS, rather than hardcoded from memory - a hardcoded address that is wrong quietly files a whole
account under `unfiled`.
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populate_lib import (Store, Wall, in_window, main_wrapper, sha256,   # noqa: E402
                          since_of, ResumeStop, load_env)
from composio_client import Composio                                     # noqa: E402

STORE = "gmail"
GRAIN = "CSV index per account per month, one row per thread; bodies to _records/, git-ignored"
HEADER = ["thread_id", "date", "from", "to", "subject", "labels", "message_count", "body_path"]


def _norm(addr: str) -> str:
    return (addr or "").strip().strip("<>").lower()


def _month(datestr: str) -> str:
    d = (datestr or "").strip()[:7]
    return d if len(d) == 7 and d[4] == "-" else "undated"


def read_snapshot(path: str) -> tuple[list[dict], dict[str, bytes]]:
    """The 98 export: one INDEX.tsv of threads plus whatever bodies were saved beside it."""
    index = os.path.join(path, "INDEX.tsv")
    if not os.path.exists(index):
        raise Wall("snapshot has no INDEX.tsv at %s" % path)
    rows = []
    with open(index, encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            tid = (r.get("thread_id") or "").strip()
            # The 98 export repeats its header row inside the file (measured: one row whose
            # thread_id is literally "thread_id"). Dropping it is not filtering data - it is
            # refusing to file a header as a thread.
            if not tid or tid == "thread_id":
                continue
            rows.append(r)
    bodies = {}
    for name in os.listdir(path):
        stem, ext = os.path.splitext(name)
        if ext == ".md" and any(stem == r.get("thread_id") for r in rows):
            with open(os.path.join(path, name), "rb") as fh:
                bodies[stem] = fh.read()
    return rows, bodies


def read_live(api_key: str, since: str | None, limit: int) -> tuple[list[dict], dict[str, bytes]]:
    c = Composio(api_key)
    args = {"max_results": limit or 500}
    if since:
        args["query"] = "after:%s" % since.replace("-", "/")
    data = c.execute("GMAIL_FETCH_EMAILS", args)
    msgs = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(msgs, list):
        raise Wall("GMAIL_FETCH_EMAILS returned no `messages` list")
    rows, bodies = {}, {}
    for m in msgs:
        tid = str(m.get("threadId") or m.get("thread_id") or m.get("id") or "")
        if not tid:
            continue
        r = rows.setdefault(tid, {"thread_id": tid, "date": "", "from": "", "to": "",
                                  "subject": "", "labels": "", "message_count": 0})
        r["date"] = str(m.get("messageTimestamp") or m.get("date") or r["date"])[:10]
        r["from"] = m.get("sender") or m.get("from") or r["from"]
        r["to"] = m.get("to") or r["to"]
        r["subject"] = m.get("subject") or r["subject"]
        r["labels"] = ",".join(m.get("labelIds") or []) or r["labels"]
        r["message_count"] = int(r["message_count"]) + 1
        body = m.get("messageText") or m.get("preview", {}).get("body") if isinstance(m.get("preview"), dict) else None
        if body:
            bodies[tid] = (bodies.get(tid, b"") + str(body).encode("utf-8") + b"\n\n---\n\n")
    return list(rows.values()), bodies


def own_accounts(rows: list[dict], share: float) -> set[str]:
    """An address is ours when it sits on at least `share` of threads. Measured, not remembered."""
    seen: dict[str, int] = {}
    for r in rows:
        for side in ("from", "to"):
            for a in str(r.get(side, "")).split(","):
                a = _norm(a)
                if "@" in a:
                    seen[a] = seen.get(a, 0) + 1
    floor = max(2, int(len(rows) * share))
    return {a for a, n in seen.items() if n >= floor}


def run(args) -> dict:
    st = Store(STORE, args.estate, args.dry_run)
    since = since_of(args)
    walls: list[str] = []

    if args.snapshot:
        rows, bodies = read_snapshot(args.snapshot)
        source = "snapshot:%s" % os.path.basename(args.snapshot.rstrip("\\/"))
    else:
        api_key = load_env(args.estate).get("COMPOSIO_API_KEY") or os.environ.get("COMPOSIO_API_KEY")
        if not api_key:
            raise Wall("BUILT - NOT RUN LIVE (key absent): set COMPOSIO_API_KEY or pass --snapshot")
        rows, bodies = read_live(api_key, since, args.limit)
        source = "composio:GMAIL_FETCH_EMAILS"

    at_origin = len(rows)
    ours = own_accounts(rows, args.own_share)
    by_month: dict[str, list[dict]] = {}
    n = 0
    try:
        for r in rows:
            tid = r["thread_id"]
            if not in_window(r.get("date", ""), since):
                continue
            if args.limit and n >= args.limit:
                break
            account = next((a for side in ("to", "from") for a in
                            (_norm(x) for x in str(r.get(side, "")).split(","))
                            if a in ours), "unfiled")
            body_path = ""
            if tid in bodies:
                body_path = "threads/%s.md" % tid
                st.put_bulk(body_path, bodies[tid], kind="thread-body")
            row = {c: r.get(c, "") for c in HEADER}
            row["body_path"] = body_path
            csv_key = "%s/%s.csv" % (account, _month(r.get("date", "")))
            by_month.setdefault(csv_key, []).append(row)
            st.record(tid, sha256(repr(sorted(row.items()))), len(str(row)),
                      csv_key, "thread")
            n += 1
            if args.fail_after and n >= args.fail_after:
                raise ResumeStop("--fail-after %d" % args.fail_after)
    except ResumeStop as stop:
        walls.append("stopped early (%s) - the manifest is saved, the next run resumes" % stop)

    for relpath, batch in sorted(by_month.items()):
        st.write_csv(relpath, HEADER, batch, key="thread_id")

    counts = st.finish(at_origin, since, source, GRAIN, walls)
    counts["accounts"] = sorted(ours)
    return counts


run.STORE = STORE


def _own_share(ap):
    ap.add_argument("--own-share", type=float, default=0.05,
                    help="an address on at least this share of threads is one of ours")


if __name__ == "__main__":
    sys.exit(main_wrapper(STORE, run, _own_share))
