#!/usr/bin/env python3
"""populate_claude_project.py - the Claude Project docs, which ARE the exception the grain allows.

GRAIN: `records/claude-project/INDEX.csv` (one row per doc) + the body in `_records/`.
The stress test's rule is "a record is not a note" - and its own exception is a doc a person would
read as prose. These forty are exactly that: BEV END STATE, the DOCTRINE, the STANDARD research,
the habit doctrine. They are indexed here as records and become notes when CONTAINER-SHAPE-1 gives
them a home; nothing is lost either way, because the body is manifested by sha.

THIS IS WHAT PASTE 98 ACTUALLY LANDED. K2's "66 outputs" is a NUMBERING (C27-F66), not a count:
fifty files are on this laptop. The receipt says so, and this script counts them rather than
repeating the claim.

ONE DIRECTORY, TWO STORES. `Claude outputs\\` also holds Gmail's INDEX.tsv and six thread bodies.
They are SKIPPED here with a named reason rather than filed twice - a record counted in two stores
is a record whose counts can never be reconciled again.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populate_lib import (Store, Wall, sha256, since_of, ResumeStop, in_window,   # noqa: E402
                          main_wrapper)

STORE = "claude-project"
GRAIN = "one INDEX row per doc; bodies to _records/, git-ignored, manifested by sha"
HEADER = ["doc_id", "date", "title", "kind", "bytes", "sha256", "body_path", "source"]

GMAIL_THREAD = re.compile(r"^[0-9a-f]{12,20}$")          # a gmail thread id, not a project doc
GMAIL_FILES = {"INDEX.tsv"}
TEXTY = (".md", ".txt", ".tsv", ".csv", ".json", ".yaml", ".yml", ".py", ".html", ".js", ".css")


def source_dir(estate: str, override: str | None) -> str:
    d = override or os.path.join(estate, "Claude outputs")
    if not os.path.isdir(d):
        raise Wall("no Claude outputs directory at %s" % d)
    return d


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines()[:40]:
        if line.startswith("# "):
            return line[2:].strip()[:160]
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"')[:160]
    return fallback


def run(args) -> dict:
    st = Store(STORE, args.estate, args.dry_run)
    since = since_of(args)
    src = source_dir(args.estate, args.snapshot)
    walls: list[str] = []

    names = sorted(n for n in os.listdir(src) if os.path.isfile(os.path.join(src, n)))
    at_origin = len(names)
    rows, n = [], 0
    try:
        for name in names:
            stem, ext = os.path.splitext(name)
            if name in GMAIL_FILES or (ext == ".md" and GMAIL_THREAD.match(stem)):
                walls.append("skipped %s (belongs to store gmail)" % name)
                continue
            path = os.path.join(src, name)
            with open(path, "rb") as fh:
                raw = fh.read()
            sha = sha256(raw)
            import datetime
            modified = datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")
            if not in_window(modified, since):
                continue
            body_path = "%s%s" % (stem, ext)
            if not st.manifest.unchanged(stem, sha):
                st.put_bulk(body_path, raw, kind="project-doc")
                st.record(stem, sha, len(raw), body_path, "project-doc")
                n += 1
            else:
                st.skipped += 1
            text = raw.decode("utf-8", "replace") if ext in TEXTY else ""
            rows.append({"doc_id": stem, "date": modified,
                         "title": _title(text, stem) if text else stem,
                         "kind": ext.lstrip(".") or "bin", "bytes": str(len(raw)),
                         "sha256": sha[:16], "body_path": "_records/%s/%s" % (STORE, body_path),
                         "source": "Claude outputs/%s" % name})
            if args.limit and n >= args.limit:
                break
            if args.fail_after and n >= args.fail_after:
                raise ResumeStop("--fail-after %d" % args.fail_after)
    except ResumeStop as stop:
        walls.append("stopped early (%s) - the manifest is saved, the next run resumes" % stop)

    st.write_csv("INDEX.csv", HEADER, rows, key="doc_id")
    return st.finish(at_origin, since, "local:Claude outputs (the PASTE 98 snapshot)", GRAIN, walls)


run.STORE = STORE


if __name__ == "__main__":
    sys.exit(main_wrapper(STORE, run))
