#!/usr/bin/env python3
"""bev_env.py - the credential enters through the TERMINAL, once, and never through a chat.

    python bev/tools/bev_env.py --prompt     # ask once, hidden, write .env, verify each store
    python bev/tools/bev_env.py --check      # verify what is already there; ask nothing
    python bev/tools/bev_env.py --names      # print the variable table; touch nothing

R70.315 §2 / PASTE 108 P1. `BEV\\_reconcile\\.env` is git-ignored (R35.5), mode 600, and holds
`COMPOSIO_API_KEY` - the Bitwarden item is named "Composio API key". Where Composio cannot reach a
store from a script, that store's own token is named in FALLBACKS below, one line each.

THE PROMPT MUST NOT BE ABLE TO BLOCK THE WIRE, and that is a design constraint, not a nicety. A
populate that waits forever on an unattended keyboard is a populate that does not run at 02:00.
So the prompt runs on a daemon thread with a 120 s deadline, and on timeout - or on EOF, which is
what a non-interactive shell gives you immediately - every script falls through to `--snapshot`
and reports `BUILT · NOT RUN LIVE (key absent)`. The wall is named; nothing hangs.

THE VALUE IS NEVER ECHOED, never printed, never in an exception, never in a receipt line. The only
thing this file ever prints about a key is whether a read-only probe passed.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populate_lib import estate_root, estate_path, load_env, now_cdt          # noqa: E402
from composio_client import Composio, PROBES                     # noqa: E402

PROMPT_TIMEOUT = 120

# One line each (PASTE 108 P1). PRIMARY reaches the store through the account already connected to
# Composio; FALLBACK is what that store needs if Composio cannot reach it from a script.
FALLBACKS = [
    ("gmail",          "COMPOSIO_API_KEY", "GOOGLE_OAUTH_CLIENT_JSON - Gmail API, read-only scope"),
    ("calendar",       "COMPOSIO_API_KEY", "GOOGLE_OAUTH_CLIENT_JSON - Calendar API, read-only scope"),
    ("drive",          "COMPOSIO_API_KEY", "GOOGLE_OAUTH_CLIENT_JSON - Drive API, read-only scope"),
    ("clickup",        "COMPOSIO_API_KEY", "CLICKUP_TOKEN - ClickUp personal API token"),
    ("registers",      "none - local files", "-"),
    ("claude-project", "none - local files", "-"),
]


def env_path(estate: str) -> str:
    return os.path.join(estate_path(estate, "_reconcile"), ".env")


def ask_hidden(label: str, timeout: int = PROMPT_TIMEOUT) -> str | None:
    """getpass on a daemon thread. Returns None on timeout, on EOF, or on no tty.

    A daemon thread is the point: if the read is still blocked at the deadline the interpreter can
    still exit, so an unattended run ends instead of hanging until someone notices tomorrow."""
    if not sys.stdin or not sys.stdin.isatty():
        return None                                   # non-interactive shell: EOF is immediate
    box: list[str] = []

    def _read():
        try:
            import getpass
            box.append(getpass.getpass(label))
        except Exception:
            pass

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box[0].strip() if box and box[0].strip() else None


def write_env(estate: str, key: str, value: str) -> str:
    """Merge one variable into .env, 600, atomically. Existing variables are preserved."""
    path = env_path(estate)
    env = load_env(estate)
    env[key] = value
    lines = ["# BEV credentials. GIT-IGNORED (R35.5). Written by bev/tools/bev_env.py.",
             "# Never paste a value into a chat; never commit this file. Bitwarden holds the originals.",
             "# last written %s" % now_cdt()]
    lines += ["%s=%s" % (k, env[k]) for k in sorted(env)]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass                                          # Windows ACLs; the git-ignore is the real gate
    return path


def verify(estate: str) -> list[tuple[str, str]]:
    """ONE read-only call per store. Returns [(store, 'PASS' | the wall's own words)]."""
    key = load_env(estate).get("COMPOSIO_API_KEY") or os.environ.get("COMPOSIO_API_KEY")
    c = Composio(key)
    if not c.live:
        return [(s, "no COMPOSIO_API_KEY on this laptop") for s in PROBES]
    return [(store, c.ping(slug, args)) for store, (slug, args) in PROBES.items()]


def main() -> int:
    ap = argparse.ArgumentParser(prog="bev_env.py")
    ap.add_argument("--prompt", action="store_true", help="ask once for the key (hidden), then verify")
    ap.add_argument("--check", action="store_true", help="verify what is already on disk")
    ap.add_argument("--names", action="store_true", help="print the variable table and exit")
    ap.add_argument("--estate", default=None)
    ap.add_argument("--timeout", type=int, default=PROMPT_TIMEOUT)
    a = ap.parse_args()
    estate = estate_root(a.estate)

    if a.names or not (a.prompt or a.check):
        print("%-16s %-22s %s" % ("store", "primary", "fallback if Composio cannot reach it"))
        for row in FALLBACKS:
            print("%-16s %-22s %s" % row)
        print("\n.env: %s   (git-ignored; Bitwarden item \"Composio API key\")" % env_path(estate))
        print("copy the key from: Composio dashboard -> Settings -> API keys")
        return 0

    if a.prompt and not load_env(estate).get("COMPOSIO_API_KEY"):
        v = ask_hidden("Composio API key (hidden, %ss, Enter to skip): " % a.timeout, a.timeout)
        if v:
            p = write_env(estate, "COMPOSIO_API_KEY", v)
            print("wrote COMPOSIO_API_KEY to %s (mode 600, git-ignored). Value not echoed." % p)
        else:
            print("no key given (timeout / non-interactive). Every populate falls through to "
                  "--snapshot and reports: BUILT - NOT RUN LIVE (key absent).")

    print("\n%-16s %s" % ("store", "read-only probe"))
    walls = 0
    for store, result in verify(estate):
        print("%-16s %s" % (store, result))
        walls += result != "PASS"
    for store, primary, _fb in FALLBACKS:
        if store not in PROBES:
            print("%-16s n/a - local files, no credential" % store)
    return 0 if walls == 0 else 0        # a wall is a report, never a non-zero exit (CONTRACT 8)


if __name__ == "__main__":
    sys.exit(main())
