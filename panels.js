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
  /* THE CAPTION IS CONDITIONAL.  It read "denominator moves until the census
     closes" unconditionally, so the moment ROCK-01 passed the page went on saying
     it about a census that had closed.  A caption that outlives its condition is a
     lie the page tells every day. */
  pct.textContent = n.score.provisional
    ? em(n.score.pct, '%') + ' PROVISIONAL  ·  denominator ' + em(n.score.denominator)
      + ' moves until the census closes (Rock 1)'
    : em(n.score.pct, '%') + '  ·  denominator ' + em(n.score.denominator)
      + '  ·  ROCK-01 census CLOSED — no longer provisional';
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

/* ================================================================ S4 · THE HORIZON */

/* DECISIONS OWED — ONE INBOX ACROSS ALL FOUR LANES.  Each row carries the
   question, the PROPOSAL and the DEFAULT IF SILENT, which lane it came from, and
   a tap through to the receipt line that raised it.

   Rows parsed from the old free-text `FOR CORY` lines carry `parsed: false` and
   render as `unparsed` rather than being dropped.  A DECISION THE BOARD LOSES IS
   WORSE THAN ONE IT RENDERS UNTIDILY. */
function renderHorizon() {
  var B = S.board, H = B.horizon;

  var h = clear(body('p-decisions'));
  var owed = H.decisions_owed || [];
  var un = owed.filter(function (d) { return d.parsed === false; }).length;
  h.appendChild(el('div', 'sub', owed.length + ' owed'
    + (un ? '  ·  ' + un + ' unparsed, shown rather than dropped' : '')));
  var tb = tbl(h, ['lane', 'id', 'question', 'proposal', 'if silent', 'where']);
  owed.slice(0, 200).forEach(function (d) {
    var where = d.link ? addrLink(d.link, d.source && d.source.file)
                       : (d.source ? addrLink(d.source.file) : dash(null));
    var idCell = d.parsed === false ? el('span', 'pill', 'unparsed') : d.id;
    row(tb, [d.lane, idCell, d.question, d.proposal, d.default_if_silent, where]);
  });
  if (!owed.length) row(tb, ['—', '—', 'nothing owed', '—', '—', '—']);

  /* OBLIGATIONS 7 / 30 / 90, ramped by days left.  THE DATED DEPENDENCIES RIDE
     BY NAME: a row the board named is a row a rename cannot lose. */
  var o = clear(body('p-obligations'));
  var obl = H.obligations || [];
  var named = obl.filter(function (x) { return x.named_dependency; });
  if (named.length) {
    var nb = el('div');
    nb.appendChild(el('div', 'lbl', 'dated dependencies'));
    named.forEach(function (x) {
      var line = el('div', 'sub');
      line.appendChild(el('span', 'mono', x.id + '  '));
      line.appendChild(el('span', daysClass(x.days_left), em(x.days_left, 'd') + '  '));
      line.appendChild(document.createTextNode(x.named_dependency));
      nb.appendChild(line);
    });
    o.appendChild(nb);
  }
  /* THE BANDS GROUP THE ROWS; THEY DO NOT FILTER THEM.  A first cut printed only
     the three open bands and the board lost ten dated obligations — Rock 22's
     probe counts DATED rows that REACH the board and it was right to fail.  A
     closed obligation with a date is history the horizon still shows; it is
     grouped apart, never dropped. */
  [[7, 'within 7 days'], [30, 'within 30 days'], [90, 'within 90 days'],
   [null, 'open, beyond 90 days or undated'], ['closed', 'dated, no longer open']
  ].forEach(function (g) {
    var rows = g[0] === 'closed'
      ? obl.filter(function (x) { return !x.open; })
      : obl.filter(function (x) { return x.open && x.band === g[0]; });
    var head = el('div', 'lbl', g[1] + ' — ' + rows.length);
    head.style.marginTop = '12px';
    o.appendChild(head);
    var t = tbl(o, ['id', 'due', 'days', 'subject', 'counterparty', 'amount']);
    rows.forEach(function (x) {
      var d = el('span', x.open ? daysClass(x.days_left) : 'none',
                 x.open ? em(x.days_left, 'd') : x.status);
      row(t, [x.id, x.due, d, x.subject, x.counterparty, x.amount_usd]);
    });
    if (!rows.length) row(t, ['—', '—', '—', 'none in this band', '—', '—']);
  });
  o.appendChild(el('div', 'src', obl.length + ' obligation row(s), none filtered out'
    + '  ·  source: life-taxonomy/registers/obligations.csv + _reconcile/OBLIGATIONS_HORIZON.md'));

  /* TODAY (HT) and MONEY (SB) render an em dash until their feeds exist.  Not a
     zero.  Not a NaN.  Not a hidden panel: a panel that disappears when it has
     no data teaches its reader that the number is fine. */
  feedPanel('p-today', H.today, [
    ['completion', function (t) { return t.completion === null ? null : Math.round(t.completion * 100) + '%'; }],
    ['rating', function (t) { return t.rating; }],
    ['streak', function (t) { return t.streak === null ? null : t.streak + 'd'; }],
    ['standards', function (t) { return t.standards; }]
  ], 'HT feed — _reconcile/ht_feed/adherence.json (R70.47)');

  /* COMMITTED TIME (S4). The unblocked count is the number that matters and it is
     rendered in the bad token: a dated promise with nothing on a calendar behind
     it is an earlier, quieter failure than a missed deadline. */
  var ct = H.committed_time;
  var cth = clear(body('p-committed'));
  if (!ct) {
    cth.appendChild(el('div', 'num none', '—'));
    cth.appendChild(el('div', 'sub', 'not measured — the time ledger has not run'));
    cth.appendChild(el('div', 'src', 'life-taxonomy/state/committed_time.json (tools/time_ledger.py)'));
  } else {
    var n = ct.unblocked_obligations.length;
    var hd = el('div');
    hd.appendChild(el('span', 'num sm ' + (n ? 'bad' : 'good'), String(n)));
    hd.appendChild(el('span', 'sub', '  dated obligation(s) with NO time behind them'));
    cth.appendChild(hd);
    cth.appendChild(el('div', 'sub', ct.next_7.length + ' committed in 7d · '
      + ct.next_30.length + ' in 30d' + (ct.mode === 'DRY' ? '  ·  DRY (no token)' : '')));
    var ctt = tbl(cth, ['id', 'due', 'what']);
    ct.unblocked_obligations.slice(0, 30).forEach(function (u) {
      row(ctt, [u.id, u.due, u.subject]);
    });
    if (!n) row(ctt, ['—', '—', 'every dated obligation has time behind it']);
    if (ct.source) cth.appendChild(srcLine(ct.source));
  }

  feedPanel('p-money', H.money, [
    ['book cash', function (m) { return m.book_cash; }],
    ['months reserve', function (m) { return m.months_reserve; }],
    ['gaps', function (m) { return m.gap_count; }]
  ], 'SB feed — _reconcile/sb_feed/money.json');

  /* S10 · ENVIRONMENT.  A NUMBER WITHOUT A SOURCE DOES NOT RENDER, and the fetch
     date rides every value: a rate presented as current when it is three weeks old
     is worse than no rate. */
  var env = B.environment;
  var eh = clear(body('p-env'));
  if (!env || !(env.indicators || []).length) {
    eh.appendChild(el('div', 'num none', '—'));
    eh.appendChild(el('div', 'sub', env ? 'the scan ran and fetched nothing — see the log'
                                        : 'not measured — env_scan.py has not run'));
    (env && env.log || []).forEach(function (l) { eh.appendChild(el('div', 'src', l)); });
  } else {
    var et = tbl(eh, ['indicator', 'value', 'as of', 'why it matters', 'source']);
    env.indicators.forEach(function (x) {
      row(et, [x.key, x.value + (x.unit === 'percent' ? '%' : ''), x.as_of, x.why_it_matters,
               link(x.url, 'FRED')]);
    });
    (env.unavailable || []).forEach(function (u) {
      row(et, [u.key, el('span', 'none', '—'), '—', u.reason, u.source]);
    });
    eh.appendChild(el('div', 'src', 'fetched ' + em(env.fetched_at)
      + '  ·  free sources only, no key, no login, no stored credential'));
  }

  /* S11 · SIMULATE-LITE.  Dates and dollars only, every input traced to a register
     row, and a constant that is NOT in a register is NAMED rather than computed. */
  var sc = B.scenarios;
  var sh = clear(body('p-scenarios'));
  if (!sc) {
    sh.appendChild(el('div', 'num none', '—'));
    sh.appendChild(el('div', 'sub', 'not measured — simulate.py has not run'));
  } else {
    var hd2 = el('div');
    hd2.appendChild(el('span', 'pill crit', sc.label));
    hd2.appendChild(el('span', 'sub', '  ' + sc.subject));
    sh.appendChild(hd2);
    var st2 = tbl(sh, ['extend', 'new maturity', 'days out', 'payments', 'ext fee (prior rate)',
                       'total SOURCED', 'carry']);
    (sc.scenarios || []).forEach(function (x) {
      row(st2, ['+' + x.months + ' mo', x.new_maturity, x.days_from_today + 'd',
                x.payments_consumed, x.extension_fee_at_prior_rate, x.total_sourced_cost,
                el('span', 'none', 'NOT COMPUTED')]);
    });
    (sc.missing || []).forEach(function (m) {
      var w = el('div', 'note warn');
      w.appendChild(el('div', 'lbl', 'NOT COMPUTED — ' + m.value));
      w.appendChild(el('div', 'sub', m.why));
      w.appendChild(el('div', 'src', 'settles it: ' + m.settles_it));
      sh.appendChild(w);
    });
    sh.appendChild(el('div', 'src', sc.no_outbound));
  }

  var i = clear(body('p-issues'));
  var iss = H.issues || [];
  var crit = iss.filter(function (x) { return x.severity === 'CRITICAL'; });
  var hd = el('div');
  hd.appendChild(el('span', 'num sm ' + (crit.length ? 'bad' : 'good'), String(crit.length)));
  hd.appendChild(el('span', 'sub', '  critical  ·  ' + iss.length + ' open'));
  i.appendChild(hd);
  var it = tbl(i, ['id', 'sev', 'what']);
  iss.slice(0, 40).forEach(function (x) {
    row(it, [x.id, el('span', 'pill ' + (x.severity === 'CRITICAL' ? 'crit' : ''), x.severity), x.what]);
  });
  if (!iss.length) row(it, ['—', '—', 'no open issue']);
}

/* Ramped by days left, using the one ramp inverted: less time is worse.  An
   undated obligation gets no colour at all - unknown is not urgent and it is
   not safe either. */
function daysClass(d) {
  if (d === null || d === undefined) return 'none';
  if (d < 0) return 'ramp0';
  if (d <= 7) return 'ramp1';
  if (d <= 30) return 'ramp2';
  if (d <= 90) return 'ramp3';
  return 'ramp4';
}

function feedPanel(id, feed, fields, note) {
  var h = clear(body(id));
  if (feed === null || feed === undefined) {
    var n = el('div');
    n.appendChild(el('div', 'num none', '—'));
    n.appendChild(el('div', 'sub', 'not measured — this feed does not exist yet'));
    n.appendChild(el('div', 'src', note));
    h.appendChild(n);
    return;
  }
  var dl = el('dl', 'kv');
  fields.forEach(function (f) {
    dl.appendChild(el('dt', null, f[0]));
    var dd = el('dd');
    dd.appendChild(dash(f[1](feed)));
    dl.appendChild(dd);
  });
  h.appendChild(dl);
  if (feed.generated) h.appendChild(el('div', 'sub', 'as of ' + feed.generated));
  if (feed.source) h.appendChild(srcLine(feed.source));
}

/* ================================================================ S5 · THE 13 DOMAINS */

/* ALL THIRTEEN, ids fixed and never renumbered (DEC-001).  One card per domain
   in the square grid; on a phone one column, equal widths.  Every count on a
   card is read straight off board.json - the card computes nothing, so a number
   here and a number in the machine panel cannot disagree. */
function renderDomains() {
  var B = S.board;
  var h = clear(body('p-domains'));

  var grid = el('div', 'grid');
  grid.style.gridTemplateColumns = 'repeat(12, 1fr)';
  B.domains.forEach(function (d) {
    var card = el('div', 'panel domcard c3');
    card.style.cursor = 'pointer';
    card.style.background = 'var(--surface)';

    var top = el('div');
    top.appendChild(el('span', 'lbl', d.id + '  ' + d.name));
    card.appendChild(top);

    var pct = d.score.pct;
    var num = el('div', 'num sm ' + rampClass(pct));
    num.textContent = em(pct, '%');
    card.appendChild(num);
    var bar = el('div', 'bar');
    var fill = el('i');
    fill.style.width = (pct === null || pct === undefined ? 0 : pct) + '%';
    fill.style.background = rampVar(pct);
    bar.appendChild(fill);
    card.appendChild(bar);

    var dl = el('dl', 'kv');
    function kv(k, v, cls) {
      dl.appendChild(el('dt', null, k));
      var dd = el('dd', cls);
      if (v && v.nodeType !== undefined) dd.appendChild(v); else dd.appendChild(dash(v));
      dl.appendChild(dd);
    }
    kv('LB', d.lb.total + '  (A ' + d.lb.A + ' · D ' + d.lb.D + ' · J ' + d.lb.J + ')',
       d.lb.A ? 'bad' : 'good');
    kv('KNOWN', d.known.registers + ' reg · ' + d.known.catalog_rows + ' cat');
    /* A STALE WATCHER IS NOT A BINDING.  fresh/watchers, and the number that
       matters is the first one. */
    kv('WATCHED', d.watched.watchers
       ? d.watched.fresh + '/' + d.watched.watchers + ' fresh'
       : null, d.watched.watchers && d.watched.fresh < d.watched.watchers ? 'bad' : null);
    kv('OWED', d.owed || null);
    kv('BLOCKED', d.blocked || null, d.blocked ? 'bad' : null);
    kv('NEXT', d.next_rock ? d.next_rock.id + ' ' + d.next_rock.status : null);
    card.appendChild(dl);

    /* S12 · NEXT BEST ACTION on every card, and NO CARD IS EVER BLANK.  A JUDGMENT
       domain says "no mover" in words: printing "ask Cory" against 56 judgment
       functions would be a lie the board tells every day, and those functions are
       the moat, not the debt (DEC-029). */
    var nba = d.next_best_action;
    var nb = el('div', 'sub');
    nb.style.marginTop = '8px';
    if (!nba) {
      nb.appendChild(el('span', 'none', 'NEXT — nothing load-bearing in this domain'));
    } else {
      nb.appendChild(el('span', 'lbl', 'NEXT '));
      nb.appendChild(el('span', 'mono', nba.function + '  '));
      nb.appendChild(el('span', nba.has_mover ? null : 'none', nba.what));
    }
    card.appendChild(nb);
    if (d.id === '04' && (S.board.people || []).length) {
      /* R70.152: the people register surfaces under domain 04, where relationships live. */
      var pl = el('div', 'sub');
      pl.textContent = 'PEOPLE ' + S.board.people.length + '  ·  '
        + S.board.people.filter(function (p) { return p.owed_to_us.length || p.owed_by_us.length; }).length
        + ' with an open obligation';
      card.appendChild(pl);
    }
    card.appendChild(el('div', 'src', d.links.length + ' container link(s)'));
    card.addEventListener('click', function () { openDrawer(d.id); });
    grid.appendChild(card);
  });
  h.appendChild(grid);

  var total = B.domains.reduce(function (a, d) { return a + d.lb.total; }, 0);
  h.appendChild(el('div', 'src', '13 cards · LB across the cards sums to ' + total
    + ' and board.numbers.load_bearing.total is ' + em(B.numbers.load_bearing.total)
    + ' · source: state/board.json domains[]'));

  if (S.domain) openDrawer(S.domain);
}

/* THE DOMAIN DRAWER: its functions by route with their movers, its rocks, its
   registers, its links.  Everything here is already on the board; the drawer
   only groups it, which is why it can never disagree with the card. */
function openDrawer(id) {
  S.domain = id;
  var B = S.board;
  var d = B.domains.filter(function (x) { return x.id === id; })[0];
  var host = q('#p-drawer');
  if (!d) { host.classList.add('hidden'); return; }
  host.classList.remove('hidden');
  host.querySelector('h2').textContent = d.id + ' · ' + d.name;
  var h = clear(body('p-drawer'));

  var close = el('button', 'act', 'CLOSE');
  close.addEventListener('click', function () {
    S.domain = null;
    host.classList.add('hidden');
  });
  h.appendChild(close);

  var mine = B.lb_ledger.filter(function (r) { return r.domain === id; });
  var byRoute = {};
  mine.forEach(function (r) { (byRoute[r.route] = byRoute[r.route] || []).push(r); });
  h.appendChild(el('div', 'lbl', 'LOAD-BEARING FUNCTIONS BY ROUTE — ' + mine.length));
  var ft = tbl(h, ['fn', 'route', 'function', 'mover', 'sor', 'status']);
  ['KNOW', 'WATCH', 'DO', 'ROUTE', 'DISCIPLINE', 'JUDGMENT'].forEach(function (rt) {
    (byRoute[rt] || []).forEach(function (r) {
      row(ft, [r.function, rt, r.name, r.mover, r.sor,
               el('span', 'pill ' + (r.status === 'OPEN' ? 'crit' : ''), r.status)]);
    });
  });
  if (!mine.length) row(ft, ['—', '—', 'nothing load-bearing in this domain', '—', '—', '—']);

  var rocks = B.rocks.filter(function (r) {
    return (r.name + ' ' + r.evidence).toLowerCase().indexOf(d.name.toLowerCase()) !== -1;
  });
  h.appendChild(el('div', 'lbl', 'ROCKS NAMING THIS DOMAIN — ' + rocks.length));
  var rt2 = tbl(h, ['id', 'phase', 'status', 'rock']);
  rocks.forEach(function (r) { row(rt2, [r.id, r.phase, r.status, r.name]); });
  if (!rocks.length) row(rt2, ['—', '—', '—', 'no rock names this domain']);

  var iss = B.horizon.issues.filter(function (x) {
    return x.domain.slice(0, 2) === id || x.function.slice(0, 2) === id;
  });
  h.appendChild(el('div', 'lbl', 'OPEN ISSUES — ' + iss.length));
  var it = tbl(h, ['id', 'sev', 'what']);
  iss.forEach(function (x) { row(it, [x.id, x.severity, x.what]); });
  if (!iss.length) row(it, ['—', '—', 'nothing open']);

  h.appendChild(el('div', 'lbl', 'CONTAINERS — ' + d.links.length));
  var lt = tbl(h, ['catalog id', 'where', 'address', 'title']);
  d.links.forEach(function (l) {
    row(lt, [l.catalog_id, l.location, addrLink(l.address), l.title]);
  });
  if (!d.links.length) row(lt, ['—', '—', 'nothing cataloged in this domain yet', '—']);
  h.appendChild(el('div', 'src', 'source: state/board.json domains[' + id + '] + lb_ledger[] + catalog[]'));
}

/* ================================================================ S6 · THE MACHINE */

/* THIS PANEL IS THE SWEEP.  When it is live, reading four BUILD_LOGs by hand to
   learn where the estate stands stops being a task anyone does — which is the
   hours-returned claim this whole wire rests on. */
function renderMachine() {
  var B = S.board;

  var lh = clear(body('p-lanes'));
  var lt = tbl(lh, ['lane', 'last receipt', 'age', 'active wire', 'queue', 'usage', 'FOR CORY']);
  (B.lanes || []).forEach(function (l) {
    var age = el('span', l.last_receipt_age_days === null ? 'none'
      : (l.last_receipt_age_days > 1 ? 'bad' : 'good'), em(l.last_receipt_age_days, 'd'));
    row(lt, [l.lane, l.last_receipt_date, age, l.active_wire, l.queue_depth, l.usage,
             el('span', l.for_cory ? 'pill crit' : 'pill', String(l.for_cory))]);
  });
  if (!(B.lanes || []).length) row(lt, ['—', '—', '—', 'lane files not readable from this build', '—', '—', '—']);
  lh.appendChild(el('div', 'src', 'source: _reconcile/BUILD_LOG_<LANE>.md · NEXT_<LANE>.md · <lane>_queue/QUEUE.md'));

  /* THE LB LEDGER, filterable by domain / route / status, EVERY ROW SHOWING ITS
     MOVER.  The mover column is the countermeasure the 07:22 receipt asked for:
     three wires in a row predicted a movement from one clause of a two-clause
     function, and a ledger that names what actually moves each row makes that
     mistake visible before the wire is written rather than after it stops. */
  var h = clear(body('p-ledger'));
  var ctl = el('div');
  ctl.style.display = 'flex';
  ctl.style.gap = '8px';
  ctl.style.marginBottom = '10px';
  ctl.style.flexWrap = 'wrap';

  function sel(label, values, key) {
    var wrap = el('div');
    wrap.appendChild(el('div', 'lbl', label));
    var s = document.createElement('select');
    ['(all)'].concat(values).forEach(function (v) {
      var o = document.createElement('option');
      o.value = v === '(all)' ? '' : v;
      o.textContent = v;
      s.appendChild(o);
    });
    s.value = S.filter[key] || '';
    s.addEventListener('change', function () { S.filter[key] = s.value; drawLedger(); });
    wrap.appendChild(s);
    ctl.appendChild(wrap);
    return s;
  }
  var uniq = function (k) {
    var seen = {}, out = [];
    B.lb_ledger.forEach(function (r) { if (r[k] && !seen[r[k]]) { seen[r[k]] = 1; out.push(r[k]); } });
    return out.sort();
  };
  sel('domain', uniq('domain'), 'domain');
  sel('route', uniq('route'), 'route');
  sel('status', uniq('status'), 'status');
  h.appendChild(ctl);

  var count = el('div', 'sub');
  h.appendChild(count);
  var tb = tbl(h, ['fn', 'dom', 'route', 'bucket', 'function', 'mover', 'sor', 'status']);

  function drawLedger() {
    clear(tb);
    var f = S.filter;
    var rows = B.lb_ledger.filter(function (r) {
      return (!f.domain || r.domain === f.domain)
        && (!f.route || r.route === f.route)
        && (!f.status || r.status === f.status);
    });
    count.textContent = rows.length + ' of ' + B.lb_ledger.length + ' load-bearing rows';
    rows.forEach(function (r) {
      row(tb, [r.function, r.domain, r.route, r.bucket, r.name, r.mover, r.sor,
               el('span', 'pill ' + (r.status === 'OPEN' ? 'crit' : ''), r.status)]);
    });
  }
  drawLedger();

  /* PEOPLE (S5 · Rock 13).  DATA ONLY.  There is no sentiment column in people.csv
     and there is none here: `owed_to_us` and `owed_by_us` are register row IDS, so
     this table renders a JOIN rather than a claim, and every cell opens a row.
     A "how are they doing" column does not exist and is not an oversight. */
  var ph = clear(body('p-people'));
  var people = B.people || [];
  ph.appendChild(el('div', 'sub', people.length + ' people · data only, no evaluation (B1)'));
  var pt = tbl(ph, ['id', 'name', 'role', 'entity', 'owed to us', 'owed by us', 'packets', 'last touch']);
  people.forEach(function (p) {
    row(pt, [p.id, p.name, el('span', 'pill', p.role), p.entity,
             p.owed_to_us.join(' ') || null, p.owed_by_us.join(' ') || null,
             p.packets.join(' ') || null,
             p.last_touch === 'UNMEASURED' ? el('span', 'none', 'UNMEASURED') : p.last_touch]);
  });
  if (!people.length) row(pt, ['—', '—', '—', '—', '—', '—', '—', 'people.csv not built']);
  ph.appendChild(el('div', 'src', 'source: life-taxonomy/registers/people.csv — generated by '
    + 'tools/people_build.py, joined from obligations.csv and the packets, never typed'));

  /* ROCKS BY PHASE.  Status comes from a receipt, never from a document. */
  var rh = clear(body('p-rocks'));
  var tally = {};
  B.rocks.forEach(function (r) { tally[r.status] = (tally[r.status] || 0) + 1; });
  rh.appendChild(el('div', 'sub', Object.keys(tally).sort().map(function (k) {
    return k + ' ' + tally[k];
  }).join('  ·  ') + '   (of ' + B.rocks.length + ')'));
  var phases = {};
  B.rocks.forEach(function (r) { (phases[r.phase] = phases[r.phase] || []).push(r); });
  var rt = tbl(rh, ['id', 'phase', 'status', 'rock', 'lane', 'last receipt', 'evidence']);
  Object.keys(phases).sort().forEach(function (p) {
    phases[p].forEach(function (r) {
      row(rt, [r.id, r.phase,
               el('span', 'pill ' + (r.status === 'PASS' ? 'ok' : r.status === 'FAIL' ? 'crit' : ''), r.status),
               r.name, r.owner_lane, r.last_receipt, r.evidence]);
    });
  });
  rh.appendChild(el('div', 'src', 'status is computed by tools/rock_check.py from a receipt, never typed'));
}

/* ================================================================ S7 · THE BRAIN */

/* CATALOG-FIRST SEARCH, client-side over catalog[].  A result row links straight
   to its address — Drive, repo path, ClickUp, HT, SB, or a Brain shelf.

   THE STRANGER TEST (R9.5) IS THE GOLDEN: any catalog id typed here is reached in
   two hops — hop one is this box, hop two is the address on the row it returns.
   A row with no address fails the test, which is exactly what it should do.

   SENSITIVITY IS SHOWN ON EVERY ROW.  PRIVATE rows are visible because the page
   itself is private by R70.109 — and build_board.py's B1 export filter REFUSES an
   untagged row, so an untagged row never reaches the board at all. */
function renderBrain() {
  var B = S.board;
  var h = clear(body('p-brain'));

  var box = document.createElement('input');
  box.type = 'text';
  box.placeholder = 'catalog id, title, address, alias, domain, type…';
  box.value = S.query || '';
  h.appendChild(box);

  var meta = el('div', 'sub');
  h.appendChild(meta);
  var tb = tbl(h, ['id', 'where', 'address', 'domain', 'type', 'sensitivity', 'title']);

  function draw() {
    clear(tb);
    var qs = (S.query || '').trim().toLowerCase();
    var rows = !qs ? B.catalog : B.catalog.filter(function (c) {
      return [c.id, c.title, c.address, c.aliases, c.domain, c.type, c.location]
        .join(' ').toLowerCase().indexOf(qs) !== -1;
    });
    meta.textContent = rows.length + ' of ' + B.catalog.length + ' catalog rows'
      + (B.catalog_refused && B.catalog_refused.length
        ? '  ·  ' + B.catalog_refused.length + ' untagged row(s) REFUSED by the export filter (B1)'
        : '  ·  0 refused');
    rows.slice(0, 400).forEach(function (c) {
      row(tb, [c.id, c.location, addrLink(c.address), c.domain, c.type,
               el('span', 'pill', c.sensitivity), c.title]);
    });
    if (rows.length > 400) {
      row(tb, ['…', '', 'narrow the search — ' + (rows.length - 400) + ' more rows match', '', '', '', '']);
    }
  }
  box.addEventListener('input', function () { S.query = box.value; draw(); });
  box.addEventListener('change', function () { S.query = box.value; draw(); });
  draw();
  h.appendChild(el('div', 'src', 'source: master-brain/CATALOG.md — 164 LIVE rows, parsed from the header '
    + 'to the fence; the 6 RETIRED rows below it are not the estate'));
}

/* ---------------------------------------------------------------- boot

   LAST LINE OF THE LAST SCRIPT.  app.js defines boot() and deliberately does not
   call it: render() asks `typeof renderNumbers === 'function'`, so booting from
   app.js renders every panel empty because this file has not been parsed yet.
   Whoever loads last starts the app, and that is this file. */
boot();
