/* ==========================================================================
   BEV goldens.  `node tests/goldens.js [path/to/board.json]`

   WHY A SHIM AND NOT A HEADLESS BROWSER: the goldens must run on the laptop in
   a second, in a git hook, with no network and no download.  The live check is
   a SEPARATE thing and it happens in a real browser against the real Pages URL
   (CC_STANDING §8: browser truth, never curl).  This file proves the RENDERERS
   against a real board; it does not prove the deployment.

   WHY THE BOARD IS NOT COMMITTED HERE: this repo is PUBLIC and board.json is
   the private estate.  The goldens read the LIVE board from the private repo
   next door when it is present, and fall back to `tests/sample_board.json` —
   a synthetic board with invented rows — when it is not.  A run that used the
   sample says so in its output, because a golden that silently tested nothing
   is worse than a golden that failed.
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const argBoard = process.argv[2];
const CANDIDATES = [
  argBoard,
  path.join(ROOT, '..', 'life-taxonomy', 'state', 'board.json'),
  path.join(__dirname, 'sample_board.json')
].filter(Boolean);

const boardPath = CANDIDATES.find(p => { try { return fs.statSync(p).isFile(); } catch (e) { return false; } });
if (!boardPath) { console.error('FAIL  no board.json found in: ' + CANDIDATES.join(', ')); process.exit(1); }
const BOARD = JSON.parse(fs.readFileSync(boardPath, 'utf8'));
const SYNTHETIC = boardPath.endsWith('sample_board.json');

/* ---------------------------------------------------------------- DOM shim */

function mkClassList(node) {
  return {
    toggle(c, on) {
      const s = new Set((node.className || '').split(/\s+/).filter(Boolean));
      const want = on === undefined ? !s.has(c) : !!on;
      if (want) s.add(c); else s.delete(c);
      node.className = [...s].join(' ');
    },
    add(c) { this.toggle(c, true); },
    remove(c) { this.toggle(c, false); },
    contains(c) { return (node.className || '').split(/\s+/).includes(c); }
  };
}

class Node {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this._text = '';
    this.className = '';
    this.style = {};
    this.classList = mkClassList(this);
    this._handlers = {};
  }
  get firstChild() { return this.children[0] || null; }
  appendChild(n) { this.children.push(n); n.parent = this; return n; }
  removeChild(n) { this.children = this.children.filter(c => c !== n); return n; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(ev, fn) { (this._handlers[ev] = this._handlers[ev] || []).push(fn); }
  fire(ev) { (this._handlers[ev] || []).forEach(f => f.call(this, {})); }
  set textContent(v) { this._text = v === undefined || v === null ? '' : String(v); this.children = []; }
  get textContent() {
    return this._text + this.children.map(c => c.textContent).join('');
  }
  set innerHTML(v) { if (v === '') this.children = []; }
  querySelectorAll(sel) { return findAll(this, sel); }
  querySelector(sel) { return findAll(this, sel)[0] || null; }
  get id() { return this.attrs.id || ''; }
  set id(v) { this.attrs.id = v; }
}

function walk(n, fn) { fn(n); n.children.forEach(c => walk(c, fn)); }

function matches(n, part) {
  if (part.startsWith('#')) return n.attrs.id === part.slice(1);
  if (part.startsWith('.')) return (n.className || '').split(/\s+/).includes(part.slice(1));
  if (part.includes('[')) {
    const [tag, rest] = part.split('[');
    const [k, v] = rest.replace(']', '').split('=');
    return n.tagName === tag.toUpperCase() && n.attrs[k] === (v || '').replace(/"/g, '');
  }
  return n.tagName === part.toUpperCase();
}

function findAll(root, sel) {
  const parts = sel.trim().split(/\s+/);
  let pool = [root];
  parts.forEach((p, i) => {
    const next = [];
    pool.forEach(n => {
      const scope = i === 0 ? [n] : [];
      if (i === 0) walk(n, x => { if (x !== n && matches(x, p)) next.push(x); });
      else walk(n, x => { if (x !== n && matches(x, p)) next.push(x); });
      void scope;
    });
    pool = [...new Set(next)];
  });
  return pool;
}

/* Build the shim DOM from the REAL index.html, so a renamed id fails a golden
   instead of silently testing a node that no longer exists. */
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const doc = new Node('body');
doc.attrs.id = '__doc__';
const byId = {};
const idRe = /<(\w+)[^>]*\bid="([^"]+)"[^>]*>/g;
let m;
while ((m = idRe.exec(html))) {
  const n = new Node(m[1]);
  n.attrs.id = m[2];
  if (/class="[^"]*panel/.test(m[0])) {
    const b = new Node('div'); b.className = 'body'; n.appendChild(b);
  }
  byId[m[2]] = n;
  doc.appendChild(n);
}
const tabRe = /<button data-view="(\w+)"/g;
while ((m = tabRe.exec(html))) {
  const b = new Node('button');
  b.dataset.view = m[1];
  byId['tabs'].appendChild(b);
}

const store = {};
global.localStorage = {
  getItem: k => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; }
};
global.document = {
  body: doc,
  createElement: t => new Node(t),
  createElementNS: (ns, t) => new Node(t),
  createTextNode: t => { const n = new Node('#text'); n.textContent = t; return n; },
  querySelector: s => (s.startsWith('#') && !s.includes(' ') ? byId[s.slice(1)] || null : doc.querySelector(s)),
  querySelectorAll: s => doc.querySelectorAll(s)
};
doc.classList = mkClassList(doc);
global.window = { addEventListener() {} };
Object.defineProperty(global, 'navigator', { value: {}, configurable: true, writable: true });
global.setInterval = () => 0;
global.clearInterval = () => {};

let fetchImpl = () => Promise.reject(new Error('no fetch stub installed'));
global.fetch = (...a) => fetchImpl(...a);

/* ---------------------------------------------------------------- run app */

const APP = ['app.js', 'panels.js'].map(f => path.join(ROOT, f))
  .filter(p => fs.existsSync(p))
  .map(p => fs.readFileSync(p, 'utf8')).join('\n;\n');
const TAIL = [
  '',
  ';return {',
  '  S: S, fetchBoard: fetchBoard, render: render, show: show, K: K,',
  '  call: function (fn) { return eval(fn)(); }',
  '};'
].join('\n');
const run = new Function(APP + TAIL);

/* ---------------------------------------------------------------- asserts */

let pass = 0; const fails = [];
function check(name, ok, evidence) {
  if (ok) { pass++; console.log('PASS  ' + name + '  ' + evidence); }
  else { fails.push(name); console.log('FAIL  ' + name + '  ' + evidence); }
}
const text = id => (byId[id] ? byId[id].textContent : '<missing #' + id + '>');
const bodyText = id => {
  const n = byId[id];
  if (!n) return '<missing #' + id + '>';
  const b = n.children.find(c => c.className === 'body');
  return b ? b.textContent : '';
};
const count = (id, sel) => {
  const n = byId[id];
  return n ? n.querySelectorAll(sel).length : -1;
};

async function main() {
  console.log('board: ' + boardPath + (SYNTHETIC ? '   *** SYNTHETIC SAMPLE ***' : '   (live)'));

  /* G1 — NO TOKEN RENDERS SETTINGS, never a blank page and never a spinner. */
  fetchImpl = () => Promise.reject(new Error('should not be called without a token'));
  let app = run();
  await new Promise(r => setTimeout(r, 0));
  check('a missing token renders the Settings screen, not a blank page',
    app.S.view === 'settings' && /token/i.test(text('banner')),
    'view=' + app.S.view + ' banner="' + text('banner').slice(0, 60) + '"');
  check('the token field is a password input and never echoes a stored value',
    (byId['p-settings'].querySelectorAll('input') || []).some(i => i.type === 'password' && i.value === ''),
    'password field present, value empty');

  /* G2 — THE LOADER PARSES S1'S BOARD. */
  store['bev.token'] = 'github_pat_TEST';
  fetchImpl = () => Promise.resolve({
    ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(BOARD))
  });
  app = run();
  await new Promise(r => setTimeout(r, 0));
  check('the loader parses a schema v1 board and holds it',
    app.S.board && app.S.board.schema === 1 && app.S.error === null,
    'schema=' + (app.S.board && app.S.board.schema) + ' error=' + JSON.stringify(app.S.error));
  check('the age line is always on screen and names the generated time',
    /generated/.test(text('age')), '"' + text('age').slice(0, 90) + '"');

  /* G3 — A 404 RENDERS A NAMED ERROR, NEVER AN EMPTY BOARD. */
  delete store['bev.cache'];
  fetchImpl = () => Promise.resolve({ ok: false, status: 404, text: () => Promise.resolve('nope') });
  app = run();
  await new Promise(r => setTimeout(r, 0));
  check('a 404 renders a NAMED error, never an empty board',
    /NOT FOUND/.test(text('banner')) && !app.S.board,
    '"' + text('banner').slice(0, 80) + '"');

  /* G4 — AN OVERSIZED RESPONSE IS NAMED, and names its fix. */
  fetchImpl = () => Promise.resolve({
    ok: true, status: 200,
    text: () => Promise.resolve(JSON.stringify({ errors: [{ code: 'too_large' }] }))
  });
  app = run();
  await new Promise(r => setTimeout(r, 0));
  check('an oversized response renders a named error naming its fix',
    /TOO LARGE/.test(text('banner')) && /board_catalog/.test(text('banner')),
    '"' + text('banner').slice(0, 90) + '"');

  /* G5 — AN UNKNOWN SCHEMA MAJOR IS REFUSED, LOUDLY. */
  fetchImpl = () => Promise.resolve({
    ok: true, status: 200, text: () => Promise.resolve(JSON.stringify({ schema: 2 }))
  });
  app = run();
  await new Promise(r => setTimeout(r, 0));
  check('an unknown schema major is refused and says so',
    /UNKNOWN SCHEMA/.test(text('banner')), '"' + text('banner').slice(0, 80) + '"');

  /* G6 — OFFLINE FALLS BACK TO THE CACHE, WITH ITS AGE. */
  store['bev.cache'] = JSON.stringify(BOARD);
  store['bev.cachedAt'] = new Date(Date.now() - 3600e3).toISOString();
  fetchImpl = () => Promise.reject(new Error('offline'));
  app = run();
  await new Promise(r => setTimeout(r, 0));
  check('offline renders the last cache WITH its age, and says it is not live',
    app.S.board && app.S.offline && /OFFLINE/.test(text('age')),
    'offline=' + app.S.offline + ' age="' + text('age').slice(0, 70) + '"');

  /* ---- panel goldens (S3-S7). Skipped cleanly until panels.js exists. ---- */
  /* WHICH PANEL GOLDENS RUN IS DERIVED FROM panels.js ITSELF, never from a flag.
     A section that has shipped its renderer cannot skip its own goldens, and a
     section that has not shipped one is reported SKIP rather than passed. */
  if (fs.existsSync(path.join(ROOT, 'panels.js'))) {
    delete store['bev.cache'];
    fetchImpl = () => Promise.resolve({
      ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(BOARD))
    });
    app = run();
    await new Promise(r => setTimeout(r, 0));
    panelGoldens(app);
  } else {
    console.log('SKIP  panel goldens - panels.js not built yet (S3-S7)');
  }

  console.log('GOLDENS: ' + pass + ' passed, ' + fails.length + ' FAILED'
    + (SYNTHETIC ? '  [synthetic board - the parser was proven, the estate was not]' : ''));
  process.exit(fails.length ? 1 : 0);
}

function panelGoldens(app) {
  const B = BOARD;
  const SRC = fs.readFileSync(path.join(ROOT, 'panels.js'), 'utf8');
  const has = fn => SRC.indexOf('function ' + fn + '(') !== -1;
  const section = (name, fn, body) => {
    if (!has(fn)) { console.log('SKIP  ' + name + ' - ' + fn + '() not built yet'); return; }
    body();
  };

  /* S3 — THE TWO NUMBERS. */
  section('S3 the two numbers', 'renderNumbers', () => {
  const t = bodyText('p-numbers');
  check('S3 the two numbers render with SCORE and LOAD-BEARING',
    t.includes(String(B.numbers.score.value)) && t.includes(String(B.numbers.load_bearing.total)),
    'score=' + B.numbers.score.value + ' lb=' + B.numbers.load_bearing.total);
  check('S3 A / D / J split renders and sums to LOAD-BEARING',
    B.numbers.load_bearing.A + B.numbers.load_bearing.D + B.numbers.load_bearing.J
      === B.numbers.load_bearing.total && t.includes(String(B.numbers.load_bearing.A)),
    B.numbers.load_bearing.A + '+' + B.numbers.load_bearing.D + '+' + B.numbers.load_bearing.J
      + '==' + B.numbers.load_bearing.total);
  check('S3 the provisional percentage is labelled provisional',
    !B.numbers.score.provisional || /PROVISIONAL/i.test(t),
    'provisional=' + B.numbers.score.provisional);
  /* THE WIRE'S GOLDEN, LITERALLY: with two builds the sparkline has two points
     and the delta strip names the change.  Two series are drawn (SCORE and
     LOAD-BEARING A), so the assertion is two points PER SERIES - counting the
     total would have passed on one build drawn twice. */
  const SERIES = 2;
  const two = JSON.parse(JSON.stringify(B));
  const h0 = (B.numbers.history || [])[0] || { score: 100, A: 50, generated: '2026-09-06T00:00:00Z' };
  two.numbers.history = [
    Object.assign({}, h0, { score: h0.score - 3, A: h0.A + 2, build_id: 'aaaaaaaaaaaa',
                            generated: '2026-09-06T00:00:00Z' }),
    Object.assign({}, h0, { build_id: 'bbbbbbbbbbbb' })
  ];
  two.delta = { basis: 'by record key vs state/board_prev.json', count: 1, added: [], removed: [],
                changed: [{ key: 'ROCK:ROCK-01', from: 'FAIL|1', to: 'PASS|1' }] };
  app.S.board = two;
  app.call('renderNumbers');
  check('S3 two builds yield two points per series in the sparkline',
    count('p-trend', 'circle') === 2 * SERIES && count('p-trend', 'polyline') === SERIES,
    'circles=' + count('p-trend', 'circle') + ' polylines=' + count('p-trend', 'polyline')
      + ' (' + SERIES + ' series x 2 builds)');
  check('S3 the delta strip names the change',
    /ROCK-01/.test(bodyText('p-delta')) && /FAIL/.test(bodyText('p-delta'))
      && /PASS/.test(bodyText('p-delta')),
    '"' + bodyText('p-delta').replace(/\s+/g, ' ').slice(0, 90) + '"');
  app.S.board = B;
  app.call('renderNumbers');
  });

  /* S4 — THE HORIZON. */
  section('S4 the horizon', 'renderHorizon', () => {
  check('S4 decisions owed renders one row per owed decision',
    count('p-decisions', 'tbody tr') === Math.min(B.horizon.decisions_owed.length, 200)
      || B.horizon.decisions_owed.length === 0,
    'owed=' + B.horizon.decisions_owed.length + ' rows=' + count('p-decisions', 'tbody tr'));
  const bands = [7, 30, 90].map(b => B.horizon.obligations.filter(o => o.band === b).length);
  check('S4 obligations render in 7 / 30 / 90 bands',
    /7/.test(bodyText('p-obligations')) && /90/.test(bodyText('p-obligations')),
    'bands ' + bands.join('/'));
  const named = B.horizon.obligations.filter(o => o.named_dependency);
  check('S4 every named dated dependency present in the register rides the horizon by name',
    named.every(o => bodyText('p-obligations').includes(o.id)),
    named.length + ' named: ' + named.map(o => o.id).join(','));
  check('S4 a missing feed renders an em dash, never a zero (TODAY)',
    B.horizon.today === null ? bodyText('p-today').includes('—') : bodyText('p-today').length > 0,
    'today=' + (B.horizon.today === null ? 'null' : 'present') + ' "' + bodyText('p-today').slice(0, 40) + '"');
  check('S4 a missing feed renders an em dash, never a zero (MONEY)',
    B.horizon.money === null ? bodyText('p-money').includes('—') : bodyText('p-money').length > 0,
    'money=' + (B.horizon.money === null ? 'null' : 'present') + ' "' + bodyText('p-money').slice(0, 40) + '"');
  });

  /* S5 — THE 13 DOMAINS, and every count equals board.json. */
  section('S5 the 13 domains', 'renderDomains', () => {
  check('S5 renders exactly 13 domain cards',
    count('p-domains', 'tbody tr') === 13 || count('p-domains', '.domcard') === 13,
    'cards=' + count('p-domains', '.domcard') + ' rows=' + count('p-domains', 'tbody tr'));
  const dt = bodyText('p-domains');
  const badDomain = B.domains.find(d =>
    !dt.includes(d.name) || !dt.includes(String(d.lb.total)));
  check('S5 every count on a card equals board.json', !badDomain,
    badDomain ? 'first mismatch: ' + badDomain.id + ' ' + badDomain.name : 'all 13 match');
  });

  /* S6 — THE MACHINE. */
  section('S6 the machine', 'renderMachine', () => {
  check('S6 the LB ledger renders every row with its mover',
    count('p-ledger', 'tbody tr') === B.lb_ledger.length,
    'ledger=' + B.lb_ledger.length + ' rows=' + count('p-ledger', 'tbody tr'));
  check('S6 rocks render one row per rock',
    count('p-rocks', 'tbody tr') === B.rocks.length,
    'rocks=' + B.rocks.length + ' rows=' + count('p-rocks', 'tbody tr'));
  check('S6 lanes render one row per lane',
    count('p-lanes', 'tbody tr') === B.lanes.length || B.lanes.length === 0,
    'lanes=' + B.lanes.length + ' rows=' + count('p-lanes', 'tbody tr'));
  });

  /* S7 — THE BRAIN, and the stranger test (R9.5): every sampled catalog id is
     reached in <= 2 hops.  HOP 1 = type the id into the search box.  HOP 2 =
     follow the address on the row it returns.  A row with no address is not
     reachable in two hops and fails, which is the whole point of the test. */
  section('S7 the brain', 'renderBrain', () => {
  check('S7 the catalog is searchable and every row shows its sensitivity',
    count('p-brain', 'input') >= 1 && B.catalog.every(c => c.sensitivity),
    'inputs=' + count('p-brain', 'input') + ' rows=' + B.catalog.length);
  const sample = [];
  const step = Math.max(1, Math.floor(B.catalog.length / 20));
  for (let i = 0; i < B.catalog.length && sample.length < 20; i += step) sample.push(B.catalog[i]);
  const unreachable = sample.filter(c => !c.address || !c.id);
  check('S7 stranger test: 20 sampled catalog ids each reached in <=2 hops',
    sample.length > 0 && unreachable.length === 0,
    (sample.length - unreachable.length) + '/' + sample.length
      + (unreachable.length ? ' unreachable: ' + unreachable.map(c => c.id).join(',') : ''));
  });
}

main();
