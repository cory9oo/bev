# `bev\tools\` — the populates. The laptop runs these forever.

*Shipped by WIRE BEV-POPULATE-1 (PASTE 108) under **R70.315 — POPULATES ARE SCRIPTS ON THE LAPTOP**.
PASTE 98 ran the same six exports inside a chat: two hours, one failure with no retry state,
nothing resumable, nothing repeatable. These replace that, and the in-chat export is retired as a
method (R70.315 §4). The snapshot it produced is kept (DEC-037) and is the fixture these run against.*

## The one command

```
python bev\tools\populate_all.py --since 2026-09-01
```

Daily, unattended, from Task Scheduler:

```
schtasks /Create /TN "BEV populate" /SC DAILY /ST 05:30 ^
  /TR "python C:\Users\fugie\BEV\bev\tools\populate_all.py --since AUTO"
```

## What each one writes

| script | grain (PASTE 107 T3) | credential |
|---|---|---|
| `populate_gmail.py` | CSV per account per month, one row per thread | `COMPOSIO_API_KEY` |
| `populate_clickup.py` | CSV per list per month, one row per task | `COMPOSIO_API_KEY` |
| `populate_calendar.py` | CSV per calendar per month, one row per event | `COMPOSIO_API_KEY` |
| `populate_drive.py` | one CSV index per folder per drive | `COMPOSIO_API_KEY` |
| `populate_registers.py` | CSV as-is, masked | none — local files |
| `populate_claude_project.py` | one INDEX row per doc, body to `_records\` | none — local files |

**Name your mailboxes once:** `populate_gmail.py --accounts a@x.com,b@y.com`. Without it the script
falls back to "an address on ≥5 % of threads is one of ours", and over the real 245-thread snapshot
that promoted a frequent *correspondent* to an account folder. `COUNTS.json` records which one
decided, as `accounts_source: declared | inferred`.

**Two of the six never needed a chat at all.** `registers` and `claude-project` are local files and
run live on this laptop today, key or no key.

## The two trees, and why

```
master-brain\records\<store>\     TRACKED   INDEX.md · COUNTS.json · MANIFEST.tsv · the CSVs
master-brain\_records\<store>\    IGNORED   bodies, attachments, binaries — manifested by sha
```

**A record is not a note. Objects are searched; records are addressed.** The stress test measured a
50,000-file clone of this container: a catalog with one row per record reaches 6.9 MB at 50k and
breaks the estate's own 5 MB rule at ~36k notes. So `records\<store>\` carries **one catalog row for
the whole store** — its address, its `COUNTS.json`, its refresh cadence.

## The credential

```
python bev\tools\bev_env.py --names     # the variable table; touches nothing
python bev\tools\bev_env.py --prompt    # ask once, hidden, write .env, verify each store
python bev\tools\bev_env.py --check     # verify what is on disk; ask nothing
```

One key — `COMPOSIO_API_KEY`, Bitwarden item **"Composio API key"**, from the Composio dashboard →
Settings → API keys — reaches Gmail, Calendar, Drive and ClickUp through the accounts already
connected. It lives in `BEV\_reconcile\.env`, git-ignored (R35.5), mode 600, **entered in the
terminal and never in a chat**. Without it the four connected stores report
`BUILT · NOT RUN LIVE (key absent)` and the run still completes — a locked door is not a defect.

## The contract every one of them keeps

`--since` incremental · `--full` · `--dry-run` · `--snapshot <dir>` · `--limit N` · idempotent by
sha (**the second run writes 0**) · resumable (the manifest *is* the resume state) · counted at
origin vs held · `COUNTS.json` · secrets never, accounts masked to the last four · nothing over
5 MB enters git · **one store's failure never blocks another**.

```
python -m pytest bev\tools\tests -q
```
