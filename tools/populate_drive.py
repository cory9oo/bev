#!/usr/bin/env python3
"""populate_drive.py - the three Drives, at the grain the stress test ruled.

GRAIN (PASTE 107 T3): one INDEX per FOLDER, not one note per file. ~300 files/yr.
    records/drive/<drive>/<folder>.csv      one row per file in that folder
    _records/drive/<drive>/<id>-<name>      the body, only for a note-like doc, git-ignored
R70.308's stated grain produced 5,200 md/yr for this store alone. A spreadsheet is not knowledge
until somebody distils it; until then it is a record with an address.

THREE DRIVES, THREE MIRRORS (R70.314): dcigproperties, fugielc, steadfast each get their own
subtree. One source never fans out to three targets and three sources never collapse into one.
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populate_lib import (Store, Wall, in_window, sha256, since_of,        # noqa: E402
                          ResumeStop, load_env, main_wrapper)
from composio_client import Composio                                       # noqa: E402

STORE = "drive"
GRAIN = "one CSV index per folder per drive; a body only for a note-like doc, to _records/"
HEADER = ["file_id", "date", "drive", "folder", "name", "mime", "size", "owner",
          "modified", "url", "body_path"]

# A doc is "note-like" when a person would read it as prose. Everything else is addressed, never
# copied: a 40 MB spreadsheet in the container is 40 MB nobody greps and git never forgets.
NOTE_LIKE = ("application/vnd.google-apps.document", "text/markdown", "text/plain")


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in str(s).strip())[:60] or "root"


def read_snapshot(path: str) -> list[dict]:
    for name in ("FILES.tsv", "FILES.csv", "INDEX.tsv", "INDEX.csv"):
        p = os.path.join(path, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace", newline="") as fh:
                return list(csv.DictReader(fh, delimiter="\t" if p.endswith(".tsv") else ","))
    raise Wall("snapshot at %s holds no FILES/INDEX export - PASTE 98 was paused at step 3 of 7 "
               "before Drive ran" % path)


def read_live(api_key: str, since: str | None, limit: int) -> list[dict]:
    c = Composio(api_key)
    args = {"page_size": min(limit or 1000, 1000),
            "fields": "files(id,name,mimeType,size,parents,owners,modifiedTime,webViewLink)"}
    if since:
        args["query"] = "modifiedTime > '%sT00:00:00'" % since
    data = c.execute("GOOGLEDRIVE_LIST_FILES", args)
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        raise Wall("GOOGLEDRIVE_LIST_FILES returned no `files` list")
    out = []
    for f in files:
        owners = f.get("owners") or []
        owner = owners[0].get("emailAddress", "") if owners else ""
        out.append({
            "file_id": str(f.get("id", "")),
            "date": str(f.get("modifiedTime", ""))[:10],
            "drive": owner.split("@")[0] or "unfiled",
            "folder": ",".join(f.get("parents") or []) or "root",
            "name": f.get("name", ""),
            "mime": f.get("mimeType", ""),
            "size": str(f.get("size", "")),
            "owner": owner,
            "modified": f.get("modifiedTime", ""),
            "url": f.get("webViewLink", ""),
        })
        if limit and len(out) >= limit:
            break
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
        source = "composio:GOOGLEDRIVE_LIST_FILES"

    at_origin = len(rows)
    by_file: dict[str, list[dict]] = {}
    n = 0
    try:
        for r in rows:
            fid = str(r.get("file_id") or r.get("id") or "")
            if not fid or not in_window(r.get("date", ""), since):
                continue
            if args.limit and n >= args.limit:
                break
            row = {c: r.get(c, "") for c in HEADER}
            row["file_id"] = fid
            row["body_path"] = ""           # bodies are fetched by a later pass, only when linked
            if row.get("mime") in NOTE_LIKE:
                row["body_path"] = "%s/%s-%s" % (_slug(row.get("drive")), fid, _slug(row.get("name")))
            csv_key = "%s/%s.csv" % (_slug(row.get("drive")), _slug(row.get("folder")))
            by_file.setdefault(csv_key, []).append(row)
            st.record(fid, sha256(repr(sorted(row.items()))), len(str(row)), csv_key, "file")
            n += 1
            if args.fail_after and n >= args.fail_after:
                raise ResumeStop("--fail-after %d" % args.fail_after)
    except ResumeStop as stop:
        walls.append("stopped early (%s) - the manifest is saved, the next run resumes" % stop)

    for relpath, batch in sorted(by_file.items()):
        st.write_csv(relpath, HEADER, batch, key="file_id")
    return st.finish(at_origin, since, source, GRAIN, walls)


run.STORE = STORE


if __name__ == "__main__":
    sys.exit(main_wrapper(STORE, run))
