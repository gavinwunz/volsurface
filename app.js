/* ============================================================================
   VolFoundry — live surface console
   Browser-only. Live data: public Deribit WebSocket (no auth, no backend).
   Pipeline in this file: book summary -> per-expiry forward -> OTM total
   variance -> local-quadratic smoothing -> (k,T) grid -> lit 3D surface.
   ========================================================================= */
'use strict';

/* ---- configuration (edit these two on the repo rename) ------------------ */
const REPO_URL = 'https://github.com/gavinwunz/volsurface';   // -> /volfoundry after rename
const REPO_LABEL = 'gavinwunz/volsurface';
const PACKAGE = 'volfoundry';

const WS_URL = 'wss://www.deribit.com/ws/api/v2';
const POLL_MS = 3500;            // book-summary refresh cadence
const YEAR_MS = 365 * 864e5;     // ACT/365 year in ms
const MIN_T = 1 / 365;           // drop anything under 1 day: mark_iv is unstable there
const MAX_T = 2.0;
const TAPE_MAX = 5;
const SPARK_MAX = 180;

/* ---- plot palette (shared with styles.css) ------------------------------ */
const C = {
  ink: '#e9eef6', ink2: '#adbaca', mut: '#718094', dim: '#4c596b',
  line: 'rgba(255,255,255,.07)', hot: '#ff8f42', hot2: '#ff5a2e',
  tq: '#4fd8c4', up: '#2fd07f', down: '#ff6058', gold: '#f0b429'
};
const SURFACE_SCALE = [
  [0.00, '#0e2745'], [0.20, '#155f78'], [0.40, '#2a9d92'],
  [0.58, '#8cc07e'], [0.74, '#e8bf5a'], [0.88, '#ff9247'], [1.00, '#ff5a2e']
];
const PLOT_FONT = { family: '"IBM Plex Mono", ui-monospace, monospace', size: 10, color: C.mut };
const PLOT_CFG = { displayModeBar: false, responsive: true, scrollZoom: false };

/* ---- tiny helpers ------------------------------------------------------- */
const $ = (id) => document.getElementById(id);
const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);
const nf = (n, d = 2) => (n == null || !isFinite(n)) ? '—'
  : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (n, d = 2) => (n == null || !isFinite(n)) ? '—' : nf(n, d) + '%';
const hhmmss = (ms) => new Date(ms).toISOString().slice(11, 19);
const MON = { JAN: 0, FEB: 1, MAR: 2, APR: 3, MAY: 4, JUN: 5, JUL: 6, AUG: 7, SEP: 8, OCT: 9, NOV: 10, DEC: 11 };
const MONS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

/** BTC-28AUG26-110000-P -> {strike, type, expMs, tag}. Deribit settles 08:00 UTC. */
function parseInst(name) {
  const p = name.split('-');
  if (p.length !== 4) return null;
  const m = /^(\d{1,2})([A-Z]{3})(\d{2})$/.exec(p[1]);
  if (!m || !(m[2] in MON)) return null;
  const strike = +p[2];
  if (!isFinite(strike) || strike <= 0) return null;
  return {
    strike, type: p[3],
    expMs: Date.UTC(2000 + +m[3], MON[m[2]], +m[1], 8, 0, 0),
    tag: p[1]
  };
}
const expTag = (ms) => {
  const d = new Date(ms);
  return d.getUTCDate() + MONS[d.getUTCMonth()] + String(d.getUTCFullYear()).slice(2);
};

/* ============================================================================
   1. NUMERICS — weighted local-quadratic smoother on total variance
   ========================================================================= */

/** Solve A x = b for small dense symmetric systems (Gaussian elim, partial pivot). */
function solve(A, b, n) {
  const M = A.map((r, i) => r.slice(0, n).concat([b[i]]));
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    if (Math.abs(M[p][c]) < 1e-12) return null;
    const t = M[c]; M[c] = M[p]; M[p] = t;
    for (let r = c + 1; r < n; r++) {
      const f = M[r][c] / M[c][c];
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  const x = new Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let s = M[r][n];
    for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k];
    x[r] = s / M[r][r];
  }
  return x.every(isFinite) ? x : null;
}

/**
 * Local polynomial regression of total variance w on log-moneyness k.
 * Degree 2 (smiles are curved); falls back to degree 1, then to a weighted mean.
 * Bandwidth widens automatically until enough quotes carry weight, so thin
 * wings and dense ATM regions are both handled.
 */
function makeSmoother(pts) {
  const ks = pts.map(p => p.k), ws = pts.map(p => p.w);
  const kmin = Math.min.apply(null, ks), kmax = Math.max.apply(null, ks);
  const wlo = Math.min.apply(null, ws) * 0.55, whi = Math.max.apply(null, ws) * 1.7;
  const h0 = clamp(0.17 * (kmax - kmin), 0.045, 0.30);
  const guard = (v) => (v == null ? null : clamp(v, wlo, whi));
  return function evalAt(kq) {
    const kc = clamp(kq, kmin, kmax);          // hold the fit flat outside quoted strikes
    for (let pass = 0; pass < 5; pass++) {
      const h = h0 * Math.pow(1.8, pass);
      const wt = [], eff = [];
      let sw = 0, neff = 0;
      for (let i = 0; i < ks.length; i++) {
        const u = (ks[i] - kc) / h;
        const g = Math.exp(-0.5 * u * u);
        wt.push(g); sw += g;
        if (g > 0.05) neff++;
      }
      if (neff < 4 && pass < 4) continue;
      for (let deg = 2; deg >= 1; deg--) {
        const n = deg + 1;
        const A = Array.from({ length: n }, () => new Array(n).fill(0));
        const b = new Array(n).fill(0);
        for (let i = 0; i < ks.length; i++) {
          if (wt[i] < 1e-6) continue;
          const d = ks[i] - kc, ph = [1, d, d * d].slice(0, n);
          for (let a = 0; a < n; a++) {
            b[a] += wt[i] * ph[a] * ws[i];
            for (let c = 0; c < n; c++) A[a][c] += wt[i] * ph[a] * ph[c];
          }
        }
        const x = solve(A, b, n);
        if (x && isFinite(x[0]) && x[0] > 0) return guard(x[0]);
        eff.push(deg);
      }
      if (sw > 0) {
        let s = 0;
        for (let i = 0; i < ks.length; i++) s += wt[i] * ws[i];
        const mean = s / sw;
        if (isFinite(mean) && mean > 0) return guard(mean);
      }
    }
    return null;
  };
}

/**
 * Turn a raw book-summary payload into a surface model.
 * Per expiry: forward from Deribit's per-expiry `underlying_price`, OTM filter
 * (calls above F, puts below), duplicate strikes averaged, total variance
 * w = sigma^2 T with sigma decimal and T in years (ACT/365).
 */
function buildModel(rows, nowMs) {
  const groups = new Map();
  let raw = 0, kept = 0;

  for (const r of rows) {
    raw++;
    const inst = parseInst(r.instrument_name);
    if (!inst) continue;
    const iv = r.mark_iv, F = r.underlying_price;
    if (!(iv > 1) || iv > 500 || !(F > 0)) continue;       // obvious garbage out first
    const T = (inst.expMs - nowMs) / YEAR_MS;
    if (!(T >= MIN_T) || T > MAX_T) continue;
    const otm = inst.strike >= F ? 'C' : 'P';
    if (inst.type !== otm) continue;                       // one quote per strike: the OTM one
    if (!groups.has(inst.expMs)) groups.set(inst.expMs, { expMs: inst.expMs, T, Fs: [], byK: new Map() });
    const g = groups.get(inst.expMs);
    g.Fs.push(F);
    const cur = g.byK.get(inst.strike);
    if (cur) { cur.iv = (cur.iv * cur.n + iv) / (cur.n + 1); cur.n++; }
    else g.byK.set(inst.strike, { K: inst.strike, iv, n: 1, type: inst.type });
    kept++;
  }

  const slices = [];
  let trimmed = 0;
  for (const g of groups.values()) {
    g.Fs.sort((a, b) => a - b);
    const F = g.Fs[Math.floor(g.Fs.length / 2)];
    let pts = [];
    for (const q of g.byK.values()) {
      const sig = q.iv / 100;
      const k = Math.log(q.K / F);
      if (!isFinite(k) || Math.abs(k) > 2.5) continue;
      pts.push({ k, K: q.K, iv: q.iv, sig, w: sig * sig * g.T, type: q.type });
    }
    if (pts.length < 6) continue;
    pts.sort((a, b) => a.k - b.k);

    /* Deep wings on very short maturities carry meaningless mark IVs (a 1-day
       option 20% out of the money is ~10 standard deviations away). Keep the
       strikes inside an ATM-standard-deviation window, widening it until the
       slice has enough quotes to fit. Everything dropped here is counted. */
    let ref = pts[0];
    for (const p of pts) if (Math.abs(p.k) < Math.abs(ref.k)) ref = p;
    const sd = ref.sig * Math.sqrt(g.T);
    const before = pts.length;
    for (let win = 4 * sd; ; win *= 1.25) {
      const sub = pts.filter(p => Math.abs(p.k) <= win);
      if (sub.length >= 8 || win > 1.25) { if (sub.length >= 6) pts = sub; break; }
    }
    trimmed += before - pts.length;

    if (pts.length < 6) continue;
    if (pts[pts.length - 1].k - pts[0].k < 0.02) continue;
    const s = {
      expMs: g.expMs, T: g.T, days: g.T * 365, F, pts,
      tag: expTag(g.expMs), kmin: pts[0].k, kmax: pts[pts.length - 1].k
    };
    s.fit = makeSmoother(pts);
    const w0 = s.fit(0);
    s.atm = w0 != null ? Math.sqrt(w0 / s.T) * 100 : null;
    /* Skew measured one ATM standard deviation out on each side, so it stays
       comparable across maturities (a fixed +/-0.10 in k is meaningless at 1 day). */
    const kx = clamp((s.atm != null ? s.atm / 100 : ref.sig) * Math.sqrt(s.T), 0.005, 0.6);
    const wl = s.fit(-kx), wr = s.fit(kx);
    s.sd1 = kx;
    s.skew = (wl != null && wr != null && wl > 0 && wr > 0)
      ? (Math.sqrt(wl / s.T) - Math.sqrt(wr / s.T)) * 100 : null;
    slices.push(s);
  }
  slices.sort((a, b) => a.T - b.T);
  return { slices, raw, kept, trimmed, nowMs };
}

/** ATM vol interpolated to an arbitrary maturity (linear in total variance). */
function atmAt(slices, Tq) {
  const usable = slices.filter(s => s.atm != null);
  if (!usable.length) return null;
  if (Tq <= usable[0].T) return usable[0].atm;
  const last = usable[usable.length - 1];
  if (Tq >= last.T) return last.atm;
  for (let i = 1; i < usable.length; i++) {
    const a = usable[i - 1], b = usable[i];
    if (Tq <= b.T) {
      const wa = (a.atm / 100) ** 2 * a.T, wb = (b.atm / 100) ** 2 * b.T;
      const u = (Tq - a.T) / (b.T - a.T);
      return Math.sqrt((wa + u * (wb - wa)) / Tq) * 100;
    }
  }
  return last.atm;
}

/**
 * Rectangular grid for the 3D surface. Three x-axes, same underlying fits:
 *   'z' -> standardised moneyness  z = k / (sigma_ATM * sqrt(T)).  Every expiry
 *          quotes roughly the same number of standard deviations, so slices are
 *          directly comparable and the surface fills its domain. Default.
 *   'k' -> raw log-moneyness ln(K/F), shared across expiries.
 *   'K' -> strike; each slice evaluated at k = ln(K / F_slice), so a non-flat
 *          forward curve stays honest.
 * Rows are densified in T (linear in total variance = flat forward variance)
 * purely so the lit surface reads smoothly; every row still comes from fits.
 */
function sdOf(s) { return clamp((s.atm != null ? s.atm / 100 : 0.5) * Math.sqrt(s.T), 1e-4, 5); }

function buildGrid(model, mode) {
  const S = model.slices.filter(s => s.atm != null);
  if (S.length < 2) return null;

  const allK = [];
  for (const s of S) {
    const sd = sdOf(s);
    for (const p of s.pts) allK.push(mode === 'K' ? p.K : mode === 'z' ? p.k / sd : p.k);
  }
  allK.sort((a, b) => a - b);
  const q = (f) => allK[clamp(Math.round(f * (allK.length - 1)), 0, allK.length - 1)];
  let lo = q(0.03), hi = q(0.97);
  if (mode === 'k') { lo = clamp(lo, -1.15, -0.10); hi = clamp(hi, 0.10, 0.95); }
  if (mode === 'z') { lo = clamp(lo, -4.5, -1.2); hi = clamp(hi, 1.2, 4.5); }
  const NX = 61;
  const xs = Array.from({ length: NX }, (_, i) => lo + (hi - lo) * i / (NX - 1));

  /* Each slice is drawn only across the strikes it actually quotes (inset a
     little, where a local fit is least reliable). A single expiry that quotes
     wider than both of its neighbours would leave a fin sticking out of the
     surface, so the drawn domain is eroded against neighbouring slices — that
     only ever removes area, it never invents a wing. */
  const dom = S.map(s => {
    const sd = sdOf(s);
    const toX = (k) => mode === 'K' ? s.F * Math.exp(k) : mode === 'z' ? k / sd : k;
    const a = toX(s.kmin), b = toX(s.kmax);
    const pad = 0.035 * (b - a);
    return [a + pad, b - pad];
  });
  let eroded = dom;
  for (let pass = 0; pass < 2; pass++) {
    const src = eroded;
    eroded = src.map((d, i) => {
      const lo = Math.max(d[0], src[Math.max(i - 1, 0)][0], src[Math.min(i + 1, src.length - 1)][0]);
      const hi = Math.min(d[1], src[Math.max(i - 1, 0)][1], src[Math.min(i + 1, src.length - 1)][1]);
      return hi > lo ? [lo, hi] : d;
    });
  }

  const wS = S.map((s, si) => xs.map(x => {
    if (x < eroded[si][0] || x > eroded[si][1]) return null;
    const k = mode === 'K' ? Math.log(x / s.F) : mode === 'z' ? x * sdOf(s) : x;
    const w = s.fit(k);
    return (w != null && w > 0) ? w : null;
  }));

  // densify in maturity
  const Tmin = S[0].T, Tmax = S[S.length - 1].T;
  const NY = Math.min(34, Math.max(14, S.length * 4));
  const Ts = Array.from({ length: NY }, (_, j) =>
    Tmin * Math.pow(Tmax / Tmin, j / (NY - 1)));

  const z = [], rowT = [];
  for (const Tq of Ts) {
    let i1 = 1;
    while (i1 < S.length - 1 && S[i1].T < Tq) i1++;
    const a = S[i1 - 1], b = S[i1];
    const u = clamp((Tq - a.T) / Math.max(b.T - a.T, 1e-9), 0, 1);
    const row = xs.map((_, i) => {
      const wa = wS[i1 - 1][i], wb = wS[i1][i];
      if (wa == null || wb == null) return null;
      const w = wa + u * (wb - wa);
      return w > 0 ? Math.sqrt(w / Tq) * 100 : null;
    });
    z.push(row); rowT.push(Tq * 365);
  }
  smoothGrid(z);
  return { xs, days: rowT, z, mode, lo, hi, slices: S };
}

/** Light [1,2,1]/4 pass along both axes. Cosmetic only: it removes the sawtooth
    a per-slice fit leaves at its own boundary, and never fills an empty cell. */
function smoothGrid(z) {
  const ny = z.length, nx = z[0].length;
  for (let pass = 0; pass < 2; pass++) {
    const src = z.map(r => r.slice());
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      if (src[j][i] == null) continue;
      const a = i > 0 ? src[j][i - 1] : null, b = i < nx - 1 ? src[j][i + 1] : null;
      const c = j > 0 ? src[j - 1][i] : null, d = j < ny - 1 ? src[j + 1][i] : null;
      let sum = 2 * src[j][i], wgt = 2;
      [a, b, c, d].forEach(v => { if (v != null) { sum += 0.5 * v; wgt += 0.5; } });
      z[j][i] = sum / wgt;
    }
  }
}

/* ============================================================================
   2. STATE
   ========================================================================= */
const state = {
  ccy: 'BTC',
  price: null, prevPrice: null, refPrice: null,
  ticks: [],                       // {t, p}
  model: null, grid: null,
  selExp: null,
  axis: 'z', showRaw: false, termLog: true,
  prevIv: new Map(),               // instrument -> mark_iv, for churn + tape
  churn: 0, churnMag: 0,
  tape: [], tapeSeq: 0, lastIdxTape: 0,
  camera: { eye: { x: 1.36, y: -1.34, z: 0.60 }, center: { x: 0, y: 0, z: -0.10 } },
  firstBook: false
};

/* ============================================================================
   3. DERIBIT SOCKET — reconnecting, heartbeat-aware, currency-switch safe
   ========================================================================= */
const sock = (function () {
  let ws = null, id = 100, retry = 0, pollTimer = null, alive = false;
  const handlers = new Map();
  let channel = null;

  const send = (method, params, onResult) => {
    if (!ws || ws.readyState !== 1) return false;
    const rid = ++id;
    if (onResult) handlers.set(rid, onResult);
    ws.send(JSON.stringify({ jsonrpc: '2.0', id: rid, method, params: params || {} }));
    return true;
  };

  function setStatus(cls, text) {
    const d = $('wsdot'), s = $('wsstat');
    if (d) d.className = 'dot ' + cls;
    if (s) s.textContent = text;
  }

  function subscribe() {
    channel = 'deribit_price_index.' + state.ccy.toLowerCase() + '_usd';
    send('public/subscribe', { channels: [channel] });
  }
  function unsubscribe() {
    if (channel) send('public/unsubscribe', { channels: [channel] });
    channel = null;
  }
  function poll() {
    send('public/get_book_summary_by_currency',
      { currency: state.ccy, kind: 'option' },
      (res) => { if (Array.isArray(res)) onBook(res); });
  }

  function connect() {
    setStatus(retry ? 'warn' : '', retry ? 'reconnecting…' : 'connecting…');
    try { ws = new WebSocket(WS_URL); } catch (e) { schedule(); return; }

    ws.onopen = () => {
      alive = true; retry = 0;
      setStatus('live', 'live · deribit');
      send('public/set_heartbeat', { interval: 30 });
      subscribe(); poll();
      clearInterval(pollTimer);
      pollTimer = setInterval(poll, POLL_MS);
    };
    ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.method === 'heartbeat') {
        if (m.params && m.params.type === 'test_request') send('public/test', {});
        return;
      }
      if (m.method === 'subscription') {
        const p = m.params || {};
        if (p.channel && p.channel.indexOf('deribit_price_index') === 0 && p.data) onIndex(p.data);
        return;
      }
      if (m.id && handlers.has(m.id)) {
        const h = handlers.get(m.id); handlers.delete(m.id);
        if (m.result !== undefined) h(m.result);
      }
    };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* noop */ } };
    ws.onclose = () => {
      alive = false;
      clearInterval(pollTimer); pollTimer = null;
      handlers.clear();
      setStatus('err', 'disconnected');
      schedule();
    };
  }
  function schedule() {
    retry = Math.min(retry + 1, 6);
    const wait = Math.min(1000 * Math.pow(1.7, retry), 15000) + Math.random() * 400;
    setStatus('warn', 'reconnecting in ' + Math.round(wait / 1000) + 's');
    setTimeout(connect, wait);
  }

  return {
    start: connect,
    isAlive: () => alive,
    switchCcy() {
      unsubscribe();
      if (alive) { subscribe(); poll(); }
    }
  };
})();

/* ============================================================================
   4. INBOUND DATA
   ========================================================================= */
function onIndex(d) {
  const p = d.price, t = d.timestamp || Date.now();
  if (!(p > 0)) return;
  state.prevPrice = state.price;
  state.price = p;
  if (state.refPrice == null) state.refPrice = p;
  state.ticks.push({ t, p });
  if (state.ticks.length > SPARK_MAX) state.ticks.shift();

  renderPrice();
  renderSpark();
  renderMoveTile();

  if (state.prevPrice != null && state.prevPrice !== p && t - state.lastIdxTape > 900) {
    state.lastIdxTape = t;
    pushTape({
      t, kind: 'index',
      what: state.ccy + ' index',
      from: nf(state.prevPrice, 2), to: nf(p, 2),
      dir: p > state.prevPrice ? 1 : -1
    });
  }
}

function onBook(rows) {
  const now = Date.now();
  const model = buildModel(rows, now);
  if (!model.slices.length) return;

  // churn + biggest repricings, measured against the previous refresh
  let churn = 0, mag = 0;
  const moves = [];
  for (const r of rows) {
    const iv = r.mark_iv;
    if (!(iv > 0)) continue;
    const prev = state.prevIv.get(r.instrument_name);
    if (prev != null && prev !== iv) {
      churn++; mag += Math.abs(iv - prev);
      moves.push({ name: r.instrument_name, from: prev, to: iv, d: Math.abs(iv - prev) });
    }
    state.prevIv.set(r.instrument_name, iv);
  }
  state.churn = churn;
  state.churnMag = churn ? mag / churn : 0;

  state.model = model;
  if (state.selExp == null || !model.slices.some(s => s.expMs === state.selExp)) {
    state.selExp = model.slices[0].expMs;
  }
  state.grid = buildGrid(model, state.axis);

  moves.sort((a, b) => b.d - a.d);
  for (const mv of moves.slice(0, 2)) {
    const inst = parseInst(mv.name);
    pushTape({
      t: now, kind: 'iv',
      what: inst ? (inst.tag + ' · ' + (inst.strike >= 1000 ? (inst.strike / 1000) + 'k' : inst.strike) + ' ' + inst.type)
        : mv.name,
      from: nf(mv.from, 2) + '%', to: nf(mv.to, 2) + '%',
      dir: mv.to > mv.from ? 1 : -1
    });
  }
  if (!state.firstBook) {
    state.firstBook = true;
    pushTape({ t: now, kind: 'sys', what: 'book snapshot · ' + model.raw + ' quotes · ' + model.slices.length + ' expiries' });
  }

  renderSurface();
  renderSmile();
  renderTerm();
  renderChips();
  renderTiles();
}

/* ============================================================================
   5. RENDER — header, tiles, tape
   ========================================================================= */
function flash(el, dir) {
  if (!el) return;
  el.classList.remove('fl-up', 'fl-dn');
  void el.offsetWidth;
  el.classList.add(dir > 0 ? 'fl-up' : 'fl-dn');
}

function renderPrice() {
  const el = $('bigPrice');
  if (!el) return;
  el.textContent = '$' + nf(state.price, 2);
  if (state.prevPrice != null && state.price !== state.prevPrice) {
    flash(el, state.price > state.prevPrice ? 1 : -1);
  }
  const ref = state.refPrice;
  const chg = $('priceChg');
  if (ref && chg) {
    const d = state.price - ref, r = d / ref * 100;
    chg.className = 'num ' + (d >= 0 ? 'up' : 'down');
    chg.textContent = (d >= 0 ? '+' : '') + nf(d, 2) + '  (' + (d >= 0 ? '+' : '') + nf(r, 3) + '%)';
  }
  const st = $('priceStamp');
  if (st) st.textContent = hhmmss(Date.now()) + 'Z';
  const cnt = $('tickCount');
  if (cnt) cnt.textContent = state.ticks.length + ' ticks';
}

function renderSpark() {
  const svg = $('spark');
  if (!svg || state.ticks.length < 2) return;
  const W = 300, H = 46, ps = state.ticks.map(t => t.p);
  let lo = Math.min.apply(null, ps), hi = Math.max.apply(null, ps);
  if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
  const pad = (hi - lo) * 0.18; lo -= pad; hi += pad;
  const X = i => (i / (state.ticks.length - 1)) * W;
  const Y = p => H - ((p - lo) / (hi - lo)) * H;
  let d = '';
  state.ticks.forEach((t, i) => { d += (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(t.p).toFixed(1) + ' '; });
  const up = state.price >= (state.refPrice || state.price);
  const stroke = up ? C.up : C.down;
  $('sparkLine').setAttribute('d', d.trim());
  $('sparkLine').setAttribute('stroke', stroke);
  $('sparkArea').setAttribute('d', d + 'L' + W + ' ' + H + ' L0 ' + H + ' Z');
  $('sparkArea').setAttribute('fill', up ? 'url(#gUp)' : 'url(#gDn)');
  if (state.refPrice != null) {
    const y = clamp(Y(state.refPrice), 0, H).toFixed(1);
    $('sparkRef').setAttribute('d', 'M0 ' + y + ' L' + W + ' ' + y);
  }
}

/** 60-second index range in basis points — a proxy for "is it moving right now". */
function renderMoveTile() {
  const el = $('tMove'), meter = $('mMove'), note = $('tMoveNote');
  if (!el) return;
  const cut = Date.now() - 60000;
  const win = state.ticks.filter(t => t.t >= cut);
  if (win.length < 2) { el.textContent = '—'; return; }
  const ps = win.map(t => t.p);
  const lo = Math.min.apply(null, ps), hi = Math.max.apply(null, ps);
  const bps = (hi - lo) / ((hi + lo) / 2) * 1e4;
  el.textContent = nf(bps, 1);
  el.className = 'v num ' + (bps > 18 ? 'hotc' : bps > 8 ? 'warnc' : '');
  if (meter) meter.style.width = clamp(bps / 30 * 100, 2, 100) + '%';
  if (note) note.textContent = win.length + ' ticks · high ' + nf(hi, 0) + ' / low ' + nf(lo, 0);
}

function renderTiles() {
  const m = state.model;
  if (!m) return;
  const front = m.slices.find(s => s.atm != null);
  const set = (id, v, cls) => { const e = $(id); if (e) { e.textContent = v; if (cls != null) e.className = 'v num ' + cls; } };

  if (front) {
    set('tAtm', pct(front.atm, 2), 'tqc');
    $('tAtmNote').textContent = front.tag + ' · ' + nf(front.days, 1) + 'd · F ' + nf(front.F, 0);
  }
  const a30 = atmAt(m.slices, 30 / 365);
  set('tAtm30', pct(a30, 2), '');
  const a7 = atmAt(m.slices, 7 / 365), a90 = atmAt(m.slices, 90 / 365);
  if (a7 != null && a90 != null) {
    const sl = a90 - a7;
    $('tAtm30Note').textContent = '7d ' + pct(a7, 1) + ' → 90d ' + pct(a90, 1) +
      ' (' + (sl >= 0 ? 'contango +' : 'backwardation ') + nf(sl, 2) + ')';
  }
  set('tQuotes', String(m.raw), '');
  $('tQuotesNote').textContent = m.kept + ' OTM · ' + m.trimmed + ' wing-trimmed · ' +
    m.slices.length + ' expiries fitted';

  set('tChurn', String(state.churn), state.churn > 0 ? 'hotc' : '');
  $('tChurnNote').textContent = state.churnMag > 0
    ? 'mean |Δ| ' + nf(state.churnMag, 2) + ' vol pts / ' + (POLL_MS / 1000) + 's'
    : 'instruments repriced per refresh';

  if (front && front.skew != null) {
    set('tSkew', (front.skew >= 0 ? '+' : '') + nf(front.skew, 2), front.skew >= 0 ? 'down' : 'up');
    $('tSkewNote').textContent = 'σ(−1σ) − σ(+1σ) at k = ±' + nf(front.sd1, 3) + ', ' + front.tag;
  }
}

/* ---- the tape ----------------------------------------------------------- */
function pushTape(ev) {
  ev.seq = ++state.tapeSeq;
  state.tape.unshift(ev);
  if (state.tape.length > TAPE_MAX) state.tape.length = TAPE_MAX;
  renderTape();
}
function renderTape() {
  const ul = $('tape');
  if (!ul) return;
  const empty = $('tapeEmpty');
  if (empty) empty.style.display = state.tape.length ? 'none' : '';
  const have = new Map();
  Array.from(ul.children).forEach(li => have.set(li.dataset.seq, li));

  state.tape.forEach((ev, i) => {
    let li = have.get(String(ev.seq));
    if (!li) {
      li = document.createElement('li');
      li.dataset.seq = String(ev.seq);
      const arrow = ev.dir > 0 ? '▲' : '▼';
      const cls = ev.dir > 0 ? 'up' : 'down';
      li.innerHTML =
        '<span class="t">' + hhmmss(ev.t) + '</span>' +
        '<span class="w">' + (ev.kind === 'index' ? '<b>' + ev.what + '</b>' : ev.what) + '</span>' +
        (ev.from != null
          ? '<span class="d ' + cls + '">' + ev.from + ' → ' + ev.to + ' ' + arrow + '</span>'
          : '<span class="d" style="color:var(--dim)">·</span>');
      ul.insertBefore(li, ul.firstChild);
      have.set(String(ev.seq), li);
    }
    li.className = 'r' + i;
  });
  Array.from(ul.children).forEach(li => {
    if (!state.tape.some(e => String(e.seq) === li.dataset.seq)) li.remove();
  });
}

/* ============================================================================
   6. RENDER — plots
   ========================================================================= */
const AXIS3D = (title, extra) => Object.assign({
  title: { text: title, font: { family: PLOT_FONT.family, size: 10.5, color: C.mut } },
  tickfont: { family: PLOT_FONT.family, size: 9, color: C.dim },
  gridcolor: '#1c2736', zerolinecolor: '#4a3325',
  showbackground: true, backgroundcolor: '#090d15',
  showspikes: false, linecolor: '#22303f'
}, extra || {});

function renderSurface() {
  const el = $('surface');
  if (!el || !window.Plotly) return;
  const g = state.grid;
  if (!g) return;
  const ov = $('surfaceWait'); if (ov) ov.classList.add('gone');

  const xTitle = g.mode === 'K' ? 'strike  K (USD)'
    : g.mode === 'z' ? 'standardised moneyness  z = k / (σ√T)'
      : 'log-moneyness  k = ln(K / F)';
  const traces = [{
    type: 'surface', x: g.xs, y: g.days, z: g.z,
    colorscale: SURFACE_SCALE, showscale: false, opacity: 1, connectgaps: false,
    hovertemplate: (g.mode === 'K' ? 'K %{x:,.0f}' : g.mode === 'z' ? 'z %{x:.2f}σ' : 'k %{x:.3f}') +
      '<br>%{y:.1f}d<br><b>σ %{z:.2f}%</b><extra></extra>',
    contours: {
      z: { show: true, usecolormap: true, width: 1.6, highlight: true, highlightcolor: 'rgba(255,255,255,.4)' },
      x: { show: false }, y: { show: false }
    },
    lighting: { ambient: 0.64, diffuse: 0.86, specular: 0.10, roughness: 0.62, fresnel: 0.15 },
    lightposition: { x: -80, y: 120, z: 260 }
  }];

  if (state.showRaw) {
    const px = [], py = [], pz = [];
    for (const s of g.slices) {
      const sd = sdOf(s);
      for (const p of s.pts) {
        px.push(g.mode === 'K' ? p.K : g.mode === 'z' ? p.k / sd : p.k);
        py.push(s.days); pz.push(p.iv);
      }
    }
    traces.push({
      type: 'scatter3d', mode: 'markers', x: px, y: py, z: pz,
      marker: { size: 2.1, color: 'rgba(233,238,246,.55)', line: { width: 0 } },
      hovertemplate: 'quote σ %{z:.2f}%<extra></extra>', name: 'quotes'
    });
  }

  const layout = {
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false, font: PLOT_FONT,
    hoverlabel: {
      bgcolor: '#0d121b', bordercolor: '#1a2432',
      font: { family: PLOT_FONT.family, size: 11, color: C.ink }
    },
    scene: {
      xaxis: AXIS3D(xTitle),
      yaxis: AXIS3D('days to expiry  (log)', {
        type: 'log',
        tickvals: [1, 2, 3, 7, 14, 30, 60, 90, 180, 365, 730],
        ticktext: ['1', '2', '3', '7', '14', '30', '60', '90', '180', '365', '730']
      }),
      zaxis: AXIS3D('implied vol  σ (%)'),
      aspectmode: 'manual', aspectratio: { x: 1.62, y: 1.24, z: 0.78 },
      camera: state.camera,
      bgcolor: 'rgba(0,0,0,0)'
    }
  };
  Plotly.react(el, traces, layout, PLOT_CFG);
  if (!el.dataset.bound) {
    el.dataset.bound = '1';
    el.on('plotly_relayout', (e) => {
      if (e && e['scene.camera']) state.camera = e['scene.camera'];
    });
  }
  const meta = $('surfaceMeta');
  if (meta) {
    meta.textContent = g.slices.length + ' expiries · ' + g.xs.length + '×' + g.days.length +
      ' grid · ' + hhmmss(state.model.nowMs) + 'Z';
  }
}

const AXIS2D = (title) => ({
  title: { text: title, font: { family: PLOT_FONT.family, size: 10, color: C.mut }, standoff: 8 },
  tickfont: { family: PLOT_FONT.family, size: 9.5, color: C.dim },
  gridcolor: 'rgba(255,255,255,.055)', zerolinecolor: 'rgba(255,255,255,.09)',
  linecolor: 'rgba(255,255,255,.10)', showline: true, ticks: 'outside', ticklen: 3,
  tickcolor: 'rgba(255,255,255,.12)'
});
const LAYOUT2D = {
  paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
  margin: { l: 48, r: 14, t: 8, b: 40 }, showlegend: false, font: PLOT_FONT,
  hovermode: 'closest',
  hoverlabel: { bgcolor: '#0d121b', bordercolor: '#1a2432', font: { family: PLOT_FONT.family, size: 11, color: C.ink } }
};

function renderSmile() {
  const el = $('smile');
  if (!el || !window.Plotly || !state.model) return;
  const s = state.model.slices.find(x => x.expMs === state.selExp) || state.model.slices[0];
  if (!s) return;
  const ov = $('smileWait'); if (ov) ov.classList.add('gone');

  const Ks = s.pts.map(p => p.K), ivs = s.pts.map(p => p.iv);
  const N = 120, lo = s.kmin, hi = s.kmax;
  const fx = [], fy = [];
  for (let i = 0; i < N; i++) {
    const k = lo + (hi - lo) * i / (N - 1);
    const w = s.fit(k);
    if (w == null) continue;
    fx.push(s.F * Math.exp(k)); fy.push(Math.sqrt(w / s.T) * 100);
  }
  const layout = Object.assign({}, LAYOUT2D, {
    xaxis: Object.assign(AXIS2D('strike  K (USD)'), { tickformat: ',.0f' }),
    yaxis: Object.assign(AXIS2D('implied vol  σ (%)'), { ticksuffix: '%' }),
    shapes: [{
      type: 'line', x0: s.F, x1: s.F, yref: 'paper', y0: 0, y1: 1,
      line: { color: 'rgba(255,143,66,.45)', width: 1, dash: 'dot' }
    }],
    annotations: [{
      x: s.F, y: 1, yref: 'paper', yanchor: 'top', showarrow: false,
      text: 'F ' + nf(s.F, 0), font: { family: PLOT_FONT.family, size: 9.5, color: C.hot },
      bgcolor: 'rgba(13,18,27,.75)', borderpad: 3
    }]
  });
  Plotly.react(el, [
    {
      type: 'scatter', mode: 'lines', x: fx, y: fy, line: { color: C.hot, width: 2.4, shape: 'spline' },
      hovertemplate: 'K %{x:,.0f}<br><b>σ %{y:.2f}%</b><extra>fit</extra>'
    },
    {
      type: 'scatter', mode: 'markers', x: Ks, y: ivs,
      marker: { size: 5.2, color: 'rgba(79,216,196,.60)', line: { width: 1, color: 'rgba(79,216,196,.95)' } },
      hovertemplate: 'K %{x:,.0f}<br>mark σ %{y:.2f}%<extra>quote</extra>'
    }
  ], layout, PLOT_CFG);

  const meta = $('smileMeta');
  if (meta) meta.textContent = s.tag + ' · T = ' + nf(s.T, 4) + 'y (' + nf(s.days, 1) + 'd) · ' +
    s.pts.length + ' OTM quotes · F = ' + nf(s.F, 2);
}

function renderTerm() {
  const el = $('term');
  if (!el || !window.Plotly || !state.model) return;
  const S = state.model.slices.filter(s => s.atm != null);
  if (S.length < 2) return;
  const ov = $('termWait'); if (ov) ov.classList.add('gone');
  const days = S.map(s => s.days), atm = S.map(s => s.atm);
  const sel = S.find(s => s.expMs === state.selExp);

  const layout = Object.assign({}, LAYOUT2D, {
    xaxis: Object.assign(AXIS2D('days to expiry'), state.termLog
      ? { type: 'log', tickvals: [1, 3, 7, 14, 30, 60, 90, 180, 365, 730] }
      : { type: 'linear' }),
    yaxis: Object.assign(AXIS2D('ATM implied vol  σ (%)'), { ticksuffix: '%' })
  });
  const traces = [{
    type: 'scatter', mode: 'lines+markers', x: days, y: atm,
    line: { color: C.tq, width: 2.2, shape: 'spline' },
    marker: { size: 5, color: '#0d121b', line: { width: 1.6, color: C.tq } },
    hovertemplate: '%{x:.1f}d<br><b>ATM σ %{y:.2f}%</b><extra></extra>'
  }];
  if (sel) traces.push({
    type: 'scatter', mode: 'markers', x: [sel.days], y: [sel.atm],
    marker: { size: 10, color: C.hot, line: { width: 2, color: '#0d121b' } },
    hovertemplate: sel.tag + '<br>ATM σ %{y:.2f}%<extra></extra>'
  });
  Plotly.react(el, traces, layout, PLOT_CFG);
}

function renderChips() {
  const box = $('expChips');
  if (!box || !state.model) return;
  const S = state.model.slices;
  const sig = S.map(s => s.expMs).join(',');
  if (box.dataset.sig !== sig) {
    box.dataset.sig = sig;
    box.innerHTML = '';
    S.forEach(s => {
      const b = document.createElement('button');
      b.className = 'chip';
      b.type = 'button';
      b.textContent = s.tag;
      b.title = nf(s.days, 1) + ' days · ' + s.pts.length + ' quotes';
      b.onclick = () => { state.selExp = s.expMs; renderChips(); renderSmile(); renderTerm(); renderTiles(); };
      box.appendChild(b);
    });
  }
  Array.from(box.children).forEach((b, i) => {
    b.classList.toggle('on', S[i] && S[i].expMs === state.selExp);
  });
}

/* ============================================================================
   7. CALIBRATED SURFACE HOOK — surface.json, published by the library itself
   ========================================================================= */
function renderCalibrated(d) {
  const wrap = $('calBody'), badge = $('calBadge');
  if (!wrap) return;
  const v = d.validation || {};
  const ok = v.is_valid === true;
  if (badge) {
    badge.className = 'verdict ' + (ok ? 'ok' : 'bad');
    badge.textContent = ok ? 'validated' : 'flagged';
  }
  const g = d.grid || {};
  let plotHtml = '';
  if (Array.isArray(g.k) && Array.isArray(g.T) && Array.isArray(g.w)) {
    plotHtml = '<div id="calPlot" class="plot mid"></div>';
  }
  const rows = [
    ['as of', d.as_of || '—'],
    ['currency', d.currency || '—'],
    [PACKAGE + ' version', d.volfoundry_version || '—'],
    ['butterfly g(k) ≥ 0', v.butterfly === true ? 'pass' : v.butterfly === false ? 'fail' : '—'],
    ['calendar ∂ₜw ≥ 0', v.calendar === true ? 'pass' : v.calendar === false ? 'fail' : '—'],
    ['density cross-check', v.density_crosscheck === true ? 'pass' : v.density_crosscheck === false ? 'fail' : '—'],
    ['domain', v.domain || '—'],
    ['tolerance', v.tolerance != null ? String(v.tolerance) : '—'],
    ['slices', Array.isArray(d.slices) ? String(d.slices.length) : '—']
  ];
  wrap.innerHTML = plotHtml +
    '<dl class="kv">' + rows.map(r => '<dt>' + r[0] + '</dt><dd>' + r[1] + '</dd>').join('') + '</dl>';

  if (plotHtml && window.Plotly) {
    const z = g.w.map((row, j) => row.map(w => (w > 0 && g.T[j] > 0) ? Math.sqrt(w / g.T[j]) * 100 : null));
    Plotly.react($('calPlot'), [{
      type: 'surface', x: g.k, y: g.T.map(t => t * 365), z,
      colorscale: SURFACE_SCALE, showscale: false, connectgaps: true,
      contours: { z: { show: true, usecolormap: true, width: 1.4 } },
      lighting: { ambient: 0.64, diffuse: 0.86, specular: 0.1, roughness: 0.62 },
      hovertemplate: 'k %{x:.3f}<br>%{y:.1f}d<br><b>σ %{z:.2f}%</b><extra></extra>'
    }], {
      paper_bgcolor: 'rgba(0,0,0,0)', margin: { l: 0, r: 0, t: 0, b: 0 }, font: PLOT_FONT,
      scene: {
        xaxis: AXIS3D('k'), yaxis: AXIS3D('days'), zaxis: AXIS3D('σ (%)'),
        aspectmode: 'manual', aspectratio: { x: 1.5, y: 1.1, z: 0.7 },
        camera: { eye: { x: 1.6, y: -1.5, z: 0.7 } }, bgcolor: 'rgba(0,0,0,0)'
      }
    }, PLOT_CFG);
  }
}

function loadCalibrated() {
  fetch('surface.json', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : Promise.reject(new Error('no file')))
    .then(d => { if (d && typeof d === 'object') renderCalibrated(d); })
    .catch(() => { /* absent is the expected state before v0.1.0 publishes */ });
}

/* ============================================================================
   8. CHROME — controls, scrollspy, KaTeX
   ========================================================================= */
function bindControls() {
  const ccy = $('ccySeg');
  if (ccy) ccy.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b || b.dataset.ccy === state.ccy) return;
    state.ccy = b.dataset.ccy;
    Array.from(ccy.children).forEach(x => x.classList.toggle('on', x === b));
    // hard reset of every currency-scoped statistic
    state.price = state.prevPrice = state.refPrice = null;
    state.ticks = []; state.model = null; state.grid = null; state.selExp = null;
    state.prevIv.clear(); state.churn = 0; state.churnMag = 0;
    state.tape = []; state.firstBook = false;
    renderTape();
    document.querySelectorAll('.overlay').forEach(o => o.classList.remove('gone'));
    ['bigPrice', 'tAtm', 'tAtm30', 'tQuotes', 'tChurn', 'tSkew', 'tMove']
      .forEach(id => { const e2 = $(id); if (e2) e2.textContent = '—'; });
    document.querySelectorAll('.ccyLab').forEach(n => { n.textContent = state.ccy; });
    sock.switchCcy();
  });

  const ax = $('axisSeg');
  if (ax) ax.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b || b.dataset.axis === state.axis) return;
    state.axis = b.dataset.axis;
    Array.from(ax.children).forEach(x => x.classList.toggle('on', x === b));
    if (state.model) { state.grid = buildGrid(state.model, state.axis); renderSurface(); }
  });

  const raw = $('rawToggle');
  if (raw) raw.addEventListener('click', () => {
    state.showRaw = !state.showRaw;
    raw.classList.toggle('on', state.showRaw);
    raw.textContent = state.showRaw ? 'quotes: on' : 'quotes: off';
    renderSurface();
  });

  const tg = $('termSeg');
  if (tg) tg.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    const wantLog = b.dataset.term === 'log';
    if (wantLog === state.termLog) return;
    state.termLog = wantLog;
    Array.from(tg.children).forEach(x => x.classList.toggle('on', x === b));
    renderTerm();
  });

  const cam = $('camReset');
  if (cam) cam.addEventListener('click', () => {
    state.camera = { eye: { x: 1.36, y: -1.34, z: 0.60 }, center: { x: 0, y: 0, z: -0.10 } };
    renderSurface();
  });
}

function scrollSpy() {
  const links = Array.from(document.querySelectorAll('.tabs a'));
  const map = new Map();
  links.forEach(a => {
    const t = document.querySelector(a.getAttribute('href'));
    if (t) map.set(t, a);
  });
  if (!map.size) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (en.isIntersecting) {
        links.forEach(l => l.classList.remove('on'));
        const a = map.get(en.target);
        if (a) a.classList.add('on');
      }
    });
  }, { rootMargin: '-72px 0px -62% 0px', threshold: 0 });
  map.forEach((_, sec) => io.observe(sec));
}

function typesetMath() {
  let tries = 0;
  (function attempt() {
    if (window.renderMathInElement) {
      window.renderMathInElement(document.body, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\(', right: '\\)', display: false }
        ],
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option'],
        throwOnError: false
      });
      return;
    }
    if (tries++ < 120) setTimeout(attempt, 100);
  })();
}

function boot() {
  document.querySelectorAll('[data-repo]').forEach(a => { a.href = REPO_URL; });
  document.querySelectorAll('[data-repo-label]').forEach(n => { n.textContent = REPO_LABEL; });
  document.querySelectorAll('[data-pkg]').forEach(n => { n.textContent = PACKAGE; });
  const y = $('year'); if (y) y.textContent = String(new Date().getUTCFullYear());
  bindControls();
  scrollSpy();
  typesetMath();
  renderTape();
  loadCalibrated();
  sock.start();
  window.addEventListener('resize', () => {
    if (!window.Plotly) return;
    ['surface', 'smile', 'term'].forEach(id => {
      const el = $(id);
      if (el && el.data) Plotly.Plots.resize(el);
    });
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
