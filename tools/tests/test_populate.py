#!/usr/bin/env python3
"""test_populate.py - the §STRESS TEST of WIRE BEV-POPULATE-1, as code rather than as a promise.

Every test here maps to a numbered line of the wire's stress test. A populate that passes review
and fails these is a populate that will quietly stop refreshing in three weeks, which is exactly
what PASTE 98 produced.

    python -m pytest bev/tools/tests -q
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import pytest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import populate_lib as L                     # noqa: E402
import populate_gmail                        # noqa: E402
import populate_registers                    # noqa: E402
import populate_claude_project               # noqa: E402
import populate_clickup                      # noqa: E402


# ---------------------------------------------------------------------------------------------
# A whole estate in a tmp dir: the two trees the container needs, plus two real snapshots.
# ---------------------------------------------------------------------------------------------
THREADS = [
    ("aaaa111122223333", "2026-09-09", "a@x.com", "cory@own.com", "Quote", "SENT", "1"),
    ("bbbb444455556666", "2026-09-08", "cory@own.com", "b@y.com", "Invoice 55", "INBOX", "2"),
    ("cccc777788889999", "2026-08-30", "c@z.com", "cory@own.com", "Old thread", "INBOX", "1"),
]


@pytest.fixture
def estate(tmp_path):
    root = tmp_path / "BEV"
    (root / "_reconcile").mkdir(parents=True)
    (root / "master-brain").mkdir()
    (root / "life-taxonomy" / "registers").mkdir(parents=True)
    snap = root / "Claude outputs"
    snap.mkdir()
    idx = ["\t".join(("thread_id", "date", "from", "to", "subject", "labels", "message_count"))]
    idx += ["\t".join(t) for t in THREADS]
    # The 98 export repeats its own header inside the file. The reader must not file it as a thread.
    idx.append("\t".join(("thread_id", "date", "from", "to", "subject", "labels", "message_count")))
    (snap / "INDEX.tsv").write_text("\n".join(idx) + "\n", encoding="utf-8")
    (snap / "aaaa111122223333.md").write_text("# Quote\nbody of the quote\n", encoding="utf-8")
    (snap / "C27.md").write_text("# BEV ROCKS\nthe rocks\n", encoding="utf-8")
    (snap / "D35.md").write_text("# BEV - THE LOOP\nthe loop\n", encoding="utf-8")
    (root / "life-taxonomy" / "registers" / "decisions.csv").write_text(
        "id,what\nDEC-1,ruled\nDEC-2,ruled\n", encoding="utf-8")
    (root / "life-taxonomy" / "registers" / "issues.csv").write_text(
        "id,what\nISS-1,open\n", encoding="utf-8")
    (root / "life-taxonomy" / "registers" / "issues.csv.pre-bev-home-1-h5").write_text(
        "id,what\nISS-1,open\n", encoding="utf-8")
    (root / "life-taxonomy" / "registers" / "entities.yaml").write_text("a: 1\n", encoding="utf-8")
    return root


def args_for(estate, **kw):
    base = dict(since=None, full=False, dry_run=False, snapshot=None, limit=0, fail_after=0,
                estate=str(estate), json=False, own_share=0.05, accounts="")
    base.update(kw)
    return argparse.Namespace(**base)


def counts_of(estate, store):
    p = estate / "master-brain" / "records" / store / "COUNTS.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------
# STRESS TEST 1 - the second run of every script writes 0.
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mod,kw", [
    (populate_gmail, {"snapshot": "Claude outputs"}),
    (populate_claude_project, {"snapshot": "Claude outputs"}),
    (populate_registers, {}),
])
def test_second_run_writes_zero(estate, mod, kw):
    if kw.get("snapshot"):
        kw["snapshot"] = str(estate / kw["snapshot"])
    first = mod.run(args_for(estate, **kw))
    assert first["copied"] > 0, "the first run must actually copy something"
    second = mod.run(args_for(estate, **kw))
    assert second["copied"] == 0, "second run wrote %d - idempotence is broken" % second["copied"]
    assert second["at_origin"] == first["at_origin"]


# ---------------------------------------------------------------------------------------------
# STRESS TEST 2 - --since touches only newer rows, and never drops an older one already filed.
# ---------------------------------------------------------------------------------------------
def test_since_touches_only_new_rows(estate):
    snap = str(estate / "Claude outputs")
    populate_gmail.run(args_for(estate, snapshot=snap))
    before = _all_thread_ids(estate)
    assert len(before) == 3

    c = populate_gmail.run(args_for(estate, snapshot=snap, since="2026-09-09"))
    assert c["copied"] == 0, "nothing changed, so --since must write nothing"
    after = _all_thread_ids(estate)
    assert after == before, "an incremental run deleted rows it did not fetch"


def test_since_excludes_older_records_on_a_fresh_tree(estate):
    c = populate_gmail.run(args_for(estate, snapshot=str(estate / "Claude outputs"),
                                    since="2026-09-09"))
    assert c["at_origin"] == 3           # origin is counted BEFORE the window, always
    assert _all_thread_ids(estate) == {"aaaa111122223333"}


def _all_thread_ids(estate) -> set:
    root = estate / "master-brain" / "records" / "gmail"
    out = set()
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".csv"):
                with open(os.path.join(dirpath, f), encoding="utf-8", newline="") as fh:
                    out |= {r["thread_id"] for r in csv.DictReader(fh) if r.get("thread_id")}
    return out


# ---------------------------------------------------------------------------------------------
# STRESS TEST 3 - kill a run mid-store; the next run resumes and does not duplicate.
# ---------------------------------------------------------------------------------------------
def test_kill_mid_store_resumes_without_duplicates(estate):
    snap = str(estate / "Claude outputs")
    partial = populate_gmail.run(args_for(estate, snapshot=snap, fail_after=1))
    assert partial["walls"], "a killed run must say it stopped early"
    assert len(_all_thread_ids(estate)) == 1

    full = populate_gmail.run(args_for(estate, snapshot=snap))
    ids = _all_thread_ids(estate)
    assert ids == {t[0] for t in THREADS}, "resume lost or duplicated a thread: %s" % ids
    manifest = estate / "master-brain" / "records" / "gmail" / "MANIFEST.tsv"
    keys = [r["key"] for r in csv.DictReader(manifest.read_text(encoding="utf-8").splitlines(),
                                             delimiter="\t")]
    assert len(keys) == len(set(keys)) == 3, "the manifest duplicated a key"
    assert full["at_origin"] == 3


# ---------------------------------------------------------------------------------------------
# STRESS TEST 4 - secrets never land; account numbers are masked to the last four.
# ---------------------------------------------------------------------------------------------
def test_secrets_are_redacted_and_accounts_masked():
    assert L.scrub("key sk-abcdefghijklmnopqrst here") == "key [REDACTED-SECRET] here"
    assert L.scrub("token ghp_ABCDEFGHIJKLMNOPQRSTUV") == "token [REDACTED-SECRET]"
    assert L.scrub("api_key: hunter2hunter2") == "api_key: [REDACTED-SECRET]"
    assert L.scrub("account 4111111111111111 paid") == "account ****1111 paid"
    assert L.scrub("acct 4111-1111-1111-1111.") == "acct ****1111."
    assert L.scrub("only 1234 here") == "only 1234 here", "a short number is not an account"


def test_an_identifier_is_never_masked():
    """REGRESSION. The first mask_account turned the thread id `aaaa111122223333` into
    `aaaa****3333` - it rewrote the primary key of every record in the store, silently. The suite
    caught it, not review, which is why the case is nailed down here rather than described."""
    for ident in ("aaaa111122223333", "1a08c01652f1e70a", "1234567890abcdef",
                  "task-9008812345678", "https://x.com/t/868112345678"):
        assert L.scrub(ident) == ident, "masking corrupted the identifier %s" % ident
    assert L.scrub("balance on 4111111111111111 today") == "balance on ****1111 today"


def test_scrub_runs_on_everything_written(estate):
    src = estate / "life-taxonomy" / "registers" / "money_dated.csv"
    src.write_text("id,acct\nM-1,4111111111111111\n", encoding="utf-8")
    populate_registers.run(args_for(estate))
    out = (estate / "master-brain" / "records" / "registers" / "money_dated.csv").read_text("utf-8")
    assert "4111111111111111" not in out and "****1111" in out


# ---------------------------------------------------------------------------------------------
# STRESS TEST 5 - nothing over 5 MB reaches the tracked tree.
# ---------------------------------------------------------------------------------------------
def test_oversize_goes_to_the_bulk_tree(estate):
    st = L.Store("gmail", str(estate))
    st.write_text("huge.csv", "x" * (L.MAX_GIT_BYTES + 1))
    assert not (estate / "master-brain" / "records" / "gmail" / "huge.csv").exists()
    assert (estate / "master-brain" / "_records" / "gmail" / "huge.csv").exists()
    assert st.oversize == ["huge.csv"]


# ---------------------------------------------------------------------------------------------
# STRESS TEST 7 - a missing credential degrades to a named wall; it never blocks and never crashes.
# ---------------------------------------------------------------------------------------------
def test_missing_key_is_a_wall_not_a_crash(estate, monkeypatch):
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    c = L.run_store(populate_clickup.run, args_for(estate))
    assert c["failed"] == 0, "a locked door is not a defect"
    assert any("NOT RUN LIVE" in w for w in c["walls"]), c["walls"]


def test_a_defect_is_reported_as_a_defect():
    def broken(_a):
        raise ValueError("this is a bug, not a wall")
    broken.STORE = "broken"
    c = L.run_store(broken, None)
    assert c["failed"] == 1 and "DEFECT ValueError" in c["walls"][0]


# ---------------------------------------------------------------------------------------------
# The grain ruling itself: ONE catalog row per store, never one per record (PASTE 107 T3).
# ---------------------------------------------------------------------------------------------
def test_one_index_note_per_store_not_one_per_record(estate):
    populate_gmail.run(args_for(estate, snapshot=str(estate / "Claude outputs")))
    root = estate / "master-brain" / "records" / "gmail"
    mds = [p for p in root.rglob("*.md")]
    assert [p.name for p in mds] == ["INDEX.md"], "records must not grow one note per record"
    assert "BRAIN-RECORDS-GMAIL" in (root / "INDEX.md").read_text(encoding="utf-8")


def test_bodies_are_ignored_not_tracked(estate):
    populate_gmail.run(args_for(estate, snapshot=str(estate / "Claude outputs")))
    assert (estate / "master-brain" / "_records" / "gmail" / "threads"
            / "aaaa111122223333.md").exists()
    assert not (estate / "master-brain" / "records" / "gmail" / "threads").exists()


def test_header_row_in_the_98_export_is_not_filed_as_a_thread(estate):
    c = populate_gmail.run(args_for(estate, snapshot=str(estate / "Claude outputs")))
    assert c["at_origin"] == 3, "the repeated header row was counted as a thread"
    assert "thread_id" not in _all_thread_ids(estate)


def test_backup_registers_are_skipped_with_a_reason(estate):
    c = populate_registers.run(args_for(estate))
    assert any("pre-bev-home-1-h5" in w for w in c["walls"])
    assert not (estate / "master-brain" / "records" / "registers"
                / "issues.csv.pre-bev-home-1-h5").exists()


def test_gmail_files_are_not_filed_twice_by_claude_project(estate):
    c = populate_claude_project.run(args_for(estate, snapshot=str(estate / "Claude outputs")))
    assert any("belongs to store gmail" in w for w in c["walls"])
    bulk = estate / "master-brain" / "_records" / "claude-project"
    assert sorted(p.name for p in bulk.iterdir()) == ["C27.md", "D35.md"]


def test_counts_json_has_the_contract_fields(estate):
    populate_registers.run(args_for(estate))
    c = counts_of(estate, "registers")
    for field in ("store", "at_origin", "copied", "skipped", "failed", "since", "ran_at",
                  "source", "grain"):
        assert field in c, "COUNTS.json is missing %s (R70.308 §4)" % field


@pytest.mark.parametrize("script", [
    "populate_gmail.py", "populate_clickup.py", "populate_calendar.py", "populate_drive.py",
    "populate_registers.py", "populate_claude_project.py", "populate_all.py", "bev_env.py",
])
def test_every_entry_point_actually_starts(script):
    """The suite imports `run` directly, so it never touches `__main__` - and a NameError there
    is invisible to every other test in this file. `populate_registers.py` shipped exactly that
    for one commit: a consolidation rewrote five import lines and missed the sixth, and only
    `--help` found it. So every entry point is started, in a subprocess, on every run."""
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(TOOLS, script), "--help"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, "%s --help exited %s:\n%s" % (script, r.returncode, r.stderr[-800:])


def test_estate_root_is_found_from_a_worktree_depth(tmp_path, monkeypatch):
    """`../..` is right in bev/tools and wrong in _wt/bev--WIRE/tools. The root is FOUND."""
    root = tmp_path / "BEV"
    (root / "_reconcile").mkdir(parents=True)
    (root / "master-brain").mkdir()
    deep = root / "_wt" / "bev--BEV-POPULATE-1" / "tools"
    deep.mkdir(parents=True)
    monkeypatch.setattr(L, "__file__", str(deep / "populate_lib.py"))
    monkeypatch.delenv("BEV_ROOT", raising=False)
    assert os.path.normcase(L.estate_root()) == os.path.normcase(str(root))


def test_declared_accounts_beat_the_frequency_fallback(estate):
    """MEASURED REGRESSION. Over the real 245-thread snapshot the 5%-share fallback promoted
    `palermoconstruction@outlook.com` - a frequent CORRESPONDENT - to an account folder and filed
    six of Cory's own threads under someone else's name. Frequency cannot tell "my mailbox" from
    "the person I email most". `--accounts` states it; the fallback only guesses."""
    # A correspondent Cory emails on most threads - which is what the real snapshot had.
    snap = estate / "snap2"
    snap.mkdir()
    hdr = ("thread_id", "date", "from", "to", "subject", "labels", "message_count")
    rows = [("dddd111122223333", "2026-09-09", "cory@own.com", "loud@corp.com", "a", "SENT", "1"),
            ("eeee111122223333", "2026-09-08", "loud@corp.com", "cory@own.com", "b", "INBOX", "1"),
            ("ffff111122223333", "2026-09-07", "cory@own.com", "loud@corp.com", "c", "SENT", "1")]
    (snap / "INDEX.tsv").write_text(
        "\n".join("\t".join(r) for r in [hdr] + rows) + "\n", encoding="utf-8")
    snap = str(snap)

    loud = populate_gmail.run(args_for(estate, snapshot=snap))
    assert "loud@corp.com" in loud["accounts"], "the fallback promotes a frequent correspondent"
    assert loud["accounts_source"] == "inferred"

    declared = populate_gmail.run(args_for(estate, snapshot=snap, accounts="cory@own.com"))
    assert declared["accounts"] == ["cory@own.com"]
    assert declared["accounts_source"] == "declared"
    root = estate / "master-brain" / "records" / "gmail"
    # The declared run re-files every thread under the real mailbox. The fallback's wrong folder
    # is left on disk (nothing is ever deleted - DEC-037); what matters is that no NEW thread
    # lands under a correspondent's name once the operator has said what the mailboxes are.
    assert "cory@own.com" in [p.name for p in root.iterdir() if p.is_dir()]
