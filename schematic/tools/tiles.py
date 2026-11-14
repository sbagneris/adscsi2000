#!/usr/bin/env python3
"""Register Stephane's close-up tiles (inputs/closeups/<side>_<TL|TM|TR|BL|BM|BR>.jpeg, 4032x3024) onto the
project's board coordinates (component-side reference photo pixels, see photo.py).

Solder tiles are shot from the back: they are mirrored left-right first. Registration: SIFT keypoints on the
tile (downscaled) and on the reference image of the same side (the solder reference is already registered onto
component coordinates), ratio-test matches, RANSAC homography. tile pixel -> board coordinate.
Writes schematic/tiles.json with each tile's 3x3 matrix (board <- tile, full-resolution tile pixels).
"""
import glob, json, os, sys
import numpy as np
import cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photo

ROOT = photo.ROOT
TILE_DIR = os.path.join(ROOT, 'inputs', 'closeups')
OUT = os.path.join(ROOT, 'schematic', 'tiles.json')
SCALE = 0.5                                     # tile downscale for matching (reference is ~1/4.5 of tile res)

def load_tile(path):
    im = cv2.imread(path, cv2.IMREAD_COLOR)
    if os.path.basename(path).startswith('solder'): im = cv2.flip(im, 1)
    return im

def ref_images():
    c, s = photo.images()
    return {'component': cv2.cvtColor(np.asarray(c), cv2.COLOR_RGB2BGR), 'solder': cv2.cvtColor(np.asarray(s), cv2.COLOR_RGB2BGR)}

# expected board region of each tile (component-side coordinates); solder tiles are seen from the back, so the
# solder "TL" tile covers the board's top-right, etc.
REGION = {'TL': (0, 0, 1150, 850), 'TM': (450, 0, 1650, 850), 'TR': (900, 0, 2031, 850),
          'BL': (0, 450, 1150, 1485), 'BM': (450, 450, 1650, 1485), 'BR': (900, 450, 2031, 1485)}
MIRROR = {'TL': 'TR', 'TR': 'TL', 'TM': 'TM', 'BL': 'BR', 'BR': 'BL', 'BM': 'BM'}

def register(tile, ref, region, scale=SCALE):
    x0, y0, x1, y1 = region
    sift = cv2.SIFT_create(nfeatures=20000)
    t = cv2.resize(tile, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    g1 = cv2.cvtColor(t, cv2.COLOR_BGR2GRAY); g2 = cv2.cvtColor(ref[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(2.0, (8, 8)); g1 = clahe.apply(g1); g2 = clahe.apply(g2)
    k1, d1 = sift.detectAndCompute(g1, None); k2, d2 = sift.detectAndCompute(g2, None)
    m = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
    good = [a for a, b in m if a.distance < 0.8 * b.distance]
    src = np.float32([k1[a.queryIdx].pt for a in good]) / scale
    dst = np.float32([k2[a.trainIdx].pt for a in good]) + np.float32([x0, y0])
    A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=6.0, maxIters=20000)
    if A is None: return None, 0, len(good)
    s = float(np.hypot(A[0, 0], A[1, 0]))
    sel = inl.ravel().astype(bool)
    if not (0.2 < s < 0.5) or sel.sum() < 12: return None, int(sel.sum()), len(good)
    H, inl2 = cv2.findHomography(src[sel], dst[sel], cv2.RANSAC, 3.0)
    return H, int(inl2.sum()), len(good)

def main():
    refs = ref_images(); out = {}
    for path in sorted(glob.glob(os.path.join(TILE_DIR, '*.jpeg'))):
        name = os.path.splitext(os.path.basename(path))[0]; side = name.split('_')[0]
        tile = load_tile(path)
        quad = name.split('_')[1]; region = REGION[MIRROR[quad] if side == 'solder' else quad]
        H, ninl, ngood = register(tile, refs[side], region)
        if H is None:
            print(f'{name}: FAILED ({ninl} inliers of {ngood} matches)'); continue
        h, w = tile.shape[:2]
        corners = cv2.perspectiveTransform(np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), H).reshape(-1, 2)
        scale = np.sqrt(abs(np.linalg.det(H[:2, :2])))
        out[name] = {'H': H.tolist(), 'inliers': ninl, 'matches': ngood, 'mirrored': side == 'solder',
                     'corners_board': corners.round(1).tolist(), 'board_px_per_tile_px': round(float(scale), 4)}
        print(f'{name}: {ninl}/{ngood} inliers, board box x {corners[:, 0].min():.0f}..{corners[:, 0].max():.0f} '
              f'y {corners[:, 1].min():.0f}..{corners[:, 1].max():.0f}, tile res x{1 / scale:.2f} of reference')
    json.dump(out, open(OUT, 'w'), indent=1)

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "sift":
    main()

# ---- pad-pattern registration (used for solder tiles, and to refine any tile) -----------------------------------
def board_points():
    import csv
    pts = [(float(r['x']), float(r['y'])) for r in csv.DictReader(open(os.path.join(ROOT, 'schematic', 'pins.tsv')), delimiter='\t')]
    vias = os.path.join(ROOT, 'schematic', 'vias.tsv')
    if os.path.exists(vias):
        pts += [(float(r['x']), float(r['y'])) for r in csv.DictReader(open(vias), delimiter='\t')]
    return np.array(pts)

def tile_pads(tile, scale=0.5):
    """Silver (solder-tinned) blob centres in full-resolution tile pixels."""
    t = cv2.resize(tile, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA).astype(int)
    mn, mx = t.min(axis=2), t.max(axis=2)
    silver = ((mn > 130) & (mx - mn < 70)).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(silver, 8)
    keep = [(cent[i] / scale) for i in range(1, n) if 30 <= stats[i, cv2.CC_STAT_AREA] <= 900
            and stats[i, cv2.CC_STAT_WIDTH] <= 45 and stats[i, cv2.CC_STAT_HEIGHT] <= 45]
    return np.array(keep)

def vote(tp, bp, scales, rots, cell=3.0, keep=1):
    cands = []
    for s in scales:
        for r in rots:
            c, si = np.cos(np.radians(r)) * s, np.sin(np.radians(r)) * s
            tt = np.stack([c * tp[:, 0] - si * tp[:, 1], si * tp[:, 0] + c * tp[:, 1]], 1)
            d = (bp[None, :, :] - tt[:, None, :]).reshape(-1, 2)
            key = np.round(d / cell).astype(np.int64)
            k = key[:, 0] * 100003 + key[:, 1]
            u, cnt = np.unique(k, return_counts=True)
            i = cnt.argmax(); sel = k == u[i]
            cands.append((int(cnt[i]), (s, r, d[sel].mean(axis=0))))
    cands.sort(key=lambda c: -c[0])
    return cands[:keep] if keep > 1 else cands[0]

def refine(H, tp, bp, tols=(12.0, 8.0, 5.0, 3.0, 3.0)):
    for tol in tols:
        proj = cv2.perspectiveTransform(tp.reshape(-1, 1, 2).astype(np.float32), H).reshape(-1, 2)
        dist = np.sqrt(((proj[:, None, :] - bp[None, :, :]) ** 2).sum(-1))
        j = dist.argmin(axis=1); dmin = dist[np.arange(len(tp)), j]
        sel = dmin < tol
        if sel.sum() < 12: return H, None, 0
        H2, inl = cv2.findHomography(tp[sel].astype(np.float32), bp[j[sel]].astype(np.float32), cv2.RANSAC, 2.5)
        if H2 is None: break
        H = H2
    proj = cv2.perspectiveTransform(tp.reshape(-1, 1, 2).astype(np.float32), H).reshape(-1, 2)
    dist = np.sqrt(((proj[:, None, :] - bp[None, :, :]) ** 2).sum(-1)).min(axis=1)
    ok = dist < 3.0
    return H, float(np.median(dist[ok])) if ok.any() else None, int(ok.sum())

def register_pads(tile, region=None):
    tp = tile_pads(tile); bp = board_points()
    if region is not None:
        x0, y0, x1, y1 = region
        bp = bp[(bp[:, 0] > x0 - 50) & (bp[:, 0] < x1 + 50) & (bp[:, 1] > y0 - 50) & (bp[:, 1] < y1 + 50)]
    best = None
    for n0, (s0, r0, t0) in vote(tp, bp, np.linspace(0.27, 0.37, 21), np.linspace(-4, 4, 17), cell=10, keep=3):
        n, (s, r, t) = vote(tp, bp, np.linspace(s0 - 0.005, s0 + 0.005, 11), np.linspace(r0 - 0.5, r0 + 0.5, 11), cell=4)
        c, si = np.cos(np.radians(r)) * s, np.sin(np.radians(r)) * s
        H0 = np.array([[c, -si, t[0]], [si, c, t[1]], [0, 0, 1.0]])
        H, med, nmatch = refine(H0, tp, board_points())
        if med is not None and (best is None or nmatch > best[2]): best = (H, med, nmatch, len(tp), n)
    return best if best else (H0, None, 0, len(tp), 0)

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'pads':
    js = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for path in sorted(glob.glob(os.path.join(TILE_DIR, '*.jpeg'))):
        name = os.path.splitext(os.path.basename(path))[0]; side, quad = name.split('_')
        if len(sys.argv) > 2 and name not in sys.argv[2:]: continue
        tile = load_tile(path)
        region = REGION[MIRROR[quad] if side == 'solder' else quad]
        H, med, nm, ntp, votes = register_pads(tile, region)
        h, w = tile.shape[:2]
        corners = cv2.perspectiveTransform(np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), H).reshape(-1, 2)
        print(f'{name}: {ntp} tile pads, vote {votes}, {nm} matched within 3 px, median residual '
              f'{med if med is None else round(med, 2)} board px; box x {corners[:, 0].min():.0f}..{corners[:, 0].max():.0f} '
              f'y {corners[:, 1].min():.0f}..{corners[:, 1].max():.0f}')
        if med is not None and nm >= 40:
            js[name] = {'H': H.tolist(), 'method': 'pads', 'matched': nm, 'median_residual_px': round(med, 2),
                        'mirrored': side == 'solder', 'corners_board': corners.round(1).tolist()}
    json.dump(js, open(OUT, 'w'), indent=1)

# ---- rendering board regions from the tiles ---------------------------------------------------------------------
_tiles_cache = {}
def tile_image(name):
    if name not in _tiles_cache:
        d = TILE_DIR
        js = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if name in js and js[name].get('dir'): d = os.path.join(ROOT, 'inputs', js[name]['dir'])
        _tiles_cache[name] = load_tile(os.path.join(d, name + '.jpeg'))
    return _tiles_cache[name]

def best_tile(side, x, y, js=None):
    """Tile of this side whose centre is closest to board point (x, y) and that contains it."""
    js = js or json.load(open(OUT)); best = None
    for name, e in js.items():
        if not name.startswith(side): continue
        c = np.array(e['corners_board']); cx, cy = c.mean(axis=0)
        if not (c[:, 0].min() + 30 < x < c[:, 0].max() - 30 and c[:, 1].min() + 30 < y < c[:, 1].max() - 30): continue
        d = (cx - x) ** 2 + (cy - y) ** 2
        if best is None or d < best[0]: best = (d, name)
    return best[1] if best else None

def render(side, box, scale=3.0, tile=None, marks=()):
    """Board region box = (x0, y0, x1, y1) rendered from a tile at `scale` output px per board px (BGR)."""
    js = json.load(open(OUT)); x0, y0, x1, y1 = box
    tile = tile or best_tile(side, (x0 + x1) / 2, (y0 + y1) / 2, js)
    H = np.array(js[tile]['H'])
    S = np.array([[scale, 0, -x0 * scale], [0, scale, -y0 * scale], [0, 0, 1.0]])
    out = cv2.warpPerspective(tile_image(tile), S @ H, (int((x1 - x0) * scale), int((y1 - y0) * scale)), flags=cv2.INTER_LANCZOS4)
    for (mx, my, lab) in marks:
        px, py = int((mx - x0) * scale), int((my - y0) * scale)
        cv2.circle(out, (px, py), 6, (255, 0, 255), 2)
        if lab: cv2.putText(out, str(lab), (px + 8, py - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)
    return out, tile

def mosaic(side, scale=3.0, size=(2031, 1485)):
    """Stitch all tiles of a side into board coordinates at `scale` px per board px; each output pixel comes
    from the tile whose (projected) centre is nearest (least distorted view)."""
    js = json.load(open(OUT)); W, Hh = int(size[0] * scale), int(size[1] * scale)
    out = np.zeros((Hh, W, 3), np.uint8); best = np.full((Hh, W), np.inf, np.float32)
    S = np.array([[scale, 0, 0], [0, scale, 0], [0, 0, 1.0]])
    yy, xx = np.mgrid[0:Hh, 0:W].astype(np.float32)
    for name, e in sorted(js.items()):
        if not name.startswith(side): continue
        H = S @ np.array(e['H']); img = tile_image(name)
        warped = cv2.warpPerspective(img, H, (W, Hh), flags=cv2.INTER_LANCZOS4)
        valid = cv2.warpPerspective(np.full(img.shape[:2], 255, np.uint8), H, (W, Hh)) > 0
        h, w = img.shape[:2]
        cx, cy = cv2.perspectiveTransform(np.float32([[[w / 2, h / 2]]]), H).reshape(2)
        d = (xx - cx) ** 2 + (yy - cy) ** 2
        if e.get('priority'): d = d * 0.05                   # preferred view (e.g. after desoldering) wins its area
        sel = valid & (d < best)
        out[sel] = warped[sel]; best[sel] = d[sel]
    return out

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'mosaic':
    for side in ('component', 'solder'):
        m = mosaic(side)
        p = os.path.join(ROOT, 'schematic', f'mosaic_{side}.jpg')
        cv2.imwrite(p, m, [cv2.IMWRITE_JPEG_QUALITY, 92]); print(p, m.shape)

# ---- component tiles: re-register on board-level features only (parts masked out) -------------------------------
REMOVED = ('U3', 'U4', 'U5')            # sockets desoldered 2026-11-08: footprints bare, copper visible to the pads

def part_mask(size=(2031, 1485), margin=22, skip=()):
    """255 = board surface (traces, vias, silkscreen), 0 = parts and their pins (raised: parallax)."""
    import parts
    m = np.full((size[1], size[0]), 255, np.uint8)
    pp = parts.pins(); byref = {}
    for (ref, pin), (x, y) in pp.items(): byref.setdefault(ref, []).append((x, y))
    for ref, pts in byref.items():
        if ref in skip: continue
        a = np.array(pts); x0, y0 = a.min(axis=0) - margin; x1, y1 = a.max(axis=0) + margin
        if ref.startswith('DC') or ref.startswith('C') or ref in ('R1', 'R2', 'R3', 'D1', 'F1'): pad = 10
        else: pad = 0
        cv2.rectangle(m, (int(x0 - pad), int(y0 - pad)), (int(x1 + pad), int(y1 + pad)), 0, -1)
    m[1340:, :] = 0                                     # edge fingers: repetitive
    return m

def register_masked(name, H0, ref, scale=SCALE):
    tile = tile_image(name)
    pm = part_mask()
    # tile mask = board mask pulled back into tile pixels through H0
    Hinv = np.linalg.inv(H0)
    tm = cv2.warpPerspective(pm, Hinv, (tile.shape[1], tile.shape[0]), flags=cv2.INTER_NEAREST)
    t = cv2.resize(tile, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    tm_s = cv2.resize(tm, (t.shape[1], t.shape[0]), interpolation=cv2.INTER_NEAREST)
    sift = cv2.SIFT_create(nfeatures=30000)
    clahe = cv2.createCLAHE(2.0, (8, 8))
    g1 = clahe.apply(cv2.cvtColor(t, cv2.COLOR_BGR2GRAY)); g2 = clahe.apply(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY))
    k1, d1 = sift.detectAndCompute(g1, tm_s); k2, d2 = sift.detectAndCompute(g2, pm)
    m = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
    good = [a for a, b in m if a.distance < 0.8 * b.distance]
    src = np.float32([k1[a.queryIdx].pt for a in good]) / scale
    dst = np.float32([k2[a.trainIdx].pt for a in good])
    # keep matches consistent with the prior (within 25 board px), then fit
    pred = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H0).reshape(-1, 2)
    near = np.hypot(*(pred - dst).T) < 25
    H, inl = cv2.findHomography(src[near], dst[near], cv2.RANSAC, 2.5)
    return H, int(inl.sum()) if inl is not None else 0, int(near.sum())

def overlap_check(side, step=40):
    """Median disagreement (board px) between every pair of overlapping tiles of a side, on board points."""
    js = json.load(open(OUT)); names = sorted(n for n in js if n.startswith(side))
    res = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            Ha, Hb = np.array(js[a]['H']), np.array(js[b]['H'])
            ca, cb = np.array(js[a]['corners_board']), np.array(js[b]['corners_board'])
            x0, x1 = max(ca[:, 0].min(), cb[:, 0].min(), 0) + 20, min(ca[:, 0].max(), cb[:, 0].max(), 2031) - 20
            y0, y1 = max(ca[:, 1].min(), cb[:, 1].min(), 0) + 20, min(ca[:, 1].max(), cb[:, 1].max(), 1485) - 20
            if x1 - x0 < 60 or y1 - y0 < 60: continue
            pts = np.float32([[x, y] for x in np.arange(x0, x1, step) for y in np.arange(y0, y1, step)])
            # board -> tile a -> board via b: compare tile-a pixel with tile-b pixel mapped from the same board point
            ta = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), np.linalg.inv(Ha))
            tb = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), np.linalg.inv(Hb))
            res[(a, b)] = (ta, tb, pts)
    return res

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'masked':
    js = json.load(open(OUT)); refs = ref_images()
    for name in sorted(n for n in js if n.startswith('component')):
        H0 = np.array(js[name]['H'])
        H, ninl, nnear = register_masked(name, H0, refs['component'])
        if H is None or ninl < 30: print(name, 'masked registration failed', ninl, nnear); continue
        h, w = tile_image(name).shape[:2]
        corners = cv2.perspectiveTransform(np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), H).reshape(-1, 2)
        shift = np.abs(corners - np.array(js[name]['corners_board'])).max()
        js[name] = {'H': H.tolist(), 'method': 'sift-masked', 'inliers': ninl, 'mirrored': False,
                    'corners_board': corners.round(1).tolist()}
        print(f'{name}: {ninl} inliers of {nnear} board-level matches; corners moved up to {shift:.1f} board px')
    json.dump(js, open(OUT, 'w'), indent=1)

def register_to_neighbor(name, neighbor, js, scale=0.4):
    """board <- tile via an already registered neighbouring tile of the same side (same card, same light)."""
    a, b = tile_image(name), tile_image(neighbor)
    sift = cv2.SIFT_create(nfeatures=30000); clahe = cv2.createCLAHE(2.0, (8, 8))
    ga = clahe.apply(cv2.cvtColor(cv2.resize(a, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY))
    gb = clahe.apply(cv2.cvtColor(cv2.resize(b, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY))
    mask_b = None
    if name.startswith('component'):                 # board-level features only in the neighbour (raised parts masked)
        Hb = np.array(js[neighbor]['H'])
        mb = cv2.warpPerspective(part_mask(), np.linalg.inv(Hb), (b.shape[1], b.shape[0]), flags=cv2.INTER_NEAREST)
        mask_b = cv2.resize(mb, (gb.shape[1], gb.shape[0]), interpolation=cv2.INTER_NEAREST)
    k1, d1 = sift.detectAndCompute(ga, None); k2, d2 = sift.detectAndCompute(gb, mask_b)
    m = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2)
    good = [p for p, q in m if p.distance < 0.75 * q.distance]
    src = np.float32([k1[p.queryIdx].pt for p in good]) / scale
    dst = np.float32([k2[p.trainIdx].pt for p in good]) / scale
    Hab, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0, maxIters=20000)
    return np.array(js[neighbor]['H']) @ Hab, int(inl.sum()), len(good)

if __name__ == '__main__' and len(sys.argv) > 2 and sys.argv[1] == 'neighbor':
    js = json.load(open(OUT)); name, neighbor = sys.argv[2], sys.argv[3]
    H, ninl, ngood = register_to_neighbor(name, neighbor, js)
    h, w = tile_image(name).shape[:2]
    corners = cv2.perspectiveTransform(np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), H).reshape(-1, 2)
    print(f'{name} via {neighbor}: {ninl}/{ngood} inliers; corners moved up to '
          f'{np.abs(corners - np.array(js[name]["corners_board"])).max():.1f} board px')
    js[name] = {'H': H.tolist(), 'method': f'neighbor:{neighbor}', 'inliers': ninl, 'mirrored': name.startswith('solder'),
                'corners_board': corners.round(1).tolist()}
    json.dump(js, open(OUT, 'w'), indent=1)

# ---- refine a tile on vias (board-level anchors with known positions) -------------------------------------------
def via_template(scale_px):
    """Ring template (green channel): bright annulus, dark centre; scale_px = tile px per board px."""
    r_out, r_in = 7.5 * scale_px, 3.2 * scale_px; n = int(r_out * 2 + 9) | 1
    yy, xx = np.mgrid[0:n, 0:n] - n // 2; d = np.hypot(xx, yy)
    t = np.full((n, n), 0.0, np.float32); t[d <= r_out] = 1.0; t[d <= r_in] = -1.0; t[d > r_out + 3] = 0.0
    return t

def refine_on_vias(name, js, search=14, min_score=0.45):
    import csv
    vias = np.array([(float(r['x']), float(r['y'])) for r in csv.DictReader(open(os.path.join(ROOT, 'schematic', 'vias.tsv')), delimiter='\t')])
    H = np.array(js[name]['H']); Hinv = np.linalg.inv(H)
    img = tile_image(name); g = img[..., 1].astype(np.float32)
    h, w = g.shape
    sc = 1.0 / np.sqrt(abs(np.linalg.det(H[:2, :2])))            # tile px per board px
    tpl = via_template(sc); half = tpl.shape[0] // 2; win = int(search * sc)
    pred = cv2.perspectiveTransform(vias.reshape(-1, 1, 2).astype(np.float32), Hinv).reshape(-1, 2)
    src, dst = [], []
    for (px, py), bv in zip(pred, vias):
        x0, y0 = int(px) - win - half, int(py) - win - half
        x1, y1 = int(px) + win + half + 1, int(py) + win + half + 1
        if x0 < 0 or y0 < 0 or x1 > w or y1 > h: continue
        patch = g[y0:y1, x0:x1]
        res = cv2.matchTemplate(patch, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx < min_score: continue
        src.append((x0 + loc[0] + half, y0 + loc[1] + half)); dst.append(bv)
    if len(src) < 15: return None, len(src), None
    src, dst = np.float32(src), np.float32(dst)
    H2, inl = cv2.findHomography(src, dst, cv2.RANSAC, 2.0)
    sel = inl.ravel().astype(bool)
    proj = cv2.perspectiveTransform(src[sel].reshape(-1, 1, 2), H2).reshape(-1, 2)
    resid = float(np.median(np.hypot(*(proj - dst[sel]).T)))
    return H2, int(sel.sum()), resid

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'vias':
    js = json.load(open(OUT))
    for name in sys.argv[2:] or sorted(n for n in js if n.startswith('component')):
        H2, n, resid = refine_on_vias(name, js)
        if H2 is None: print(name, 'too few vias found:', n); continue
        h, w = tile_image(name).shape[:2]
        corners = cv2.perspectiveTransform(np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), H2).reshape(-1, 2)
        # how far the previous registration was off, at the vias' own positions
        print(f'{name}: {n} vias, median residual {resid:.2f} board px; corners moved up to '
              f'{np.abs(corners - np.array(js[name]["corners_board"])).max():.1f}')
        js[name] = dict(js[name], H=H2.tolist(), method=js[name].get('method', '') + '+vias', vias=n,
                        median_residual_px=round(resid, 2), corners_board=corners.round(1).tolist())
    json.dump(js, open(OUT, 'w'), indent=1)
