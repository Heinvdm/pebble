"use strict";
(() => {
const G = typeof self !== "undefined" ? self : window;
const IN_WORKER = typeof importScripts === "function" && typeof document === "undefined";
const HOME = G.location.origin;
const DEG = 180 / Math.PI;
const S = {
  cfg: null, face: null, body: null, tag: null,
  ms: { face: 0, body: 0, tag: 0 }, sinceBody: 99, bodies: [], bodyT: -1e9,
  tracks: [], nextId: 1, trackCam: null, canvases: {}, gray: null, guarded: false, blocked: 0
};

function guardFetch() {
  if (S.guarded || typeof G.fetch !== "function") return;
  S.guarded = true;
  const real = G.fetch.bind(G);
  G.fetch = (input, init) => {
    let url = null;
    try { url = new URL(typeof input === "string" || input instanceof URL ? String(input) : input.url, G.location.href); } catch (err) { url = null; }
    if (!url || url.origin !== HOME) {
      S.blocked++;
      return Promise.reject(new TypeError("Pebble's eyes only load files from Pebble"));
    }
    return real(input, init);
  };
}
function load(src) {
  if (IN_WORKER) { importScripts(src); return Promise.resolve(); }
  return new Promise((ok, bad) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => ok();
    s.onerror = () => bad(new Error("cannot load " + src));
    document.head.appendChild(s);
  });
}
function message(err) {
  return String((err && err.message) || err).slice(0, 160);
}
function canvasOf(name, w, h) {
  let c = S.canvases[name];
  if (!c) {
    c = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(w, h) : document.createElement("canvas");
    S.canvases[name] = c;
  }
  if (c.width !== w) c.width = w;
  if (c.height !== h) c.height = h;
  return c;
}
function ema(old, now) {
  return old ? old * 0.8 + now * 0.2 : now;
}

async function makeTags(loader, wasm) {
  await load(loader);
  const M = await G.AprilTagWasm({ locateFile: () => wasm, print: () => {}, printErr: () => {} });
  const api = {
    M: M,
    init: M.cwrap("atagjs_init", "number", []),
    opts: M.cwrap("atagjs_set_detector_options", "number", ["number", "number", "number", "number", "number", "number", "number"]),
    pose: M.cwrap("atagjs_set_pose_info", "number", ["number", "number", "number", "number"]),
    buffer: M.cwrap("atagjs_set_img_buffer", "number", ["number", "number", "number"]),
    size: M.cwrap("atagjs_set_tag_size", "number", ["number", "number"]),
    detect: M.cwrap("atagjs_detect", "number", []),
    decimate: 0
  };
  api.init();
  return api;
}

async function init(cfg) {
  S.cfg = cfg;
  guardFetch();
  const v = cfg.vendor, errors = [], t0 = performance.now(), mode = cfg.people || "both";
  if (mode !== "none") {
    try {
      await load(v.vision);
      const V = G.Vision;
      const files = { wasmLoaderPath: v.vision_loader, wasmBinaryPath: v.vision_wasm };
      const base = path => ({ modelAssetPath: path, delegate: cfg.delegate === "GPU" ? "GPU" : "CPU" });
      if (mode === "both" || mode === "faces") {
        S.face = await V.FaceDetector.createFromOptions(files, { baseOptions: base(v.face_model), runningMode: "IMAGE", minDetectionConfidence: 0.5, minSuppressionThreshold: 0.3 });
      }
      if (mode === "both" || mode === "bodies") {
        S.body = await V.ObjectDetector.createFromOptions(files, { baseOptions: base(v.body_model), runningMode: "IMAGE", scoreThreshold: 0.35, maxResults: 6, categoryAllowlist: ["person"] });
      }
    } catch (err) {
      errors.push("people: " + message(err));
    }
  }
  try {
    S.tag = await makeTags(v.tag_loader, v.tag_wasm);
  } catch (err) {
    errors.push("tags: " + message(err));
  }
  return { op: "ready", faces: !!S.face, bodies: !!S.body, tags: !!S.tag, errors: errors, load_ms: Math.round(performance.now() - t0), worker: IN_WORKER };
}

function upright(bitmap, rotate, flip) {
  const sw = bitmap.width, sh = bitmap.height;
  if (!rotate && !flip) return { src: bitmap, w: sw, h: sh };
  const turn = rotate === 90 || rotate === 270, w = turn ? sh : sw, h = turn ? sw : sh;
  const c = canvasOf("up", w, h), x = c.getContext("2d");
  x.setTransform(1, 0, 0, 1, 0, 0);
  x.translate(w / 2, h / 2);
  if (flip) x.scale(-1, 1);
  x.rotate(rotate * Math.PI / 180);
  x.drawImage(bitmap, -sw / 2, -sh / 2);
  x.setTransform(1, 0, 0, 1, 0, 0);
  return { src: c, w: w, h: h };
}
function focal(w, fov) {
  return (w / 2) / Math.tan(fov * Math.PI / 360);
}
function angles(u, v, w, h, fov) {
  const f = focal(w, fov);
  return [Math.atan((u - 0.5) * w / f) * DEG, Math.atan(-(v - 0.5) * h / f) * DEG];
}
function boxOf(b, w, h, score) {
  const x = Math.max(0, b.originX / w), y = Math.max(0, b.originY / h);
  return { x: x, y: y, w: Math.min(1 - x, b.width / w), h: Math.min(1 - y, b.height / h), score: score };
}
function topScore(d) {
  return d.categories && d.categories.length ? d.categories[0].score : 0;
}

function combine(faces, bodies) {
  const used = new Set(), out = [];
  for (const b of bodies) {
    let pick = -1, area = 0;
    faces.forEach((f, i) => {
      if (used.has(i)) return;
      const cx = f.x + f.w / 2, cy = f.y + f.h / 2;
      if (cx >= b.x && cx <= b.x + b.w && cy >= b.y - f.h * 0.3 && cy <= b.y + b.h * 0.6 && f.w * f.h > area) { pick = i; area = f.w * f.h; }
    });
    if (pick >= 0) {
      used.add(pick);
      const f = faces[pick];
      out.push({ u: f.x + f.w / 2, v: f.y + f.h / 2, bw: b.w, bh: b.h, score: Math.max(b.score, f.score), face: true });
    } else {
      out.push({ u: b.x + b.w / 2, v: b.y + b.h * 0.12, bw: b.w, bh: b.h, score: b.score, face: false });
    }
  }
  faces.forEach((f, i) => {
    if (!used.has(i)) out.push({ u: f.x + f.w / 2, v: f.y + f.h / 2, bw: f.w, bh: f.h, score: f.score, face: true });
  });
  return out;
}

function track(list, t, camera, aspect) {
  if (S.trackCam !== camera) { S.tracks = []; S.trackCam = camera; }
  S.tracks = S.tracks.filter(k => t - k.last < 1.0);
  const free = S.tracks.slice();
  list.sort((a, b) => b.bw * b.bh - a.bw * a.bh);
  for (const p of list) {
    let best = null, cost = 1.3;
    for (const k of free) {
      const scale = Math.max(0.04, p.bw, k.bw);
      const c = Math.hypot(p.u - k.u, (p.v - k.v) / aspect) / scale + Math.abs(Math.log((p.bh + 0.01) / (k.bh + 0.01))) * 0.6 + (p.face === k.face ? 0 : 0.15);
      if (c < cost) { cost = c; best = k; }
    }
    if (best) {
      free.splice(free.indexOf(best), 1);
      Object.assign(best, { u: p.u, v: p.v, bw: p.bw, bh: p.bh, face: p.face, last: t });
      p.track = best.id;
    } else {
      const k = { id: S.nextId++, u: p.u, v: p.v, bw: p.bw, bh: p.bh, face: p.face, last: t };
      S.tracks.push(k);
      p.track = k.id;
    }
  }
  return list;
}

function grayOf(src, w, h) {
  const c = canvasOf("gray", w, h), x = c.getContext("2d", { willReadFrequently: true });
  x.drawImage(src, 0, 0, w, h);
  const rgba = x.getImageData(0, 0, w, h).data;
  if (!S.gray || S.gray.length !== w * h) S.gray = new Uint8Array(w * h);
  const g = S.gray;
  for (let i = 0, j = 0; j < g.length; i += 4, j++) g[j] = (rgba[i] * 77 + rgba[i + 1] * 150 + rgba[i + 2] * 29) >> 8;
  return g;
}
function yawOf(R, t) {
  let n = [R[2][0], R[2][1], R[2][2]];
  if (n[0] * t[0] + n[1] * t[1] + n[2] * t[2] > 0) n = [-n[0], -n[1], -n[2]];
  return Math.atan2(n[0], -n[2]) * DEG;
}
function wrap(a) {
  return ((a + 180) % 360 + 360) % 360 - 180;
}
function detectTags(src, w, h, fov, cfg) {
  const T = S.tag, gray = grayOf(src, w, h), f = focal(w, fov);
  const decimate = +cfg.decimate || (w > 1000 ? 2 : 1.5);
  if (decimate !== T.decimate) { T.opts(decimate, 0, 1, 1, 0, 1, 1); T.decimate = decimate; }
  T.pose(f, f, w / 2, h / 2);
  T.size(cfg.tag.id, cfg.tag.size_m);
  const ptr = T.buffer(w, h, w);
  T.M.HEAPU8.set(gray, ptr);
  const res = T.detect();
  const len = T.M.getValue(res, "i32");
  if (!len) return [];
  const sptr = T.M.getValue(res + 4, "i32");
  const list = JSON.parse(new TextDecoder().decode(T.M.HEAPU8.slice(sptr, sptr + len)));
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const d of list) {
    if (!d.pose || !d.pose.t || d.id !== cfg.tag.id) continue;
    const t = d.pose.t, bearing = Math.atan2(t[0], t[2]) * DEG;
    const yaw = wrap(yawOf(d.pose.R, t) + bearing);
    const px = d.corners.reduce((a, c, i, cs) => a + Math.hypot(c.x - cs[(i + 1) % 4].x, c.y - cs[(i + 1) % 4].y), 0) / 4;
    let score = Math.max(0.05, Math.min(1, (px - 20) / 60)), other = null;
    const alt = d.pose.asol;
    if (alt && alt.uniquesol && alt.R && alt.e > 0) {
      other = wrap(yawOf(alt.R, alt.t) + Math.atan2(alt.t[0], alt.t[2]) * DEG);
      if (Math.abs(wrap(other - yaw)) > 8) score *= Math.max(0.05, Math.min(1, 1 - d.pose.e / alt.e));
    }
    out.push({ id: d.id, bearing_deg: bearing, distance_m: Math.hypot(t[0], t[1], t[2]), yaw_deg: yaw, score: score, px: px, err: d.pose.e, alt_yaw: other, alt_err: alt ? alt.e : null });
  }
  return out;
}

function frame(m) {
  const t0 = performance.now(), cfg = S.cfg, ms = {};
  const up = upright(m.bitmap, m.rotate | 0, !!m.mirror), w = up.w, h = up.h;
  let faces = [], tags = [], error = null;
  try {
    if (m.people && S.face) {
      const a = performance.now();
      faces = (S.face.detect(up.src).detections || []).map(d => boxOf(d.boundingBox, w, h, topScore(d)));
      ms.face = performance.now() - a;
      S.ms.face = ema(S.ms.face, ms.face);
    }
    if (S.trackCam !== m.camera) { S.bodies = []; S.sinceBody = 99; }
    const budget = 1000 / Math.max(4, m.fps || 12);
    const every = Math.max(1, Math.min(8, Math.ceil(S.ms.body / Math.max(4, budget - S.ms.face - (m.tags ? S.ms.tag : 0)))));
    S.sinceBody++;
    if (m.people && S.body && (S.sinceBody >= every || m.t - S.bodyT > 1)) {
      const a = performance.now();
      S.bodies = (S.body.detect(up.src).detections || []).map(d => boxOf(d.boundingBox, w, h, topScore(d)));
      ms.body = performance.now() - a;
      S.ms.body = ema(S.ms.body, ms.body);
      S.sinceBody = 0;
      S.bodyT = m.t;
    }
    if (m.tags && S.tag) {
      const a = performance.now();
      tags = detectTags(up.src, w, h, m.fov, cfg);
      ms.tag = performance.now() - a;
      S.ms.tag = ema(S.ms.tag, ms.tag);
    }
  } catch (err) {
    error = message(err);
  }
  if (m.bitmap.close) m.bitmap.close();
  const bodies = m.t - S.bodyT < 1.2 ? S.bodies : [];
  const people = track(combine(faces, bodies), m.t, m.camera, w / h).map(p => {
    const a = angles(p.u, p.v, w, h, m.fov);
    return { bearing_deg: a[0], elevation_deg: a[1], height_frac: p.bh, width_frac: p.bw, score: p.score, face: p.face, track: p.track, u: p.u, v: p.v };
  });
  ms.total = performance.now() - t0;
  return { op: "seen", t: m.t, seq: m.seq, camera: m.camera, fov: m.fov, w: w, h: h, people: people, tags: tags, ms: ms, avg: { face: S.ms.face, body: S.ms.body, tag: S.ms.tag }, blocked: S.blocked, error: error };
}

async function handle(m) {
  if (m.op === "init") return init(m.cfg);
  if (m.op === "frame") return frame(m);
  if (m.op === "reset") { S.tracks = []; S.bodies = []; S.trackCam = null; return { op: "reset" }; }
  return { op: "error", error: "unknown op" };
}

if (IN_WORKER) {
  self.onmessage = e => {
    handle(e.data).then(r => self.postMessage(r), err => self.postMessage({ op: e.data && e.data.op === "init" ? "ready" : "seen", error: message(err), errors: [message(err)] }));
  };
} else {
  G.PebbleEyesEngine = { handle: handle };
}
})();
