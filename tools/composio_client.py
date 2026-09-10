#!/usr/bin/env python3
"""composio_client.py - the ONE way a populate script reaches a connected account.

WHY COMPOSIO AT ALL. Gmail, Calendar, Drive and ClickUp are already connected to Cory's Composio
account; the laptop is not. R70.315 §2 says the laptop holds the access, once, in a git-ignored
`.env`. One `COMPOSIO_API_KEY` reaches all four through the connections that already exist, which
is one Bitwarden item and one paste instead of a Google OAuth client plus a ClickUp token plus the
consent screens that come with them. Where Composio cannot reach a store, that store names its own
token and the script says so in one line (see `bev_env.py`'s FALLBACKS table).

WHAT THIS FILE REFUSES TO DO. It does not guess. If the API answers with a shape this client did
not expect, it raises `Wall` carrying the HTTP status and the first 200 bytes of the body - it
never returns a half-parsed result that a caller would count as records. A populate that reports
"0 records at origin" because it silently failed to parse is worse than one that reports a wall:
the first looks like an empty inbox, the second looks like what it is.

NO THIRD-PARTY IMPORT. urllib only. A populate that runs forever on this laptop cannot depend on a
`pip install` nobody re-runs after a Python upgrade.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from populate_lib import Wall

BASE = "https://backend.composio.dev/api/v3"
TIMEOUT = 60


class Composio:
    def __init__(self, api_key: str | None, user_id: str = "default"):
        self.api_key = api_key
        self.user_id = user_id

    @property
    def live(self) -> bool:
        return bool(self.api_key)

    # -- the one request path ---------------------------------------------------------------
    def _post(self, path: str, payload: dict) -> dict:
        if not self.api_key:
            raise Wall("no COMPOSIO_API_KEY on this laptop")
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            head = (e.read() or b"")[:200].decode("utf-8", "replace")
            # The key itself is never in the message: the status and the server's own words are
            # what a reader needs, and a key in a receipt is a key in git history.
            raise Wall("composio %s -> HTTP %s %s" % (path, e.code, head)) from None
        except Exception as e:                                  # network, DNS, TLS, timeout
            raise Wall("composio %s unreachable: %s" % (path, type(e).__name__)) from None
        try:
            return json.loads(body)
        except ValueError:
            raise Wall("composio %s returned non-JSON: %s"
                       % (path, body[:200].decode("utf-8", "replace"))) from None

    def execute(self, tool_slug: str, arguments: dict) -> dict:
        """Run one connected-account tool and hand back its `data` payload.

        Composio wraps every result as {successful, data, error}. A `successful: false` is a WALL,
        not an empty result - see the docstring."""
        out = self._post("/tools/execute/%s" % tool_slug,
                         {"user_id": self.user_id, "arguments": arguments})
        if isinstance(out, dict) and out.get("successful") is False:
            raise Wall("composio %s failed: %s" % (tool_slug, str(out.get("error"))[:160]))
        data = out.get("data") if isinstance(out, dict) else None
        if data is None:
            raise Wall("composio %s returned no `data` key (got %s)"
                       % (tool_slug, ", ".join(sorted(out))[:120] if isinstance(out, dict) else type(out).__name__))
        return data

    def ping(self, tool_slug: str, arguments: dict) -> str:
        """ONE read-only call per store, used by `bev_env.py --prompt` to verify the key.

        Returns 'PASS' or the wall's own words. It never raises: verification that can crash the
        verifier tells you nothing about the store."""
        try:
            self.execute(tool_slug, arguments)
            return "PASS"
        except Wall as w:
            return str(w)


# The read-only probe for each store. One call, smallest possible page, no writes anywhere.
PROBES = {
    "gmail":    ("GMAIL_FETCH_EMAILS",              {"max_results": 1}),
    "calendar": ("GOOGLECALENDAR_LIST_CALENDARS",   {"max_results": 1}),
    "drive":    ("GOOGLEDRIVE_LIST_FILES",          {"page_size": 1}),
    "clickup":  ("CLICKUP_GET_AUTHORIZED_USER",     {}),
}
