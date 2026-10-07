// 纹理 mode: look settings, the whole image area-averaged to fit (整体), and a live square crop (细节).
//
// The crop follows every slider move: one request in flight at a time, and when it lands the newest settings go
// out next, so a fast drag never queues up stale renders. The whole image (≈0.5 s on the server) and the check
// overlay wait until the sliders rest.

import { t } from './i18n.js';

const $ = (s) => document.querySelector(s);

const REF_AREA = 1280 * 1920;
const STYLE_NOTES = {
  knit: t('线与线之间的细缝透出肤色：浅色丝袜上是粉色细线，深色丝袜上是暖色亮线。'),
  loops: t('一列列 V 形线圈，像丝袜脚底加厚部分的织法。线圈小，密度调低一些更清楚。'),
  lines: t('斜着走的细线，加暖色的单像素亮点。'),
  grain: t('细碎颗粒的针织底纹，加白色小亮点。'),
  oily: t('试验：半透明的油亮丝袜，反光按画面里画出的光影找，换一张图可能不稳定。'),
};

// Stage layout. 细节 is a square; one live render fills at most BUDGET image px (measured: ~65 ms for 细线,
// ~120 ms for 加濑风), which at 200% caps its side at 1000 css px on a 100% screen, 667 at 150% scaling.
const BUDGET = 250_000;
const DMIN = 320;               // css px: 细节 never smaller (less on a very small window)
const WHOLE_WEIGHT = 0.6;       // 整体 counts a little more than 细节 when they share the stage
const PAD = 16, GAP = 18, HEAD = 34, FOOT = 30;

// Where 整体 and the square 细节 go: side by side, or 细节 below. Every size of the square is tried in both
// arrangements, and the one where the two are largest together wins (geometric mean of their areas, 整体 weighted).
// Space 细节 cannot use goes to 整体; what neither can use is shared out evenly left and right.
export function arrange(W, H, iw, ih, dpr) {
  const a = iw / ih;
  const dmax = (Math.sqrt(BUDGET) * 2) / dpr;
  const dmin = Math.min(DMIN, 0.3 * Math.min(W, H));
  let best = null;
  for (const mode of ['side', 'stack']) {
    const body = mode === 'side' ? H - HEAD - FOOT : H - 2 * HEAD - FOOT - GAP;
    const lim = Math.min(dmax, mode === 'side' ? body : W);
    for (let d = Math.floor(dmin); d <= lim; d += 2) {
      const ww = mode === 'side' ? Math.min(W - GAP - d, a * body) : Math.min((body - d) * a, W);
      const wh = ww / a;
      if (ww < 40 || wh < 40) continue;
      const score = WHOLE_WEIGHT * Math.log(ww * wh) + (1 - WHOLE_WEIGHT) * Math.log(d * d);
      if (!best || score > best.score) best = { score, mode, ww: Math.floor(ww), wh: Math.floor(wh), d };
    }
  }
  if (!best) {                  // a tiny window: share it as well as possible
    const d = Math.max(60, Math.floor(Math.min(W / 2 - GAP, H - HEAD - FOOT)));
    const ww = Math.max(40, Math.floor(Math.min(W - GAP - d, a * (H - HEAD - FOOT))));
    best = { mode: 'side', ww, wh: Math.floor(ww / a), d };
  }
  const span = best.mode === 'side' ? best.ww + GAP + best.d : Math.max(best.ww, best.d);
  const ox = PAD + Math.max(0, Math.floor((W - span) / 2));
  return best.mode === 'side'
    ? { ...best, whole: { x: ox, y: PAD }, detail: { x: ox + best.ww + GAP, y: PAD } }
    : { ...best, whole: { x: ox, y: PAD }, detail: { x: ox, y: PAD + HEAD + best.wh + GAP } };
}

// A range input lit up to its thumb.
export function fillRange(el) {
  const lo = +el.min || 0, hi = +el.max || 100;
  el.style.setProperty('--p', `${(100 * (+el.value - lo)) / (hi - lo)}%`);
}
document.addEventListener('input', (e) => { if (e.target.type === 'range') fillRange(e.target); }, true);

function latest(fn) {
  let running = false;
  let again = false;
  const go = async () => {
    if (running) { again = true; return; }
    running = true;
    try { await fn(); } catch (e) { console.warn(e); } finally {
      running = false;
      if (again) { again = false; go(); }
    }
  };
  return go;
}

function debounce(fn, ms) {
  let t = 0;
  return () => { clearTimeout(t); t = setTimeout(fn, ms); };
}

// "100" with a smaller "%" after it
function setVal(el, n, unit) {
  const u = document.createElement('span');
  u.className = 'unit';
  u.textContent = unit;
  el.replaceChildren(String(Math.round(n)), u);
}

const PCT = [0, 1].map((d) => new Intl.NumberFormat('zh-CN', { style: 'percent', minimumFractionDigits: d, maximumFractionDigits: d }));

function pct(x) {
  if (x <= 0) return t('没有');
  return x < 0.001 ? t('不到 {p}', { p: PCT[1].format(0.001) }) : PCT[x < 0.1 ? 1 : 0].format(x);
}

export function createLook({ getDoc, getArt, request, edit, flash, focusByKeyboard = () => false }) {
  const L = {
    active: false,
    docId: null,
    params: null,
    info: null,
    centre: null,          // crop centre in image px; null = where the courses are densest
    zoom: 2,               // crop magnification, 200% by default
    showCheck: false,
    peek: false,           // space held: 细节 shows the original
    size: null,
    fitImg: null,
    split: 0.5,            // before/after divider on 整体: original left of it, effect right of it
    splitDrag: false,
    checkImg: null,
    cropImg: null,
    cropRect: null,
    fitBusy: false,
    drag: null,
  };
  const fitCv = $('#fit');
  const cropCv = $('#crop');
  const stageColour = getComputedStyle(document.documentElement).getPropertyValue('--stage').trim();

  // ---------------------------------------------------------------- settings

  function query(extra) {
    const p = L.params;
    const q = new URLSearchParams({ style: p.style, density: p.density, tilt: p.tilt,
      strength: p.strength, strength_auto: p.strength_auto,
      sparkle_depth: p.sparkle_depth, sparkle_bright: p.sparkle_bright, sparkle_painted: p.sparkle_painted,
      sparkle_even: p.sparkle_even,
      sparkle_link: p.sparkle_link });
    for (const [k, v] of Object.entries(extra || {})) q.set(k, v);
    return q.toString();
  }

  // With 关联 on, depth and brightness always hold the same amount: moving either moves both to that value.
  function setAmount(key, value) {
    set(L.params.sparkle_link ? { sparkle_depth: value, sparkle_bright: value } : { [key]: value });
  }

  // Turning 关联 on makes the two equal, taking the depth amount.
  function toggleLink() {
    const on = !L.params.sparkle_link;
    set(on ? { sparkle_link: true, sparkle_bright: L.params.sparkle_depth } : { sparkle_link: false },
      { immediate: on });
  }

  function localPeriod(doc, density) {
    const raw = 4.6 / (density / 100) * Math.sqrt(doc.width * doc.height / REF_AREA);
    return { raw, period: Math.max(raw, 3.2), clamped: raw < 3.2 };
  }

  function set(changes, { immediate = true } = {}) {
    if (L.beforeReset && changes !== L.beforeReset) { L.beforeReset = null; renderReset(); }   // a new change ends the undo window
    Object.assign(L.params, changes);
    renderControls();
    if (immediate) requestCrop();
    saveSoon();
    fitSoon();
  }

  // While strength is automatic the server picks it from the stockings' lightness; show what it picked.
  function adoptInfo(info) {
    const moved = !L.centre && L.info && String(L.info.densest) !== String(info.densest);
    L.info = info;
    if (L.params && L.params.strength_auto && info.params.strength !== L.params.strength) {
      L.params.strength = info.params.strength;
      renderControls();
    }
    renderInfo();
    if (moved) requestCrop();          // the crop follows the densest courses, and they moved (a region re-solved)
  }

  const save = latest(async () => {
    const doc = getDoc();
    if (!doc || !L.params) return;
    const info = await request('PUT', `/api/doc/${doc.id}/look`, L.params);
    if (getDoc() && getDoc().id === doc.id) adoptInfo(info);
  });
  const saveSoon = debounce(save, 150);

  // ---------------------------------------------------------------- layout

  function layout() {
    const doc = getDoc();
    if (!doc) return false;
    const box = $('#look-stage').getBoundingClientRect();
    if (box.width < 50 || box.height < 50) return false;
    const dpr = window.devicePixelRatio || 1;
    const A = arrange(box.width - 2 * PAD, box.height - 2 * PAD, doc.width, doc.height, dpr);
    const whole = $('.whole-pane'), detail = $('.detail-pane');
    Object.assign(whole.style, { left: `${A.whole.x}px`, top: `${A.whole.y}px`, width: `${A.ww}px` });
    Object.assign(detail.style, { left: `${A.detail.x}px`, top: `${A.detail.y}px`, width: `${A.d}px` });
    fitCv.style.width = `${A.ww}px`;
    fitCv.style.height = `${A.wh}px`;
    fitCv.width = Math.round(A.ww * dpr);
    fitCv.height = Math.round(A.wh * dpr);
    const cw = Math.round(A.d * dpr);
    cropCv.width = cw;
    cropCv.height = cw;
    cropCv.style.width = `${A.d}px`;
    cropCv.style.height = `${A.d}px`;
    const changed = !L.size || L.size.fitW !== fitCv.width || L.size.fitH !== fitCv.height || L.size.cropW !== cw;
    L.size = { dpr, fitW: fitCv.width, fitH: fitCv.height, cropW: cw, cropH: cw, scale: fitCv.width / doc.width, mode: A.mode };
    cmp.style.height = `${A.wh}px`;
    $('#compare-tags').style.width = `${A.ww}px`;
    placeCompare();
    drawFit();
    drawCrop();
    return changed;
  }

  // ---------------------------------------------------------------- 细节

  function cropRect() {
    const doc = getDoc();
    const w = Math.max(1, Math.round(L.size.cropW / L.zoom));
    const h = Math.max(1, Math.round(L.size.cropH / L.zoom));
    const c = L.centre || (L.info && { x: L.info.densest[0], y: L.info.densest[1] }) || { x: doc.width / 2, y: doc.height / 2 };
    const x0 = Math.round(Math.min(Math.max(c.x - w / 2, 0), Math.max(doc.width - w, 0)));
    const y0 = Math.round(Math.min(Math.max(c.y - h / 2, 0), Math.max(doc.height - h, 0)));
    return { x0, y0, w: Math.min(w, doc.width), h: Math.min(h, doc.height) };
  }

  const requestCrop = latest(async () => {
    const doc = getDoc();
    if (!L.active || !doc || !L.size || !L.params || !L.info) return;
    const r = cropRect();
    const q = query({ x0: r.x0, y0: r.y0, w: r.w, h: r.h });
    const [res, check] = await Promise.all([
      fetch(`/api/doc/${doc.id}/render/crop?${q}`),
      L.showCheck ? fetch(`/api/doc/${doc.id}/render/check?${q}`).then((x) => x.blob()).then(createImageBitmap) : null,
    ]);
    if (!res.ok) throw new Error(await res.text());
    const meta = JSON.parse(res.headers.get('X-Look') || '{}');
    const img = await createImageBitmap(await res.blob());
    if (!getDoc() || getDoc().id !== doc.id) return;
    L.cropImg = img;
    L.cropCheckImg = check;
    L.cropRect = { x0: meta.x0, y0: meta.y0, w: meta.w, h: meta.h };
    L.cropMs = meta.ms;
    drawCrop();
    drawFit();
  });

  function drawCrop() {
    const c = cropCv.getContext('2d');
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.fillStyle = stageColour;
    c.fillRect(0, 0, cropCv.width, cropCv.height);
    const densest = $('#btn-densest');
    densest.disabled = !L.centre;
    densest.textContent = L.centre ? t('回到最密处') : t('已在最密处');
    if (!L.cropImg) return;
    c.imageSmoothingEnabled = false;
    const r = L.cropRect, art = getArt();
    if (L.peek && art && r) c.drawImage(art, r.x0, r.y0, r.w, r.h, 0, 0, r.w * L.zoom, r.h * L.zoom);
    else c.drawImage(L.cropImg, 0, 0, L.cropImg.width * L.zoom, L.cropImg.height * L.zoom);
    if (L.showCheck && L.cropCheckImg && !L.peek) {
      c.globalAlpha = 0.6;      // lighter than on 整体, so the texture still shows through
      c.drawImage(L.cropCheckImg, 0, 0, L.cropCheckImg.width * L.zoom, L.cropCheckImg.height * L.zoom);
      c.globalAlpha = 1;
    }
  }

  function setPeek(on) {
    if (L.peek === on) return;
    L.peek = on;
    $('#peek-hint').classList.toggle('on', on);
    drawCrop();
  }

  // ---------------------------------------------------------------- 整体 and the check overlay

  const requestFit = latest(async () => {
    const doc = getDoc();
    if (!L.active || !doc || !L.size || !L.params || !L.info || !L.info.textured) return;
    L.fitBusy = true;
    renderFitStatus();
    const q = query({ w: L.size.fitW, h: L.size.fitH });
    try {
      const [fit, check] = await Promise.all([
        fetch(`/api/doc/${doc.id}/render/fit?${q}`).then((r) => r.blob()).then(createImageBitmap),
        L.showCheck ? fetch(`/api/doc/${doc.id}/render/check?${q}`).then((r) => r.blob()).then(createImageBitmap) : null,
      ]);
      if (!getDoc() || getDoc().id !== doc.id) return;
      L.fitImg = fit;
      L.checkImg = check;
      drawFit();
    } finally {
      L.fitBusy = false;
      renderFitStatus();
    }
  });
  const fitSoon = debounce(requestFit, 200);

  function drawFit() {
    const c = fitCv.getContext('2d');
    const W = fitCv.width, H = fitCv.height;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.fillStyle = stageColour;
    c.fillRect(0, 0, W, H);
    if (L.fitImg) c.drawImage(L.fitImg, 0, 0, W, H);
    const sx = Math.round(L.split * W);
    const art = getArt();
    if (art && sx > 0) {
      c.save();
      c.beginPath();
      c.rect(0, 0, sx, H);
      c.clip();
      c.imageSmoothingQuality = 'high';
      c.drawImage(art, 0, 0, W, H);
      c.restore();
    }
    if (L.showCheck && L.checkImg) {
      c.save();
      c.beginPath();
      c.rect(sx, 0, W - sx, H);
      c.clip();
      c.drawImage(L.checkImg, 0, 0, W, H);
      c.restore();
    }
    if (L.cropRect && L.size) {
      const s = L.size.scale;
      const r = L.cropRect;
      c.lineWidth = 3;
      c.strokeStyle = 'rgba(0,0,0,0.6)';
      c.strokeRect(r.x0 * s, r.y0 * s, r.w * s, r.h * s);
      c.lineWidth = 1.5;
      c.strokeStyle = '#ffffff';
      c.strokeRect(r.x0 * s, r.y0 * s, r.w * s, r.h * s);
    }
  }

  function renderFitStatus() {
    $('#fit-status').textContent = L.fitBusy ? t('更新中…') : t('缩到窗口大小，看整体观感');
  }

  const cmp = $('#compare');

  function placeCompare() {
    if (!L.size) return;
    const w = L.size.fitW / L.size.dpr;
    const p = Math.round(L.split * 100);
    cmp.style.left = `${L.split * w}px`;
    cmp.setAttribute('aria-valuenow', String(p));
    cmp.setAttribute('aria-valuetext', t('左边 {p}% 是原图', { p }));
    $('#compare-before').style.visibility = L.split > 0.12 ? 'visible' : 'hidden';
    $('#compare-after').style.visibility = L.split < 0.88 ? 'visible' : 'hidden';
  }

  function setSplit(x) {
    L.split = Math.min(1, Math.max(0, x));
    placeCompare();
    drawFit();
  }

  // ---------------------------------------------------------------- panel

  function renderControls() {
    const p = L.params;
    const doc = getDoc();
    if (!p || !doc) return;
    for (const b of document.querySelectorAll('.styles .opt')) b.setAttribute('aria-checked', String(b.dataset.style === p.style));
    $('#style-note').textContent = STYLE_NOTES[p.style];
    $('#density').value = p.density;
    setVal($('#density-val'), p.density, '%');
    const g = localPeriod(doc, p.density);
    const note = $('#density-note');
    if (g.clamped) {
      const max = Math.floor(100 * 4.6 * Math.sqrt(doc.width * doc.height / REF_AREA) / 3.2);
      note.textContent = t('横纹间距已到 3.2\u00a0px 下限，再密就会出摩尔纹，这张图最多 {max}%。想更密，先把图放大（比如 1.5 倍）再来。', { max });
      note.className = 'sub warn';
    } else {
      note.textContent = t('横纹间距 {p}\u00a0px', { p: g.period.toFixed(2) });
      note.className = 'sub';
    }
    $('#tilt-section').hidden = p.style !== 'lines';
    $('#tilt').value = p.tilt;
    setVal($('#tilt-val'), p.tilt, '°');
    $('#strength').value = p.strength;
    setVal($('#strength-val'), p.strength, '%');
    $('#strength-auto').hidden = !p.strength_auto;
    $('#btn-strength-auto').hidden = !!p.strength_auto;
    for (const k of ['depth', 'bright', 'painted', 'even']) {
      $(`#sparkle-${k}`).value = p[`sparkle_${k}`];
      setVal($(`#sparkle-${k}-val`), p[`sparkle_${k}`], '%');
    }
    $('#btn-sparkle-link').setAttribute('aria-pressed', String(!!p.sparkle_link));
    $('#btn-check').setAttribute('aria-pressed', String(L.showCheck));
    $('#check-legend').hidden = !L.showCheck;
    $('#peek-hint').hidden = L.showCheck;
    for (const el of document.querySelectorAll('.look-only input[type="range"]')) fillRange(el);
    renderExclude();
    renderReset();
  }

  // 颜色排除 is a document setting (undoable, saved with the work), not a look parameter
  function renderExclude() {
    const doc = getDoc();
    if (!doc) return;
    const on = doc.color_exclude !== false;
    $('#exclude').checked = on;
    const i = L.info;
    $('#exclude-note').textContent = !on ? t('已关闭：部位里每一处都加纹理。')
      : !i ? '' : i.solving.length ? t('正在更新…')
        : i.check.excluded > 0 ? t('现在排除了已涂部位的 {p}。', { p: pct(i.check.excluded) }) : t('这张图没有被排除的地方。');
  }

  function renderInfo() {
    const i = L.info;
    if (!i) return;
    $('#check-faded').textContent = pct(i.check.faded);
    $('#check-excluded').textContent = pct(i.check.excluded);
    renderExclude();
    const ns = $('#check-nostroke');
    ns.textContent = (i.untextured.length ? pct(i.check.nostroke) : t('没有')) + (i.solving.length ? t('（求解中…）') : '');
    const tip = t('部位已经涂好，但还没画走向线，所以不生成纹理。')
      + (i.untextured.length ? t('没有走向线的部位：{names}。', { names: i.untextured.join(t('、')) }) : '')
      + (i.solving.length ? t('{names}正在求解，求解完再看。', { names: i.solving.join(t('、')) }) : '');
    ns.parentElement.dataset.tip = tip;
    ns.parentElement.setAttribute('aria-description', tip);
    $('#sparkle-painted-field').hidden = !i.has_sparkle_layer;
    const sn = $('#sparkle-note');
    sn.className = 'note';
    const usesDepth = L.params.sparkle_depth > 0;
    if (usesDepth && i.depth !== 'ready' && i.depth !== 'error') sn.textContent = t('正在估算深度（第一次要几秒）…');
    else if (usesDepth && i.depth === 'error') {
      sn.textContent = t('深度模型不可用：{error}。按深度的亮点先不显示，按画面亮部的照常。', { error: i.depth_error || t('未知错误') });
      sn.className = 'note warn';
    } else sn.textContent = '';
  }

  // ---------------------------------------------------------------- lifecycle

  async function load() {
    const doc = getDoc();
    if (!doc) return;
    const info = await request('GET', `/api/doc/${doc.id}/look`);
    if (!getDoc() || getDoc().id !== doc.id) return;
    L.info = info;
    L.params = { ...info.params };
    renderControls();
    renderInfo();
    layout();
    renderFitStatus();
    requestCrop();
    requestFit();
  }

  function refresh() {
    if (!L.active) return;
    const doc = getDoc();
    if (!doc || !L.params) return;        // a document still loading: load() fetches the latest itself
    request('GET', `/api/doc/${doc.id}/look?${query()}`).then((info) => {
      if (!getDoc() || getDoc().id !== doc.id) return;
      adoptInfo(info);
      requestCrop();
      requestFit();
    }).catch((e) => flash(e.message, true));
  }
  const refreshSoon = debounce(refresh, 300);

  // ---------------------------------------------------------------- input

  for (const b of document.querySelectorAll('.styles .opt')) b.addEventListener('click', () => set({ style: b.dataset.style }));
  $('#density').addEventListener('input', (e) => set({ density: +e.target.value }));
  $('#tilt').addEventListener('input', (e) => set({ tilt: +e.target.value }));
  $('#strength').addEventListener('input', (e) => set({ strength: +e.target.value, strength_auto: false }));
  $('#btn-strength-auto').addEventListener('click', () => set({ strength_auto: true }));
  $('#sparkle-depth').addEventListener('input', (e) => setAmount('sparkle_depth', +e.target.value));
  $('#sparkle-bright').addEventListener('input', (e) => setAmount('sparkle_bright', +e.target.value));
  $('#sparkle-painted').addEventListener('input', (e) => set({ sparkle_painted: +e.target.value }));
  $('#sparkle-even').addEventListener('input', (e) => set({ sparkle_even: +e.target.value }));
  $('#btn-sparkle-link').addEventListener('click', toggleLink);
  $('#exclude').addEventListener('change', (e) => {
    const doc = getDoc();
    if (!doc) return;
    const on = e.target.checked;
    e.target.checked = doc.color_exclude !== false;           // shown once the server has it
    edit('PUT', '/coverage/exclude', { on }).then((st) => {
      if (st) flash(st.color_exclude ? t('已打开颜色排除，Ctrl+Z 可以撤销') : t('已关闭颜色排除：部位里每一处都加纹理，Ctrl+Z 可以撤销'));
    });
  });
  $('#btn-check').addEventListener('click', () => {
    L.showCheck = !L.showCheck;
    renderControls();
    drawFit();
    drawCrop();
    requestFit();
    requestCrop();
  });

  // ? buttons: the note floats beside the panel; click again, Esc or a click elsewhere hides it
  for (const btn of document.querySelectorAll('.look-only .info-btn')) {
    const pop = document.getElementById(btn.getAttribute('aria-controls'));
    const show = (on) => {
      pop.hidden = !on;
      btn.setAttribute('aria-expanded', String(on));
      if (!on) return;
      const side = $('.side').getBoundingClientRect(), b = btn.getBoundingClientRect();
      pop.style.left = `${Math.round(side.right + 8)}px`;
      pop.style.top = `${Math.round(Math.max(8, Math.min(b.top - 10, window.innerHeight - pop.offsetHeight - 8)))}px`;
    };
    btn.addEventListener('click', () => show(pop.hidden));
    btn.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); show(false); } });
    document.addEventListener('click', (e) => {
      if (!pop.hidden && !btn.contains(e.target) && !pop.contains(e.target)) show(false);
    });
    $('.side').addEventListener('scroll', () => show(false));
  }
  // 全部恢复默认 puts everything back at once, so until the next change it offers to take that back
  const resetBtn = $('#btn-look-reset');
  function renderReset() {
    resetBtn.textContent = L.beforeReset ? t('撤销恢复默认') : t('全部恢复默认');
    resetBtn.title = L.beforeReset ? t('回到恢复默认之前的设置') : t('样式、密度、斜度、强度和亮点都回到默认值');
  }
  resetBtn.addEventListener('click', () => {
    if (L.beforeReset) {
      const before = L.beforeReset;
      L.beforeReset = null;
      set(before);
      renderReset();
      flash(t('已回到恢复默认之前的设置'));
      return;
    }
    const before = { ...L.params };
    const layer = !!(L.info && L.info.has_sparkle_layer);       // a painted 亮点 layer is the default when there is one
    set({ style: 'knit', density: 100, tilt: 32,
      strength: L.info ? L.info.strength_suggested : 100, strength_auto: true,
      sparkle_depth: layer ? 0 : 100,
      sparkle_bright: layer ? 0 : 100, sparkle_painted: layer ? 100 : 0, sparkle_even: 0, sparkle_link: true });
    L.beforeReset = before;
    renderReset();
    flash(t('已全部恢复默认；想回去，点“撤销恢复默认”'));
  });
  for (const b of document.querySelectorAll('.seg-btn')) {
    b.addEventListener('click', () => {
      L.zoom = +b.dataset.zoom;
      for (const x of document.querySelectorAll('.seg-btn')) x.setAttribute('aria-checked', String(x === b));
      requestCrop();
    });
  }
  $('#btn-densest').addEventListener('click', () => { L.centre = null; requestCrop(); });

  // hold space: 细节 shows the original, so the texture can be flicked on and off
  // (a control reached with the keyboard keeps Space for itself: it presses the control)
  window.addEventListener('keydown', (e) => {
    if (!L.active || e.code !== 'Space' || e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.target instanceof HTMLInputElement && e.target.type === 'text') return;
    const a = document.activeElement;
    if (a && a !== document.body && a !== cropCv && a.id !== 'stage' && focusByKeyboard()) return;
    if (a && a.closest && a.closest('dialog, .menu')) return;
    e.preventDefault();
    setPeek(true);
  });
  window.addEventListener('keyup', (e) => { if (e.code === 'Space' && L.peek) { e.preventDefault(); setPeek(false); } });
  window.addEventListener('blur', () => setPeek(false));

  fitCv.addEventListener('click', (e) => {
    if (!L.size) return;
    const r = fitCv.getBoundingClientRect();
    const s = L.size.scale / L.size.dpr;
    L.centre = { x: (e.clientX - r.left) / s, y: (e.clientY - r.top) / s };
    requestCrop();
  });
  cmp.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    cmp.setPointerCapture(e.pointerId);
    cmp.focus();
    L.splitDrag = true;
  });
  cmp.addEventListener('pointermove', (e) => {
    if (!L.splitDrag) return;
    const r = fitCv.getBoundingClientRect();
    setSplit((e.clientX - r.left) / r.width);
  });
  const endSplit = () => { L.splitDrag = false; };
  cmp.addEventListener('pointerup', endSplit);
  cmp.addEventListener('pointercancel', endSplit);
  cmp.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 0.1 : 0.02;
    const to = { ArrowLeft: L.split - step, ArrowRight: L.split + step, Home: 0, End: 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    setSplit(to);
  });
  cropCv.addEventListener('pointerdown', (e) => {
    if (!L.cropRect) return;
    cropCv.setPointerCapture(e.pointerId);
    const r = L.cropRect;
    L.drag = { x: e.clientX, y: e.clientY, cx: r.x0 + r.w / 2, cy: r.y0 + r.h / 2 };
    cropCv.classList.add('dragging');
  });
  cropCv.addEventListener('pointermove', (e) => {
    if (!L.drag) return;
    const k = L.size.dpr / L.zoom;
    L.centre = { x: L.drag.cx - (e.clientX - L.drag.x) * k, y: L.drag.cy - (e.clientY - L.drag.y) * k };
    requestCrop();
  });
  cropCv.addEventListener('keydown', (e) => {
    const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!dir || !L.size || !getDoc()) return;
    e.preventDefault();
    const r = L.cropRect || cropRect(), step = (e.shiftKey ? 0.5 : 0.125) * r.w;
    L.centre = { x: r.x0 + r.w / 2 + dir[0] * step, y: r.y0 + r.h / 2 + dir[1] * step };
    requestCrop();
  });
  const endDrag = () => { L.drag = null; cropCv.classList.remove('dragging'); };
  cropCv.addEventListener('pointerup', endDrag);
  cropCv.addEventListener('pointercancel', endDrag);

  new ResizeObserver(() => {
    if (L.active && layout()) { requestCrop(); fitSoon(); }
  }).observe($('#look-stage'));

  return {
    params() { return L.params ? { ...L.params } : null; },
    enter() {
      L.active = true;
      for (const b of document.querySelectorAll('.seg-btn')) b.setAttribute('aria-checked', String(+b.dataset.zoom === L.zoom));
      load().catch((e) => flash(e.message, true));
    },
    leave() { L.active = false; setPeek(false); },
    onArt() { if (L.active) { drawFit(); drawCrop(); } },
    onState(st) {
      if (!st || st.id !== L.docId) {
        L.docId = st ? st.id : null;
        L.coverageV = st ? st.coverage_v : null;
        Object.assign(L, { params: null, info: null, centre: null, fitImg: null, checkImg: null, cropImg: null,
          beforeReset: null,
          cropCheckImg: null,
          cropRect: null });
        if (L.active && st) load().catch((e) => flash(e.message, true));
        return;
      }
      renderExclude();
      if (st.coverage_v !== L.coverageV) {        // 颜色排除 toggled (or undone), a mask changed: new coverage
        L.coverageV = st.coverage_v;
        refreshSoon();
      }
    },
    onEvent(ev) {
      if (!L.active) return;
      if (ev.type === 'solved' || ev.type === 'depth') refreshSoon();
    },
  };
}
