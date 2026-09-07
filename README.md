# BEV — the container

**The one place Cory and Claude look at all of life.** It **indexes**; the containers **hold**.
Every card links out to whatever holds the records — HT, SlowBooks, ClickUp, Drive, a Brain shelf,
a register row — and **copies none of them**.

Three altitudes on one page: **THE TWO NUMBERS → THE HORIZON → THE 13 DOMAINS**, with THE MACHINE
and THE BRAIN beneath. Cory reads it here on his phone and laptop; Claude reads the same truth from
`state/board.json` on the private repo. One artifact, two readers, no second copy to drift.

## This repo holds no data

Everything on screen is fetched at runtime from `state/board.json` in the **private**
`cory9oo/life-taxonomy` repo, through the GitHub contents API, with a token the reader supplies.
**No estate data is committed here and none ever should be.** The goldens read the live board from
the private repo next door when it is present and fall back to a synthetic sample otherwise; a run
that used the sample says so.

## The token, and the trade it is

The app needs a GitHub token to read a private file, and **the token lives in `localStorage` on each
device**. That is a real trade and it is named rather than hidden:

* It is scoped to **Contents: Read-only on `life-taxonomy` alone**, so the worst case is disclosure
  of a private repo the owner already owns — **no write, no other repo, no account.**
* The alternatives were worse: a service key sitting on the laptop, or Pages on the private repo
  (which is still a public page).
* **The app cannot verify a token's scope.** Settings states the exact scope it needs in words next
  to the field instead of pretending to check it.
* If BEV ever goes multi-user, this route is replaced by HT's Supabase auth — named here, not built.

Make one at `github.com/settings/personal-access-tokens/new`: name `bev-app-read`, Expiration
**Custom → 1 year**, Repository access **Only select repositories → cory9oo/life-taxonomy**,
Permissions **Contents → Read-only**. Paste it into **Settings** in the app, on each device.
It never enters a chat, a file, or a paste.

## Files

| file | what |
|---|---|
| `index.html` | the shell — the frame, the tabs, the panel containers |
| `app.js` | loader, cache, settings, router |
| `panels.js` | the five panels: numbers · horizon · domains · machine · brain |
| `app.css` | the frame (R70.99) and the 12-column square grid (R70.100) |
| `tokens.css` | **a vendored copy** of HT's STEALTH seed-A tokens. Do not edit — see its header |
| `sw.js` | service worker: shell offline, API never silently cached |
| `tests/goldens.js` | `node tests/goldens.js` — loader and panel goldens, no network |

## Three outcomes, and no fourth

The loader renders **a board**, **a cache with its age**, or **a named error**. Never a blank page,
and never a spinner that lies. An unknown `schema` major is refused loudly: a newer board rendered
by an older app would show numbers whose meaning had moved.
