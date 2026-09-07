/* ==========================================================================
   BEV — the panels.  Loaded after app.js; every renderer reads S.board and
   writes into one panel body.  Tokens only (R-THEME).  No panel explains
   itself in prose (R-NOFLUFF): the numbers and their sources are the caption.
   ========================================================================== */
'use strict';

/* ---------------------------------------------------------------- helpers */

function tbl(host, cols) {
  var wrap = el('div', 'scroll');
  var t = el('table');
  var thead = el('thead'), tr = el('tr');
  cols.forEach(function (c) { tr.appendChild(el('th', null, c)); });
  thead.appendChild(tr);
  t.appendChild(thead);
  var tb = el('tbody');
  t.appendChild(tb);
  wrap.appendChild(t);
  host.appendChild(wrap);
  return tb;
}

function row(tb, cells) {
  var tr = el('tr');
  cells.forEach(function (c) {
    var td = el('td');
    if (c === null || c === undefined || c === '') td.appendChild(dash(null));
    else if (typeof c === 'object' && c.nodeType !== undefined) td.appendChild(c);
    else if (typeof c === 'object') td.appendChild(c);
    else td.textContent = String(c);
    tr.appendChild(td);
  });
  tb.appendChild(tr);
  return tr;
}

function link(href, label) {
  if (!href) return dash(null);
  var a = el('a', null, label || href);
  a.href = href;
  a.target = '_blank';
  a.rel = 'noopener';
  return a;
}

/* An address is stored; a link is DERIVED.  Links rot when tools change;
   addresses survive because they are only ever system plus object id
   (life-taxonomy/resolve.py, same rule).  Anything this cannot resolve renders
   as the raw address rather than as a broken hyperlink. */
function addrLink(address, label) {
  if (!address) return dash(null);
  var a = String(address);
  var href = null;
  if (/^https?:\/\//.test(a)) href = a;
  else if (a.indexOf('drive://') === 0) href = 'https://drive.google.com/file/d/' + a.slice(8).split('#')[0] + '/view';
  else if (a.indexOf('cu://') === 0) href = 'https://app.clickup.com/t/' + a.slice(5);
  else if (a.indexOf('gmail://') === 0) href = 'https://mail.google.com/mail/u/0/#search/' + encodeURIComponent(a.slice(8));
  else if (a.indexOf('life-taxonomy/') === 0 || a.indexOf('registers/') === 0)
    href = 'https://github.com/' + get(K.repo, DEFAULTS.repo).split('/')[0] + '/life-taxonomy/blob/main/'
      + a.replace(/^life-taxonomy\//, '').split('#')[0];
  else if (a.indexOf('master-brain/') === 0)
    href = 'https://github.com/' + get(K.repo, DEFAULTS.repo).split('/')[0] + '/master-brain/blob/main/'
      + a.replace(/^master-brain\//, '').split('#')[0];
  if (!href) { var s = el('span', 'mono'); s.textContent = label || a; return s; }
  return link(href, label || a);
}

/* ================================================================ S3 · THE TWO NUMBERS */

/* SCORE must rise.  LOAD-BEARING must fall.  A is the target and the page says
   so: D is HT's to move and J is reported and never attacked.  Both forms of
   the score print, because the percentage FALLS as the census adds functions
   and a number that drops when the system improves teaches people to stop
   reading it. */
function renderNumbers() {
  var B = S.board, n = B.numbers;
  var h = clear(body('p-numbers'));

  var a = el('div');
  a.appendChild(el('div', 'lbl', 'SCORE — tests passed, absolute, only goes up'));
  var v = el('div', 'num good');
  v.textContent = em(n.score.value);
  a.appendChild(v);
  var pct = el('div', 'sub');
  pct.textContent = em(n.score.pct, '%') + (n.score.provisional ? ' PROVISIONAL' : '')
    + '  ·  denominator ' + em(n.score.denominator)
    + (n.score.provisional ? ' moves until the census closes (Rock 1)' : '');
  a.appendChild(pct);
  if (srcLine(n.score.source)) a.appendChild(srcLine(n.score.source));
  h.appendChild(a);

  var b = el('div');
  b.style.marginTop = '16px';
  b.appendChild(el('div', 'lbl', 'LOAD-BEARING — must fall'));
  var lv = el('div', 'num bad');
  lv.textContent = em(n.load_bearing.total);
  b.appendChild(lv);
  h.appendChild(b);

  var split = el('dl', 'kv');
  [['A automatable', n.load_bearing.A, 'THE TARGET — A to zero', 'bad'],
   ['D discipline', n.load_bearing.D, "HT's to move — adherence, never attacked here", 'dim'],
   ['J judgment', n.load_bearing.J, 'RELATIONAL — reported, never attacked', 'dim']
  ].forEach(function (r) {
    split.appendChild(el('dt', r[3], r[0]));
    var dd = el('dd');
    dd.appendChild(el('span', 'mono', em(r[1])));
    dd.appendChild(el('span', 'sub', '   ' + r[2]));
    split.appendChild(dd);
  });
  h.appendChild(split);
  if (srcLine(n.load_bearing.source)) h.appendChild(srcLine(n.load_bearing.source));

  var f = el('div', 'sub');
  f.style.marginTop = '12px';
  f.textContent = em(n.functions.measured) + ' measured · ' + em(n.functions.addressable)
    + ' addressable · ' + em(n.functions.answerable) + ' answerable · '
    + em(n.functions.executable) + ' executable  (of ' + em(n.functions.total) + ')';
  h.appendChild(f);

  renderTrend();
  renderDelta();
}

/* Thirty builds of REAL movement (R70.114).  The history file gains a line only
   when the board's content actually changed, so thirty points here are thirty
   changes, not thirty runs of the hook. */
function renderTrend() {
  var B = S.board, hist = (B.numbers.history || []).slice(-30);
  var h = clear(body('p-trend'));
  if (!hist.length) { h.appendChild(el('div', 'sub', '— no history yet')); return; }

  function series(key, colour, label, host) {
    var vals = hist.map(function (r) { return r[key]; }).filter(function (x) { return typeof x === 'number'; });
    var wrap = el('div');
    wrap.appendChild(el('div', 'lbl', label + '  ' + (vals.length ? vals[vals.length - 1] : '—')
      + (vals.length > 1 ? '   (' + (vals[vals.length - 1] - vals[0] >= 0 ? '+' : '')
        + (vals[vals.length - 1] - vals[0]) + ' over ' + vals.length + ' builds)' : '')));
    var W = 600, H = 34, P = 2;
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('class', 'spark');
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var span = (hi - lo) || 1;
    var x = function (i) { return vals.length === 1 ? W / 2 : P + i * (W - 2 * P) / (vals.length - 1); };
    var y = function (val) { return H - P - ((val - lo) / span) * (H - 2 * P); };
    var pl = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    pl.setAttribute('fill', 'none');
    pl.setAttribute('stroke', colour);
    pl.setAttribute('stroke-width', '1.5');
    pl.setAttribute('vector-effect', 'non-scaling-stroke');
    pl.setAttribute('points', vals.map(function (v, i) { return x(i) + ',' + y(v); }).join(' '));
    svg.appendChild(pl);
    vals.forEach(function (v, i) {
      var c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', x(i)); c.setAttribute('cy', y(v)); c.setAttribute('r', '2');
      c.setAttribute('fill', colour);
      var ti = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      ti.textContent = (hist[i] && hist[i].generated ? hist[i].generated + '  ' : '') + label + ' ' + v;
      c.appendChild(ti);
      svg.appendChild(c);
    });
    wrap.appendChild(svg);
    host.appendChild(wrap);
  }

  series('score', 'var(--line-completion)', 'SCORE', h);
  series('A', 'var(--red-bright)', 'LOAD-BEARING A', h);
  h.appendChild(el('div', 'src', 'source: life-taxonomy/state/score_history.jsonl · last '
    + hist.length + ' real changes'));
}

/* THE STATE DELTA STRIP — what changed since the last build, BY RECORD KEY.
   A line diff cannot tell an added record from a changed field, so this never
   shows one. */
function renderDelta() {
  var d = S.board.delta || {}, h = clear(body('p-delta'));
  var head = el('div', 'sub');
  head.textContent = em(d.count, ' record(s) changed') + '  ·  ' + em(d.basis);
  h.appendChild(head);
  if (!d.count) return;
  var tb = tbl(h, ['change', 'record', 'from', 'to']);
  ['changed', 'added', 'removed'].forEach(function (kind) {
    (d[kind] || []).slice(0, 40).forEach(function (r) {
      row(tb, [kind, r.key, kind === 'added' ? null : r.from, kind === 'removed' ? null : r.to]);
    });
  });
}
