#!/usr/bin/env python3
"""populate_calendar.py - events, at the grain the stress test ruled.

GRAIN (PASTE 107 T3): `records/calendar/<calendar>/YYYY-MM.csv`, one row per EVENT. ~62 files/yr.
A meeting becomes a NOTE only when it has an OUTCOME. An event with no outcome is a record.

PASTE 98's calendar export is the one that finished inside the chat. Nothing of it is re-done by
hand (R70.315 §4): point `--snapshot` at whatever it saved and this script backfills from it, or
run live once the key is on the laptop.
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populate_lib import (Store, Wall, in_window, sha256, since_of,        # noqa: E402
                          ResumeStop, load_env, main_wrapper)
from composio_client import Composio                                       # noqa: E402

STORE = "calendar"
GRAIN = "CSV per calendar per month, one row per event; a note only for a meeting with an outcome"
HEADER = ["event_id", "date", "calendar", "start", "end", "summary", "location",
          "attendees", "status", "recurring", "url"]


def _month(d: str) -> str:
    d = (d or "")[:7]
    return d if len(d) == 7 and d[4] == "-" else "undated"


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_@." else "-" for c in str(s).strip())[:60] or "primary"


def read_snapshot(path: str) -> list[dict]:
    """Accepts EVENTS.tsv/.csv, INDEX.tsv/.csv, or a events.json array from the 98 export."""
    for name in ("EVENTS.tsv", "EVENTS.csv", "INDEX.tsv", "INDEX.csv"):
        p = os.path.join(path, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace", newline="") as fh:
                return list(csv.DictReader(fh, delimiter="\t" if p.endswith(".tsv") else ","))
    p = os.path.join(path, "events.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else data.get("items", [])
    raise Wall("snapshot at %s holds no EVENTS/INDEX/events.json - PASTE 98's calendar run "
               "finished in the chat but landed no file on this laptop" % path)


def read_live(api_key: str, since: str | None, limit: int) -> list[dict]:
    c = Composio(api_key)
    cals = c.execute("GOOGLECALENDAR_LIST_CALENDARS", {"max_results": 50})
    items = cals.get("items") if isinstance(cals, dict) else None
    if not isinstance(items, list) or not items:
        raise Wall("GOOGLECALENDAR_LIST_CALENDARS returned no `items` list")
    out = []
    for cal in items:
        cid = cal.get("id")
        if not cid:
            continue
        args = {"calendar_id": cid, "max_results": limit or 2500, "single_events": True}
        if since:
            args["timeMin"] = "%sT00:00:00Z" % since
        data = c.execute("GOOGLECALENDAR_EVENTS_LIST", args)
        evs = data.get("items") if isinstance(data, dict) else None
        if not isinstance(evs, list):
            raise Wall("GOOGLECALENDAR_EVENTS_LIST returned no `items` for %s" % cid)
        for e in evs:
            start = (e.get("start") or {})
            end = (e.get("end") or {})
            s = start.get("dateTime") or start.get("date") or ""
            out.append({
                "event_id": str(e.get("id", "")),
                "date": s[:10],
                "calendar": cal.get("summary") or cid,
                "start": s,
                "end": end.get("dateTime") or end.get("date") or "",
                "summary": e.get("summary", ""),
                "location": e.get("location", ""),
                "attendees": ",".join(a.get("email", "") for a in (e.get("attendees") or [])),
                "status": e.get("status", ""),
                "recurring": "yes" if e.get("recurringEventId") else "",
                "url": e.get("htmlLink", ""),
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
        source = "composio:GOOGLECALENDAR_EVENTS_LIST"

    at_origin = len(rows)
    by_file: dict[str, list[dict]] = {}
    n = 0
    try:
        for r in rows:
            eid = str(r.get("event_id") or r.get("id") or "")
            if not eid or not in_window(r.get("date", ""), since):
                continue
            if args.limit and n >= args.limit:
                break
            row = {c: r.get(c, "") for c in HEADER}
            row["event_id"] = eid
            csv_key = "%s/%s.csv" % (_slug(row.get("calendar")), _month(row.get("date", "")))
            by_file.setdefault(csv_key, []).append(row)
            st.record(eid, sha256(repr(sorted(row.items()))), len(str(row)), csv_key, "event")
            n += 1
            if args.fail_after and n >= args.fail_after:
                raise ResumeStop("--fail-after %d" % args.fail_after)
    except ResumeStop as stop:
        walls.append("stopped early (%s) - the manifest is saved, the next run resumes" % stop)

    for relpath, batch in sorted(by_file.items()):
        st.write_csv(relpath, HEADER, batch, key="event_id")
    return st.finish(at_origin, since, source, GRAIN, walls)


run.STORE = STORE


if __name__ == "__main__":
    sys.exit(main_wrapper(STORE, run))
