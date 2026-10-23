import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from geom import mesh_arrays

CHUNK = 2_500_000


def camera(azim, elev):
    a = math.radians(azim)
    e = math.radians(elev)
    c = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    d = -c
    r = np.array([-math.sin(a), math.cos(a), 0.0])
    u = np.cross(r, d)
    return d, r, u


def _gather(items):
    vs, fs, ids = [], [], []
    off = 0
    for i, (m, _) in enumerate(items):
        if m is None or m.is_empty():
            continue
        v, f = mesh_arrays(m)
        vs.append(v)
        fs.append(f + off)
        ids.append(np.full(len(f), i, dtype=np.int32))
        off += len(v)
    if not vs:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), np.zeros(0, dtype=np.int32)
    return np.vstack(vs), np.vstack(fs), np.concatenate(ids)


def render(items, path, azim=-60.0, elev=25.0, size=(1400, 1000), ss=2, title=None, bounds=None, light=None, margin=0.06):
    W, H = size[0] * ss, size[1] * ss
    v, f, ids = _gather(items)
    d, r, u = camera(azim, elev)
    sx = v @ r
    sy = v @ u
    dz = v @ d
    if bounds is None:
        bx0, bx1, by0, by1 = sx.min(), sx.max(), sy.min(), sy.max()
    else:
        pts = np.array([[x, y, z] for x in (bounds[0], bounds[3]) for y in (bounds[1], bounds[4]) for z in (bounds[2], bounds[5])])
        bx0, bx1 = (pts @ r).min(), (pts @ r).max()
        by0, by1 = (pts @ u).min(), (pts @ u).max()
    span = max((bx1 - bx0) / (W * (1 - 2 * margin)), (by1 - by0) / (H * (1 - 2 * margin)))
    cx = (bx0 + bx1) / 2.0
    cy = (by0 + by1) / 2.0
    px = (sx - cx) / span + W / 2.0
    py = H / 2.0 - (sy - cy) / span
    tv = v[f]
    n = np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0])
    ln = np.linalg.norm(n, axis=1)
    keep = (ln > 1e-12)
    n = n / np.maximum(ln, 1e-12)[:, None]
    front = (n @ d) < 0
    keep &= front
    f = f[keep]
    n = n[keep]
    ids = ids[keep]
    L = -d * 0.75 + u * 0.55 - r * 0.35
    L = L / np.linalg.norm(L)
    if light is not None:
        L = np.asarray(light, dtype=float)
        L = L / np.linalg.norm(L)
    shade = 0.30 + 0.70 * np.clip(n @ L, 0.0, 1.0)
    X = px[f]
    Y = py[f]
    Z = dz[f]
    zbuf = np.full(W * H, np.inf)
    tbuf = np.full(W * H, -1, dtype=np.int64)
    x0 = np.floor(X.min(axis=1)).astype(np.int64)
    x1 = np.floor(X.max(axis=1)).astype(np.int64)
    y0 = np.floor(Y.min(axis=1)).astype(np.int64)
    y1 = np.floor(Y.max(axis=1)).astype(np.int64)
    x0 = np.clip(x0, 0, W - 1)
    y0 = np.clip(y0, 0, H - 1)
    x1 = np.clip(x1, 0, W - 1)
    y1 = np.clip(y1, 0, H - 1)
    wspan = x1 - x0 + 1
    hspan = y1 - y0 + 1
    kmax = np.maximum(wspan, hspan)
    valid = (X.max(axis=1) >= 0) & (X.min(axis=1) < W) & (Y.max(axis=1) >= 0) & (Y.min(axis=1) < H)
    tri_all = np.nonzero(valid)[0]
    lo = 0
    k = 1
    while k <= 128:
        sel = tri_all[(kmax[tri_all] <= k) & (kmax[tri_all] > lo)]
        if len(sel):
            _raster(sel, k, k, X, Y, Z, x0, y0, x1, y1, W, zbuf, tbuf)
        lo = k
        k *= 2
    for t in tri_all[kmax[tri_all] > 128]:
        rows = max(1, CHUNK // int(wspan[t]))
        for ys in range(int(y0[t]), int(y1[t]) + 1, rows):
            ye = min(int(y1[t]), ys + rows - 1)
            yy0 = y0.copy()
            yy1 = y1.copy()
            yy0[t] = ys
            yy1[t] = ye
            _raster(np.array([t]), int(wspan[t]), ye - ys + 1, X, Y, Z, x0, yy0, x1, yy1, W, zbuf, tbuf)
    img = _compose(tbuf, zbuf, ids, shade, n, items, W, H, span)
    im = Image.fromarray(img, "RGB").resize(size, Image.LANCZOS)
    if title:
        dr = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("arial.ttf", 22)
        except OSError:
            font = ImageFont.load_default()
        dr.text((16, 12), title, fill=(30, 30, 30), font=font)
    im.save(path)
    return path


def _raster(sel, kx, ky, X, Y, Z, x0, y0, x1, y1, W, zbuf, tbuf):
    oy, ox = np.mgrid[0:ky, 0:kx]
    ox = ox.ravel()
    oy = oy.ravel()
    per = kx * ky
    step = max(1, CHUNK // per)
    for s in range(0, len(sel), step):
        t = sel[s:s + step]
        PX = x0[t][:, None] + ox[None, :]
        PY = y0[t][:, None] + oy[None, :]
        m = (PX <= x1[t][:, None]) & (PY <= y1[t][:, None])
        cxp = PX + 0.5
        cyp = PY + 0.5
        ax, ay = X[t, 0][:, None], Y[t, 0][:, None]
        bx, by = X[t, 1][:, None], Y[t, 1][:, None]
        qx, qy = X[t, 2][:, None], Y[t, 2][:, None]
        area = (bx - ax) * (qy - ay) - (by - ay) * (qx - ax)
        sgn = np.where(area >= 0, 1.0, -1.0)
        w0 = ((bx - cxp) * (qy - cyp) - (by - cyp) * (qx - cxp)) * sgn
        w1 = ((qx - cxp) * (ay - cyp) - (qy - cyp) * (ax - cxp)) * sgn
        w2 = ((ax - cxp) * (by - cyp) - (ay - cyp) * (bx - cxp)) * sgn
        aa = np.abs(area)
        eps = -1e-9 * np.maximum(aa, 1.0)
        m &= (w0 >= eps) & (w1 >= eps) & (w2 >= eps) & (aa > 1e-12)
        if not m.any():
            continue
        inv = 1.0 / np.where(aa > 1e-12, aa, 1.0)
        depth = (w0 * Z[t, 0][:, None] + w1 * Z[t, 1][:, None] + w2 * Z[t, 2][:, None]) * inv
        tri = np.broadcast_to(t[:, None], m.shape)
        pix = (PY * W + PX)[m]
        dep = depth[m]
        tt = tri[m]
        order = np.lexsort((dep, pix))
        ps = pix[order]
        first = np.ones(len(ps), dtype=bool)
        first[1:] = ps[1:] != ps[:-1]
        o = order[first]
        p = pix[o]
        dd = dep[o]
        better = dd < zbuf[p]
        zbuf[p[better]] = dd[better]
        tbuf[p[better]] = tt[o][better]


def _compose(tbuf, zbuf, ids, shade, n, items, W, H, span):
    cols = np.array([np.asarray(c[1], dtype=float) for c in items] + [[255.0, 255.0, 255.0]])
    bg = len(items)
    t = tbuf.reshape(H, W)
    hit = t >= 0
    item = np.where(hit, ids[np.maximum(t, 0)], bg)
    sh = np.where(hit, shade[np.maximum(t, 0)], 1.0)
    img = cols[item] * np.where(hit, sh, 1.0)[..., None]
    img = np.where(hit[..., None], img, np.array([250.0, 250.0, 252.0]))
    z = np.where(hit, zbuf.reshape(H, W), np.nan)
    nn = np.where(hit[..., None], n[np.maximum(t, 0)], 0.0)
    edge = np.zeros((H, W), dtype=bool)
    thr = 4.0 * span
    for dy, dx in ((0, 1), (1, 0), (1, 1)):
        a_item = item[: H - dy, : W - dx]
        b_item = item[dy:, dx:]
        e = a_item != b_item
        dot = (nn[: H - dy, : W - dx] * nn[dy:, dx:]).sum(axis=2)
        e |= (dot < 0.82) & hit[: H - dy, : W - dx] & hit[dy:, dx:]
        edge[: H - dy, : W - dx] |= e
    for dy, dx in ((0, 1), (1, 0)):
        z0 = z[: H - 2 * dy, : W - 2 * dx]
        z1 = z[dy: H - dy, dx: W - dx]
        z2 = z[2 * dy:, 2 * dx:]
        with np.errstate(invalid="ignore"):
            e = np.abs(z0 - 2.0 * z1 + z2) > thr
        edge[dy: H - dy, dx: W - dx] |= e
    img[edge] = img[edge] * 0.25
    return np.clip(img, 0, 255).astype(np.uint8)
