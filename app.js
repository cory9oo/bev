/* ==========================================================================
   BEV — the container.  WIRE BEV-VIEW-1 S2 (scaffold + loader + settings).

   THE APP INDEXES; THE CONTAINERS HOLD.  Every row links out to whatever holds
   the record — HT, SlowBooks, ClickUp, Drive, a Brain shelf, a register row —
   and copies none of it.  One artifact (`state/board.json` on the private
   life-taxonomy repo), two readers: Cory here, Claude straight off the file.

   THE TOKEN LIVES IN localStorage ON EACH DEVICE, AND THAT IS A REAL TRADE
   (R70.109).  It is a credential on a phone.  It is scoped to contents:read on
   `life-taxonomy` ALONE, so the worst case is disclosure of a private repo Cory
   already owns — no write, no other repo, no account.  The alternatives were
   worse: a service key on the laptop, or Pages on the private repo (still
   public).  THE APP CANNOT VERIFY A TOKEN'S SCOPE, so Settings states the exact
   scope in words next to the field rather than pretending to check it.  If BEV
   ever goes multi-user this route is replaced by HT's Supabase auth — named
   here, not built.
   ========================================================================== */
'use strict';

var K = {
  token:    'bev.token',
  repo:     'bev.repo',
  path:     'bev.path',
  ref:      'bev.ref',
  refresh:  'bev.refresh',
  sources:  'bev.sources',
  cache:    'bev.cache',
  cachedAt: 'bev.cachedAt'
};

var DEFAULTS = { repo: 'cory9oo/life-taxonomy', path: 'state/board.json', ref: 'main', refresh: '15' };

function get(k, d) { try { var v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } }
function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
function del(k)    { try { localStorage.removeItem(k); } catch (e) {} }

var S = {
  board: null,
  fetchedAt: null,
  offline: false,
  error: null,
  view: 'board',
  domain: null,
  timer: null
};

/* ------------------------------------------------------------------ util */

function el(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}
function q(sel) { return document.querySelector(sel); }
function body(id) { return document.querySelector('#' + id + ' .body'); }
function clear(n) { while (n && n.firstChild) n.removeChild(n.firstChild); return n; }

/* AN UNMEASURED VALUE RENDERS AN EM DASH, NEVER A ZERO (R70.106).  `0` and
   "nobody measured it" are different facts and the board exists to keep them
   apart. */
function em(v, suffix) {
  if (v === null || v === undefined || v === '') return '—';
  return String(v) + (suffix || '');
}
function dash(v, suffix) {
  var s = el('span', v === null || v === undefined || v === '' ? 'none' : null);
  s.textContent = em(v, suffix);
  return s;
}

/* THE ONE RAMP (R70.92): 0-24 · 25-49 · 50-74 · 75-89 · 90-100.  Anything
   unmeasured gets no ramp class at all — an unmeasured value must not read as
   a bad one. */
function rampClass(pct) {
  if (pct === null || pct === undefined) return 'none';
  if (pct < 25) return 'ramp0';
  if (pct < 50) return 'ramp1';
  if (pct < 75) return 'ramp2';
  if (pct < 90) return 'ramp3';
  return 'ramp4';
}
function rampVar(pct) {
  if (pct === null || pct === undefined) return 'var(--surface)';
  if (pct < 25) return 'var(--ramp-0)';
  if (pct < 50) return 'var(--ramp-1)';
  if (pct < 75) return 'var(--ramp-2)';
  if (pct < 90) return 'var(--ramp-3)';
  return 'var(--ramp-4)';
}

function ago(iso) {
  if (!iso) return null;
  var t = Date.parse(iso);
  if (isNaN(t)) return null;
  var s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return Math.round(s) + 's';
  if (s < 5400) return Math.round(s / 60) + 'm';
  if (s < 172800) return Math.round(s / 3600) + 'h';
  return Math.round(s / 86400) + 'd';
}

function srcLine(src) {
  if (!src) return null;
  var n = el('div', 'src');
  n.textContent = 'source: ' + src.file + (src.row ? ' · ' + src.row : '');
  return n;
}

/* ---------------------------------------------------------------- loader */

/* THE LOADER: contents API -> board.json -> cache.  Three named outcomes and
   no fourth: a board, a cache with its age, or a NAMED error.  Never a blank
   page, and never a spinner that lies. */
function fetchBoard(force) {
  var token = get(K.token, '');
  if (!token) { S.error = { kind: 'NO_TOKEN' }; render(); return Promise.resolve(); }

  var repo = get(K.repo, DEFAULTS.repo),
      path = get(K.path, DEFAULTS.path),
      ref  = get(K.ref, DEFAULTS.ref);
  var url = 'https://api.github.com/repos/' + repo + '/contents/' + path + '?ref=' + encodeURIComponent(ref);

  q('#age').textContent = 'fetching…';

  return fetch(url, {
    cache: force ? 'reload' : 'default',
    headers: {
      /* raw media type: the JSON representation caps at 1 MB, which is exactly
         the ceiling build_board.py's 900 KB size gate is defending. */
      'Accept': 'application/vnd.github.raw',
      'Authorization': 'Bearer ' + token,
      'X-GitHub-Api-Version': '2022-11-28'
    }
  }).then(function (r) {
    if (r.status === 401 || r.status === 403) {
      return r.text().then(function (t) {
        throw { kind: 'AUTH', status: r.status, detail: t.slice(0, 400) };
      });
    }
    if (r.status === 404) throw { kind: 'NOT_FOUND', status: 404, detail: repo + '/' + path + '@' + ref };
    if (!r.ok) {
      return r.text().then(function (t) {
        throw { kind: 'HTTP', status: r.status, detail: t.slice(0, 400) };
      });
    }
    return r.text();
  }).then(function (txt) {
    var b;
    try { b = JSON.parse(txt); }
    catch (e) {
      /* An oversized file comes back as a JSON error object or as truncated
         content, not as a board.  Name it; never render an empty board. */
      throw { kind: 'PARSE', detail: txt.slice(0, 300) };
    }
    if (b && b.errors) throw { kind: 'TOO_LARGE', detail: JSON.stringify(b.errors).slice(0, 300) };
    return acceptBoard(b, txt);
  }).catch(function (e) {
    if (e && e.kind) S.error = e;
    else S.error = { kind: 'NETWORK', detail: String(e && e.message || e) };
    loadCache();
    render();
  });
}

/* THE APP REFUSES AN UNKNOWN MAJOR AND SAYS SO.  A newer board rendered by an
   older app is worse than no board: it would show numbers whose meaning moved. */
function acceptBoard(b, raw) {
  if (!b || typeof b.schema !== 'number') { S.error = { kind: 'NO_SCHEMA' }; loadCache(); render(); return; }
  if (b.schema !== 1) {
    S.error = { kind: 'SCHEMA', detail: 'board.json is schema v' + b.schema + '; this app reads v1 only.' };
    loadCache(); render(); return;
  }
  S.board = b;
  S.error = null;
  S.offline = false;
  S.fetchedAt = new Date().toISOString();
  try { localStorage.setItem(K.cache, raw); localStorage.setItem(K.cachedAt, S.fetchedAt); } catch (e) {}
  render();
}

function loadCache() {
  if (S.board) return;
  var raw = get(K.cache, null);
  if (!raw) return;
  try {
    var b = JSON.parse(raw);
    if (b && b.schema === 1) { S.board = b; S.offline = true; S.fetchedAt = get(K.cachedAt, null); }
  } catch (e) {}
}

function scheduleRefresh() {
  if (S.timer) clearInterval(S.timer);
  var m = parseInt(get(K.refresh, DEFAULTS.refresh), 10);
  if (!m || m < 1) return;
  S.timer = setInterval(function () { fetchBoard(true); }, m * 60000);
}

/* ---------------------------------------------------------------- header */

function renderAge() {
  var n = q('#age');
  clear(n);
  n.className = 'age';
  if (!S.board) { n.textContent = S.error ? 'no board' : 'loading…'; return; }
  var gen = S.board.meta && S.board.meta.generated;
  var a = ago(gen);
  var parts = ['generated ' + (a ? a + ' ago' : em(gen))];
  if (S.fetchedAt) parts.push('fetched ' + em(ago(S.fetchedAt)) + ' ago');
  if (S.offline) parts.push('OFFLINE — cached');
  parts.push('build ' + em(S.board.meta && S.board.meta.build_id));
  n.textContent = parts.join('  ·  ');
  /* Stale is a colour, not a footnote: a day-old board on a phone at 6am is the
     case this whole panel exists for. */
  var t = Date.parse(gen);
  if (S.offline || (!isNaN(t) && (Date.now() - t) > 36 * 3600 * 1000)) n.className = 'age stale';
}

function renderBanner() {
  var n = clear(q('#banner'));
  if (!S.error) return;
  var e = S.error, box = el('div', 'err');
  var head = el('div'), b = el('b');
  var msg = {
    NO_TOKEN:  'NO TOKEN — open Settings and paste a fine-grained token.',
    AUTH:      'GITHUB REFUSED THE TOKEN (' + e.status + ') — it is missing, expired, or lacks Contents: Read on this repo.',
    NOT_FOUND: 'NOT FOUND — ' + e.detail + '. Check the repo, path and ref in Settings.',
    TOO_LARGE: 'BOARD TOO LARGE for the contents API. The named fix is to split catalog[] into state/board_catalog.json.',
    PARSE:     'THE RESPONSE WAS NOT A BOARD. Nothing is rendered from a body this app could not parse.',
    SCHEMA:    'UNKNOWN SCHEMA — ' + e.detail,
    NO_SCHEMA: 'THE FILE CARRIES NO schema FIELD — it is not a board.',
    HTTP:      'GITHUB RETURNED ' + e.status + '.',
    NETWORK:   'NETWORK UNREACHABLE — ' + em(e.detail)
  }[e.kind] || ('ERROR — ' + e.kind);
  b.textContent = msg;
  head.appendChild(b);
  box.appendChild(head);
  if (S.board) box.appendChild(el('div', 'sub', S.offline
    ? 'Showing the last cached board and its age. Nothing below is live.'
    : 'Showing the last board this session loaded.'));
  else if (e.kind !== 'NO_TOKEN') box.appendChild(el('div', 'sub', 'No cached board on this device.'));
  if (e.detail && e.kind !== 'NOT_FOUND') {
    var d = el('div', 'src'); d.textContent = e.detail; box.appendChild(d);
  }
  n.appendChild(box);
  if (e.kind === 'NO_TOKEN') show('settings');
}

/* ---------------------------------------------------------------- settings */

function renderSettings() {
  var n = clear(body('p-settings'));

  function field(label, key, dflt, type, help) {
    var l = el('label', 'field');
    l.appendChild(el('span', 'lbl', label));
    var i = document.createElement('input');
    i.type = type || 'text';
    i.value = get(key, dflt);
    i.addEventListener('change', function () {
      var v = i.value.trim();
      if (v) set(key, v); else del(key);
      if (key === K.refresh) scheduleRefresh();
    });
    l.appendChild(i);
    if (help) l.appendChild(el('div', 'sub', help));
    n.appendChild(l);
    return i;
  }

  var tok = field('GitHub token', K.token, '', 'password',
    'FINE-GRAINED, Contents: Read-only, repository life-taxonomy ONLY, 1 year. ' +
    'This app CANNOT verify a token\'s scope — it states the scope it needs and trusts you. ' +
    'The token is stored in this browser\'s localStorage on this device alone. It is never sent ' +
    'anywhere but api.github.com.');
  tok.placeholder = get(K.token, '') ? '•••••••• stored on this device' : 'github_pat_…';
  tok.value = '';
  tok.addEventListener('change', function () {
    var v = tok.value.trim();
    if (v) { set(K.token, v); tok.value = ''; tok.placeholder = '•••••••• stored on this device'; }
    fetchBoard(true);
  });

  field('Repository', K.repo, DEFAULTS.repo, 'text', 'owner/name. Private is expected.');
  field('Board path', K.path, DEFAULTS.path, 'text', 'The file build_board.py writes.');
  field('Ref', K.ref, DEFAULTS.ref, 'text', 'Branch or tag.');
  field('Refresh (minutes)', K.refresh, DEFAULTS.refresh, 'number', '0 disables the timer.');

  var sw = el('label', 'field');
  var cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = get(K.sources, '0') === '1';
  cb.addEventListener('change', function () {
    set(K.sources, cb.checked ? '1' : '0');
    document.body.classList.toggle('show-sources', cb.checked);
  });
  var sp = el('span', 'lbl', 'Show sources');
  sw.appendChild(sp); sw.appendChild(cb);
  sw.appendChild(el('div', 'sub', 'Print the file and row behind every number. A figure with no source does not render.'));
  n.appendChild(sw);

  var row = el('div');
  var b1 = el('button', 'act', 'REFRESH NOW');
  b1.addEventListener('click', function () { fetchBoard(true); });
  var b2 = el('button', 'act', 'FORGET TOKEN');
  b2.addEventListener('click', function () {
    del(K.token); S.board = null; S.error = { kind: 'NO_TOKEN' }; render();
  });
  var b3 = el('button', 'act', 'CLEAR CACHE');
  b3.addEventListener('click', function () { del(K.cache); del(K.cachedAt); fetchBoard(true); });
  row.appendChild(b1); row.appendChild(document.createTextNode(' '));
  row.appendChild(b2); row.appendChild(document.createTextNode(' '));
  row.appendChild(b3);
  n.appendChild(row);

  var a = clear(body('p-about'));
  var dl = el('dl', 'kv');
  var rows = [
    ['reads', get(K.repo, DEFAULTS.repo) + ' · ' + get(K.path, DEFAULTS.path)],
    ['schema', 'v1 only — an unknown major is refused, loudly'],
    ['cache', 'last good board in localStorage, shown with its age when offline'],
    ['writes', 'nothing. This app has no write path to anything.'],
    ['sources', S.board && S.board.meta ? (S.board.meta.sources || []).length + ' input files' : '—']
  ];
  rows.forEach(function (r) {
    dl.appendChild(el('dt', null, r[0]));
    dl.appendChild(el('dd', null, r[1]));
  });
  a.appendChild(dl);
  if (S.board && S.board.meta && S.board.meta.sources) {
    var t = el('div', 'scroll');
    var tb = el('table');
    var th = el('thead'); var tr = el('tr');
    ['file', 'rows', 'mtime'].forEach(function (h) { tr.appendChild(el('th', null, h)); });
    th.appendChild(tr); tb.appendChild(th);
    var bd = el('tbody');
    S.board.meta.sources.forEach(function (s) {
      var r = el('tr');
      r.appendChild(el('td', null, s.file));
      r.appendChild(el('td', null, em(s.count)));
      r.appendChild(el('td', null, em(s.mtime)));
      bd.appendChild(r);
    });
    tb.appendChild(bd); t.appendChild(tb); a.appendChild(t);
  }
}

/* ---------------------------------------------------------------- router */

var VIEWS = ['board', 'domains', 'machine', 'brain', 'settings'];

function show(v) {
  S.view = v;
  VIEWS.forEach(function (name) {
    var n = q('#view-' + name);
    if (n) n.classList.toggle('hidden', name !== v);
  });
  Array.prototype.forEach.call(document.querySelectorAll('#tabs button'), function (b) {
    b.setAttribute('aria-selected', b.dataset.view === v ? 'true' : 'false');
  });
}

function render() {
  document.body.classList.toggle('show-sources', get(K.sources, '0') === '1');
  renderAge();
  renderBanner();
  renderSettings();
  if (!S.board) return;
  if (typeof renderNumbers === 'function') renderNumbers();
  if (typeof renderHorizon === 'function') renderHorizon();
  if (typeof renderDomains === 'function') renderDomains();
  if (typeof renderMachine === 'function') renderMachine();
  if (typeof renderBrain === 'function') renderBrain();
}

/* ---------------------------------------------------------------- boot */

Array.prototype.forEach.call(document.querySelectorAll('#tabs button'), function (b) {
  b.addEventListener('click', function () { show(b.dataset.view); });
});

loadCache();
render();
fetchBoard(false);
scheduleRefresh();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('./sw.js').catch(function () {});
  });
}
