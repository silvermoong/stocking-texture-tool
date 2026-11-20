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
  coil: t('整齐的线圈针织，按画师原图的规律变化：透出肤色的亮处是清楚整齐的线圈，不透肤的暗处渐渐变成粗糙的细颗粒。适合画画时当底纹。线圈小，密度调低一些更清楚。'),
  lines: t('斜着走的细线，加暖色的单像素亮点。'),
  grain: t('细碎颗粒的针织底纹，加白色小亮点。'),
  oily: t('试验：半透明的油亮丝袜，反光按画面里画出的光影找，深色丝袜上反光会延续到整条腿（画里没画或变暗的地方自动补一条淡淡的光线），换一张图可能不稳定。'),
};

// Stage layout. 细节 is a square; one live render fills at most BUDGET image px (measured: ~65 ms for 细线,
// ~120 ms for 加濑风), which at 200% caps its side at 1000 css px on a 100% screen, 667 at 150% scaling.
const BUDGET = 250_000;
const DMIN = 320;               // css px: 细节 never smaller (less on a very small window)
const WHOLE_WEIGHT = 0.6;       // 整体 counts a little more than 细节 when they share the stage
const PAD = 16, GAP = 18, MIN_PICTURE = 48;

// Where 整体 and the square 细节 go: side by side, or 细节 below. Try for the largest pictures together, but
// leave room for the controls even when a portrait or a small square does not fill the width of its pane.
export function arrange(W, H, iw, ih, dpr, { head, foot, minWhole, minDetail }) {
  const a = iw / ih;
  const dmax = (Math.sqrt(BUDGET) * 2) / dpr;
  const dmin = Math.min(DMIN, 0.3 * Math.min(W, H));
  let best = null;
  for (const mode of ['side', 'stack']) {
    const body = mode === 'side' ? H - head - foot : H - 2 * head - foot - GAP;
    const lim = Math.min(dmax, mode === 'side' ? body : W);
    for (let d = Math.floor(dmin); d <= lim; d += 2) {
      const room = mode === 'side' ? W - GAP - Math.max(d, minDetail) : W;
      if (mode === 'side' && room < minWhole) continue;
      const ww = Math.min(room, (mode === 'side' ? body : body - d) * a);
      const wh = ww / a;
      if (ww < 40 || wh < 40) continue;
      const score = WHOLE_WEIGHT * Math.log(ww * wh) + (1 - WHOLE_WEIGHT) * Math.log(d * d);
      if (!best || score > best.score) best = { score, mode, ww: Math.floor(ww), wh: Math.floor(wh), d };
    }
  }
  if (!best) {                  // very little room: stack, giving the controls the full width
    const ww = Math.max(1, Math.floor(Math.min(W, 40, a * H / 3)));
    best = { mode: 'stack', ww, wh: Math.max(1, Math.floor(ww / a)), d: Math.min(W, 60) };
  }
  return best;
}

// A range input lit up to its thumb.
export function fillRange(el) {
  const lo = +el.min || 0, hi = +el.max || 100;
  el.style.setProperty('--p', `${(100 * (+el.value - lo)) / (hi - lo)}%`);
}
document.addEventListener('input', (e) => { if (e.target.type === 'range') fillRange(e.target); }, true);

function latest(fn) {
  let running = false, again = false, rev = 0, timer;
  const go = async () => {
    if (running) { again = true; return; }
    running = true;
    again = false;
    const sent = rev;
    try { await fn(() => sent === rev); } catch (e) { console.warn(e); } finally {
      running = false;
      if (again) go();
    }
  };
  // Scheduling a newer preview supersedes the last one immediately, even while the new one is debounced.
  return (delay = 0) => {
    rev++;
    again = false;
    clearTimeout(timer);
    if (delay) timer = setTimeout(go, delay); else go();
  };
}

function debounce(fn, ms) {
  let t = 0;
  return () => { clearTimeout(t); t = setTimeout(fn, ms); };
}

// "100" with a smaller "%" after it
export function setVal(el, n, unit) {
  const u = document.createElement('span');
  u.className = 'unit';
  u.textContent = unit;
  el.replaceChildren(String(Math.round(n)), u);
}

async function fetchRender(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res;
}

async function renderBitmap(url) {
  return createImageBitmap(await (await fetchRender(url)).blob());
}

const PCT = [0, 1].map((d) => new Intl.NumberFormat('zh-CN', { style: 'percent', minimumFractionDigits: d, maximumFractionDigits: d }));

function pct(x) {
  if (x <= 0) return t('没有');
  return x < 0.001 ? t('不到 {p}', { p: PCT[1].format(0.001) }) : PCT[x < 0.1 ? 1 : 0].format(x);
}

const MAX_LAYERS = 4;                                                  // as look.MAX_LAYERS
const GESTURE_MS = 700;                                                // a slider at rest this long: the next move is a new step
const DEFAULT_AMOUNT = 50;                                             // as look.DEFAULT_AMOUNT
const LAYER_KEYS = ['style', 'density', 'tilt', 'strength', 'strength_auto', 'weight', 'amount'];     // as look.LAYER_KEYS
// the style a new layer starts with: the first of these that no layer has yet
const NEW_LAYER_STYLES = ['grain', 'lines', 'loops', 'coil', 'knit', 'oily'];

// What the first layer holds, out of the look's own settings (the others are L.params.layers).
function layerOf(params) {
  return Object.fromEntries(LAYER_KEYS.map((k) => [k, params[k]]));
}

// Whether two looks hold the same settings. An automatic strength is worked out per image: its number does not count,
// and an amount nobody set is the weight.
function sameLook(a, b) {
  const same = (x, y) => Object.keys(x).every((k) => k === 'layers'
    || (k === 'strength' && x.strength_auto && y.strength_auto)
    || (k === 'amount' ? (x.amount ?? DEFAULT_AMOUNT) === (y.amount ?? DEFAULT_AMOUNT) : x[k] === y[k]));
  const la = a.layers || [], lb = b.layers || [];
  return same(a, b) && la.length === lb.length && la.every((x, i) => same(x, lb[i]));
}

export function createLook({ getDoc, getArt, request, edit, flash, setTip, focusByKeyboard = () => false,
  canLook = () => true, onHistory = () => {} }) {
  const L = {
    active: false,
    docId: null,
    params: null,
    layer: 0,              // the 纹理层 the panel shows (0 = the first, whose settings are the look's own)
    info: null,
    lookRev: 0,            // the server's count of undos and redos of the look: it moved, so the settings changed under us
    gesture: null,         // what the last change was (a slider being dragged), when
    gestureAt: 0,
    newStep: true,         // the changes not saved yet begin a step of the 纹理 history (else they go on the last one)
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
    previewSession: 0,
    previewFailed: { fit: false, crop: false },
    drag: null,
    presets: [],           // the saved presets, as the server lists them: [{ name, params }], params null if unreadable
    presetsLoaded: false,  // the list has come from the server: only then is a name it lacks a preset that is gone
    presetName: null,      // the preset these settings were loaded from or saved as; null for none
    presetFileBusy: false, // a preset file's dialog is open (导出 / 导入)
  };
  const fitCv = $('#fit');
  const cropCv = $('#crop');
  const stageColour = getComputedStyle(document.documentElement).getPropertyValue('--stage').trim();

  // ---------------------------------------------------------------- settings

  function query(extra) {
    const p = L.params;
    const q = new URLSearchParams({ style: p.style, density: p.density, tilt: p.tilt,
      strength: p.strength, strength_auto: p.strength_auto, weight: p.weight, amount: p.amount ?? '',
      layers: JSON.stringify(p.layers || []), lock_total: p.lock_total,
      sparkle_on: p.sparkle_on, sparkle_depth: p.sparkle_depth, sparkle_bright: p.sparkle_bright,
      sparkle_painted: p.sparkle_painted, sparkle_even: p.sparkle_even,
      sparkle_link: p.sparkle_link, particle_on: p.particle_on, particle: p.particle,
      moire_on: p.moire_on, moire: p.moire, moire_area: p.moire_area, fade: p.fade !== false });
    for (const [k, v] of Object.entries(extra || {})) q.set(k, v);
    return q.toString();
  }

  // ---------------------------------------------------------------- 纹理层

  // Style, density, tilt and strength belong to a layer; sparkles and the moiré effect to the whole look. Every layer
  // has two numbers for how much of it is laid on, and 融合 shows the one that goes with the switch 自动 100%:
  //  - on (lock_total, the default): its weight, mixed in the ratio of the weights; the panel shows each layer's share
  //    of the whole, and the weights are kept adding up to 100, so a weight is its share. A new layer takes an equal
  //    share;
  //  - off: its amount (0..100%), whatever the others have. An amount nobody set (null) is 50%, whatever the weight
  //    is, so the layers look the same however they came about.
  // Both are kept while the other is in use: the switch goes back and forth without losing either.
  const layerCount = () => 1 + ((L.params && L.params.layers) || []).length;
  const layerAt = (i) => (i === 0 ? L.params : L.params.layers[i - 1]);
  const allLayers = () => [layerOf(L.params), ...L.params.layers];
  const layerName = (i) => t('纹理 {n}', { n: i + 1 });
  const amountOf = (l) => l.amount ?? DEFAULT_AMOUNT;

  // Each layer's share as a whole percentage; they add up to 100 (the biggest remainders take the odd points).
  function shareList() {
    const ws = allLayers().map((l) => l.weight);
    const total = ws.reduce((a, b) => a + b, 0);
    const raw = ws.map((w, i) => (total > 0 ? (100 * w) / total : 100 * +(i === 0)));
    const out = raw.map(Math.floor);
    const byRemainder = raw.map((_, i) => i).sort((i, j) => raw[j] - out[j] - (raw[i] - out[i]));
    const odd = 100 - out.reduce((a, b) => a + b, 0);
    for (let k = 0; k < odd; k++) out[byRemainder[k]] += 1;
    return out;
  }

  // What 融合 shows for each layer, whole percentages: its share (switch on) or its own amount (off).
  const levelList = () => (L.params.lock_total ? shareList() : allLayers().map((l) => Math.round(amountOf(l))));

  // The layers put back as a look.
  function asLook(layers) {
    const [first, ...rest] = layers;
    return { ...first, layers: rest };
  }

  // The same with the weights rescaled to add up to 100.
  function withLayers(layers) {
    const total = layers.reduce((a, l) => a + l.weight, 0);
    const ws = layers.map((l) => (total > 0 ? (100 * l.weight) / total : 100 / layers.length)).map((w) => Math.round(w * 10) / 10);
    return asLook(layers.map((l, i) => ({ ...l, weight: ws[i] })));
  }

  // A change to layer i.
  function setLayerAt(i, changes, opts) {
    if (i === 0) { set(changes, opts); return; }
    set({ layers: L.params.layers.map((l, j) => (j === i - 1 ? { ...l, ...changes } : l)) }, opts);
  }

  // A change to the layer shown.
  const setLayer = (changes, opts) => setLayerAt(L.layer, changes, opts);

  // Layer i's slider in 融合. Switch on: moving one share moves the others in proportion, so the shares keep adding up
  // to 100. Off: it is this layer's own amount and nothing else moves.
  function setLevel(i, value) {
    const v = Math.min(100, Math.max(0, value));
    const gesture = `blend:${i}`;
    if (!L.params.lock_total) { setLayerAt(i, { amount: v }, { gesture }); return; }
    const layers = allLayers();
    const total = layers.reduce((a, l) => a + l.weight, 0);
    const rest = total - layers[i].weight;
    set(withLayers(layers.map((l, j) => ({
      ...l, weight: j === i ? v : rest > 0 ? (l.weight * (100 - v)) / rest : (100 - v) / (layers.length - 1),
    }))), { gesture });
  }

  // A new layer starts with the defaults, in a style no layer has, and takes an equal share of the weights (the others
  // give way evenly); its amount is not set, so 50% like every layer's.
  function addLayer() {
    if (!L.params) return;
    const n = layerCount() + 1;
    if (n > MAX_LAYERS) return;
    const layers = allLayers();
    const have = new Set(layers.map((l) => l.style));
    const total = layers.reduce((a, l) => a + l.weight, 0);
    const kept = layers.map((l) => ({
      ...l, weight: total > 0 ? (l.weight * (100 - 100 / n)) / total : (100 - 100 / n) / (n - 1),
    }));
    kept.push({ style: NEW_LAYER_STYLES.find((s) => !have.has(s)) || 'grain', density: 100, tilt: 32,
      strength: L.info ? L.info.strength_suggested : 100, strength_auto: true, weight: 100 / n, amount: null });
    L.layer = n - 1;
    set(withLayers(kept));
  }

  // Deletes layer i (the one shown by default); the layer shown stays the same one, or the next takes the place of
  // the one deleted. The others give back its weight in proportion and keep their amounts. A lone layer is the whole
  // look: 100, and no amount.
  function deleteLayer(i = L.layer) {
    if (layerCount() < 2 || i >= layerCount()) return;
    const left = allLayers().filter((_, j) => j !== i);
    if (left.length === 1) left[0] = { ...left[0], amount: null };
    if (i < L.layer) L.layer -= 1;
    L.layer = Math.min(L.layer, left.length - 1);
    set(withLayers(left));
    flash(t('已删除“{name}”，Ctrl+Z 可以撤销', { name: layerName(i) }));
  }

  function selectLayer(i) {
    L.layer = L.params && i < layerCount() ? i : 0;
    if (L.params) renderControls();
  }

  // The 纹理层 are managed in the panel, in one place: + adds one, and with more than one there is a row for each
  // (below). The bar's tabs are the two pages and nothing else.
  //
  // + with a lone layer sits beside the 样式 title, its name written out, and costs the panel no height; with more
  // it is the + of the 纹理层 title, over the rows. It is one button, moved (renderLayers), so it keeps the focus.
  const addBtn = $('#layer-add');

  // why + cannot add a layer now ('' while there is nothing to add to: nothing to say), or null when it can
  function addBlocked() {
    if (!L.params || !canLook()) return '';
    return layerCount() >= MAX_LAYERS ? t('最多 {n} 层纹理', { n: MAX_LAYERS }) : null;
  }

  function renderAdd() {
    const why = addBlocked();
    addBtn.setAttribute('aria-disabled', String(why !== null));
    setTip(addBtn, why || t('添加一层纹理，和现有的纹理层按比例融合，最多 {n} 层', { n: MAX_LAYERS }));
  }

  addBtn.addEventListener('click', () => {
    const why = addBlocked();
    if (why === null) addLayer(); else if (why) flash(why);
  });

  // 融合: a row for each layer: its name (a button that shows the layer in the card below; Delete on it deletes the
  // layer), its slider, and × (built when the number of layers changes, so a slider being dragged is never
  // replaced); 自动 100% under the rows is the switch.
  const blendRows = $('#blend-rows');
  const blendAuto = $('#blend-auto');

  // × or Delete on a row: the layer goes (renderLayers keeps the focus with the layers: the row it was on is gone).
  function removeLayer(i) {
    if (!L.params || layerCount() < 2) return;
    deleteLayer(i);
  }

  function renderBlend() {
    const lock = !!L.params.lock_total, levels = levelList();
    if (blendRows.childElementCount !== levels.length) {
      blendRows.replaceChildren(...levels.map((_, i) => {
        const row = document.createElement('li');
        row.className = 'blend-row';
        row.dataset.layer = String(i);
        const name = document.createElement('button');
        name.className = 'blend-name';
        name.type = 'button';
        name.setAttribute('aria-keyshortcuts', 'Delete');
        name.addEventListener('click', () => selectLayer(i));
        name.addEventListener('keydown', (e) => {
          if (e.key === 'Delete') { e.preventDefault(); removeLayer(i); }
        });
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '0';
        slider.max = '100';
        slider.step = '1';
        slider.addEventListener('input', () => setLevel(i, +slider.value));
        const val = document.createElement('span');
        val.className = 'val num';
        const x = document.createElement('button');
        x.className = 'layer-x';
        x.type = 'button';
        x.textContent = '×';
        x.addEventListener('click', () => removeLayer(i));
        row.append(name, slider, val, x);
        return row;
      }));
    }
    levels.forEach((level, i) => {
      const row = blendRows.children[i];
      const [name, slider, val, x] = row.children;
      const called = { name: layerName(i) };
      row.classList.toggle('on', i === L.layer);
      name.textContent = layerName(i);
      name.setAttribute('aria-current', String(i === L.layer));
      setTip(name, t('调“{name}”的样式、密度、斜度和强度', called));
      slider.setAttribute('aria-label', t('“{name}”的融合比例', called));
      slider.value = level;
      setVal(val, level, '%');
      const remove = t('删除“{name}”', called);
      x.setAttribute('aria-label', remove);
      setTip(x, remove);
    });
    blendAuto.setAttribute('aria-pressed', String(lock));
    const total = $('#blend-total');
    total.hidden = lock;
    total.textContent = t('合计 {n}%', { n: levels.reduce((a, b) => a + b, 0) });
  }

  // One layer or several: what of the 纹理层 section shows, where + sits, and whose settings the card says it holds.
  // With no settings (another image was opened and its own are on their way) it is as with one layer: nothing of
  // the last image's layers stays to be seen or pressed.
  //
  // The rows are made anew when their number changes (a layer deleted or added, 撤销, 重做, a preset) and are gone
  // with one layer left: a focus that was on a row goes to the name of the layer now shown, or to + when there are
  // no rows, so the keyboard is never left on nothing.
  function renderLayers() {
    const many = !!L.params && layerCount() > 1;
    const focus = document.activeElement;
    const held = !!focus && blendRows.contains(focus);
    $('#layers-section').classList.toggle('single', !many);
    for (const id of ['#layers-head', '#blend-foot', '#layer-card-title-row', '#global-note']) $(id).hidden = !many;
    blendRows.hidden = !many;
    const host = many ? $('#layers-head') : $('#layer-card-head');
    if (addBtn.parentElement !== host) {
      const focused = document.activeElement === addBtn;
      host.append(addBtn);
      if (focused) addBtn.focus();
    }
    renderAdd();
    $('#layer-card-title').textContent = t('正在调：{name}', { name: layerName(L.layer) });
    if (many) renderBlend();
    else {
      if (blendRows.childElementCount) blendRows.replaceChildren();
      $('#blend-info').hidden = true;                    // its ? went with the title
      $('#layers-head .info-btn').setAttribute('aria-expanded', 'false');
    }
    if (held && !blendRows.contains(document.activeElement)) {
      const row = many ? blendRows.children[L.layer] : null;
      (row ? row.children[0] : addBtn).focus();
    }
  }

  // The user's last choice for the switch is kept (per user, the server's settings): a look not saved yet starts from it.
  blendAuto.addEventListener('click', () => {
    if (!L.params) return;
    const on = !L.params.lock_total;
    set({ lock_total: on });
    if (L.info) L.info.blend_auto = on;
    request('PUT', '/api/look/blend-auto', { on }).catch((e) => flash(e.message, true));
  });

  // With 关联 on, depth and brightness always hold the same amount: moving either moves both to that value.
  function setAmount(key, value) {
    set(L.params.sparkle_link ? { sparkle_depth: value, sparkle_bright: value } : { [key]: value }, { gesture: key });
  }

  // Turning 关联 on makes the two equal, taking the depth amount.
  function toggleLink() {
    const on = !L.params.sparkle_link;
    set(on ? { sparkle_link: true, sparkle_bright: L.params.sparkle_depth } : { sparkle_link: false },
      { immediate: on });
  }

  function localPeriod(doc, density) {
    const scaled = 4.6 * Math.sqrt(doc.width * doc.height / REF_AREA);
    const raw = scaled / (density / 100);
    return { period: Math.max(raw, 3.2), clamped: raw < 3.2, maxDensity: 100 * scaled / 3.2 };
  }

  function set(changes, { immediate = true, gesture = null } = {}) {
    // A step of the 纹理 history: a click is one; so is a drag of a slider (its `gesture`), till it rests a moment.
    const now = performance.now();
    if (!gesture || gesture !== L.gesture || now - L.gestureAt > GESTURE_MS) L.newStep = true;
    L.gesture = gesture;
    L.gestureAt = now;
    Object.assign(L.params, changes);
    if (L.layer >= layerCount()) L.layer = layerCount() - 1;                                  // a layer is gone
    renderControls();
    if (immediate) requestCrop();
    saveSoon();
    fitSoon();
  }

  // While strength is automatic the server picks it from the stockings' lightness; show what it picked (for every
  // layer that has an automatic strength: they all take the same one).
  function adoptInfo(info) {
    const moved = !L.centre && L.info && String(L.info.densest) !== String(info.densest);
    L.info = info;
    const p = L.params, auto = info.strength_suggested;
    if (p && ((p.strength_auto && p.strength !== auto) || p.layers.some((l) => l.strength_auto && l.strength !== auto))) {
      if (p.strength_auto) p.strength = auto;
      p.layers = p.layers.map((l) => (l.strength_auto ? { ...l, strength: auto } : l));
      renderControls();
    }
    renderInfo();
    history();
    if (moved) requestCrop();          // the crop follows the densest courses, and they moved (a region re-solved)
  }

  // Saves go out one after another, in order. flush() sends what is waiting now (an undo has to come after it) and
  // resolves when every save is done; it rejects if this save failed, which is then shown and kept to send again.
  // Each save names the preset the settings go with ('' for none): the server keeps it with the step, so that 撤销
  // and 重做 bring it back with the settings.
  let saving = Promise.resolve();
  let unsaved = false;
  let saveTimer = 0;
  let edits = 0;              // local changes so far: a load() answer asked for before the latest one is stale
  function flush() {
    clearTimeout(saveTimer);
    const run = saving.then(async () => {
      const doc = getDoc();
      if (!unsaved || !doc || !L.params) return;
      unsaved = false;
      const merge = !L.newStep;
      L.newStep = false;
      try {
        const preset = encodeURIComponent(L.presetName || '');
        const info = await request('PUT', `/api/doc/${doc.id}/look?merge=${+merge}&preset=${preset}`, L.params);
        if (getDoc() && getDoc().id === doc.id) adoptInfo(info);
      } catch (e) {
        if (getDoc() && getDoc().id === doc.id && L.params) {
          unsaved = true;                       // the next save sends it again, as the step it was meant to be
          if (!merge) L.newStep = true;
        }
        flash(t('纹理设置没有保存：{error}', { error: e.message }), true);
        throw e;
      }
    });
    saving = run.catch(() => {});
    return run;
  }
  function saveSoon() {
    unsaved = true;
    edits++;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => flush().catch(() => {}), 150);
  }

  // ---------------------------------------------------------------- layout

  function layout() {
    const doc = getDoc();
    if (!doc) return false;
    const k = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--k')) || 1;
    // The 272px sidebar also grows with 界面大小. Put it below before it takes half of the width.
    document.body.classList.toggle('stack-texture-settings', window.innerWidth <= Math.max(700, 2 * 272 * k));
    const box = $('#look-stage').getBoundingClientRect();
    if (box.width < 50 || box.height < 50) return false;
    const dpr = window.devicePixelRatio || 1;
    const W = Math.floor(box.width - 2 * PAD), H = box.height - 2 * PAD;
    const minWhole = Math.ceil(84 * k), minDetail = Math.ceil(156 * k);
    const head = 34 * k, foot = 30 * k;
    const A = arrange(W, H, doc.width, doc.height, dpr, { head, foot, minWhole, minDetail });
    const whole = $('.whole-pane'), detail = $('.detail-pane'), side = A.mode === 'side';
    const stackedWidth = Math.min(W, Math.max(A.ww, A.d, Math.ceil(320 * k)));
    const ww = side ? Math.max(A.ww, minWhole) : stackedWidth;
    const dw = side ? Math.max(A.d, minDetail) : stackedWidth;
    const span = side ? ww + GAP + dw : stackedWidth;
    const x = PAD + Math.floor((W - span) / 2);
    Object.assign(whole.style, { left: `${x}px`, top: `${PAD}px`, width: `${ww}px` });
    Object.assign(detail.style, { left: `${side ? x + ww + GAP : x}px`, width: `${dw}px` });

    // At these widths labels may wrap. Keep the chosen slots and fit the images in the actual space left by the rows.
    const wholeHead = $('.whole-pane .pane-head').getBoundingClientRect().height;
    const detailChrome = $('.detail-pane .pane-head').getBoundingClientRect().height + $('.detail-pane .pane-foot').getBoundingClientRect().height;
    // Once the chrome leaves too little room for a useful thumbnail, let the stage scroll the last rows into view.
    const scaleToFit = (room, size) => Math.min(1, Math.max(MIN_PICTURE, room) / size);
    const stackRoom = H - wholeHead - detailChrome - GAP;
    const stackScale = Math.min(1, Math.max(stackRoom / (A.wh + A.d), MIN_PICTURE / Math.min(A.wh, A.d)));
    const fitScale = side ? scaleToFit(H - wholeHead, A.wh) : stackScale;
    const cropScale = side ? scaleToFit(H - detailChrome, A.d) : stackScale;
    A.ww = Math.max(1, Math.floor(A.ww * fitScale));
    A.wh = Math.max(1, Math.floor(A.wh * fitScale));
    A.d = Math.max(1, Math.floor(A.d * cropScale));
    detail.style.top = `${side ? PAD : PAD + wholeHead + A.wh + GAP}px`;
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
    // A small 整体 (a narrow window at a large 界面大小) cannot hold both labels: leave them out rather than let
    // them hang off the picture. The slider's own tip still says which side is which.
    L.tagsFit = !($('#compare-before').offsetWidth + $('#compare-after').offsetWidth + 24 * k > A.ww);
    placeCompare();
    drawFit();
    drawCrop();
    return changed;
  }

  // ---------------------------------------------------------------- previews

  // Keep the last good preview while retrying. Only the newest request of this pane may change its error notice,
  // and only while the coverage it was asked for still holds: after 颜色排除 or a mask changed, its picture is of
  // the coverage before (it neither draws nor reports), and the one now due is asked for once the settings are read.
  async function updatePreview(pane, doc, isLatest, run) {
    const session = L.previewSession, coverage = L.coverageV;
    const current = () => L.active && session === L.previewSession && getDoc()?.id === doc.id
      && coverage === L.coverageV;
    try {
      await run(current);
    } catch (e) {
      if (current() && isLatest() && e?.name !== 'AbortError') {
        console.warn(e);
        L.previewFailed[pane] = true;
        renderPreviewErrors();
      }
      return;
    }
    if (current() && isLatest()) {
      L.previewFailed[pane] = false;
      renderPreviewErrors();
    }
  }

  function renderPreviewErrors() {
    const { fit, crop } = L.previewFailed;
    const message = fit && crop ? t('整体和细节预览失败') : fit ? t('整体预览失败') : crop ? t('细节预览失败') : '';
    const error = $('#preview-error');
    if (error.textContent !== message) error.textContent = message;
  }

  // The page is left: the previews still on their way are not the next visit's (they neither draw nor report), and
  // nothing is updating. A preview that failed stays failed, as its picture stays the old one, until it succeeds;
  // the notice is out of sight with the page.
  function endPreviews() {
    L.previewSession++;
    L.fitBusy = false;
    renderFitStatus();
  }

  // Another image: its previews have not failed.
  function resetPreviewStatus() {
    endPreviews();
    L.previewFailed.fit = L.previewFailed.crop = false;
    renderPreviewErrors();
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

  const requestCrop = latest(async (isLatest) => {
    const doc = getDoc();
    if (!L.active || !doc || !L.size || !L.params || !L.info) return;
    await updatePreview('crop', doc, isLatest, async (current) => {
      const r = cropRect();
      const q = query({ x0: r.x0, y0: r.y0, w: r.w, h: r.h });
      const [res, check] = await Promise.all([
        fetchRender(`/api/doc/${doc.id}/render/crop?${q}`),
        L.showCheck ? renderBitmap(`/api/doc/${doc.id}/render/check?${q}`) : null,
      ]);
      const meta = JSON.parse(res.headers.get('X-Look') || '{}');
      const img = await createImageBitmap(await res.blob());
      if (!current()) return;
      L.cropImg = img;
      L.cropCheckImg = check;
      L.cropRect = { x0: meta.x0, y0: meta.y0, w: meta.w, h: meta.h };
      L.cropMs = meta.ms;
      drawCrop();
      drawFit();
    });
  });

  function drawCrop() {
    const c = cropCv.getContext('2d');
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.fillStyle = stageColour;
    c.fillRect(0, 0, cropCv.width, cropCv.height);
    $('#btn-densest').disabled = !L.centre;
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

  const requestFit = latest(async (isLatest) => {
    const doc = getDoc();
    if (!L.active || !doc || !L.size || !L.params || !L.info || !L.info.textured) return;
    L.fitBusy = true;
    renderFitStatus();
    try {
      await updatePreview('fit', doc, isLatest, async (current) => {
        const q = query({ w: L.size.fitW, h: L.size.fitH });
        const [fit, check] = await Promise.all([
          renderBitmap(`/api/doc/${doc.id}/render/fit?${q}`),
          L.showCheck ? renderBitmap(`/api/doc/${doc.id}/render/check?${q}`) : null,
        ]);
        if (!current()) return;
        L.fitImg = fit;
        L.checkImg = check;
        drawFit();
      });
    } finally {
      L.fitBusy = false;
      renderFitStatus();
    }
  });
  const fitSoon = () => requestFit(200);

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
    const room = L.tagsFit !== false;
    $('#compare-before').style.visibility = room && L.split > 0.12 ? 'visible' : 'hidden';
    $('#compare-after').style.visibility = room && L.split < 0.88 ? 'visible' : 'hidden';
  }

  function setSplit(x) {
    L.split = Math.min(1, Math.max(0, x));
    placeCompare();
    drawFit();
  }

  // ---------------------------------------------------------------- panel

  function renderControls() {
    const all = L.params;                // sparkles and the moiré effect: one setting for the whole look
    const doc = getDoc();
    if (!all || !doc) return;
    renderLayers();
    const p = layerAt(L.layer);          // style, density, tilt and strength: the layer shown, in the card
    for (const b of document.querySelectorAll('.styles .opt')) b.setAttribute('aria-checked', String(b.dataset.style === p.style));
    $('#style-note').textContent = STYLE_NOTES[p.style];
    const density = $('#density'), densityVal = $('#density-val');
    density.value = p.density;
    setVal(densityVal, p.density, '%');
    const g = localPeriod(doc, p.density);
    const note = $('#density-note');
    if (g.clamped) {
      const max = Math.floor(g.maxDensity);
      const effective = document.createElement('span');
      effective.className = 'density-effective';
      effective.textContent = t('（实际 {max}%）', { max });
      densityVal.append(effective);
      note.textContent = t('横纹间距已到 3.2\u00a0px 下限，再密就会出摩尔纹，这张图最多 {max}%。想更密，先把图放大（比如 1.5 倍）再来。', { max });
      note.className = 'note warn';
    } else {
      note.textContent = t('横纹间距 {p}\u00a0px', { p: g.period.toFixed(2) });
      note.className = 'note';
    }
    density.setAttribute('aria-valuetext', densityVal.textContent);
    $('#tilt-section').hidden = p.style !== 'lines';
    $('#tilt').value = p.tilt;
    setVal($('#tilt-val'), p.tilt, '°');
    $('#strength').value = p.strength;
    setVal($('#strength-val'), p.strength, '%');
    $('#strength-auto').setAttribute('aria-pressed', String(!!p.strength_auto));
    $('#sparkle-on').checked = !!all.sparkle_on;
    $('#sparkle-fields').hidden = !all.sparkle_on;
    for (const k of ['depth', 'bright', 'painted', 'even']) {
      $(`#sparkle-${k}`).value = all[`sparkle_${k}`];
      setVal($(`#sparkle-${k}-val`), all[`sparkle_${k}`], '%');
    }
    $('#btn-sparkle-link').setAttribute('aria-pressed', String(!!all.sparkle_link));
    $('#particle-on').checked = !!all.particle_on;
    $('#particle-fields').hidden = !all.particle_on;
    $('#particle').value = all.particle;
    setVal($('#particle-val'), all.particle, '%');
    $('#moire-on').checked = !!all.moire_on;
    $('#moire-fields').hidden = !all.moire_on;
    $('#moire').value = all.moire;
    setVal($('#moire-val'), all.moire, '%');
    $('#moire-area').value = all.moire_area;
    setVal($('#moire-area-val'), all.moire_area, '%');
    $('#btn-check').setAttribute('aria-pressed', String(L.showCheck));
    $('#check-legend').hidden = !L.showCheck;
    $('#peek-hint').hidden = L.showCheck;
    for (const el of document.querySelectorAll('.look-only input[type="range"]')) fillRange(el);
    renderFade();
    renderExclude();
    renderPresetState();
  }

  function renderFade() {
    const p = L.params;
    if (!p) return;
    const on = p.fade !== false;
    $('#fade').checked = on;
    const i = L.info;
    $('#fade-note').textContent = !on ? t('已关闭：横纹密集处也不减弱纹理。')
      : !i ? '' : i.solving.length ? t('正在更新…')
        : i.check.faded > 0 ? t('现在减弱了纹理的 {p}。', { p: pct(i.check.faded) }) : t('这张图没有被减弱的地方。');
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

  // Use the longest localized reading, including the optional solving suffix, to size each legend value.
  for (const id of ['#check-faded', '#check-excluded', '#check-nostroke']) {
    $(id).parentElement.dataset.measure = pct(0.0005) + (id === '#check-nostroke' ? t('（求解中…）') : '');
  }

  function renderInfo() {
    const i = L.info;
    if (!i) return;
    $('#check-faded').textContent = pct(i.check.faded);
    $('#check-excluded').textContent = pct(i.check.excluded);
    renderFade();
    renderExclude();
    const ns = $('#check-nostroke');
    ns.textContent = (i.untextured.length ? pct(i.check.nostroke) : t('没有')) + (i.solving.length ? t('（求解中…）') : '');
    const tip = t('部位已经涂好，但还没画走向线，所以不生成纹理。')
      + (i.untextured.length ? t('没有走向线的部位：{names}。', { names: i.untextured.join(t('、')) }) : '')
      + (i.solving.length ? t('{names}正在求解，求解完再看。', { names: i.solving.join(t('、')) }) : '');
    setTip(ns.parentElement.parentElement, tip);
    $('#sparkle-painted-field').hidden = !i.has_sparkle_layer;
    const sn = $('#sparkle-note');
    sn.className = 'note';
    const usesDepth = !!L.params.sparkle_on && L.params.sparkle_depth > 0;
    if (usesDepth && i.depth !== 'ready' && i.depth !== 'error') sn.textContent = t('正在估算深度（第一次要几秒）…');
    else if (usesDepth && i.depth === 'error') {
      sn.textContent = t('深度模型不可用：{error}。按深度的亮点先不显示，按画面亮部的照常。', { error: i.depth_error || t('未知错误') });
      sn.className = 'note warn';
    } else sn.textContent = '';
    // 摩尔纹效果 needs the depth model too: it draws nothing until the model has run
    const mn = $('#moire-note');
    const moireOn = !!L.params.moire_on && L.params.moire > 0;
    mn.className = 'note';
    if (moireOn && i.depth !== 'ready' && i.depth !== 'error') mn.textContent = t('正在估算深度（第一次要几秒）…');
    else if (moireOn && i.depth === 'error') {
      mn.textContent = t('深度模型不可用：{error}。摩尔纹效果先不显示。', { error: i.depth_error || t('未知错误') });
      mn.className = 'note warn';
    } else mn.textContent = '';
  }

  // ---------------------------------------------------------------- presets

  // Saved settings, per user (the server keeps them with the other settings), picked from the list above 样式.
  // L.presetName is the preset the settings were loaded from or saved as: 保存 updates it, 删除 deletes it, and tweaks
  // are marked 已改动 against it. It goes with the image; 全部恢复默认 keeps it. The list's last entry, 保存为新预设…,
  // asks for a name; with no preset selected 保存 does the same.
  // The server keeps the name with the look and with each step of the 纹理 history, so 撤销 and 重做 (the only way
  // to take back a load or 全部恢复默认) bring it back with the settings: load() reads it, every save sends it.
  const presetSel = $('#preset-select');
  const presetSave = $('#btn-preset-save');
  const presetDlg = $('#preset-dialog');
  const presetNameInput = $('#preset-name');
  const presetDlgNote = $('#preset-dialog-note');

  function presetOf(name) { return name ? L.presets.find((p) => p.name === name) : undefined; }

  // Whether the settings differ from the preset (see sameLook).
  function presetModified(p) {
    if (!p || !p.params || !L.params) return false;
    return !sameLook(p.params, L.params);
  }

  function renderPresetList() {
    const none = document.createElement('option');
    none.value = '';
    none.hidden = true;
    none.textContent = L.presets.length ? t('选一个预设') : t('还没有预设');
    const asNew = document.createElement('option');
    asNew.textContent = t('保存为新预设…');
    asNew.dataset.new = '1';
    presetSel.replaceChildren(none, ...L.presets.map((p) => {
      const o = document.createElement('option');
      o.value = p.name;
      o.textContent = p.params ? p.name : t('{name}（读不了）', { name: p.name });
      o.translate = false;
      return o;
    }), ...(L.presets.length ? [document.createElement('hr')] : []), asNew);
    renderPresetState();
  }

  function renderPresetState() {
    if (!presetSel.options.length) { renderPresetList(); return; }
    const p = presetOf(L.presetName);
    if (!p && L.presetsLoaded) L.presetName = null;         // none, or deleted since
    presetSel.value = p ? p.name : '';
    presetSel.disabled = !L.params;
    const modified = presetModified(p);
    // an unreadable preset can be written over, which mends it
    const unchanged = !!L.params && !!p?.params && !modified;
    presetSave.textContent = p ? t('保存') : t('保存…');          // with none selected it asks for a name
    presetSave.disabled = !L.params;
    presetSave.setAttribute('aria-disabled', String(unchanged));
    setTip(presetSave, !L.params ? null : unchanged ? t('当前设置与所选预设一致，改动后再保存')
      : p ? t('用现在的设置更新“{name}”', { name: p.name }) : t('把现在的设置存成新预设'));
    $('#btn-preset-delete').disabled = !p;
    $('#btn-preset-export').disabled = !p || !p.params || L.presetFileBusy;       // an unreadable preset cannot be handed on
    $('#btn-preset-import').disabled = L.presetFileBusy;
    const notes = [];
    if (p && !p.params) notes.push(t('这个预设读不了（可能是新版本存的），可以删掉它。'));
    else if (modified) notes.push(t('已改动（和“{name}”不同）。', { name: p.name }));
    if (p && p.params && p.params.sparkle_on && p.params.sparkle_painted > 0 && L.info && !L.info.has_sparkle_layer) {
      notes.push(t('这张图没有“亮点”层，预设里按“亮点”层放亮点的那一项暂时不起作用。'));
    }
    $('#preset-note').textContent = notes.join(' ');
    const restore = $('#btn-preset-undo');          // 还原: the settings differ from the preset, put the preset's back
    restore.hidden = !modified;
    restore.textContent = t('还原');
  }

  async function loadPresets() {
    L.presets = (await request('GET', '/api/look/presets')).presets;
    L.presetsLoaded = true;
    renderPresetList();
  }

  // The settings as they are go with another preset (saved as a new preset, a preset holding these very settings
  // or one that cannot be read picked). The name goes to the server with a save of the settings as they are, which
  // makes no step of it. A reading of the settings still on its way comes first (撤销 was just pressed): the
  // settings it brings are the ones to send the name with, and it leaves this newer name alone (see read()).
  function namePreset(name) {
    L.presetName = name;
    L.gesture = null;                            // a slider moved after this begins a step of its own
    const doc = getDoc();
    if (!doc || !L.params) return;
    reading.then(() => {
      if (getDoc() && getDoc().id === doc.id && L.params && L.presetName === name) saveSoon();
    });
  }

  // Loading replaces the settings, as one step of the 纹理 history: 撤销 takes it back, the selected preset too.
  // 还原 is the same load, of the preset already selected. A preset holding the very settings there are changes
  // the name alone: nothing to take back, so no undo is promised.
  function applyPreset(name) {
    const p = presetOf(name);
    if (!p || !L.params) return;
    if (!p.params) {
      namePreset(name);
      renderPresetState();
      flash(t('这个预设读不了（可能是新版本存的），可以删掉它。'), true);
      return;
    }
    const next = { ...p.params };
    if (L.info) {                                                                          // worked out for this image
      if (next.strength_auto) next.strength = L.info.strength_suggested;
      next.layers = (next.layers || []).map((l) => (l.strength_auto ? { ...l, strength: L.info.strength_suggested } : l));
    }
    if (sameLook(next, L.params)) {
      namePreset(name);
      renderPresetState();
      flash(t('已载入预设“{name}”', { name }));
      return;
    }
    L.presetName = name;
    set(next);
    flash(t('已载入预设“{name}”，Ctrl+Z 可以撤销', { name }));
  }

  function renderPresetDialog() {
    const name = presetNameInput.value.trim();
    const clash = !!presetOf(name);
    $('#btn-preset-ok').disabled = !name;
    presetDlgNote.className = clash ? 'note dialog-note warn' : 'note dialog-note';
    presetDlgNote.textContent = clash ? t('已有同名预设，保存会覆盖它。') : '';
  }

  function openSavePreset() {
    if (!L.params) return;
    presetNameInput.value = '';
    renderPresetDialog();
    presetDlg.showModal();
    presetNameInput.focus();
  }

  async function putPreset(name) {
    L.presets = (await request('PUT', '/api/look/presets', { name, params: { ...L.params } })).presets;
  }

  async function savePreset() {
    const name = presetNameInput.value.trim();
    const docId = L.docId;
    if (!name || !L.params) return;
    try {
      await putPreset(name);
    } catch (e) {
      presetDlgNote.className = 'note dialog-note error';
      presetDlgNote.textContent = e.message;
      return;
    }
    presetDlg.close();
    if (L.docId === docId) namePreset(name);
    renderPresetList();
    flash(t('已保存预设“{name}”', { name }));
  }

  // 保存 with a preset selected: the settings go into it, no questions (the name is already chosen).
  async function updatePreset() {
    const name = L.presetName;
    if (!presetOf(name) || !L.params) return;
    try {
      await putPreset(name);
    } catch (e) {
      flash(e.message, true);
      return;
    }
    renderPresetList();
    flash(t('已更新预设“{name}”', { name }));
  }

  async function deletePreset() {
    const name = L.presetName;
    if (!presetOf(name)) return;
    const dlg = $('#preset-delete');
    $('#preset-delete-text').textContent = t('预设“{name}”删除后找不回来。', { name });
    dlg.returnValue = '';
    dlg.showModal();
    const choice = await new Promise((resolve) => dlg.addEventListener('close', () => resolve(dlg.returnValue), { once: true }));
    if (choice !== 'delete') return;
    try {
      L.presets = (await request('DELETE', '/api/look/presets', { name })).presets;
    } catch (e) {
      flash(e.message, true);
      return;
    }
    // the settings stay, with no preset selected now: the server has taken the name off this image and the steps of
    // its history itself, so that 撤销 never selects a preset saved under the name later
    if (L.presetName === name) L.presetName = null;
    renderPresetList();
    flash(t('已删除预设“{name}”', { name }));
  }

  // 导出 / 导入: a preset as a small file, to hand to someone else. Both ask in the system's dialog (on the server, as
  // opening and exporting an image do); a name that is already taken is not replaced, the import gets a number.
  async function presetFile(go) {
    if (L.presetFileBusy) return;
    L.presetFileBusy = true;
    renderPresetState();
    try { await go(); } catch (e) { flash(e.message, true); } finally {
      L.presetFileBusy = false;
      renderPresetState();
    }
  }

  const exportPreset = () => presetFile(async () => {
    const name = L.presetName;
    if (!presetOf(name)) return;
    const res = await request('POST', '/api/look/presets/export', { name });
    if (!res.cancelled) flash(t('已导出预设“{name}”：{file}', { name, file: res.file }));
  });

  const importPreset = () => presetFile(async () => {
    const res = await request('POST', '/api/look/presets/import');
    if (res.cancelled) return;
    L.presets = res.presets;
    renderPresetList();
    flash(res.renamed ? t('已导入预设“{name}”（已有同名预设，没有覆盖）', { name: res.imported })
      : t('已导入预设“{name}”', { name: res.imported }));
  });

  presetSel.addEventListener('change', () => {
    if (presetSel.selectedOptions[0]?.dataset.new) {
      renderPresetState();                       // the list shows the selected preset again while the name is asked
      openSavePreset();
    } else if (presetSel.value) applyPreset(presetSel.value);
    else { namePreset(null); renderPresetState(); }
  });
  presetSave.addEventListener('click', () => {
    // Enter and Space also activate the button, but an unchanged preset must not be written again.
    if (presetSave.getAttribute('aria-disabled') === 'true') { flash(presetSave.dataset.tip); return; }
    if (presetOf(L.presetName)) updatePreset(); else openSavePreset();
  });
  $('#btn-preset-delete').addEventListener('click', deletePreset);
  $('#btn-preset-export').addEventListener('click', exportPreset);
  $('#btn-preset-import').addEventListener('click', importPreset);
  $('#btn-preset-undo').addEventListener('click', () => applyPreset(L.presetName));
  presetNameInput.addEventListener('input', renderPresetDialog);
  $('#btn-preset-cancel').addEventListener('click', () => presetDlg.close());
  $('#preset-form').addEventListener('submit', (e) => { e.preventDefault(); savePreset(); });

  // ---------------------------------------------------------------- lifecycle

  // Reads the saved settings into the page. An edit still waiting goes out first; one made while that save or the
  // answer is on its way is newer than it, so the answer's settings are not taken (the edit's own save brings the
  // server's word back). Nor are they if the waiting edit could not be saved (shown already): it stays on screen,
  // to send again.
  let reading = Promise.resolve();    // the latest reading of the settings, done or still on its way
  function load() {
    const run = read();
    reading = run.catch(() => {});
    return run;
  }
  async function read() {
    const doc = getDoc();
    if (!doc) return;
    const seen = edits;
    const named = L.presetName;
    let kept = false;
    try { await flush(); } catch { kept = true; }
    const info = await request('GET', `/api/doc/${doc.id}/look`);
    if (!getDoc() || getDoc().id !== doc.id) return;
    // Read before an undo or redo the page has since been told of (撤销 pressed twice): the reading asked for then
    // brings the newer word. An answer of the step the page knows is taken, whichever reading it answers.
    if (info.look_rev < L.lookRev) return;
    L.info = info;
    if (!L.params || (!kept && !unsaved && edits === seen)) {
      L.params = { ...info.params };
      // the server's word, so 撤销 and 重做 bring the preset back too; unless a preset was picked or named since
      // this reading was asked for: that is the newer word, and namePreset sends it now that the reading is in
      if (L.presetName === named) L.presetName = info.preset ?? null;
      L.gesture = null;
      L.newStep = true;
    }
    if (L.layer >= layerCount()) L.layer = layerCount() - 1;
    renderControls();
    renderInfo();
    history();
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

  for (const b of document.querySelectorAll('.styles .opt')) b.addEventListener('click', () => setLayer({ style: b.dataset.style }));
  $('#density').addEventListener('input', (e) => setLayer({ density: +e.target.value }, { gesture: `density:${L.layer}` }));
  $('#tilt').addEventListener('input', (e) => setLayer({ tilt: +e.target.value }, { gesture: `tilt:${L.layer}` }));
  $('#strength').addEventListener('input', (e) => setLayer({ strength: +e.target.value, strength_auto: false },
    { gesture: `strength:${L.layer}` }));
  $('#strength-auto').addEventListener('click', () => {
    if (L.params) setLayer({ strength_auto: !layerAt(L.layer).strength_auto });
  });
  $('#sparkle-on').addEventListener('change', (e) => set({ sparkle_on: e.target.checked }));
  $('#sparkle-depth').addEventListener('input', (e) => setAmount('sparkle_depth', +e.target.value));
  $('#sparkle-bright').addEventListener('input', (e) => setAmount('sparkle_bright', +e.target.value));
  $('#sparkle-painted').addEventListener('input', (e) => set({ sparkle_painted: +e.target.value }, { gesture: 'sparkle_painted' }));
  $('#sparkle-even').addEventListener('input', (e) => set({ sparkle_even: +e.target.value }, { gesture: 'sparkle_even' }));
  $('#particle-on').addEventListener('change', (e) => set({ particle_on: e.target.checked }));
  $('#particle').addEventListener('input', (e) => set({ particle: +e.target.value }, { gesture: 'particle' }));
  $('#moire-on').addEventListener('change', (e) => set({ moire_on: e.target.checked }));
  $('#moire').addEventListener('input', (e) => set({ moire: +e.target.value }, { gesture: 'moire' }));
  $('#moire-area').addEventListener('input', (e) => set({ moire_area: +e.target.value }, { gesture: 'moire_area' }));
  $('#btn-sparkle-link').addEventListener('click', toggleLink);
  $('#fade').addEventListener('change', (e) => set({ fade: e.target.checked }));
  $('#exclude').addEventListener('change', (e) => {
    const doc = getDoc();
    if (!doc) return;
    const on = e.target.checked;
    e.target.checked = doc.color_exclude !== false;           // shown once the server has it
    edit('PUT', '/coverage/exclude', { on });
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
      pop.style.left = `${Math.round(Math.max(8, Math.min(side.right + 8, window.innerWidth - pop.offsetWidth - 8)))}px`;
      pop.style.top = `${Math.round(Math.max(8, Math.min(b.top - 10, window.innerHeight - pop.offsetHeight - 8)))}px`;
    };
    btn.addEventListener('click', () => show(pop.hidden));
    btn.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); show(false); } });
    document.addEventListener('click', (e) => {
      if (!pop.hidden && !btn.contains(e.target) && !pop.contains(e.target)) show(false);
    });
    $('.side').addEventListener('scroll', () => show(false));
  }
  // 全部恢复默认 puts everything back at once, as one step of the 纹理 history: 撤销 (Ctrl+Z) takes it back, like any
  // other change, and the button keeps its name
  $('#btn-look-reset').addEventListener('click', () => {
    if (!L.params) return;
    const layer = !!(L.info && L.info.has_sparkle_layer);       // a painted 亮点 layer is the default when there is one
    const defaults = { style: 'knit', density: 100, tilt: 32,
      strength: L.info ? L.info.strength_suggested : 100, strength_auto: true, weight: 100, amount: null, layers: [],
      lock_total: L.info ? L.info.blend_auto : true,         // what a new look starts with: the user's last choice
      sparkle_on: false, sparkle_depth: layer ? 0 : 100,
      sparkle_bright: layer ? 0 : 100, sparkle_painted: layer ? 100 : 0, sparkle_even: 0, sparkle_link: true,
      particle_on: false, particle: 100,
      moire_on: false, moire: 100, moire_area: 100, fade: true };
    if (sameLook(defaults, L.params)) {           // nothing to put back: no step, so no undo is promised
      flash(t('已经是默认设置'));
      return;
    }
    set(defaults);
    flash(t('已全部恢复默认，Ctrl+Z 可以撤销'));
  });
  for (const b of document.querySelectorAll('.seg-btn[data-zoom]')) {
    b.addEventListener('click', () => {
      L.zoom = +b.dataset.zoom;
      for (const x of document.querySelectorAll('.seg-btn[data-zoom]')) x.setAttribute('aria-checked', String(x === b));
      requestCrop();
    });
  }
  $('#btn-densest').addEventListener('click', () => { L.centre = null; requestCrop(); });

  // hold space: 细节 shows the original, so the texture can be flicked on and off
  // (a control reached with the keyboard keeps Space for itself: it presses the control)
  window.addEventListener('keydown', (e) => {
    if (!L.active || e.code !== 'Space' || e.ctrlKey || e.altKey || e.metaKey) return;
    if ((e.target instanceof HTMLInputElement && e.target.type === 'text') || e.target instanceof HTMLSelectElement) return;
    const a = document.activeElement;
    if (a && a !== document.body && a !== cropCv && a.id !== 'stage' && focusByKeyboard()) return;
    if (a && a.closest && a.closest('dialog, .menu')) return;
    if (document.querySelector('dialog:modal')) return;     // the focus can be on the body behind an open dialog
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

  // Refit when a translated label or a legend value takes another line. Measure outside the observer delivery.
  const previewResize = new ResizeObserver(() => requestAnimationFrame(() => {
    if (L.active && layout()) { requestCrop(); fitSoon(); }
  }));
  for (const selector of ['#look-stage', '.detail-pane .pane-head', '.detail-pane .pane-foot']) previewResize.observe($(selector));

  // The 纹理 page's undo and redo buttons: the server's latest word on whether there is a step to take or to put back.
  function history() {
    if (L.info) onHistory(!!L.info.can_undo_look, !!L.info.can_redo_look);
  }

  return {
    params() { return L.params ? { ...L.params } : null; },
    flush,
    enter() {
      L.active = true;
      for (const b of document.querySelectorAll('.seg-btn[data-zoom]')) b.setAttribute('aria-checked', String(+b.dataset.zoom === L.zoom));
      load().catch((e) => flash(e.message, true));
      loadPresets().catch((e) => flash(e.message, true));
    },
    leave() { L.active = false; endPreviews(); setPeek(false); },
    onArt() { if (L.active) { drawFit(); drawCrop(); } },
    onState(st) {
      if (!st || st.id !== L.docId) {
        L.docId = st ? st.id : null;
        L.coverageV = st ? st.coverage_v : null;
        L.lookRev = st ? st.look_rev : 0;
        clearTimeout(saveTimer);                  // the last document's settings are not this one's to save
        unsaved = false;
        Object.assign(L, { params: null, info: null, centre: null, fitImg: null, checkImg: null, cropImg: null,
          presetName: null, layer: 0,
          gesture: null, newStep: true,
          cropCheckImg: null,
          cropRect: null });
        resetPreviewStatus();
        renderPresetState();
        renderLayers();                           // the last document's layers are not this one's to show
        if (L.active && st) load().catch((e) => flash(e.message, true));
        return;
      }
      renderAdd();
      renderExclude();
      if (st.look_rev !== L.lookRev) {            // undo or redo changed the settings: read them again, and with
        L.lookRev = st.look_rev;                  // them the preset they went with at that step
        if (L.active) load().catch((e) => flash(e.message, true)); else L.params = null;
      }
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
