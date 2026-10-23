"use strict";
(() => {
const MAX_HOLD = 30;
const DEFAULT_HOLD = 20;
const QUIET = 4;
const QR_SHARE = 0.85;
const RETRY_MS = 2000;
const ORBIT_MS = 10000;
const ORBIT_PX = 4;
const ORBIT_STEPS = 8;
const BADGE_MS = 60000;
const FORGET_S = 120;
const BLEED = 8;
const FONT = "system-ui, -apple-system, \"Segoe UI\", Roboto, \"Noto Sans\", Arial, sans-serif";
const INK = "#d8d8d8";
const DIM = "#888";
const BADGE_INK = "#666";
const LINE_HEIGHT = 1.25;
const MIN_LINE = 0.03;
const CAPTION_LINE = 0.065;
const CAPTION_MIN = 0.035;
const LOOKS = {
  list: { title: 0.07, line: 0.05, center: false },
  qr: { title: 0.07, line: 0.05, center: false },
  card: { title: 0.12, line: 0.065, center: true }
};

function holdSeconds(hold) {
  if (typeof hold !== "number" || !(hold > 0)) return DEFAULT_HOLD;
  return Math.min(MAX_HOLD, hold);
}

function moduleSize(modules, width, height) {
  const side = Math.min(width, height) * QR_SHARE;
  return Math.max(1, Math.floor(side / ((modules | 0) + 2 * QUIET)));
}

function nextCorner(i) {
  return (((i | 0) % 4) + 5) % 4;
}

const S = {
  es: null, retry: 0, root: null, panel: null, inner: null, qrBox: null, qrCanvas: null, drawn: null,
  textBox: null, head: null, title: null, count: null, lines: null, band: null, badge: null, measure: null,
  item: null, caption: null, badgeText: null, itemTimer: 0, captionTimer: 0, bandHeight: 0,
  corner: 0, orbit: 0, seen: new Map()
};

function now() {
  return performance.now() / 1000;
}

function make(tag, css, parent) {
  const el = document.createElement(tag);
  el.style.cssText = css;
  if (parent) parent.appendChild(el);
  return el;
}

function textWidth(text, px, weight) {
  S.measure.font = weight + " " + px + "px " + FONT;
  return S.measure.measureText(text).width;
}

function words(value) {
  return typeof value === "string" ? value : "";
}

function wordList(value) {
  return Array.isArray(value) ? value.filter(v => typeof v === "string") : [];
}

function validRows(rows) {
  if (!Array.isArray(rows) || rows.length < 21 || rows.length > 177) return null;
  for (const row of rows) if (typeof row !== "string" || row.length !== rows.length) return null;
  return rows;
}

function build() {
  S.root = make("div", "position:fixed;left:0;top:0;width:100%;height:100%;z-index:2147483000;pointer-events:none;transition:transform 3s ease-in-out;color:" + INK + ";font-family:" + FONT + ";-webkit-user-select:none;user-select:none", document.body);
  S.panel = make("div", "position:absolute;left:" + -BLEED + "px;top:" + -BLEED + "px;right:" + -BLEED + "px;bottom:" + -BLEED + "px;padding:" + BLEED + "px;box-sizing:border-box;background:#000;display:none;pointer-events:auto;overflow:hidden", S.root);
  S.inner = make("div", "position:relative;width:100%;box-sizing:border-box;display:flex;align-items:center", S.panel);
  S.qrBox = make("div", "flex:none;display:none;align-items:center;justify-content:center", S.inner);
  S.qrCanvas = make("canvas", "position:static;display:block;margin:0;cursor:default;image-rendering:pixelated;image-rendering:crisp-edges", S.qrBox);
  S.textBox = make("div", "flex:1 1 auto;align-self:stretch;min-width:0;min-height:0;display:flex;flex-direction:column", S.inner);
  S.head = make("div", "flex:none;display:none;align-items:baseline;gap:0.5em", S.textBox);
  S.title = make("div", "flex:1 1 auto;min-width:0;font-weight:600;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis", S.head);
  S.count = make("div", "flex:none;color:" + DIM, S.head);
  S.lines = make("div", "flex:none;display:flex;min-height:0", S.textBox);
  S.band = make("div", "position:absolute;left:" + -BLEED + "px;right:" + -BLEED + "px;bottom:" + -BLEED + "px;box-sizing:border-box;background:#000;display:none;pointer-events:auto;text-align:center", S.root);
  S.badge = make("div", "position:absolute;display:none;pointer-events:none;white-space:nowrap;color:" + BADGE_INK, S.root);
  S.measure = document.createElement("canvas").getContext("2d");
  S.panel.addEventListener("click", () => dismiss(S.item));
  S.band.addEventListener("click", () => dismiss(S.caption));
}

function drawQr(rows, size) {
  const n = rows.length, total = (n + 2 * QUIET) * size, dpr = window.devicePixelRatio || 1, cv = S.qrCanvas;
  cv.style.width = total / dpr + "px";
  cv.style.height = total / dpr + "px";
  if (S.drawn && S.drawn.rows === rows && S.drawn.size === size) return;
  cv.width = total;
  cv.height = total;
  const g = cv.getContext("2d", { alpha: false });
  g.imageSmoothingEnabled = false;
  g.fillStyle = "#fff";
  g.fillRect(0, 0, total, total);
  g.fillStyle = "#000";
  for (let y = 0; y < n; y++) {
    const row = rows[y];
    let x = 0;
    while (x < n) {
      if (row.charCodeAt(x) !== 49) { x++; continue; }
      let end = x + 1;
      while (end < n && row.charCodeAt(end) === 49) end++;
      g.fillRect((x + QUIET) * size, (y + QUIET) * size, (end - x) * size, size);
      x = end;
    }
  }
  S.drawn = { rows: rows, size: size };
}

function layoutBand() {
  const cap = S.caption;
  if (!cap) {
    S.band.style.display = "none";
    S.bandHeight = 0;
    return;
  }
  const W = window.innerWidth, H = window.innerHeight;
  const lines = cap.lines.slice(-2);
  const padX = Math.round(W * 0.04), padY = Math.round(H * 0.02), room = Math.max(1, W - 2 * padX);
  let px = CAPTION_LINE * H;
  let widest = 1;
  for (const line of lines) widest = Math.max(widest, textWidth(line, px, 500));
  if (widest > room) px = Math.max(CAPTION_MIN * H, px * room / widest);
  S.band.textContent = "";
  for (const line of lines) {
    const row = make("div", "font-size:" + px + "px;font-weight:500;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis", S.band);
    row.textContent = line;
  }
  S.band.style.padding = padY + "px " + (padX + BLEED) + "px " + (padY + BLEED) + "px";
  S.band.style.display = "block";
  S.bandHeight = Math.ceil(lines.length * px * 1.2 + 2 * padY);
}

function layoutPanel() {
  const item = S.item;
  if (!item) {
    S.panel.style.display = "none";
    return;
  }
  const W = window.innerWidth, H = window.innerHeight, dpr = window.devicePixelRatio || 1;
  const areaH = Math.max(1, H - S.bandHeight);
  const pad = Math.round(Math.min(W, areaH) * 0.05);
  const look = LOOKS[item.kind] || LOOKS.list;
  const wide = W >= areaH;
  S.panel.style.display = "block";
  const box = S.inner.style;
  box.height = areaH + "px";
  box.padding = pad + "px";
  box.gap = pad + "px";
  box.flexDirection = wide ? "row" : "column";
  let side = 0;
  const rows = validRows(item.qr);
  if (rows) {
    const size = moduleSize(rows.length, W * dpr, areaH * dpr);
    drawQr(rows, size);
    side = (rows.length + 2 * QUIET) * size / dpr;
    S.qrBox.style.display = "flex";
  } else {
    S.qrBox.style.display = "none";
  }
  const textW = Math.max(1, (wide && side ? W - side - pad : W) - 2 * pad);
  const textH = Math.max(1, (wide || !side ? areaH : areaH - side - pad) - 2 * pad);
  S.textBox.style.justifyContent = look.center ? "center" : "flex-start";
  const counter = item.pages > 1 ? item.page + "/" + item.pages : "";
  let titlePx = 0;
  if (item.title || counter) {
    titlePx = look.title * H;
    const countPx = Math.max(10, Math.round(H * 0.035));
    const room = Math.max(1, textW - (counter ? textWidth(counter, countPx, 400) + titlePx * 0.5 : 0));
    const need = item.title ? textWidth(item.title, titlePx, 600) : 0;
    if (need > room) titlePx = Math.max(MIN_LINE * H, titlePx * room / need);
    S.head.style.display = "flex";
    S.head.style.justifyContent = look.center ? "center" : "flex-start";
    S.title.style.flex = look.center ? "0 1 auto" : "1 1 auto";
    S.title.style.fontSize = titlePx + "px";
    S.title.textContent = item.title;
    S.count.style.fontSize = countPx + "px";
    S.count.textContent = counter;
  } else {
    S.head.style.display = "none";
  }
  const lines = item.lines;
  const roomH = Math.max(1, textH - (titlePx ? titlePx * 1.2 + pad * 0.4 : 0));
  const gap = Math.round(W * 0.03);
  let px = look.line * H, per = Math.max(1, lines.length), cols = 1;
  while (lines.length) {
    per = Math.max(1, Math.floor(roomH / (px * LINE_HEIGHT)));
    cols = Math.ceil(lines.length / per);
    const colW = (textW - gap * (cols - 1)) / cols;
    let widest = 0;
    for (const line of lines) widest = Math.max(widest, textWidth(line, px, 400));
    if (widest <= colW || px <= MIN_LINE * H) break;
    px = Math.max(MIN_LINE * H, px * 0.9);
  }
  S.lines.textContent = "";
  S.lines.style.gap = gap + "px";
  S.lines.style.marginTop = titlePx ? Math.round(pad * 0.4) + "px" : "0";
  S.lines.style.justifyContent = look.center ? "center" : "flex-start";
  for (let c = 0; c < cols && lines.length; c++) {
    const col = make("div", "min-width:0;display:flex;flex-direction:column;flex:" + (look.center ? "0 1 auto" : "1 1 0"), S.lines);
    for (const line of lines.slice(c * per, (c + 1) * per)) {
      const row = make("div", "font-size:" + px + "px;line-height:" + LINE_HEIGHT + ";white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:" + (look.center ? "center" : "left"), col);
      row.textContent = line;
    }
  }
}

function placeBadge() {
  const b = S.badge.style;
  if (!S.badgeText || S.item) {
    b.display = "none";
    return;
  }
  const W = window.innerWidth, H = window.innerHeight;
  const m = Math.round(Math.min(W, H) * 0.025) + ORBIT_PX;
  S.badge.textContent = S.badgeText;
  b.fontSize = Math.max(10, Math.round(H * 0.035)) + "px";
  b.left = b.right = b.top = b.bottom = "auto";
  if (S.corner === 0 || S.corner === 3) b.left = m + "px";
  else b.right = m + "px";
  if (S.corner < 2) b.top = m + "px";
  else b.bottom = m + S.bandHeight + "px";
  b.display = "block";
}

function layout() {
  layoutBand();
  layoutPanel();
  placeBadge();
}

function forget(t) {
  for (const [id, entry] of S.seen) if (t - entry.since > FORGET_S) S.seen.delete(id);
}

function hide(id) {
  let changed = false;
  if (S.item && (id === null || S.item.id === id)) {
    S.item = null;
    clearTimeout(S.itemTimer);
    changed = true;
  }
  if (S.caption && (id === null || S.caption.id === id)) {
    S.caption = null;
    clearTimeout(S.captionTimer);
    changed = true;
  }
  if (changed) layout();
}

function dismiss(item) {
  if (!item) return;
  const entry = S.seen.get(item.id);
  if (entry) entry.dismissed = true;
  hide(item.id);
}

function show(data) {
  const id = typeof data.id === "string" ? data.id : "";
  const t = now();
  forget(t);
  let entry = S.seen.get(id);
  if (!entry) {
    entry = { since: t, dismissed: false };
    S.seen.set(id, entry);
  }
  if (entry.dismissed) return;
  const left = Math.min(holdSeconds(data.hold), MAX_HOLD - (t - entry.since));
  if (left <= 0) {
    hide(id);
    return;
  }
  const item = { id: id, kind: words(data.kind), title: words(data.title), lines: wordList(data.lines), qr: data.qr, page: data.page | 0, pages: data.pages | 0 };
  if (item.kind === "caption") {
    if (!item.lines.length) return;
    S.caption = item;
    clearTimeout(S.captionTimer);
    S.captionTimer = setTimeout(() => hide(id), left * 1000);
  } else {
    S.item = item;
    clearTimeout(S.itemTimer);
    S.itemTimer = setTimeout(() => hide(id), left * 1000);
  }
  layout();
}

function setBadge(text) {
  S.badgeText = typeof text === "string" && text ? text : null;
  placeBadge();
}

function onText(data) {
  if (!data || typeof data !== "object") return;
  if (data.op === "show") show(data);
  else if (data.op === "clear") hide(typeof data.id === "string" ? data.id : null);
  else if (data.op === "badge") setBadge(data.text);
}

function connect() {
  S.retry = 0;
  if (typeof EventSource === "undefined") return;
  let es;
  try {
    es = new EventSource("/events");
  } catch (err) {
    later();
    return;
  }
  S.es = es;
  es.addEventListener("text", m => {
    try { onText(JSON.parse(m.data)); } catch (err) { return; }
  });
  es.onerror = () => {
    if (S.es !== es) return;
    es.close();
    S.es = null;
    later();
  };
}

function later() {
  if (!S.retry) S.retry = setTimeout(connect, RETRY_MS);
}

function orbit() {
  S.orbit = (S.orbit + 1) % ORBIT_STEPS;
  const dpr = window.devicePixelRatio || 1, angle = S.orbit / ORBIT_STEPS * Math.PI * 2;
  const dx = Math.round(Math.cos(angle) * ORBIT_PX * dpr) / dpr, dy = Math.round(Math.sin(angle) * ORBIT_PX * dpr) / dpr;
  S.root.style.transform = "translate(" + dx + "px," + dy + "px)";
}

function start() {
  build();
  window.addEventListener("resize", layout);
  setInterval(orbit, ORBIT_MS);
  setInterval(() => {
    S.corner = nextCorner(S.corner);
    placeBadge();
  }, BADGE_MS);
  connect();
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start, { once: true });
}

if (typeof module !== "undefined" && module.exports) module.exports = { holdSeconds, moduleSize, nextCorner };
})();
