// 丝袜纹理工具 UI. The server owns all state; this file draws it and turns pointer input into edits.
//
// Coordinates: "view" px are CSS px on the stage canvas; image coords are continuous (pixel i spans [i, i+1)).
// The server works in pixel-centre coords (pixel i is centred on i), so values cross the wire shifted by 0.5.

import { createLook, fillRange } from './look.js';
import { LANG, t, translatePage } from './i18n.js';

const $ = (s) => document.querySelector(s);

translatePage();                         // the page's own text, before anything reads it

const S = {
  mode: 'edit',         // 'edit' (引导) or 'look' (纹理)
  doc: null,            // server state of the open document
  art: null,            // decoded art image
  masks: new Map(),     // region id -> {canvas, ctx, v, want, color}
  courses: new Map(),   // region id -> {v, want, courses: Path2D, wales: Path2D, walls: Path2D}
  strokes: [],          // {id, region, pts (server coords, flat), path}
  dividers: [],         // the user's 隔开 lines: {id, pts (server coords, flat), path}
  wallHover: null,      // wall under the pointer (隔开 tool): {at: image point, path: Path2D to highlight}
  pending: null,        // stroke drawn locally and not yet confirmed by the server
  view: { s: 1, x: 0, y: 0 },
  tool: 'segment',
  current: null,        // selected region id
  brush: 40,            // brush radius in image px
  show: { regions: true, strokes: true, courses: true, wales: false, walls: true, coverage: false },
  coverage: null,       // {v, want, canvas, covered, pixels}
  segPending: null,     // click being segmented: {x, y, subtract} in image coords
  tiers: null,          // outlines of the last click's SAM candidates: {click, paths: [Path2D]}
  tierHover: null,      // tier under the pointer in the floating chooser
  hover: null,          // stroke id under the pointer (走向 tool)
  mouse: null,          // last pointer position in view px
  drag: null,
  space: false,
  painting: false,
  inflightPaint: 0,
  solving: null,
};

// colours the canvas needs, read once from the stylesheet's tokens
const css = getComputedStyle(document.documentElement);
const TOKENS = { stage: css.getPropertyValue('--stage').trim(), ink: css.getPropertyValue('--grey-950').trim() };

const cv = $('#view');
const ctx = cv.getContext('2d');
const stage = $('#stage');
const lookUI = createLook({ getDoc: () => S.doc, getArt: () => S.art, request, edit, flash,
  focusByKeyboard: () => !focusByPointer });

// 纹理 opens once some painted region has a 走向 line: before that there is no texture to look at.
function canLook(st = S.doc) {
  return !!st && st.regions.some((r) => r.strokes > 0 && r.status !== 'empty');
}

const LOOK_LOCKED = t('先给一个部位画走向线，才能看纹理');

// The page is in the URL (?page=look), so a reload (or the reload after an update) stays on it.
let wantPage = new URLSearchParams(location.search).get('page');

function setMode(m) {
  if (m === 'look' && !canLook()) m = 'edit';
  const changed = S.mode !== m;
  S.mode = m;
  document.body.dataset.mode = m;
  for (const b of document.querySelectorAll('.mode')) b.setAttribute('aria-selected', String(b.dataset.mode === m));
  const url = new URL(location.href);
  if (m === 'look') url.searchParams.set('page', 'look'); else url.searchParams.delete('page');
  if (url.href !== location.href) history.replaceState(null, '', url);
  if (!changed) return;
  if (m === 'look') { S.drag = null; closeMenus(); lookUI.enter(); } else { lookUI.leave(); resize(); }
  renderHint();
}

for (const b of document.querySelectorAll('.mode')) {
  b.addEventListener('click', () => {
    if (b.getAttribute('aria-disabled') === 'true') { if (S.doc) flash(LOOK_LOCKED); return; }
    setMode(b.dataset.mode);
  });
}
const lookTab = $('.mode[data-mode="look"]');

// whether the focus last moved because of a pointer press (a click) rather than a key: whichever came last when
// it moved
let lastInput = 'key', focusByPointer = false;
document.addEventListener('pointerdown', () => { lastInput = 'pointer'; }, true);
document.addEventListener('keydown', () => { lastInput = 'key'; }, true);
document.addEventListener('focusin', () => { focusByPointer = lastInput === 'pointer'; }, true);

// Radio groups and the page tabs: one tab stop per group (the chosen item), arrow keys move the choice.
function rovingGroup(group, itemSel, stateAttr) {
  const usable = () => [...group.querySelectorAll(itemSel)]
    .filter((b) => !b.hidden && !b.disabled && b.getAttribute('aria-disabled') !== 'true');
  const sync = () => {
    const all = [...group.querySelectorAll(itemSel)];
    const on = all.find((b) => b.getAttribute(stateAttr) === 'true' && !b.hidden) || usable()[0];
    for (const b of all) if (b.tabIndex !== (b === on ? 0 : -1)) b.tabIndex = b === on ? 0 : -1;
  };
  group.addEventListener('keydown', (e) => {
    const list = usable();
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    let next = null;
    if (step) next = list[(list.indexOf(document.activeElement) + step + list.length) % list.length];
    else if (e.key === 'Home') next = list[0];
    else if (e.key === 'End') next = list[list.length - 1];
    if (!next) return;
    e.preventDefault();
    e.stopPropagation();
    next.focus();
    next.click();
  });
  new MutationObserver(sync).observe(group, {
    subtree: true, attributes: true, attributeFilter: [stateAttr, 'hidden', 'disabled', 'aria-disabled'],
  });
  sync();
}
// 中 / EN: the choice is kept (the server's settings) and the page reloads in it; the work is all on the server
for (const b of document.querySelectorAll('.lang .seg-btn')) {
  b.setAttribute('aria-checked', String(b.dataset.lang === LANG));
  b.addEventListener('click', async () => {
    if (b.dataset.lang === LANG) return;
    try {
      await request('POST', '/api/lang', { lang: b.dataset.lang });
      location.reload();
    } catch (e) { flash(e.message, true); }
  });
}

for (const g of document.querySelectorAll('[role="radiogroup"]')) rovingGroup(g, '[role="radio"]', 'aria-checked');
rovingGroup($('.modes'), '[role="tab"]', 'aria-selected');

// data-tip: a short note shown on hover and on keyboard focus (a title shows on neither for the keyboard), and
// read out as the element's description.
const tooltip = $('#tooltip');
let tipFor = null;

function setTip(el, text) {
  if (text) { el.dataset.tip = text; el.setAttribute('aria-description', text); } else {
    delete el.dataset.tip;
    el.removeAttribute('aria-description');
    if (tipFor === el) hideTip();
  }
}

function showTip(el) {
  if (!el.dataset.tip) return;
  tipFor = el;
  tooltip.textContent = el.dataset.tip;
  tooltip.hidden = false;
  const r = el.getBoundingClientRect();
  const w = tooltip.offsetWidth, h = tooltip.offsetHeight;
  const below = r.bottom + 8 + h <= window.innerHeight - 8;
  tooltip.style.left = `${Math.round(Math.min(Math.max(8, r.left), window.innerWidth - w - 8))}px`;
  tooltip.style.top = `${Math.round(below ? r.bottom + 8 : r.top - 8 - h)}px`;
}

function hideTip(el = tipFor) {
  if (el !== tipFor) return;
  tooltip.hidden = true;
  tipFor = null;
}

for (const el of document.querySelectorAll('[data-tip]')) setTip(el, el.dataset.tip);
document.addEventListener('pointerover', (e) => {
  const el = e.target instanceof Element && e.target.closest('[data-tip]');
  if (el && el !== tipFor) showTip(el);
});
document.addEventListener('pointerout', (e) => {
  const el = e.target instanceof Element && e.target.closest('[data-tip]');
  if (el && !(e.relatedTarget instanceof Node && el.contains(e.relatedTarget)) && el !== document.activeElement) hideTip(el);
});
document.addEventListener('focusin', (e) => {
  const el = e.target instanceof Element && e.target.closest('[data-tip]');
  if (el) showTip(el);
});
document.addEventListener('focusout', (e) => {
  const el = e.target instanceof Element && e.target.closest('[data-tip]');
  if (el) hideTip(el);
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && tipFor) hideTip(); }, true);
window.addEventListener('scroll', () => hideTip(), true);

// ------------------------------------------------------------------ server

async function request(method, url, body) {
  const opt = { method };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) {
    opt.headers = { 'Content-Type': 'application/json' };
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(url, opt);
  const text = await r.text();
  let j = null;
  try { j = text ? JSON.parse(text) : null; } catch { /* not JSON */ }
  if (!r.ok) throw new Error((j && j.detail) || t('服务器出错（{status}），再试一次；一直这样就关掉工具重新打开', { status: r.status }));
  return j;
}

// Edits run one after another so their responses arrive in order.
let chain = Promise.resolve();
function queue(fn) {
  const p = chain.then(fn);
  chain = p.catch(() => {});
  return p;
}

function edit(method, path, body) {
  if (!S.doc) return Promise.resolve(null);
  const id = S.doc.id;
  return queue(() => request(method, `/api/doc/${id}${path}`, body)).then((st) => {
    applyState(st);
    return st;
  }).catch((e) => { flash(e.message, true); return null; });
}

let refreshTimer = 0;
function refresh(delay = 40) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    queue(() => request('GET', '/api/doc')).then(applyState).catch((e) => flash(e.message, true));
  }, delay);
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(t('图像加载失败，重新打开这个文件试试')));
    img.src = url;
  });
}

// ------------------------------------------------------------------ state from the server

function applyState(st) {
  if (st === undefined) return;
  if (!st) { setNoDoc(); return; }
  const fresh = !S.doc || S.doc.id !== st.id;
  S.doc = st;
  if (fresh) {
    S.masks.clear();
    S.courses.clear();
    S.coverage = null;
    S.art = null;
    S.hover = null;
    S.pending = null;
    S.current = null;
    $('#exported').hidden = true;
    setMode('edit');                    // a newly opened image starts at 引导 (a reload keeps its page: below)
    fit();
    const id = st.id;
    loadImage(`/api/doc/${id}/art`).then((img) => {
      if (S.doc && S.doc.id === id) { S.art = img; redraw(); lookUI.onArt(); }
    }).catch((e) => flash(e.message, true));
  }
  if (!st.regions.some((r) => r.id === S.current)) S.current = st.regions.length ? st.regions[0].id : null;
  const ids = new Set(st.regions.map((r) => r.id));
  for (const rid of [...S.masks.keys()]) if (!ids.has(rid)) S.masks.delete(rid);
  for (const r of st.regions) {
    syncMask(r);
    syncCourses(r);
  }
  syncCoverage();
  syncTiers();
  S.strokes = st.strokes.map((s) => ({ id: s.id, region: s.region, pts: s.pts, path: polyPath(s.pts, 1, 0.5) }));
  S.dividers = (st.dividers || []).map((d) => ({ id: d.id, pts: d.pts, path: polyPath(d.pts, 1, 0.5) }));
  if (S.hover !== null && !S.strokes.some((s) => s.id === S.hover)) S.hover = null;
  S.solving = st.regions.find((r) => r.status === 'solving') || null;
  if (S.mode === 'look' && !canLook(st)) {            // e.g. undo took back the last 走向 line
    setMode('edit');
    flash(t('没有走向线了，回到引导页'));
  }
  lookUI.onState(st);
  if (fresh && wantPage === 'look') setMode('look');
  if (fresh) wantPage = null;
  renderChrome();
  redraw();
}

function setNoDoc() {
  S.doc = null;
  S.art = null;
  S.masks.clear();
  S.courses.clear();
  S.coverage = null;
  S.strokes = [];
  S.dividers = [];
  S.wallHover = null;
  lookUI.onState(null);
  setMode('edit');
  renderChrome();
  redraw();
}

// Outlines of SAM's candidates for the last click, so every tier is visible before choosing it.
function syncTiers() {
  const c = S.doc && S.doc.segment_cycle;
  if (!c) return;
  if (S.tiers && S.tiers.click === c.click) return;
  const id = S.doc.id;
  S.tiers = { click: c.click, paths: null };
  const t = S.tiers;
  request('GET', `/api/doc/${id}/segment/outlines`).then((j) => {
    if (S.tiers !== t || j.click !== t.click) return;
    t.paths = j.outlines.map(linesPath);
    redraw();
  }).catch(() => {});
}

const TIER_NAMES = [t('小'), t('中'), t('大')];

// The chooser floats beside the click, inside the stage. It runs every frame, so it only writes: its contents
// change only with the click, and its size is measured once after they do; the stage size comes from resize().
let stageBox = { width: 0, height: 0 };
let tiersKey = null, tiersSize = null;

function placeTiers() {
  const el = $('#tiers');
  const c = S.doc && S.doc.segment_cycle;
  const show = !!(c && S.tool === 'segment' && !S.segPending);
  if (el.hidden === show) { el.hidden = !show; tiersSize = null; }
  if (!show) return;
  const key = `${c.click}|${c.n}|${c.k}|${c.subtract}`;
  if (key !== tiersKey) {
    tiersKey = key;
    tiersSize = null;
    $('#tiers-label').textContent = c.subtract ? t('减去范围') : t('加入范围');
    for (const b of el.querySelectorAll('.tier')) {
      const k = +b.dataset.k;
      b.hidden = k >= c.n;
      b.setAttribute('aria-checked', String(k === c.k));
    }
  }
  if (!tiersSize) tiersSize = { w: el.offsetWidth, h: el.offsetHeight };
  const mx = (c.pt[0] + 0.5) * S.view.s + S.view.x, my = (c.pt[1] + 0.5) * S.view.s + S.view.y;
  const { w, h } = tiersSize;
  let left = mx + 16, top = my + 14;
  if (left + w > stageBox.width - 8) left = mx - 16 - w;
  if (top + h > stageBox.height - 8) top = my - 14 - h;
  el.style.left = `${Math.max(8, left)}px`;
  el.style.top = `${Math.max(8, top)}px`;
}

// Fetched only while the overlay is on; a veil that darkens everything the texture will not reach.
function syncCoverage() {
  if (!S.doc || !S.show.coverage) return;
  const v = S.doc.coverage_v;
  if (!S.coverage) {
    const c = document.createElement('canvas');
    c.width = S.doc.width;
    c.height = S.doc.height;
    S.coverage = { v: null, want: null, canvas: c, covered: 0, pixels: 0 };
  }
  const cov = S.coverage;
  if (cov.want === v) return;
  cov.want = v;
  const id = S.doc.id;
  Promise.all([
    loadImage(`/api/doc/${id}/coverage?v=${v}`),
    request('GET', `/api/doc/${id}/coverage/stats`),
  ]).then(([img, stats]) => {
    if (!S.doc || S.doc.id !== id || cov.want !== v || S.coverage !== cov) return;
    const c = cov.canvas.getContext('2d');
    c.globalCompositeOperation = 'copy';
    c.fillStyle = '#000';
    c.fillRect(0, 0, cov.canvas.width, cov.canvas.height);
    c.globalCompositeOperation = 'destination-out';
    c.drawImage(img, 0, 0);
    c.globalCompositeOperation = 'source-over';
    cov.v = stats.coverage_v;
    cov.pixels = stats.regions.reduce((a, r) => a + r.pixels, 0);
    cov.covered = stats.regions.reduce((a, r) => a + r.covered, 0);
    renderCoverageNote();
    redraw();
  }).catch(() => { cov.want = null; });
}

function renderCoverageNote() {
  const el = $('#coverage-note');
  const cov = S.coverage;
  el.hidden = !(S.doc && S.show.coverage);
  if (el.hidden) return;
  if (!cov || cov.v === null) { el.textContent = t('正在计算…'); return; }
  if (!cov.pixels) { el.textContent = t('还没有涂任何部位。'); return; }
  const pct = Math.round((100 * cov.covered) / cov.pixels);
  el.textContent = S.doc.color_exclude === false
    ? t('部位里 {pct}% 会出纹理。颜色排除已在“纹理”页关掉。', { pct })
    : t('部位里 {pct}% 会出纹理。变暗的地方颜色和丝袜差得远（金边、手套、皮肤等），不会出纹理；排除错了可以在“纹理”页关掉颜色排除。', { pct });
}

function maskSlot(r) {
  let m = S.masks.get(r.id);
  if (!m) {
    const c = document.createElement('canvas');
    c.width = S.doc.width;
    c.height = S.doc.height;
    m = { canvas: c, ctx: c.getContext('2d'), v: -1, want: -1, color: r.color };
    S.masks.set(r.id, m);
  }
  return m;
}

// Masks arriving mid-stroke would wipe what the brush has drawn so far; they wait until painting settles.
function syncMask(r) {
  const m = maskSlot(r);
  if (m.want === r.mask_v && m.color === r.color) return;
  if (S.painting || S.inflightPaint) return;
  m.want = r.mask_v;
  m.color = r.color;
  const id = S.doc.id;
  loadImage(`/api/doc/${id}/regions/${r.id}/mask?v=${r.mask_v}`).then((img) => {
    if (!S.doc || S.doc.id !== id || S.masks.get(r.id) !== m || m.want !== r.mask_v) return;
    if (S.painting || S.inflightPaint) { m.want = -1; return; }   // reloaded once painting settles
    m.ctx.globalCompositeOperation = 'copy';
    m.ctx.drawImage(img, 0, 0);
    m.ctx.globalCompositeOperation = 'source-in';
    m.ctx.fillStyle = r.color;
    m.ctx.fillRect(0, 0, m.canvas.width, m.canvas.height);
    m.ctx.globalCompositeOperation = 'source-over';
    m.v = r.mask_v;
    redraw();
  }).catch(() => { m.want = -1; });
}

function flushMasks() {
  if (S.doc) for (const r of S.doc.regions) syncMask(r);
}

function syncCourses(r) {
  let c = S.courses.get(r.id);
  if (!c) { c = { v: 0, want: 0, courses: null, wales: null }; S.courses.set(r.id, c); }
  if (c.want === r.solve_v) return;
  c.want = r.solve_v;
  const id = S.doc.id;
  request('GET', `/api/doc/${id}/regions/${r.id}/courses`).then((j) => {
    if (!S.doc || S.doc.id !== id || c.want !== r.solve_v) return;
    c.courses = linesPath(j.courses);
    c.wales = linesPath(j.wales);
    c.walls = linesPath(j.walls || []);
    c.wallLines = j.walls || [];
    c.v = j.version;
    redraw();
  }).catch(() => { c.want = -1; });
}

// Flat [x, y, ...] -> Path2D in image coords. `div` undoes the server's tenths; `off` moves pixel centres.
function polyPath(a, div, off) {
  const p = new Path2D();
  if (a.length < 2) return p;
  p.moveTo(a[0] / div + off, a[1] / div + off);
  for (let i = 2; i < a.length; i += 2) p.lineTo(a[i] / div + off, a[i + 1] / div + off);
  return p;
}

function linesPath(lines) {
  const p = new Path2D();
  for (const a of lines) p.addPath(polyPath(a, 10, 0.5));
  return p;
}

// ------------------------------------------------------------------ chrome (panel, bar, status)

const STATUS_TEXT = {
  empty: t('还没涂'),
  nostroke: t('还没画走向线'),
  pending: t('等待求解…'),
  solving: t('正在求解…'),
};

function regionMeta(r) {
  if (r.status === 'ok' && r.unguided) {
    return [t('{n} 条走向线；有一块分开的没画走向线，那里没有纹理', { n: r.strokes }), 'warn'];
  }
  if (r.status === 'ok') return [t('{n} 条走向线，求解 {s}\u00a0秒', { n: r.strokes, s: r.seconds }), ''];
  if (r.status === 'error') return [r.error || t('求解出错，试着调整或重画这个部位的走向线'), 'error'];
  return [STATUS_TEXT[r.status] || '', ''];
}

let renaming = null;

function renderChrome() {
  const d = S.doc;
  document.body.classList.toggle('no-doc', !d);
  $('#empty').hidden = !!d;
  $('#btn-undo').disabled = !d || !d.can_undo;
  $('#btn-redo').disabled = !d || !d.can_redo;
  $('.mode[data-mode="edit"]').setAttribute('aria-disabled', String(!d));
  lookTab.setAttribute('aria-disabled', String(!canLook()));
  lookTab.title = canLook() ? t('选样式、调参数，看纹理') : '';
  setTip(lookTab, d && !canLook() ? LOOK_LOCKED : null);
  for (const id of ['#btn-add-region', '#btn-fit', '#btn-100']) $(id).disabled = !d;
  renderExport();
  const r = currentRegion();
  $('.side').style.setProperty('--rc', r ? r.color : 'var(--chalk)');   // the chosen tool wears the region's colour
  if (!r || !d) closeMenus();
  renderRegions();
  renderZoom();
  renderHint();
  renderSam();
  renderCoverageNote();
  renderCutbar();
  renderMirror();
}

function renderSam() {
  const el = $('#sam-status');
  const sam = S.doc && S.doc.sam;
  el.classList.remove('error');
  if (!sam) { el.textContent = ''; return; }
  if (sam.state === 'error') {
    el.classList.add('error');
    el.textContent = t('点选不可用：{error}。画笔和橡皮照常能用。', { error: sam.error || t('未知错误') });
  } else if (sam.state === 'loading') el.textContent = t('点选：正在加载模型…');
  else if (sam.state === 'waiting' || sam.state === 'embedding') el.textContent = t('点选：正在分析这张图…');
  else el.textContent = t('点选就绪（{device}）', { device: (sam.device || '').replace(/^NVIDIA GeForce /, '') });
}

// Each region is a row: a button that picks it (the current one is the row's tab stop; ↑ ↓ move between rows,
// F2 or a double click renames) and its ··· menu. The rows are rebuilt on every state change, so the keyboard focus
// is carried over to the same button in the new row.
function renderRegions() {
  const ul = $('#region-list');
  if (renaming !== null) return;      // keep the inline editor alive
  const open = menuFor;
  const was = document.activeElement;
  const focused = ul.contains(was) ? { id: was.closest('.region')?.dataset.id, part: was.classList.contains('more') ? 'more' : 'pick' } : null;
  ul.replaceChildren();
  if (!S.doc) return;
  for (const r of S.doc.regions) {
    const cur = r.id === S.current;
    const li = document.createElement('li');
    li.className = cur ? 'region current' : 'region';
    li.dataset.id = r.id;
    li.style.setProperty('--c', r.color);
    const [meta, cls] = regionMeta(r);
    const pick = document.createElement('button');
    pick.type = 'button';
    pick.className = 'pick';
    pick.tabIndex = cur ? 0 : -1;
    if (cur) pick.setAttribute('aria-current', 'true');
    const sw = document.createElement('span'); sw.className = 'sw';
    const name = document.createElement('span'); name.className = 'name'; name.textContent = r.name;
    const m = document.createElement('span'); m.className = 'meta' + (cls ? ` ${cls}` : ''); m.textContent = meta;
    if (r.status === 'solving' || r.status === 'pending') {
      const dot = document.createElement('span'); dot.className = 'busy-dot'; m.append(dot);
    }
    pick.append(sw, name, m);
    pick.addEventListener('click', () => selectRegion(r.id));
    pick.addEventListener('dblclick', () => startRename(r.id));
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'more';
    more.tabIndex = cur ? 0 : -1;
    more.textContent = '···';
    more.title = t('改名、清空、合并、删除');
    more.setAttribute('aria-label', t('{name}：更多操作', { name: r.name }));
    more.setAttribute('aria-haspopup', 'menu');
    more.setAttribute('aria-expanded', String(open === r.id));
    more.addEventListener('click', (e) => {
      e.stopPropagation();
      if (menuFor === r.id) closeMenus(); else openRegionMenu(r.id, more);
    });
    li.append(pick, more);
    ul.append(li);
  }
  if (focused) focusRegion(+focused.id, focused.part);
}

function focusRegion(rid, part = 'pick') {
  const el = $(`#region-list .region[data-id="${rid}"] .${part}`);
  if (el) el.focus();
}

function selectRegion(rid) {
  S.current = rid;
  if (S.cutPair && !S.cutPair.has(rid)) S.cutPair = null;
  renderChrome();
}

function currentRegion() {
  return S.doc ? S.doc.regions.find((r) => r.id === S.current) || null : null;
}

// The name becomes a text box in place; Enter or leaving it keeps the new name, Esc keeps the old one. A name the
// server turns down comes back with the reason beside it.
function startRename(rid, { value = null, error = null } = {}) {
  const li = $(`#region-list .region[data-id="${rid}"]`);
  const r = S.doc && S.doc.regions.find((x) => x.id === rid);
  if (!li || !r) return;
  renaming = rid;
  const box = document.createElement('div');
  box.className = 'pick editing';
  const sw = document.createElement('span'); sw.className = 'sw';
  const name = document.createElement('span'); name.className = 'name';
  const input = document.createElement('input');
  input.value = value ?? r.name;
  input.maxLength = 40;
  input.name = 'region-name';
  input.autocomplete = 'off';
  input.spellcheck = false;
  input.setAttribute('aria-label', t('部位名称'));
  name.append(input);
  box.append(sw, name);
  if (error) {
    const m = document.createElement('span');
    m.className = 'meta error';
    m.id = 'rename-error';
    m.textContent = error;
    box.append(m);
    input.setAttribute('aria-invalid', 'true');
    input.setAttribute('aria-describedby', 'rename-error');
  }
  li.querySelector('.pick').replaceWith(box);
  input.focus();
  input.select();
  let done = false;
  const finish = (commit) => {
    if (done) return;
    done = true;
    renaming = null;
    const nm = input.value.trim();
    if (commit && nm && nm !== r.name) renameRegion(rid, nm);
    else { renderChrome(); focusRegion(rid); }
  };
  input.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') finish(true);
    else if (e.key === 'Escape') finish(false);
  });
  input.addEventListener('blur', () => finish(true));
}

async function renameRegion(rid, name) {
  const id = S.doc.id;
  try {
    applyState(await queue(() => request('PATCH', `/api/doc/${id}/regions/${rid}`, { name })));
    focusRegion(rid);
  } catch (e) {
    renderChrome();
    startRename(rid, { value: name, error: e.message });
  }
}

const PERCENT = new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 0 });

function renderZoom() {
  $('#zoom-pct').textContent = S.doc ? PERCENT.format(S.view.s) : '';
}

const HINTS = {
  segment: t('左键把点到的部分加进当前部位，右键从当前部位减去；点完在旁边选 小 / 中 / 大，或按 Tab 换范围'),
  brush: t('左键涂当前部位（会从别的部位里抢过来），右键擦除；[ ] 调笔刷大小'),
  erase: t('左键擦除当前部位；[ ] 调笔刷大小'),
  pen: t('沿一道横纹画一条线；右键或 Delete 删掉指针下的线'),
  cut: t('分割当前部位：画一条线，松开鼠标就分成两块；线不用画满，两端会顺着方向延长（虚线）；Esc 回到原来的工具'),
  wall: t('沿两块丝袜的交界画线，横纹不会穿过它，会从线的末端绕过去：一块挡住另一块的轮廓会自动找到（虚线），贴在一起的（比如大腿压着小腿）要自己画；右键或 Delete 删除指针下的隔开线（自动找到的虚线也能删）'),
};

function renderHint() {
  $('#status-hint').textContent = !S.doc ? '' : S.mode === 'look'
    ? t('拖动滑杆，细节跟着变；按住空格看细节的原图；点整体换细节的位置，拖动细节看别处')
    : HINTS[S.tool] + t('；空格或中键拖动画面，方向键平移，+ − 缩放');
}

let flashTimer = 0;
function flash(text, isError = false) {
  const el = $('#status-msg');
  el.textContent = text;
  el.title = text;                       // the whole of a message too long for the bar
  el.classList.toggle('error', isError);
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => { el.textContent = ''; el.title = ''; }, isError ? 9000 : 5000);
}

function busy(text) {
  $('#busy').hidden = !text;
  if (text) $('#busy-text').textContent = text;
  $('#busy-live').textContent = text || '';     // the overlay is hidden from the screen reader; this is read out
}

// ------------------------------------------------------------------ view transform

function resize() {
  const r = stage.getBoundingClientRect();
  stageBox = { width: r.width, height: r.height };
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.max(1, Math.round(r.width * dpr));
  cv.height = Math.max(1, Math.round(r.height * dpr));
  redraw();
}

function fit() {
  if (!S.doc) return;
  const r = stage.getBoundingClientRect();
  const s = Math.min(r.width / S.doc.width, r.height / S.doc.height) * 0.96;
  S.view = { s, x: (r.width - S.doc.width * s) / 2, y: (r.height - S.doc.height * s) / 2 };
  renderZoom();
  redraw();
}

function zoomAt(vx, vy, s) {
  s = Math.min(32, Math.max(0.03, s));
  const k = s / S.view.s;
  S.view = { s, x: vx - (vx - S.view.x) * k, y: vy - (vy - S.view.y) * k };
  renderZoom();
  redraw();
}

function zoomCentre(s) {
  const r = stage.getBoundingClientRect();
  zoomAt(r.width / 2, r.height / 2, s);
}

function viewPos(e) {
  const r = cv.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}

function toImage(p) {
  return { x: (p.x - S.view.x) / S.view.s, y: (p.y - S.view.y) / S.view.s };
}

// ------------------------------------------------------------------ drawing

let raf = 0;
function redraw() {
  if (!raf) raf = requestAnimationFrame(draw);
}

function lighten(hex, t) {
  const n = parseInt(hex.slice(1), 16);
  const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(v + (255 - v) * t));
  return `rgb(${c.join(',')})`;
}

function draw() {
  raf = 0;
  placeTiers();
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, cv.width, cv.height);
  const d = S.doc;
  if (!d) return;
  const { s, x, y } = S.view;
  ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * x, dpr * y);
  if (S.art) {
    ctx.imageSmoothingEnabled = s < 2;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(S.art, 0, 0);
  } else {
    ctx.fillStyle = TOKENS.stage;
    ctx.fillRect(0, 0, d.width, d.height);
  }
  if (S.show.coverage && S.coverage && S.coverage.v !== null) {
    ctx.globalAlpha = 0.68;
    ctx.drawImage(S.coverage.canvas, 0, 0);
    ctx.globalAlpha = 1;
  }
  if (S.show.regions) {
    for (const r of d.regions) {
      const m = S.masks.get(r.id);
      // while cutting, the region being cut stands out (the two halves of the last cut both count)
      const lit = r.id === S.current || (S.cutPair && S.cutPair.has(r.id));
      ctx.globalAlpha = S.tool === 'cut' && !lit ? 0.12 : 0.45;
      if (m && (m.v >= 0 || S.painting)) ctx.drawImage(m.canvas, 0, 0);
    }
    ctx.globalAlpha = 1;
  }
  const px = 1 / s;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  const live = (r) => r.status === 'ok' || r.status === 'pending' || r.status === 'solving';
  if (S.show.wales) {
    for (const r of d.regions) {
      const c = S.courses.get(r.id);
      if (!c || !c.wales || !live(r)) continue;
      ctx.globalAlpha = r.status === 'ok' ? 0.55 : 0.2;
      ctx.lineWidth = px;
      ctx.strokeStyle = '#f4f1ec';
      ctx.setLineDash([4 * px, 3 * px]);
      ctx.stroke(c.wales);
    }
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  }
  if (S.show.courses) {
    for (const r of d.regions) {
      const c = S.courses.get(r.id);
      if (!c || !c.courses || !live(r)) continue;
      ctx.globalAlpha = r.status === 'ok' ? 1 : 0.35;     // stale lines stay visible, faded, until the new solve lands
      ctx.lineWidth = 3 * px;
      ctx.strokeStyle = 'rgba(0,0,0,0.45)';
      ctx.stroke(c.courses);
      ctx.lineWidth = 1.3 * px;
      ctx.strokeStyle = lighten(r.color, 0.45);
      ctx.stroke(c.courses);
    }
    ctx.globalAlpha = 1;
  }
  if (S.show.walls || S.tool === 'wall') {
    // 前后交界: where one stretch of stocking lies in front of another; the courses do not continue across it.
    // Found ones dashed, the user's 隔开 lines solid; the one under the pointer (隔开 tool) red, to be deleted.
    for (const r of d.regions) {
      const c = S.courses.get(r.id);
      if (!c || !c.walls || !live(r)) continue;
      ctx.globalAlpha = r.status === 'ok' ? 1 : 0.35;
      ctx.lineWidth = 4.5 * px;
      ctx.strokeStyle = 'rgba(0,0,0,0.6)';
      ctx.stroke(c.walls);
      ctx.lineWidth = 2.2 * px;
      ctx.strokeStyle = '#fff';
      ctx.setLineDash([7 * px, 5 * px]);
      ctx.stroke(c.walls);
      ctx.setLineDash([]);
    }
    ctx.globalAlpha = 1;
    for (const dv of S.dividers) {
      ctx.lineWidth = 5 * px;
      ctx.strokeStyle = 'rgba(0,0,0,0.6)';
      ctx.stroke(dv.path);
      ctx.lineWidth = 2.6 * px;
      ctx.strokeStyle = '#fff';
      ctx.stroke(dv.path);
    }
    if (S.tool === 'wall' && S.wallHover) {
      ctx.lineWidth = 4 * px;
      ctx.strokeStyle = '#ff4d4d';
      ctx.stroke(S.wallHover.path);
    }
  }
  if (S.show.strokes) {
    const colour = new Map(d.regions.map((r) => [r.id, r.color]));
    const list = S.pending ? [...S.strokes, S.pending] : S.strokes;
    for (const st of list) {
      const hot = st.id === S.hover;
      ctx.lineWidth = (hot ? 7 : 5) * px;
      ctx.strokeStyle = 'rgba(0,0,0,0.6)';
      ctx.stroke(st.path);
      ctx.lineWidth = (hot ? 4 : 2.4) * px;
      ctx.strokeStyle = hot ? '#ffffff' : (colour.get(st.region) || '#b9b7bd');
      if (st.region === null && !hot) ctx.setLineDash([5 * px, 4 * px]);
      ctx.stroke(st.path);
      ctx.setLineDash([]);
    }
  }
  if (S.drag && (S.drag.kind === 'pen' || S.drag.kind === 'wall')) {
    if (S.drag.kind === 'wall') {
      ctx.lineWidth = 5 * px;
      ctx.strokeStyle = 'rgba(0,0,0,0.6)';
      ctx.stroke(S.drag.path);
    }
    ctx.lineWidth = (S.drag.kind === 'wall' ? 2.6 : 2.4) * px;
    ctx.strokeStyle = '#ffffff';
    ctx.stroke(S.drag.path);
  }
  if (S.drag && S.drag.kind === 'cut' && S.drag.pts.length > 1) {
    const ext = new Path2D();
    for (const [a, b] of cutExtensions(S.drag.pts)) { ext.moveTo(a.x, a.y); ext.lineTo(b.x, b.y); }
    ctx.lineWidth = 4 * px;
    ctx.strokeStyle = 'rgba(0,0,0,0.6)';
    ctx.stroke(S.drag.path);
    ctx.lineWidth = 2 * px;
    ctx.strokeStyle = '#ffffff';
    ctx.stroke(S.drag.path);
    ctx.setLineDash([7 * px, 6 * px]);
    ctx.lineWidth = 3 * px;
    ctx.strokeStyle = 'rgba(0,0,0,0.5)';
    ctx.stroke(ext);
    ctx.lineWidth = 1.4 * px;
    ctx.strokeStyle = 'rgba(255,255,255,0.9)';
    ctx.stroke(ext);
    ctx.setLineDash([]);
  }
  // where the last click landed, while its candidates can still be cycled, or while it is being segmented
  const cyc = d.segment_cycle;
  if (S.tool === 'segment' && cyc && !S.segPending && S.tiers && S.tiers.paths && S.tiers.click === cyc.click) {
    S.tiers.paths.forEach((path, k) => {
      const on = k === cyc.k, hot = k === S.tierHover;
      ctx.setLineDash(on || hot ? [] : [6 * px, 5 * px]);
      ctx.lineWidth = (hot ? 4.5 : on ? 3.5 : 2.5) * px;
      ctx.strokeStyle = 'rgba(0,0,0,0.6)';
      ctx.stroke(path);
      ctx.lineWidth = (hot ? 2.4 : on ? 1.8 : 1.1) * px;
      ctx.strokeStyle = hot ? '#ffd84d' : on ? '#ffffff' : 'rgba(255,255,255,0.75)';
      ctx.stroke(path);
    });
    ctx.setLineDash([]);
  }
  const mark = S.segPending || (S.tool === 'segment' && cyc ? { x: cyc.pt[0] + 0.5, y: cyc.pt[1] + 0.5, subtract: cyc.subtract } : null);
  if (mark) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const mx = mark.x * s + x, my = mark.y * s + y;
    ctx.beginPath();
    ctx.arc(mx, my, 7, 0, Math.PI * 2);
    ctx.fillStyle = mark.subtract ? TOKENS.ink : '#ffffff';
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = mark.subtract ? '#ffffff' : TOKENS.ink;
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(mx - 3.5, my);
    ctx.lineTo(mx + 3.5, my);
    if (!mark.subtract) { ctx.moveTo(mx, my - 3.5); ctx.lineTo(mx, my + 3.5); }
    ctx.stroke();
    ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * x, dpr * y);
  }
  // brush cursor, in view px
  if (S.mouse && (S.tool === 'brush' || S.tool === 'erase') && !S.space && !(S.drag && S.drag.kind === 'pan')) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const rad = Math.max(S.brush * s, 1.5);
    ctx.beginPath();
    ctx.arc(S.mouse.x, S.mouse.y, rad, 0, Math.PI * 2);
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(0,0,0,0.55)';
    ctx.stroke();
    ctx.lineWidth = 1.2;
    ctx.strokeStyle = S.tool === 'erase' ? '#ffffff' : lighten((currentRegion() || { color: '#ffffff' }).color, 0.3);
    if (S.tool === 'erase') ctx.setLineDash([4, 3]);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

// ------------------------------------------------------------------ tools

function setTool(t) {
  if (t === 'cut' && S.tool !== 'cut') S.toolBeforeCut = S.tool;
  if (t !== 'cut') S.cutPair = null;
  S.tool = t;
  for (const b of document.querySelectorAll('.tool')) b.setAttribute('aria-checked', String(b.dataset.tool === t));
  stage.classList.remove('tool-brush', 'tool-erase', 'tool-pen', 'tool-segment', 'tool-cut', 'tool-wall');
  stage.classList.add(`tool-${t}`);
  for (const st of document.querySelectorAll('.step')) st.classList.toggle('active', !!st.querySelector(`.tool[data-tool="${t}"]`));
  if (t !== 'pen') S.hover = null;
  if (t !== 'wall') S.wallHover = null;
  renderHint();
  renderCutbar();
  redraw();
}

function renderCutbar() {
  const bar = $('#cutbar');
  bar.hidden = !(S.doc && S.tool === 'cut');
  if (bar.hidden) return;
  const r = currentRegion();
  const text = $('#cutbar-text');
  text.replaceChildren();
  if (r) {
    const name = document.createElement('strong');
    name.textContent = r.name;
    name.style.setProperty('--c', lighten(r.color, 0.35));
    text.append(t('分割 '), name, t('：画一条线，松开鼠标就分成两块'));
  } else {
    text.append(t('先在左边选一个要分割的部位'));
  }
  $('#btn-auto-cut').disabled = !r;
}

function leaveCut() {
  setTool(S.toolBeforeCut && S.toolBeforeCut !== 'cut' ? S.toolBeforeCut : 'segment');
}

const SNAP_VIEW_PX = 14;     // how far (screen px) a cut line may move to reach the line art

// The drawn line carried on straight past both ends, as the server will cut along it: the direction of the last
// 12 px of each end, or when snapping, of the last 40% of the line (at least 24 px), so hand jitter does not tilt it.
function cutExtensions(pts) {
  let total = 0;
  for (let i = 1; i < pts.length; i++) total += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  const endLen = $('#cut-snap').checked ? Math.max(24, 0.4 * total) : 12;
  const dir = (P) => {
    let d = 0, k = 1;
    for (; k < P.length; k++) {
      d += Math.hypot(P[k].x - P[k - 1].x, P[k].y - P[k - 1].y);
      if (d >= endLen) break;
    }
    const q = P[Math.min(k, P.length - 1)];
    const vx = P[0].x - q.x, vy = P[0].y - q.y, n = Math.hypot(vx, vy);
    return n > 1e-6 ? { x: vx / n, y: vy / n } : null;
  };
  const reach = 4 * (S.doc.width + S.doc.height);
  const out = [];
  for (const P of [pts, [...pts].reverse()]) {
    const v = dir(P);
    if (v) out.push([P[0], { x: P[0].x + v.x * reach, y: P[0].y + v.y * reach }]);
  }
  return out;
}

function cutAlong(drag) {
  const r = S.doc && S.doc.regions.find((x) => x.id === drag.rid);
  if (!r) return;
  const snap = $('#cut-snap').checked ? +(SNAP_VIEW_PX / S.view.s).toFixed(1) : 0;
  edit('POST', `/regions/${r.id}/split`, { pts: flat(drag.pts), snap }).then((st) => splitDone(st, r.name));
}

function splitDone(st, oldName) {
  if (!st || !st.split) return;
  const [a, b] = st.split.map((id) => st.regions.find((x) => x.id === id));
  S.cutPair = new Set([a.id, b.id]);      // both halves keep their colour while cutting goes on
  selectRegion(a.id);
  flash(t('已把“{old}”分割成“{a}”和“{b}”，Ctrl+Z 可以撤销', { old: oldName, a: a.name, b: b.name }));
}

function setBrush(r) {
  S.brush = Math.round(Math.min(400, Math.max(2, r)));
  $('#brush-size').value = S.brush;
  fillRange($('#brush-size'));
  $('#brush-val').textContent = S.brush;
  redraw();
}

function paintLocal(a, b, drag) {
  const m = maskSlot({ id: drag.rid, color: drag.color });
  if (m.v < 0) m.v = 0;
  stamp(m.ctx, a, b, drag.color, drag.erase);
  // painting takes the pixels from every other region, as the server does
  if (!drag.erase) for (const [rid, o] of S.masks) if (rid !== drag.rid) stamp(o.ctx, a, b, '#000', true);
}

function stamp(c, a, b, color, erase) {
  c.globalCompositeOperation = erase ? 'destination-out' : 'source-over';
  c.fillStyle = c.strokeStyle = color;
  c.lineWidth = 2 * S.brush;
  c.lineCap = 'round';
  c.beginPath();
  if (a === b) {
    c.arc(a.x, a.y, S.brush, 0, Math.PI * 2);
    c.fill();
  } else {
    c.moveTo(a.x, a.y);
    c.lineTo(b.x, b.y);
    c.stroke();
  }
  c.globalCompositeOperation = 'source-over';
}

function flat(pts) {
  const out = [];
  for (const p of pts) out.push(+(p.x - 0.5).toFixed(2), +(p.y - 0.5).toFixed(2));
  return out;
}

function distToSeg(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const l2 = dx * dx + dy * dy;
  let t = l2 ? ((px - ax) * dx + (py - ay) * dy) / l2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}

function strokeAt(p) {
  const lim = 8 / S.view.s;
  let best = null, bd = lim;
  const x = p.x - 0.5, y = p.y - 0.5;
  for (const st of S.strokes) {
    const a = st.pts;
    for (let i = 2; i < a.length; i += 2) {
      const dd = distToSeg(x, y, a[i - 2], a[i - 1], a[i], a[i + 1]);
      if (dd < bd) { bd = dd; best = st.id; }
    }
  }
  return best;
}

function deleteStroke(id) {
  S.hover = null;
  S.strokes = S.strokes.filter((s) => s.id !== id);
  redraw();
  edit('DELETE', `/strokes/${id}`).then((st) => { if (st) flash(t('已删除走向线，Ctrl+Z 可以撤销')); });
}

// The wall nearest image point p within 8 screen px: one of the user's 隔开 lines (image px) or a found one (the
// server sends those in tenths of a px). Returns {at, path} or null.
function wallAt(p) {
  const lim = 8 / S.view.s;
  const x = p.x - 0.5, y = p.y - 0.5;
  let best = null, bd = lim;
  const scan = (a, div, path) => {
    for (let i = 2; i < a.length; i += 2) {
      const dd = distToSeg(x, y, a[i - 2] / div, a[i - 1] / div, a[i] / div, a[i + 1] / div);
      if (dd < bd) { bd = dd; best = path; }
    }
  };
  for (const d of S.dividers) scan(d.pts, 1, d.path);
  if (S.doc) {
    for (const r of S.doc.regions) {
      const c = S.courses.get(r.id);
      if (c && c.wallLines) for (const a of c.wallLines) scan(a, 10, polyPath(a, 10, 0.5));
    }
  }
  return best ? { at: { x, y }, path: best } : null;
}

function removeWallAt(at) {
  S.wallHover = null;
  redraw();
  edit('POST', '/walls/remove', { x: +at.x.toFixed(1), y: +at.y.toFixed(1), tol: +(8 / S.view.s).toFixed(1) })
    .then((st) => {
      if (st && st.removed) flash(st.removed === 'found' ? t('已删掉这条自动找到的隔开线，Ctrl+Z 可以撤销') : t('已删掉隔开线，Ctrl+Z 可以撤销'));
    });
}

function segmentClick(p, subtract) {
  const r = currentRegion();
  if (!r) { flash(t('先在左边选一个部位'), true); return; }
  if (p.x < 0 || p.y < 0 || p.x >= S.doc.width || p.y >= S.doc.height) return;
  if (S.segPending) return;           // one click at a time; each depends on the last
  S.segPending = { x: p.x, y: p.y, subtract };
  stage.classList.add('segment-busy');
  redraw();
  edit('POST', `/regions/${r.id}/segment`, { x: +(p.x - 0.5).toFixed(1), y: +(p.y - 0.5).toFixed(1), subtract })
    .then((st) => { if (st) segmentFlash(st); })
    .finally(() => { S.segPending = null; stage.classList.remove('segment-busy'); redraw(); });
}

function segmentFlash(st) {
  const c = st.segment_cycle;
  const r = c && st.regions.find((x) => x.id === c.region);
  if (!r) return;
  const verb = c.subtract ? t('从“{name}”减去', { name: r.name }) : t('加进“{name}”', { name: r.name });
  flash(t('已{verb}（{tier}范围）。点旁边的 小 / 中 / 大 或按 Tab 换范围，Ctrl+Z 撤销', { verb, tier: TIER_NAMES[c.k] || c.k + 1 }));
}

function cycleSegment(step) {
  edit('POST', '/segment/cycle', { step }).then((st) => { if (st) segmentFlash(st); });
}

function selectTier(k) {
  edit('POST', '/segment/select', { k }).then((st) => { if (st) segmentFlash(st); });
}

for (const b of document.querySelectorAll('#tiers .tier')) {
  const k = +b.dataset.k;
  b.addEventListener('click', () => selectTier(k));
  b.addEventListener('pointerenter', () => { S.tierHover = k; redraw(); });
  b.addEventListener('pointerleave', () => { if (S.tierHover === k) { S.tierHover = null; redraw(); } });
}

cv.addEventListener('contextmenu', (e) => e.preventDefault());

cv.addEventListener('pointerdown', (e) => {
  if (!S.doc) return;
  const v = viewPos(e);
  S.mouse = v;
  if (e.button === 1 || S.space) {
    e.preventDefault();
    cv.setPointerCapture(e.pointerId);
    S.drag = { kind: 'pan', sx: v.x, sy: v.y, vx: S.view.x, vy: S.view.y };
    stage.classList.add('dragging');
    return;
  }
  const p = toImage(v);
  if (S.tool === 'segment') {
    if (e.button !== 0 && e.button !== 2) return;
    segmentClick(p, e.button === 2);
  } else if (S.tool === 'brush' || S.tool === 'erase') {
    if (e.button !== 0 && e.button !== 2) return;
    const r = currentRegion();
    if (!r) { flash(t('先在左边选一个部位'), true); return; }
    cv.setPointerCapture(e.pointerId);
    S.drag = { kind: 'paint', rid: r.id, color: r.color, erase: S.tool === 'erase' || e.button === 2, pts: [p], last: p };
    S.painting = true;
    paintLocal(p, p, S.drag);
    redraw();
  } else if (S.tool === 'pen' || S.tool === 'cut' || S.tool === 'wall') {
    if (S.tool === 'pen' && e.button === 2) {
      const id = strokeAt(p);
      if (id !== null) deleteStroke(id);
      return;
    }
    if (S.tool === 'wall' && e.button === 2) {
      const h = wallAt(p);
      if (h) removeWallAt(h.at);
      else flash(t('指针下没有隔开线：把指针移到隔开线上（线变红）再右键'), true);
      return;
    }
    if (e.button !== 0) return;
    const r = currentRegion();
    if (S.tool === 'cut' && !r) { flash(t('先在左边选一个部位'), true); return; }
    cv.setPointerCapture(e.pointerId);
    const path = new Path2D();
    path.moveTo(p.x, p.y);
    S.drag = { kind: S.tool, pts: [p], last: p, path, rid: r && r.id };
    S.hover = null;
    S.wallHover = null;
    redraw();
  }
});

cv.addEventListener('pointermove', (e) => {
  if (!S.doc) return;
  const v = viewPos(e);
  S.mouse = v;
  const ip = toImage(v);
  const inside = ip.x >= 0 && ip.y >= 0 && ip.x < S.doc.width && ip.y < S.doc.height;
  $('#status-pos').textContent = inside ? `${Math.floor(ip.x)}, ${Math.floor(ip.y)}` : '';
  const d = S.drag;
  if (d && d.kind === 'pan') {
    S.view.x = d.vx + v.x - d.sx;
    S.view.y = d.vy + v.y - d.sy;
  } else if (d && (d.kind === 'paint' || d.kind === 'pen' || d.kind === 'cut' || d.kind === 'wall')) {
    const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
    const minStep = d.kind === 'paint' ? Math.max(S.brush * 0.2, 0.75) : 0.75;
    for (const ce of (evs.length ? evs : [e])) {
      const p = toImage(viewPos(ce));
      if (Math.hypot(p.x - d.last.x, p.y - d.last.y) < minStep) continue;
      if (d.kind === 'paint') paintLocal(d.last, p, d);
      else d.path.lineTo(p.x, p.y);
      d.pts.push(p);
      d.last = p;
    }
  } else if (S.tool === 'pen' && !S.space) {
    const h = strokeAt(ip);
    if (h !== S.hover) S.hover = h;
  } else if (S.tool === 'wall' && !S.space) {
    S.wallHover = wallAt(ip);
  }
  redraw();
});

function endDrag(e) {
  const d = S.drag;
  if (!d) return;
  S.drag = null;
  stage.classList.remove('dragging');
  if (d.kind === 'paint') {
    const p = toImage(viewPos(e));
    if (Math.hypot(p.x - d.last.x, p.y - d.last.y) > 0.5) { paintLocal(d.last, p, d); d.pts.push(p); }
    S.painting = false;
    S.inflightPaint++;
    edit('POST', `/regions/${d.rid}/paint`, { pts: flat(d.pts), radius: S.brush, erase: d.erase })
      .finally(() => { S.inflightPaint--; if (!S.inflightPaint && !S.painting) flushMasks(); });
  } else if (d.kind === 'pen' || d.kind === 'cut' || d.kind === 'wall') {
    let len = 0;
    for (let i = 1; i < d.pts.length; i++) len += Math.hypot(d.pts[i].x - d.pts[i - 1].x, d.pts[i].y - d.pts[i - 1].y);
    if (len < (d.kind === 'pen' ? 10 : 6)) { redraw(); return; }
    if (d.kind === 'cut') { cutAlong(d); redraw(); return; }
    if (d.kind === 'wall') {
      const pts = flat(d.pts);
      S.dividers = [...S.dividers, { id: -1, pts, path: polyPath(pts, 1, 0.5) }];
      redraw();
      edit('POST', '/dividers', { pts });
      return;
    }
    const pts = flat(d.pts);
    S.pending = { id: -1, region: S.current, pts, path: polyPath(pts, 1, 0.5) };
    redraw();
    edit('POST', '/strokes', { pts, hint: S.current }).then(() => { S.pending = null; redraw(); });
  }
  redraw();
}

cv.addEventListener('pointerup', endDrag);
cv.addEventListener('pointercancel', endDrag);
cv.addEventListener('pointerleave', () => {
  if (!S.drag) { S.mouse = null; $('#status-pos').textContent = ''; redraw(); }
});

cv.addEventListener('wheel', (e) => {
  if (!S.doc) return;
  e.preventDefault();
  const v = viewPos(e);
  const k = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018));
  zoomAt(v.x, v.y, S.view.s * k);
}, { passive: false });

// ------------------------------------------------------------------ export

// what can be exported, one file at a time; the main half of 导出 exports the last one picked (成品图 at first)
const EXPORTS = {
  png: { label: t('成品图'), desc: t('PNG，合成好的整张图'), main: t('导出成品图'), doing: t('正在导出成品图…'),
    done: t('已导出成品图到 {folder}'), needsLook: true },
  cutout: { label: t('仅丝袜'), desc: t('PNG，只有丝袜，其他地方透明'), main: t('导出仅丝袜'), doing: t('正在导出仅丝袜…'),
    done: t('已导出仅丝袜到 {folder}'), needsLook: true },
  guides: { label: t('丝袜引导.psd'), desc: t('部位和走向线，可以再打开接着改'), main: t('导出丝袜引导.psd'),
    doing: t('正在导出丝袜引导.psd…'), done: t('已导出丝袜引导.psd到 {folder}'), needsLook: false },
};
let exportKind = 'png';
let exporting = false;

function exportBlocked(kind) {
  return !S.doc ? '' : EXPORTS[kind].needsLook && !canLook() ? LOOK_LOCKED : null;
}

function renderExport() {
  const d = S.doc;
  const main = $('#btn-export');
  main.textContent = EXPORTS[exportKind].main;
  const blocked = exportBlocked(exportKind);
  main.disabled = !d || blocked !== null;
  main.title = !d ? '' : blocked
    || t('{what} (Ctrl+E)：选择保存位置和文件名，原文件不会被改动', { what: EXPORTS[exportKind].main });
  $('#btn-export-more').disabled = !d;
  if (!d) closeExportMenu();
}

// Returns true once the file is written. remember: the main half of 导出 exports this kind from now on.
async function exportDoc(kind = exportKind, { remember = true } = {}) {
  if (!S.doc || exporting) return false;
  const blocked = exportBlocked(kind);
  if (blocked) { flash(blocked); return false; }
  if (remember) { exportKind = kind; renderExport(); }
  const id = S.doc.id;
  exporting = true;
  $('#exported').hidden = true;
  try {
    busy(t('在弹出的窗口里选择保存位置和文件名…'));
    const to = await request('POST', `/api/doc/${id}/export/ask`, { kind });
    busy(null);
    if (!to || to.cancelled) return false;
    busy(EXPORTS[kind].doing);
    const body = { kind, path: to.path };
    if (EXPORTS[kind].needsLook) body.params = lookUI.params();
    const res = await request('POST', `/api/doc/${id}/export`, body);
    busy(null);
    showExported(res);
    flash(t(EXPORTS[kind].done, { folder: res.folder }));
    if (kind === 'guides') refresh(0);           // the guides are in a file now: nothing to lose by opening another
    return true;
  } catch (e) {
    busy(null);
    flash(e.message, true);
    return false;
  } finally {
    exporting = false;
  }
}

function showExported(res) {
  $('#exported-folder').textContent = res.folder;
  const li = document.createElement('li');
  const what = document.createElement('span');
  what.textContent = t('　{what}', { what: EXPORTS[res.kind].desc });
  const file = document.createElement('span');
  file.translate = false;
  file.textContent = res.file.split(/[\\/]/).pop();
  li.append(file, what);
  li.title = res.file;
  $('#exported-files').replaceChildren(li);
  $('#exported-notes').textContent = res.notes.join(t('；'));
  $('#exported').hidden = false;
}

function openExportMenu() {
  const m = $('#export-menu');
  closeMenus();
  m.replaceChildren(...Object.entries(EXPORTS).map(([k, e]) => {
    const b = document.createElement('button');
    b.setAttribute('role', 'menuitemradio');
    b.setAttribute('aria-checked', String(k === exportKind));
    const tick = document.createElement('span'); tick.className = 'tick'; tick.textContent = k === exportKind ? '✓' : '';
    tick.setAttribute('aria-hidden', 'true');
    const what = document.createElement('span'); what.className = 'what';
    const name = document.createElement('span'); name.textContent = e.label;
    if (k === 'guides') name.translate = false;
    const desc = document.createElement('span'); desc.className = 'desc'; desc.textContent = e.desc;
    what.append(name, desc);
    b.append(tick, what);
    const blocked = exportBlocked(k);
    b.disabled = blocked !== null;
    if (blocked) b.title = blocked;
    b.addEventListener('click', () => { closeExportMenu(); $('#btn-export').focus(); exportDoc(k); });
    return b;
  }));
  const at = $('.split').getBoundingClientRect();
  m.hidden = false;
  m.style.left = `${Math.round(Math.max(8, at.right - m.offsetWidth))}px`;
  m.style.top = `${Math.round(at.bottom + 6)}px`;
  $('#btn-export-more').setAttribute('aria-expanded', 'true');
  (m.querySelector('[aria-checked="true"]:not(:disabled)') || m.querySelector('button:not(:disabled)'))?.focus();
}

function closeExportMenu(refocus = false) {
  const m = $('#export-menu');
  if (m.hidden) return;
  m.hidden = true;
  m.replaceChildren();
  $('#btn-export-more').setAttribute('aria-expanded', 'false');
  if (refocus) $('#btn-export-more').focus();
}

$('#btn-export').addEventListener('click', () => exportDoc());
$('#btn-export-more').addEventListener('click', () => {
  if ($('#export-menu').hidden) openExportMenu(); else closeExportMenu();
});
$('#export-menu').addEventListener('keydown', (e) => {
  const items = [...$('#export-menu').querySelectorAll('button:not(:disabled)')];
  const i = items.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' && items.length) { e.preventDefault(); items[(i + 1) % items.length].focus(); }
  else if (e.key === 'ArrowUp' && items.length) { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  else if (e.key === 'Escape' || e.key === 'Tab') { e.preventDefault(); e.stopPropagation(); closeExportMenu(true); }
});
document.addEventListener('pointerdown', (e) => {
  if (!e.target.closest('#export-menu, #btn-export-more')) closeExportMenu();
});
window.addEventListener('resize', () => closeExportMenu());
$('#btn-exported-close').addEventListener('click', () => { $('#exported').hidden = true; });
$('#btn-reveal').addEventListener('click', () => {
  if (S.doc) request('POST', `/api/doc/${S.doc.id}/export/reveal`).catch((e) => flash(e.message, true));
});

// ------------------------------------------------------------------ opening files

// Opening another image replaces this one: its regions and 走向 lines are gone unless a file holds them (the one
// opened, or a 丝袜引导.psd exported since). Then ask first. Resolves true to go ahead.
async function readyToReplace() {
  if (!S.doc) return true;
  let d;
  try { d = await request('GET', '/api/doc'); } catch { d = S.doc; }    // the latest, not the last one drawn
  if (!d || !d.unsaved_guides) return true;
  const dlg = $('#confirm-open');
  $('#confirm-open-text').textContent = t('打开新图后，「{name}」的部位和走向线就找不回来了。先导出成丝袜引导.psd，以后可以再打开接着改。', { name: d.name });
  dlg.returnValue = '';
  dlg.showModal();
  const choice = await new Promise((resolve) => dlg.addEventListener('close', () => resolve(dlg.returnValue), { once: true }));
  if (choice === 'discard') return true;
  if (choice === 'export') return exportDoc('guides', { remember: false });
  return false;
}

async function openDialog() {
  if (!(await readyToReplace())) return;
  busy(t('在弹出的窗口里选择文件…'));
  try {
    const st = await request('POST', '/api/open/dialog');
    busy(null);
    if (st && st.cancelled) return;
    applyState(st);
  } catch (e) {
    busy(null);
    flash(e.message, true);
  }
}

async function openUpload(file) {
  if (!(await readyToReplace())) return;
  busy(t('正在打开 {name}…', { name: file.name }));
  const fd = new FormData();
  fd.append('file', file);
  try {
    applyState(await request('POST', '/api/open/upload', fd));
  } catch (e) {
    flash(e.message, true);
  } finally {
    busy(null);
  }
}

let dragDepth = 0;
window.addEventListener('dragenter', (e) => {
  if (![...e.dataTransfer.types].includes('Files')) return;
  e.preventDefault();
  dragDepth++;
  $('#drop').hidden = false;
});
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('dragleave', () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) $('#drop').hidden = true;
});
window.addEventListener('drop', (e) => {
  e.preventDefault();
  dragDepth = 0;
  $('#drop').hidden = true;
  const f = e.dataTransfer.files[0];
  if (f) openUpload(f);
});

// ------------------------------------------------------------------ buttons and keys

// the skip link moves the focus without putting #stage in the URL (a fragment there blocks a dialog's autofocus)
$('.skip').addEventListener('click', (e) => { e.preventDefault(); stage.focus(); });
$('#btn-open').addEventListener('click', openDialog);
$('#btn-open-2').addEventListener('click', openDialog);
$('#file-input').addEventListener('change', (e) => { const f = e.target.files[0]; if (f) openUpload(f); e.target.value = ''; });
$('#btn-undo').addEventListener('click', () => edit('POST', '/undo'));
$('#btn-redo').addEventListener('click', () => edit('POST', '/redo'));
$('#btn-fit').addEventListener('click', fit);
$('#btn-100').addEventListener('click', () => zoomCentre(1));

for (const b of document.querySelectorAll('.tool')) b.addEventListener('click', () => setTool(b.dataset.tool));
$('#brush-size').addEventListener('input', (e) => setBrush(+e.target.value));

for (const [id, key] of [['#show-regions', 'regions'], ['#show-strokes', 'strokes'], ['#show-courses', 'courses'], ['#show-wales', 'wales'], ['#show-walls', 'walls'], ['#show-coverage', 'coverage']]) {
  $(id).addEventListener('change', (e) => {
    S.show[key] = e.target.checked;
    if (key === 'coverage') { syncCoverage(); renderCoverageNote(); }
    redraw();
  });
}

$('#btn-add-region').addEventListener('click', async () => {
  const used = new Set(S.doc.regions.map((r) => r.name));
  let n = S.doc.regions.length + 1;
  while (used.has(t('部位 {n}', { n }))) n++;
  const st = await edit('POST', '/regions', { name: t('部位 {n}', { n }) });
  if (st && st.created) { selectRegion(st.created); startRename(st.created); }
});
$('#btn-auto-cut').addEventListener('click', () => {
  const r = currentRegion();
  if (!r) return;
  edit('POST', `/regions/${r.id}/split`).then((st) => splitDone(st, r.name));
});
$('#cut-snap').checked = localStorage.getItem('cut_snap') !== '0';
$('#cut-snap').addEventListener('change', (e) => { localStorage.setItem('cut_snap', e.target.checked ? '1' : '0'); redraw(); });

// ------------------------------------------------------------------ a region's ··· menu

let menuFor = null;          // region id whose menu is open

function closeMenus() {
  closeMergeSub();
  const m = $('#region-menu');
  if (m.hidden && menuFor === null) return;
  m.hidden = true;
  m.replaceChildren();
  const was = menuFor;
  menuFor = null;
  const btn = $(`#region-list .region[data-id="${was}"] .more`);
  if (btn) btn.setAttribute('aria-expanded', 'false');
}

function closeMergeSub() {
  const sub = $('#merge-menu');
  sub.hidden = true;
  sub.replaceChildren();
  for (const b of $('#region-menu').querySelectorAll('.open')) b.classList.remove('open');
}

function menuItem(label, onPick, { danger = false, chev = false, disabled = false } = {}) {
  const b = document.createElement('button');
  b.setAttribute('role', 'menuitem');
  if (danger) b.className = 'danger';
  const t = document.createElement('span'); t.textContent = label;
  b.append(t);
  if (chev) {
    const c = document.createElement('span'); c.className = 'chev'; c.textContent = '›';
    b.append(c);
    b.setAttribute('aria-haspopup', 'menu');
  }
  b.disabled = disabled;
  b.addEventListener('click', (e) => { e.stopPropagation(); onPick(b); });
  return b;
}

function openRegionMenu(rid, anchor) {
  const at = anchor.getBoundingClientRect();
  closeMenus();
  menuFor = rid;
  selectRegion(rid);
  const r = currentRegion();
  if (!r) { menuFor = null; return; }
  const m = $('#region-menu');
  m.replaceChildren(
    menuItem(t('改名'), () => { closeMenus(); startRename(r.id); }),
    menuItem(t('清空'), () => {
      closeMenus();
      focusRegion(r.id, 'more');
      edit('POST', `/regions/${r.id}/clear`).then((st) => { if (st) flash(t('已清空“{name}”，Ctrl+Z 可以撤销', { name: r.name })); });
    }),
    menuItem(t('合并到'), (b) => openMergeSub(r, b), { chev: true, disabled: S.doc.regions.length < 2 }),
    document.createElement('hr'),
    menuItem(t('删除'), () => {
      closeMenus();
      edit('DELETE', `/regions/${r.id}`).then((st) => {
        if (!st) return;
        flash(t('已删除“{name}”，Ctrl+Z 可以撤销', { name: r.name }));
        if (S.current !== null) focusRegion(S.current); else $('#btn-add-region').focus();
      });
    }, { danger: true }),
  );
  m.setAttribute('aria-label', t('{name}：更多操作', { name: r.name }));
  m.hidden = false;
  m.style.left = `${Math.round(at.right + 6)}px`;
  m.style.top = `${Math.round(Math.min(at.top - 4, window.innerHeight - m.offsetHeight - 8))}px`;
  const merge = m.querySelectorAll('button')[2];
  merge.addEventListener('pointerenter', () => { if (!merge.disabled && $('#merge-menu').hidden) openMergeSub(r, merge); });
  for (const b of [...m.querySelectorAll('button')].filter((x) => x !== merge)) b.addEventListener('pointerenter', closeMergeSub);
  const btn = $(`#region-list .region[data-id="${rid}"] .more`);
  if (btn) btn.setAttribute('aria-expanded', 'true');
  m.querySelector('button').focus();
}

async function openMergeSub(r, item) {
  if (item.classList.contains('open')) return;
  closeMergeSub();
  item.classList.add('open');
  let list;
  try {
    list = await request('GET', `/api/doc/${S.doc.id}/regions/${r.id}/neighbours`);
  } catch (e) { flash(e.message, true); return; }
  if (menuFor !== r.id || !item.classList.contains('open')) return;
  const sub = $('#merge-menu');
  const head = document.createElement('div');
  head.className = 'head';
  head.textContent = t('把“{name}”并进', { name: r.name });
  sub.replaceChildren(head);
  for (const o of list) {
    const b = document.createElement('button');
    b.setAttribute('role', 'menuitem');
    b.style.setProperty('--c', o.color);
    const sw = document.createElement('span'); sw.className = 'sw';
    const name = document.createElement('span'); name.textContent = o.name;
    const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = o.shared ? t('相邻') : '';
    b.append(sw, name, tag);
    b.addEventListener('click', () => {
      closeMenus();
      edit('POST', `/regions/${r.id}/merge`, { into: o.id }).then((st) => {
        if (!st) return;
        selectRegion(o.id);
        focusRegion(o.id);
        flash(t('已把“{name}”并进“{into}”，Ctrl+Z 可以撤销', { name: r.name, into: o.name }));
      });
    });
    sub.append(b);
  }
  const at = item.getBoundingClientRect();
  sub.hidden = false;
  sub.style.left = `${Math.round(at.right + 8)}px`;
  sub.style.top = `${Math.round(Math.min(at.top - 34, window.innerHeight - sub.offsetHeight - 8))}px`;
}

document.addEventListener('pointerdown', (e) => {
  if (menuFor !== null && !e.target.closest('.menu, .region .more')) closeMenus();
});
window.addEventListener('resize', closeMenus);
$('.side').addEventListener('scroll', closeMenus);

// ------------------------------------------------------------------ 镜像: the current region's strokes onto the other side

const SIDE_SWAP = { 左: '右', 右: '左', Left: 'Right', Right: 'Left', left: 'right', right: 'left' };

// The region named like r with left and right swapped (左腿 ↔ 右腿, and 左胸-左 ↔ 右胸-右 after a cut), or null.
function mirrorPartner(r) {
  const name = r.name.replace(/左|右|Left|Right|left|right/g, (m) => SIDE_SWAP[m]);
  return name === r.name ? null : S.doc.regions.find((o) => o.id !== r.id && o.name === name) || null;
}

function mirrorBlocked(r) {
  if (!r) return t('先在上面选一个部位');
  if (S.doc.regions.length < 2) return t('至少要两个部位才能镜像');
  if (!r.strokes) return t('先在“{name}”上画走向线，再镜像到另一边', { name: r.name });
  return null;
}

function renderMirror() {
  const b = $('#btn-mirror');
  const r = currentRegion();
  const blocked = S.doc ? mirrorBlocked(r) : '';
  const p = S.doc && r ? mirrorPartner(r) : null;
  b.setAttribute('aria-disabled', String(blocked !== null));
  if (p || blocked !== null) {
    b.removeAttribute('aria-haspopup');
    b.removeAttribute('aria-expanded');
  } else {
    b.setAttribute('aria-haspopup', 'menu');
    b.setAttribute('aria-expanded', String(!$('#mirror-menu').hidden));
  }
  setTip(b, blocked || (r && (p
    ? t('把“{name}”的走向线左右翻转，按两边的轮廓对齐画到“{into}”上，替换它原来的走向线。镜像出来的线可以照常修改。', { name: r.name, into: p.name })
    : t('把“{name}”的走向线左右翻转，按两边的轮廓对齐画过去，替换那边原来的走向线。镜像出来的线可以照常修改。', { name: r.name }))));
  if (blocked !== null) closeMirrorMenu();
}

function mirrorTo(r, o) {
  closeMirrorMenu();
  edit('POST', `/regions/${r.id}/mirror`, { into: o.id }).then((st) => {
    if (st) flash(t('已把“{name}”的走向线镜像到“{into}”，Ctrl+Z 可以撤销', { name: r.name, into: o.name }));
  });
}

function closeMirrorMenu() {
  const m = $('#mirror-menu');
  if (m.hidden) return;
  m.hidden = true;
  m.replaceChildren();
  const b = $('#btn-mirror');
  if (b.hasAttribute('aria-expanded')) b.setAttribute('aria-expanded', 'false');
}

// No region is named as r's other side: the user picks it.
function openMirrorMenu(r, anchor) {
  const m = $('#mirror-menu');
  const head = document.createElement('div');
  head.className = 'head';
  head.textContent = t('把“{name}”的走向线镜像到', { name: r.name });
  m.replaceChildren(head);
  for (const o of S.doc.regions.filter((x) => x.id !== r.id)) {
    const b = document.createElement('button');
    b.setAttribute('role', 'menuitem');
    b.style.setProperty('--c', o.color);
    const sw = document.createElement('span'); sw.className = 'sw';
    const name = document.createElement('span'); name.textContent = o.name;
    const tag = document.createElement('span'); tag.className = 'tag';
    tag.textContent = o.strokes ? t('替换 {n} 条', { n: o.strokes }) : '';
    b.append(sw, name, tag);
    b.addEventListener('click', () => { mirrorTo(r, o); anchor.focus(); });
    m.append(b);
  }
  const at = anchor.getBoundingClientRect();
  m.hidden = false;
  m.style.left = `${Math.round(at.left)}px`;
  m.style.top = `${Math.round(Math.min(at.bottom + 4, window.innerHeight - m.offsetHeight - 8))}px`;
  anchor.setAttribute('aria-expanded', 'true');
  m.querySelector('button').focus();
}

$('#btn-mirror').addEventListener('click', (e) => {
  const b = e.currentTarget;
  if (!$('#mirror-menu').hidden) { closeMirrorMenu(); return; }
  const r = currentRegion();
  const blocked = S.doc ? mirrorBlocked(r) : '';
  if (blocked !== null) { if (blocked) flash(blocked); return; }
  const p = mirrorPartner(r);
  if (p) mirrorTo(r, p); else openMirrorMenu(r, b);
});
$('#mirror-menu').addEventListener('keydown', (e) => {
  const items = [...$('#mirror-menu').querySelectorAll('button')];
  const i = items.indexOf(document.activeElement);
  if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  else if (e.key === 'Escape' || e.key === 'Tab') {
    e.preventDefault(); e.stopPropagation();
    closeMirrorMenu();
    $('#btn-mirror').focus();
  }
});
document.addEventListener('pointerdown', (e) => {
  if (!e.target.closest('#mirror-menu, #btn-mirror')) closeMirrorMenu();
});
window.addEventListener('resize', closeMirrorMenu);
$('.side').addEventListener('scroll', closeMirrorMenu);

// arrows move through the open menu; → opens 合并到, ← and Esc step back out
for (const sel of ['#region-menu', '#merge-menu']) {
  $(sel).addEventListener('keydown', (e) => {
    const menu = $(sel);
    const items = [...menu.querySelectorAll('button:not(:disabled)')];
    const i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' && items.length) { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp' && items.length) { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    else if (e.key === 'ArrowRight' && sel === '#region-menu' && document.activeElement.getAttribute('aria-haspopup')) {
      e.preventDefault();
      const item = document.activeElement;
      const r = currentRegion();
      if (r) openMergeSub(r, item).then(() => { const f = $('#merge-menu button'); if (f) f.focus(); });
    } else if ((e.key === 'ArrowLeft' || e.key === 'Escape') && sel === '#merge-menu') {
      e.preventDefault(); e.stopPropagation();
      const open = $('#region-menu .open');
      closeMergeSub();
      if (open) open.focus();
    } else if (e.key === 'Escape' || e.key === 'Tab') {
      e.preventDefault(); e.stopPropagation();
      const rid = menuFor;
      closeMenus();
      focusRegion(rid, 'more');
    }
  });
}

$('#region-list').addEventListener('keydown', (e) => {
  if (!S.doc || renaming !== null) return;
  if (e.key === 'F2') { e.preventDefault(); if (S.current !== null) startRename(S.current); return; }
  if (!['ArrowUp', 'ArrowDown'].includes(e.key)) return;
  e.preventDefault();
  e.stopPropagation();
  const ids = S.doc.regions.map((r) => r.id);
  const i = ids.indexOf(S.current) + (e.key === 'ArrowDown' ? 1 : -1);
  if (i >= 0 && i < ids.length) {
    selectRegion(ids[i]);
    focusRegion(ids[i], e.target.classList.contains('more') ? 'more' : 'pick');
  }
});

// Space pans and Tab cycles 点选's range only while the keyboard is not on a control: a control reached with the
// keyboard keeps its own keys (Space presses it, Tab moves on). A control clicked with the mouse keeps the focus,
// and Space still pans after it. (:focus-visible cannot tell them apart: any key press turns it on.)
function onCanvas() {
  const a = document.activeElement;
  return !a || a === document.body || a === cv || a === stage;
}

function keyboardOnControl() {
  return !onCanvas() && !focusByPointer;
}

const PAN_KEYS = { ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };

const TOOL_KEYS = { s: 'segment', b: 'brush', e: 'erase', p: 'pen', k: 'cut', w: 'wall' };

window.addEventListener('keydown', (e) => {
  if (e.target instanceof HTMLInputElement && e.target.type !== 'checkbox' && e.target.type !== 'range') return;
  if (e.target instanceof Element && e.target.closest('.menu, dialog')) return;
  const k = e.key.toLowerCase();
  if (e.key === 'Tab' && S.mode === 'edit' && S.doc && S.doc.segment_cycle && !e.ctrlKey && !e.altKey && onCanvas()) {
    e.preventDefault();
    cycleSegment(e.shiftKey ? -1 : 1);
    return;
  }
  if (e.ctrlKey || e.metaKey) {
    if (k === 'z') { e.preventDefault(); edit('POST', e.shiftKey ? '/redo' : '/undo'); }
    else if (k === 'y') { e.preventDefault(); edit('POST', '/redo'); }
    else if (k === 'o') { e.preventDefault(); openDialog(); }
    else if (k === 'e') { e.preventDefault(); exportDoc(); }
    return;
  }
  if (e.code === 'Space') {
    if (S.mode !== 'edit' || keyboardOnControl()) return;
    e.preventDefault();
    if (!S.space) { S.space = true; stage.classList.add('panning'); redraw(); }
    return;
  }
  if (!S.doc || S.mode !== 'edit') return;
  if (e.key === 'Escape' && S.tool === 'cut') {
    if (S.drag && S.drag.kind === 'cut') { S.drag = null; redraw(); } else leaveCut();
    return;
  }
  if (PAN_KEYS[e.key] && onCanvas()) {
    e.preventDefault();
    const [dx, dy] = PAN_KEYS[e.key];
    const step = (e.shiftKey ? 0.4 : 0.1) * Math.min(stageBox.width, stageBox.height);
    S.view.x += dx * step;
    S.view.y += dy * step;
    redraw();
    return;
  }
  if (k === '+' || k === '=') { zoomCentre(S.view.s * 1.25); return; }
  if (k === '-' || k === '_') { zoomCentre(S.view.s / 1.25); return; }
  if (TOOL_KEYS[k]) setTool(TOOL_KEYS[k]);
  else if (k === '[') setBrush(S.brush / 1.2);
  else if (k === ']') setBrush(S.brush * 1.2);
  else if (k === 'f') fit();
  else if (k === '1') zoomCentre(1);
  else if ((k === 'delete' || k === 'backspace') && S.hover !== null) deleteStroke(S.hover);
  else if ((k === 'delete' || k === 'backspace') && S.wallHover) removeWallAt(S.wallHover.at);
});

window.addEventListener('keyup', (e) => {
  if (e.code === 'Space') { S.space = false; stage.classList.remove('panning'); redraw(); }
});

window.addEventListener('blur', () => { S.space = false; stage.classList.remove('panning'); });

// ------------------------------------------------------------------ server events

// The page reloads when it reconnects to a server running different code (after an update), so the UI and the
// server never disagree about the API.
let serverVersion = null;

function checkVersion() {
  request('GET', '/api/ping').then((p) => {
    if (serverVersion && p.version !== serverVersion) location.reload();
    else serverVersion = p.version;
  }).catch(() => {});
}

function connectEvents() {
  const es = new EventSource('/api/events');
  es.onopen = () => { checkVersion(); refresh(0); };
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === 'opening') busy(t('正在打开 {name}…', { name: ev.name }));
    else if (ev.type === 'open-failed') { busy(null); flash(t('打不开 {name}：{error}', { name: ev.name, error: ev.error }), true); }
    else if (ev.type === 'opened') { busy(null); refresh(0); }
    else if (ev.type === 'sam') refresh();
    else if (ev.type === 'depth') lookUI.onEvent(ev);
    else if (S.doc && ev.doc === S.doc.id) {
      lookUI.onEvent(ev);
      if (ev.type === 'solved') {
        const r = S.doc.regions.find((x) => x.id === ev.region);
        if (r && ev.error) flash(t('{name}：{error}', { name: r.name, error: ev.error }), true);
        else if (r) flash(t('{name}的横纹已更新，用时 {s} 秒', { name: r.name, s: ev.seconds }));
      }
      refresh();
    }
  };
}

new ResizeObserver(resize).observe(stage);
setTool('segment');
setBrush(S.brush);
renderChrome();
connectEvents();
