"use strict";

// ---------------------------------------------------------------------------
// Real-time straightedge-and-compass animator.
//
// The backend sends an ordered stream of drawing commands.  This renderer plays
// them one at a time with requestAnimationFrame: every command is drawn live
// (circles/arcs sweep, lines grow, points pop, the polygon strokes edge by edge),
// and the command list on the right is highlighted in lockstep with the drawing.
// Nothing is pre-rendered; frame N shows commands [0..i) fully plus command i in
// mid-progress, exactly matching the highlighted row.
// ---------------------------------------------------------------------------

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

// Logical drawing size (world->screen math is in these units); the backing store is
// supersampled by PIX for a high-DPI, crisp figure regardless of display scale.
const VIEW = 900;
const PIX = Math.min(3, Math.max(2, Math.round((window.devicePixelRatio || 1) * 2)));
canvas.width = VIEW * PIX;
canvas.height = VIEW * PIX;

const els = {
  nInput: document.getElementById("n-input"),
  go: document.getElementById("go-btn"),
  play: document.getElementById("play-btn"),
  step: document.getElementById("step-btn"),
  replay: document.getElementById("replay-btn"),
  speed: document.getElementById("speed"),
  speedVal: document.getElementById("speed-val"),
  decay: document.getElementById("decay"),
  decayVal: document.getElementById("decay-val"),
  status: document.getElementById("status"),
  factor: document.getElementById("factorization"),
  list: document.getElementById("cmd-list"),
  count: document.getElementById("cmd-count"),
  theme: document.getElementById("theme-btn"),
  zoomIn: document.getElementById("zoom-in"),
  zoomOut: document.getElementById("zoom-out"),
  zoomReset: document.getElementById("zoom-reset"),
};

// Canvas label/ink color follows the active theme (light vs dark).
function ink() {
  return document.body.classList.contains("light") ? "#1a2230" : "#c8d2de";
}

const COLORS = {
  mainCircle: "#4ea1ff",
  auxCircle: "#3a5a78",
  line: "#7d8794",
  vertex: "#ff6b6b",
  carlyle: "#caa24a",
  helper: "#7d8794",
  polygon: "#6ad27e",
  apex: "#caa24a",
  emphasis: "#e64980",  // temporary highlight of the objects the current step depends on
};

let state = null; // { items, len } and playback fields

// ---- math / easing --------------------------------------------------------
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
const easeOut = (t) => 1 - Math.pow(1 - t, 3);
const clamp01 = (t) => (t < 0 ? 0 : t > 1 ? 1 : t);

// ---------------------------------------------------------------------------
// Build a renderable model from the command document.
// ---------------------------------------------------------------------------
function buildModel(doc) {
  const pts = {}; // id -> {x, y}
  let mainCircleId = null; // the circumscribed circle == the first circle drawn
  const vertexIds = new Set();
  for (const c of doc.commands) {
    if (c.op === "point") {
      pts[c.id] = { x: c.at[0], y: c.at[1] };
    } else if (c.op === "circle" && mainCircleId === null) {
      mainCircleId = c.id;
    } else if (c.op === "polygon") {
      c.vertices.forEach((id) => vertexIds.add(id));
    }
  }

  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const items = [];
  const byId = {};                  // command id -> its renderable item (for emphasis)
  const add = (id, item) => { items.push(item); if (id != null) byId[id] = item; return item; };
  for (const c of doc.commands) {
    if (c.op === "point") {
      const p = pts[c.id];
      const isVertex = vertexIds.has(c.id);
      const isCarlyle = c.def && c.def.type === "carlyle_center";
      const isApex = (c.label === "A");
      // only show short, tidy labels (e.g. O, A, W, V0); hide long internal labels
      const label = (c.label && c.label.length <= 3) ? c.label : "";
      // a point's inputs are the loci/points its def references (intersection of two
      // loci, or the diameter endpoints A,B a Carlyle center is the midpoint of)
      const deps = (c.def && Array.isArray(c.def.of)) ? c.def.of.slice() : [];
      add(c.id, {
        op: "point", cmd: c, dur: 240, perm: isVertex, deps,
        geom: { x: p.x, y: p.y, label, isVertex, isCarlyle, isApex },
      });
    } else if (c.op === "line") {
      const a = pts[c.p1], b = pts[c.p2];
      add(c.id, { op: "line", cmd: c, dur: 380, perm: false, deps: [c.p1, c.p2],
                  geom: { a, b, kind: c.kind } });
    } else if (c.op === "circle") {
      const ctr = pts[c.center];
      let r, deps;
      if (c.radius.through) { r = dist(ctr, pts[c.radius.through]); deps = [c.center, c.radius.through]; }
      else { const [s1, s2] = c.radius.segment; r = dist(pts[s1], pts[s2]); deps = [c.center, s1, s2]; }
      const main = c.id === mainCircleId;       // the original circumscribed circle
      add(c.id, { op: "circle", cmd: c, dur: main ? 650 : 460, perm: main, deps,
                  geom: { ctr, r, main } });
    } else if (c.op === "polygon") {
      const vs = c.vertices.map((id) => pts[id]);
      add(c.id, { op: "polygon", cmd: c, dur: Math.min(1600, 120 * vs.length), perm: true,
                  deps: [], geom: { vs } });
    } else if (c.op === "note") {
      // a compute/explanation step: draws nothing new, just highlights its referenced
      // points (deps) while it is the current step and shows its text in the panel
      add(c.id, { op: "note", cmd: c, dur: 900, perm: false, deps: (c.refs || []).slice(),
                  geom: null });
    }
  }
  return { doc, items, pts, byId };
}

// ---------------------------------------------------------------------------
// World -> screen transform (fit all geometry, equal aspect, y flipped).
// ---------------------------------------------------------------------------
function computeTransform(model) {
  let minx = -1, maxx = 1, miny = -1, maxy = 1;
  const grow = (x, y) => {
    if (x < minx) minx = x; if (x > maxx) maxx = x;
    if (y < miny) miny = y; if (y > maxy) maxy = y;
  };
  for (const it of model.items) {
    if (it.op === "point") grow(it.geom.x, it.geom.y);
    else if (it.op === "circle") {
      grow(it.geom.ctr.x - it.geom.r, it.geom.ctr.y - it.geom.r);
      grow(it.geom.ctr.x + it.geom.r, it.geom.ctr.y + it.geom.r);
    }
  }
  // keep within a sane window so far-off helper points don't shrink the figure, but wide
  // enough to include the Carlyle diameter endpoints B=(s,q) for small n (e.g. n=17: B can
  // reach y=-4) so the current step's new point is actually visible.
  const LIM = 5.0;
  minx = Math.max(minx, -LIM); maxx = Math.min(maxx, LIM);
  miny = Math.max(miny, -LIM); maxy = Math.min(maxy, LIM);
  const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2;
  const range = Math.max(maxx - minx, maxy - miny) * 1.12;
  const margin = 36;
  const scale = (VIEW - 2 * margin) / range;
  model.tf = {
    scale,
    ox: VIEW / 2 - cx * scale,
    oy: VIEW / 2 + cy * scale,
  };
}

function sx(x) { return state.view.ox + x * state.view.scale; }
function sy(y) { return state.view.oy - y * state.view.scale; }

// ---------------------------------------------------------------------------
// Per-item drawing at progress t in [0,1].  `alpha` is the layer opacity used by
// the decay effect: older elements are drawn fainter.  All draw helpers multiply
// their own opacity into `layerAlpha`.
// ---------------------------------------------------------------------------
let layerAlpha = 1;
let boldF = 1; // >1 thickens/enlarges the current (newly drawn) object so it stands out

function drawItem(it, t, alpha, emph) {
  t = clamp01(t);
  layerAlpha = alpha;
  boldF = emph ? 2.2 : 1;
  switch (it.op) {
    case "circle": drawCircle(it.geom, t); break;
    case "line": drawLine(it.geom, t); break;
    case "point": drawPoint(it.geom, t); break;
    case "polygon": drawPolygon(it.geom, t); break;
  }
  ctx.globalAlpha = 1;
  layerAlpha = 1;
  boldF = 1;
}

function drawCircle(g, t) {
  ctx.globalAlpha = layerAlpha;
  ctx.beginPath();
  ctx.arc(sx(g.ctr.x), sy(g.ctr.y), g.r * state.view.scale, -Math.PI / 2,
          -Math.PI / 2 + 2 * Math.PI * easeInOut(t));
  ctx.strokeStyle = g.main ? COLORS.mainCircle : COLORS.auxCircle;
  ctx.lineWidth = (g.main ? 2 : 1) * boldF;
  if (!g.main) ctx.setLineDash([4, 4]);
  ctx.stroke();
  ctx.setLineDash([]);
}

function lineEndpoints(g) {
  const dx = g.b.x - g.a.x, dy = g.b.y - g.a.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const BIG = 12;
  if (g.kind === "segment") return { e1: g.a, e2: g.b };
  if (g.kind === "ray") return { e1: g.a, e2: { x: g.a.x + ux * BIG, y: g.a.y + uy * BIG } };
  // full line: extend both ways from the midpoint
  const mx = (g.a.x + g.b.x) / 2, my = (g.a.y + g.b.y) / 2;
  return {
    e1: { x: mx - ux * BIG, y: my - uy * BIG },
    e2: { x: mx + ux * BIG, y: my + uy * BIG },
  };
}

function drawLine(g, t) {
  const { e1, e2 } = lineEndpoints(g);
  const tt = easeInOut(t);
  ctx.globalAlpha = layerAlpha;
  ctx.beginPath();
  ctx.moveTo(sx(e1.x), sy(e1.y));
  ctx.lineTo(sx(e1.x + (e2.x - e1.x) * tt), sy(e1.y + (e2.y - e1.y) * tt));
  ctx.strokeStyle = COLORS.line;
  ctx.lineWidth = 1 * boldF;
  ctx.stroke();
}

function drawPoint(g, t) {
  const e = easeOut(t);
  let color = COLORS.helper, r = 3;
  if (g.isVertex) { color = COLORS.vertex; r = 4.5; }
  else if (g.isApex) { color = COLORS.apex; r = 3.5; }
  else if (g.isCarlyle) { color = COLORS.carlyle; r = 3; }
  if (boldF > 1) r *= 1.7;            // enlarge the current (newly drawn) point
  ctx.beginPath();
  ctx.arc(sx(g.x), sy(g.y), r * e, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.globalAlpha = (g.isVertex || g.isApex ? 1 : 0.8) * layerAlpha;
  ctx.fill();
  // label vertices/apex always, and the current (bold) point so each step's new
  // object — e.g. the Carlyle center K — is marked by name while it is drawn.
  if ((g.isVertex || g.isApex || boldF > 1) && t > 0.4 && g.label) {
    ctx.globalAlpha = layerAlpha;
    ctx.fillStyle = ink();
    ctx.font = "11px ui-monospace, monospace";
    ctx.fillText(g.label, sx(g.x) + 6, sy(g.y) - 6);
  }
}

function drawPolygon(g, t) {
  const n = g.vs.length;
  const total = n; // closed loop
  const drawn = total * easeInOut(t);
  ctx.globalAlpha = layerAlpha;
  ctx.beginPath();
  ctx.moveTo(sx(g.vs[0].x), sy(g.vs[0].y));
  for (let k = 1; k <= Math.floor(drawn); k++) {
    const v = g.vs[k % n];
    ctx.lineTo(sx(v.x), sy(v.y));
  }
  const frac = drawn - Math.floor(drawn);
  if (frac > 0 && Math.floor(drawn) < total) {
    const a = g.vs[Math.floor(drawn) % n], b = g.vs[(Math.floor(drawn) + 1) % n];
    ctx.lineTo(sx(a.x + (b.x - a.x) * frac), sy(a.y + (b.y - a.y) * frac));
  }
  ctx.strokeStyle = COLORS.polygon;
  ctx.lineWidth = 2.5 * boldF;
  ctx.stroke();
  if (t >= 1) {
    ctx.fillStyle = "rgba(106,210,126,0.12)";
    ctx.beginPath();
    ctx.moveTo(sx(g.vs[0].x), sy(g.vs[0].y));
    for (let k = 1; k < n; k++) ctx.lineTo(sx(g.vs[k].x), sy(g.vs[k].y));
    ctx.closePath();
    ctx.fill();
  }
}

// Temporarily emphasize the objects the current step depends on (its inputs): the two
// points of a new line, the line & circle a new point intersects, or a Carlyle circle's
// center and apex A.  Drawn just before the new element, so it reads as "from these".
// Ring one object (point/line/circle) in the emphasis color.
function emphasizeObject(d) {
  if (!d || !d.geom) return;
  ctx.globalAlpha = 1;
  ctx.strokeStyle = COLORS.emphasis;
  ctx.fillStyle = COLORS.emphasis;
  if (d.op === "point") {
    const px = sx(d.geom.x), py = sy(d.geom.y);
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(px, py, 9, 0, 2 * Math.PI); ctx.stroke();
    ctx.beginPath(); ctx.arc(px, py, 4.5, 0, 2 * Math.PI); ctx.fill();
  } else if (d.op === "line") {
    const { e1, e2 } = lineEndpoints(d.geom);
    ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(sx(e1.x), sy(e1.y)); ctx.lineTo(sx(e2.x), sy(e2.y)); ctx.stroke();
  } else if (d.op === "circle") {
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(sx(d.geom.ctr.x), sy(d.geom.ctr.y), d.geom.r * state.view.scale, 0, 2 * Math.PI);
    ctx.stroke();
  }
}

// Highlight the objects a step depends on (its inputs).
function drawEmphasis(item) {
  if (!item || !item.deps) return;
  for (const id of item.deps) emphasizeObject(state.byId[id]);
}

// ---------------------------------------------------------------------------
// Frame rendering: commands [0..idx) full, command idx at progress.
// ---------------------------------------------------------------------------
function render(idx, progress) {
  ctx.setTransform(PIX, 0, 0, PIX, 0, 0); // map logical VIEW units onto the hi-DPI backing
  ctx.clearRect(0, 0, VIEW, VIEW);
  const last = Math.min(idx, state.items.length);
  if (state.huge) renderHuge(idx, last);
  else renderAll(idx, last);
  if (idx < state.items.length) {
    const cur = state.items[idx];
    drawEmphasis(cur);                 // highlight the inputs this step uses
    drawItem(cur, progress, 1, true);  // draw the new object (bold, in its own color)
    emphasizeObject(cur);              // and ring the new object so it's clearly stressed
  }
  updatePanel(idx);
}

// Normal path: draw every prior command; auxiliary ones fade with decay.
function renderAll(idx, last) {
  const decay = state.decay || 0;
  for (let k = 0; k < last; k++) {
    const it = state.items[k];
    // permanent elements (main circle, polygon, vertices) never fade.
    let a = 1;
    if (!it.perm && decay > 0) {
      a = Math.pow(1 - decay, idx - k);
      if (a < 0.012) continue; // fully faded -> skip
    }
    drawItem(it, 1, a);
  }
}

// Huge path (e.g. 65537-gon): bound per-frame work to stay responsive. Always show the
// main circle and (once reached) the polygon; every other element — INCLUDING completed
// vertices — is drawn only within a recent window. (Drawing all ~65k vertex dots per
// frame is the cost this avoids; the full vertex set is conveyed by the polygon outline.)
function renderHuge(idx, last) {
  const decay = state.decay || 0;
  const AUX = 2000;
  if (state.mainIdx >= 0 && state.mainIdx < last) drawItem(state.items[state.mainIdx], 1, 1);
  const start = Math.max(0, idx - AUX);
  for (let k = start; k < last; k++) {
    if (k === state.mainIdx) continue;
    const it = state.items[k];
    let a = 1;
    if (!it.perm && decay > 0) {
      a = Math.pow(1 - decay, idx - k);
      if (a < 0.012) continue;
    }
    drawItem(it, 1, a);
  }
  if (state.polyIdx >= 0 && state.polyIdx < last && state.polyIdx < start) {
    drawItem(state.items[state.polyIdx], 1, 1); // completed polygon, outside the window
  }
}

// ---------------------------------------------------------------------------
// Playback control
// ---------------------------------------------------------------------------
function advance(dt) {
  let guard = 0;
  while (state.playing && guard++ < 1000) {
    if (state.index >= state.items.length) { finish(); return; }
    const dur = state.items[state.index].dur / state.speed;
    state.progress += dt / dur;
    if (state.progress < 1) break;
    state.progress -= 1;
    dt = 0;
    state.index += 1;
    if (state.stepTarget !== null && state.index >= state.stepTarget) {
      state.playing = false; state.stepTarget = null; state.progress = 0;
    }
    if (state.index >= state.items.length) { finish(); return; }
  }
}

function frame(ts) {
  if (!state || !state.playing) return;
  const dt = Math.min(ts - state.lastTs, 64);
  state.lastTs = ts;
  advance(dt);
  render(state.index, state.progress);
  setStatusPlaying();
  if (state.playing) state.raf = requestAnimationFrame(frame);
}

function play() {
  if (!state || state.playing) return;
  if (state.index >= state.items.length) return;
  state.playing = true;
  state.lastTs = performance.now();
  els.play.textContent = "暂停";
  state.raf = requestAnimationFrame(frame);
}

function pause() {
  if (!state) return;
  state.playing = false;
  if (state.raf) { cancelAnimationFrame(state.raf); state.raf = null; }
  els.play.textContent = "继续";
}

function togglePlay() { if (state.playing) pause(); else play(); }

function step() {
  if (!state || state.index >= state.items.length) return;
  pause();
  state.stepTarget = state.index + 1;
  state.playing = true;
  state.lastTs = performance.now();
  state.raf = requestAnimationFrame(frame);
}

function replay() {
  if (!state) return;
  state.index = 0; state.progress = 0; state.stepTarget = null;
  play();
}

function seek(i) {
  if (!state) return;
  pause();
  state.stepTarget = null;
  i = Math.max(0, Math.min(i, state.items.length));
  if (i >= state.items.length) { finish(); return; }
  state.index = i; state.progress = 1; // show through command i
  render(state.index, state.progress);
  setStatusPlaying();
}

function finish() {
  state.playing = false;
  state.index = state.items.length;
  state.progress = 0;
  els.play.textContent = "继续";
  render(state.index, 0);
  els.status.className = "status ok";
  els.status.textContent = `完成：正 ${state.doc.n} 边形，共 ${state.items.length} 条绘图命令。`;
}

function setStatusPlaying() {
  if (state.index >= state.items.length) return;
  els.status.className = "status";
  const it = state.items[state.index];
  els.status.textContent = `绘制中 ${state.index + 1}/${state.items.length}：${it.cmd.desc || it.op}`;
}

// ---------------------------------------------------------------------------
// Command-list panel (right pane), kept 1:1 with the animation.
// ---------------------------------------------------------------------------
const OP_LABEL = { point: "点", line: "线", circle: "圆", polygon: "形", note: "算" };

function rowHtml(i) {
  const it = state.items[i];
  return `<li data-idx="${i}"><span class="idx">${i + 1}</span>` +
    `<span class="op">${OP_LABEL[it.op] || it.op}</span>` +
    `${escapeHtml(it.cmd.desc || it.op)}</li>`;
}

const PANEL_WINDOW = 48; // rows kept in the DOM for a virtualized (huge) command list

function buildPanel() {
  els.count.textContent = `(${state.items.length})`;
  if (state.huge) {                 // virtualize: render only a moving window of rows
    state.virtual = true;
    state.rows = null;
    state.winStart = -1;
    els.list.innerHTML = "";
    updatePanel(0);
    return;
  }
  state.virtual = false;
  let html = "";
  for (let i = 0; i < state.items.length; i++) html += rowHtml(i);
  els.list.innerHTML = html;
  state.rows = Array.from(els.list.children);
}

function updatePanel(idx) {
  if (state.virtual) {
    const start = Math.max(0, idx - 6);
    if (start !== state.winStart) {
      const end = Math.min(state.items.length, start + PANEL_WINDOW);
      let html = "";
      for (let i = start; i < end; i++) html += rowHtml(i);
      els.list.innerHTML = html;
      state.winStart = start;
    }
    for (const li of els.list.children) {
      const i = +li.dataset.idx;
      li.classList.toggle("done", i < idx);
      li.classList.toggle("current", i === idx);
    }
    return;
  }
  if (!state.rows) return;
  for (let i = 0; i < state.rows.length; i++) {
    const li = state.rows[i];
    li.classList.toggle("done", i < idx);
    li.classList.toggle("current", i === idx);
  }
  if (idx !== state.lastScrollIdx) {     // only scroll when the current row actually changes
    const cur = state.rows[Math.min(idx, state.rows.length - 1)];
    if (cur) cur.scrollIntoView({ block: "nearest" });
    state.lastScrollIdx = idx;
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// ---------------------------------------------------------------------------
// Browser-side cache (IndexedDB).  The server keeps only the Fermat-prime building
// blocks; every other n is built on demand and cached here, in the user's browser, so
// it loads instantly next time and is cleared whenever the user clears browser data.
// ---------------------------------------------------------------------------
const CACHE_DB = "ngon-cache";
const CACHE_STORE = "constructions";
const CACHE_VERSION = 6; // bump to invalidate stale browser caches if the format changes

function idbOpen() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(CACHE_DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(CACHE_STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function cacheGet(n) {
  try {
    const db = await idbOpen();
    return await new Promise((resolve) => {
      const req = db.transaction(CACHE_STORE, "readonly").objectStore(CACHE_STORE).get(n);
      req.onsuccess = () => {
        const rec = req.result;
        resolve(rec && rec.v === CACHE_VERSION ? rec.doc : null);
      };
      req.onerror = () => resolve(null);
    });
  } catch (e) {
    return null; // private mode / unsupported -> just skip the cache
  }
}

async function cachePut(n, doc) {
  try {
    const db = await idbOpen();
    db.transaction(CACHE_STORE, "readwrite").objectStore(CACHE_STORE)
      .put({ v: CACHE_VERSION, doc }, n);
  } catch (e) { /* ignore cache write failures */ }
}

// ---------------------------------------------------------------------------
// Load a construction (browser cache first, then the server) and start animating.
// ---------------------------------------------------------------------------
async function loadN(nOverride) {
  if (nOverride != null) els.nInput.value = String(nOverride);
  const n = parseInt(els.nInput.value, 10);
  if (!Number.isInteger(n) || n < 1) {
    setError("请输入一个正整数 n。");
    return;
  }
  els.go.disabled = true;
  els.status.className = "status";
  els.status.textContent = `正在计算正 ${n} 边形的作图命令…`;
  try {
    let doc = await cacheGet(n);
    if (!doc) {
      const resp = await fetch(`/api/construct?n=${n}`);
      doc = await resp.json();
      if (doc && doc.constructible && doc.commands && doc.commands.length) {
        cachePut(n, doc); // remember it in the browser for next time
      }
    }
    onDoc(doc);
  } catch (e) {
    setError("请求失败：" + e.message);
  } finally {
    els.go.disabled = false;
  }
}

function onDoc(doc) {
  if (state) { state.playing = false; if (state.raf) cancelAnimationFrame(state.raf); }
  if (doc.error) { els.factor.innerHTML = ""; setError(doc.error); return; }
  showFactorization(doc.n, doc.factorization);  // n's prime factorization (MathJax)
  if (!doc.constructible) {
    clearStage();
    setError(`正 ${doc.n} 边形不可用尺规作图。${doc.reason || ""}`);
    return;
  }
  if (doc.supported === false || !doc.commands || doc.commands.length === 0) {
    clearStage();
    els.status.className = "status";
    els.status.textContent = doc.note || `正 ${doc.n} 边形可作图，但暂无可用的命令流。`;
    return;
  }

  const model = buildModel(doc);
  computeTransform(model);
  const huge = model.items.length > 20000; // e.g. the 65537-gon (~260k commands)
  state = {
    doc, items: model.items, byId: model.byId,
    view: { ...model.tf }, fit: { ...model.tf }, // live (zoom/pan) and baseline transforms
    index: 0, progress: 0, playing: false, speed: parseFloat(els.speed.value),
    decay: parseFloat(els.decay.value),
    stepTarget: null, lastTs: 0, raf: null, rows: null,
    huge,
    mainIdx: model.items.findIndex((it) => it.op === "circle" && it.geom.main),
    polyIdx: model.items.findIndex((it) => it.op === "polygon"),
    virtual: false, winStart: -1, lastScrollIdx: -1,
  };
  buildPanel();
  els.play.disabled = false;
  els.step.disabled = false;
  els.replay.disabled = false;
  render(0, 0);

  // Optional deep-link: ?frame=end or ?frame=<index> renders a static frame
  // (used for previews / verification); otherwise autoplay.
  const frameParam = new URLSearchParams(location.search).get("frame");
  if (frameParam === "end") { finish(); }
  else if (frameParam !== null && frameParam !== "") { seek(Math.max(0, parseInt(frameParam, 10) | 0)); }
  else { play(); }
}

function clearStage() {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  els.list.innerHTML = "";
  els.count.textContent = "";
  els.play.disabled = els.step.disabled = els.replay.disabled = true;
  state = null;
}

// Render n's prime factorization as LaTeX via MathJax, e.g. 12 = 2^{2} \cdot 3.
function showFactorization(n, factorization) {
  const keys = factorization ? Object.keys(factorization) : [];
  let latex;
  if (!keys.length) {
    latex = `${n}`;                       // n = 1 has no prime factors
  } else {
    const primes = keys.map(Number).sort((a, b) => a - b);
    const parts = primes.map((p) => {
      const e = factorization[p];
      return e === 1 ? `${p}` : `${p}^{${e}}`;
    });
    latex = `${n} = ${parts.join(" \\cdot ")}`;
  }
  els.factor.innerHTML = "\\(" + latex + "\\)";
  if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([els.factor]).catch(() => {});
}

function setError(msg) {
  els.status.className = "status bad";
  els.status.textContent = msg;
}

// ---- wiring ---------------------------------------------------------------
els.go.addEventListener("click", () => loadN());
els.nInput.addEventListener("keydown", (e) => { if (e.key === "Enter") loadN(); });
els.play.addEventListener("click", togglePlay);
els.step.addEventListener("click", step);
els.replay.addEventListener("click", replay);
els.list.addEventListener("click", (e) => {            // seek by clicking a command row
  const li = e.target.closest("li");
  if (li && li.dataset.idx != null) seek(+li.dataset.idx);
});
els.speed.addEventListener("input", () => {
  els.speedVal.textContent = parseFloat(els.speed.value).toFixed(2) + "×";
  if (state) state.speed = parseFloat(els.speed.value);
});

els.decay.addEventListener("input", () => {
  els.decayVal.textContent = parseFloat(els.decay.value).toFixed(2);
  if (state) { state.decay = parseFloat(els.decay.value); renderCurrent(); }
});

// ---------------------------------------------------------------------------
// Zoom (buttons / Ctrl +-/ wheel) and pan (mouse drag) over the figure.
// ---------------------------------------------------------------------------
function renderCurrent() { if (state) render(state.index, state.progress); }

// Zoom by factor f about the logical point (mx, my); keeps that point fixed.
function zoomAbout(mx, my, f) {
  if (!state) return;
  const v = state.view;
  v.scale *= f;
  v.ox = mx - (mx - v.ox) * f;
  v.oy = my - (my - v.oy) * f;
  renderCurrent();
}

function zoomCenter(f) { zoomAbout(VIEW / 2, VIEW / 2, f); }

function resetView() {
  if (!state) return;
  state.view = { ...state.fit };
  renderCurrent();
}

// Convert a client (CSS px) coordinate to logical VIEW coordinates.
function toView(clientX, clientY) {
  const r = canvas.getBoundingClientRect();
  return [(clientX - r.left) * (VIEW / r.width), (clientY - r.top) * (VIEW / r.height)];
}

els.zoomIn.addEventListener("click", () => zoomCenter(1.25));
els.zoomOut.addEventListener("click", () => zoomCenter(1 / 1.25));
els.zoomReset.addEventListener("click", resetView);

canvas.addEventListener("wheel", (e) => {
  if (!state) return;
  e.preventDefault();
  const [mx, my] = toView(e.clientX, e.clientY);
  zoomAbout(mx, my, e.deltaY < 0 ? 1.1 : 1 / 1.1);
}, { passive: false });

// Ctrl/Cmd + +/-/0 to zoom in / out / reset.
window.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey)) return;
  if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomCenter(1.25); }
  else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoomCenter(1 / 1.25); }
  else if (e.key === "0") { e.preventDefault(); resetView(); }
});

// Pan by dragging with the mouse.
let dragging = null;
canvas.addEventListener("pointerdown", (e) => {
  if (!state) return;
  dragging = { x: e.clientX, y: e.clientY };
  canvas.setPointerCapture(e.pointerId);
  canvas.classList.add("grabbing");
});
canvas.addEventListener("pointermove", (e) => {
  if (!dragging || !state) return;
  const r = canvas.getBoundingClientRect();
  const k = VIEW / r.width;
  state.view.ox += (e.clientX - dragging.x) * k;
  state.view.oy += (e.clientY - dragging.y) * k;
  dragging = { x: e.clientX, y: e.clientY };
  renderCurrent();
});
function endDrag() { dragging = null; canvas.classList.remove("grabbing"); }
canvas.addEventListener("pointerup", endDrag);
canvas.addEventListener("pointercancel", endDrag);

function applyTheme(light) {
  document.body.classList.toggle("light", light);
  els.theme.textContent = light ? "深色" : "浅色";
  try { localStorage.setItem("ngon-theme", light ? "light" : "dark"); } catch (e) { /* ignore */ }
  if (state) render(state.index, state.progress); // redraw labels in the new ink color
}
els.theme.addEventListener("click", () => applyTheme(!document.body.classList.contains("light")));
applyTheme((() => {
  const q = new URLSearchParams(location.search).get("theme");
  if (q === "light" || q === "dark") return q === "light";
  try {
    const stored = localStorage.getItem("ngon-theme");
    if (stored) return stored === "light";
  } catch (e) { /* ignore */ }
  return true; // default to light
})());

// initial draw (honor ?n= and ?decay= deep-links)
const _boot = new URLSearchParams(location.search);
const _bootDecay = _boot.get("decay");
if (_bootDecay !== null && _bootDecay !== "") {
  els.decay.value = _bootDecay;
  els.decayVal.textContent = parseFloat(_bootDecay).toFixed(2);
}
// Only auto-plot when an n is given via the URL (e.g. a shared ?n= link); on a plain
// launch, wait for the user to enter n and click 作图.
const _bootN = _boot.get("n");
if (_bootN) {
  loadN(parseInt(_bootN, 10));
} else {
  els.status.textContent = "输入一个正整数 n，然后点击「作图」。";
}
