#!/usr/bin/env python3
"""populate_clickup.py - tasks, at the grain the stress test ruled.

GRAIN (PASTE 107 T3): `records/clickup/<list>/YYYY-MM.csv`, one row per TASK. ~72 files/yr.
A task becomes a NOTE only when it becomes an object - a commitment somebody owes. Until then it
is a record, addressed through its list's CSV.

This is the store PASTE 98 could not finish: it failed once inside the chat with no retry state,
then re-ran for 20 steps. That is the exact failure R70.315 §3 makes impossible here - the manifest
is the resume state, so a killed run continues instead of restarting.
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populate_lib import (Store, Wall, in_window, sha256, since_of,       # noqa: E402
                          ResumeStop, load_env, main_wrapper)
from composio_client import Composio                                      # noqa: E402

STORE = "clickup"
GRAIN = "CSV per list per month, one row per task; bodies to _records/, git-ignored"
HEADER = ["task_id", "date", "list", "name", "status", "assignees", "due_date",
          "priority", "url", "body_path"]


def _month(d: str) -> str:
    d = (d or "")[:7]
    return d if len(d) == 7 and d[4] == "-" else "undated"


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in str(s).strip())[:60] or "unlisted"


def read_snapshot(path: str) -> list[dict]:
    """Accepts either a TASKS.tsv/csv from an export, or a directory of per-list CSVs."""
    for name in ("TASKS.tsv", "TASKS.csv", "INDEX.tsv", "INDEX.csv"):
        p = os.path.join(path, name)
        if os.path.exists(p):
            delim = "\t" if p.endswith(".tsv") else ","
            with open(p, encoding="utf-8", errors="replace", newline="") as fh:
                return [r for r in csv.DictReader(fh, delimiter=delim)
                        if (r.get("task_id") or r.get("id"))]
    raise Wall("snapshot at %s holds no TASKS/INDEX export - PASTE 98's ClickUp run never landed "
               "a file on this laptop" % path)


def read_live(api_key: str, since: str | None, limit: int) -> list[dict]:
    c = Composio(api_key)
    spaces = c.execute("CLICKUP_GET_AUTHORIZED_TEAMS", {})
    teams = spaces.get("teams") if isinstance(spaces, dict) else None
    if not isinstance(teams, list) or not teams:
        raise Wall("CLICKUP_GET_AUTHORIZED_TEAMS returned no `teams` list")
    out = []
    for team in teams:
        tid = team.get("id")
        if not tid:
            continue
        args = {"team_id": str(tid), "subtasks": True, "include_closed": True}
        if since:
            args["date_updated_gt"] = since
        data = c.execute("CLICKUP_GET_FILTERED_TEAM_TASKS", args)
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if not isinstance(tasks, list):
            raise Wall("CLICKUP_GET_FILTERED_TEAM_TASKS returned no `tasks` list for team %s" % tid)
        for t in tasks:
            st = t.get("status") or {}
            out.append({
                "task_id": str(t.get("id", "")),
                "date": str(t.get("date_updated") or t.get("date_created") or "")[:10],
                "list": (t.get("list") or {}).get("name", ""),
                "name": t.get("name", ""),
                "status": st.get("status", "") if isinstance(st, dict) else str(st),
                "assignees": ",".join(a.get("username", "") for a in (t.get("assignees") or [])),
                "due_date": str(t.get("due_date") or "")[:10],
                "priority": (t.get("priority") or {}).get("priority", "") if isinstance(t.get("priority"), dict) else "",
                "url": t.get("url", ""),
                "_body": t.get("description") or t.get("text_content") or "",
            })
            if limit and len(out) >= limit:
                return out
    return out


def run(args) -> dict:
    st = Store(STORE, args.estate, args.dry_run)
    since = since_of(args)
    walls: list[str] = []

    if args.snapshot:
        rows = read_snapshot(args.snapshot)
        source = "snapshot:%s" % os.path.basename(args.snapshot.rstrip("\\/"))
    else:
        key = load_env(args.estate).get("COMPOSIO_API_KEY") or os.environ.get("COMPOSIO_API_KEY")
        if not key:
            raise Wall("BUILT - NOT RUN LIVE (key absent): set COMPOSIO_API_KEY or pass --snapshot")
        rows = read_live(key, since, args.limit)
        source = "composio:CLICKUP_GET_FILTERED_TEAM_TASKS"

    at_origin = len(rows)
    by_file: dict[str, list[dict]] = {}
    n = 0
    try:
        for r in rows:
            tid = str(r.get("task_id") or r.get("id") or "")
            if not tid or not in_window(r.get("date", ""), since):
                continue
            if args.limit and n >= args.limit:
                break
            body = r.pop("_body", "")
            body_path = ""
            if body:
                body_path = "tasks/%s.md" % tid
                st.put_bulk(body_path, str(body).encode("utf-8"), kind="task-body")
            row = {c: r.get(c, "") for c in HEADER}
            row["task_id"], row["body_path"] = tid, body_path
            csv_key = "%s/%s.csv" % (_slug(row.get("list")), _month(row.get("date", "")))
            by_file.setdefault(csv_key, []).append(row)
            st.record(tid, sha256(repr(sorted(row.items()))), len(str(row)), csv_key, "task")
            n += 1
            if args.fail_after and n >= args.fail_after:
                raise ResumeStop("--fail-after %d" % args.fail_after)
    except ResumeStop as stop:
        walls.append("stopped early (%s) - the manifest is saved, the next run resumes" % stop)

    for relpath, batch in sorted(by_file.items()):
        st.write_csv(relpath, HEADER, batch, key="task_id")
    return st.finish(at_origin, since, source, GRAIN, walls)


run.STORE = STORE


if __name__ == "__main__":
    sys.exit(main_wrapper(STORE, run))
