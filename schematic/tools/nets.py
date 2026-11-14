#!/usr/bin/env python3
"""Photo-derived connectivity: copper per side, joined only through pads and vias.

Component side: trace colour only (chip markings and silkscreen are white/grey and fail it), IC bodies masked out
(their traces are hidden anyway). Both sides: known pads drawn as solid discs, via holes drawn as discs too.
Vias: small non-copper holes fully enclosed by copper on the solder side, away from known pads.
Edge fingers: gold blobs below the board edge line, numbered left to right per side (P1 pin mapping later).
Output: nets_photo.tsv (net, ref, pin) plus a report of dangling component-side traces at IC bodies.
"""
import collections, csv, os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photo, parts

N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))

def dilate(mask):
    m = mask.copy()
    m[1:, :] |= mask[:-1, :]; m[:-1, :] |= mask[1:, :]; m[:, 1:] |= mask[:, :-1]; m[:, :-1] |= mask[:, 1:]
    return m

def label(mask, nb=N4):
    """Connected components (nb = N4 or N8); returns label array (0 = background) and count."""
    from collections import deque
    H, W = mask.shape; lab = np.zeros((H, W), np.int32); n = 0
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0]: continue
        n += 1; lab[y0, x0] = n; q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for dy, dx in nb:
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n; q.append((ny, nx))
    return lab, n

def disc(mask, x, y, r, val=True):
    H, W = mask.shape
    for yy in range(int(y - r), int(y + r) + 1):
        for xx in range(int(x - r), int(x + r) + 1):
            if 0 <= yy < H and 0 <= xx < W and (xx - x) ** 2 + (yy - y) ** 2 <= r * r: mask[yy, xx] = val

def ring(mask, x, y, r0, r1):
    H, W = mask.shape; tot = hit = 0
    for yy in range(int(y - r1), int(y + r1) + 1):
        for xx in range(int(x - r1), int(x + r1) + 1):
            d2 = (xx - x) ** 2 + (yy - y) ** 2
            if r0 * r0 <= d2 <= r1 * r1 and 0 <= yy < H and 0 <= xx < W: tot += 1; hit += bool(mask[yy, xx])
    return hit / max(tot, 1)

def box(a, r):
    """Mean over a (2r+1)^2 box via an integral image."""
    I = np.pad(a, ((r + 1, r), (r + 1, r)), mode='edge').cumsum(0).cumsum(1)
    k = 2 * r + 1
    return (I[k:, k:] - I[:-k, k:] - I[k:, :-k] + I[:-k, :-k]) / (k * k)

def find_vias(G, cu, pins, ring_min=85, centre_max=85, r_ring=(5, 6), r_out=11):
    """Via = dark centre, copper all the way round at radius 5-6, little copper at radius 11 (traces leaving)."""
    H, W = G.shape
    def shifted(a, dx, dy):
        out = np.full_like(a, np.nan, dtype=float)
        ys0, ys1 = max(0, -dy), min(H, H - dy); xs0, xs1 = max(0, -dx), min(W, W - dx)
        out[ys0:ys1, xs0:xs1] = a[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
        return out
    ang = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    ring = np.full(G.shape, np.inf)
    for r in r_ring:
        for a in ang:
            ring = np.fmin(ring, shifted(G, int(round(r * np.cos(a))), int(round(r * np.sin(a)))))
    centre = box(G, 1)
    outcnt = np.zeros(G.shape)
    for a in ang:
        outcnt += np.nan_to_num(shifted(cu.astype(float), int(round(r_out * np.cos(a))), int(round(r_out * np.sin(a)))))
    cand = (ring >= ring_min) & (centre <= centre_max) & (outcnt <= 4)
    score = np.where(cand, ring - centre, -1e9)
    from numpy.lib.stride_tricks import sliding_window_view
    mx = sliding_window_view(np.pad(score, 5, mode='edge'), (11, 11)).max(axis=(2, 3))
    ys, xs = np.nonzero(cand & (score >= mx))
    pxy = np.array(list(pins.values())); taken = []
    for x, y in zip(xs, ys):
        if ((pxy[:, 0] - x) ** 2 + (pxy[:, 1] - y) ** 2).min() < 14 ** 2: continue
        if any((x - a) ** 2 + (y - b) ** 2 < 100 for a, b in taken): continue
        taken.append((float(x), float(y)))
    return taken

def main(pins_tsv, outdir):
    c, s = photo.images()
    A = {'c': np.asarray(c).astype(int), 's': np.asarray(s).astype(int)}
    pins = {(r['ref'], int(r['pin'])): (float(r['x']), float(r['y'])) for r in csv.DictReader(open(pins_tsv), delimiter='\t')}
    M = {}
    for side, a in A.items():
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        trace = (g >= 92) & (r < 90) & (g > b - 10)
        if side == 's':
            silver = (np.minimum(np.minimum(r, g), b) > 120) & (a.max(axis=2) - a.min(axis=2) < 70)
            trace = trace | silver
        trace[1340:, :] = False                       # edge fingers handled separately
        M[side] = trace
    # IC bodies on the component side: between the pin columns, minus a margin
    bodies = []
    for ref, (n, xr, xl, yb, yt) in parts.DIPS.items(): bodies.append((xl + 12, yt - 25, xr - 12, yb + 25))
    bodies.append((1375, 920, 1765, 1072))            # U12 between its rows
    for (x0, y0, x1, y1) in bodies: M['c'][int(y0):int(y1), int(x0):int(x1)] = False
    # vias on the solder side: dark centre (r <= 3) inside a bright copper annulus (r 4..7), not inside wide copper
    vias = find_vias(A['s'][..., 1].astype(float), M['s'], pins)
    dip_pins = {k for k in pins if k[0] in parts.DIPS or k[0] == 'U12'}
    for side in 'cs':
        for k, (x, y) in pins.items():
            disc(M[side], x, y, 9)
            if side == 'c' and k in dip_pins:      # leads/socket hide the copper next to the pin: widen sideways
                x0, x1 = (x - 28, x + 28) if k[0] != 'U12' else (x - 5, x + 5)
                y0, y1 = (y - 5, y + 5) if k[0] != 'U12' else (y - 28, y + 28)
                M[side][int(y0):int(y1) + 1, int(x0):int(x1) + 1] = True
        for (x, y) in vias: disc(M[side], x, y, 6)
    # edge fingers: peaks of the gold column profile (50 per side expected), each finger = a strip at its peak
    fingers = {}
    for side, a in A.items():
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        gold = (r > 150) & (g > 90) & (b < 140) & (r > b + 50)
        prof = gold[1395:1455, :].sum(axis=0).astype(float)
        prof = np.convolve(prof, np.ones(7) / 7, mode='same')
        peaks = [x for x in range(3, len(prof) - 3) if prof[x] >= 25 and prof[x] == prof[x - 3:x + 4].max()]
        merged = []
        for x in peaks:
            if merged and x - merged[-1] < 15: continue
            merged.append(x)
        fingers[side] = merged
        for i, cx in enumerate(merged):
            M[side][1340:1460, cx - 4:cx + 5] = True          # finger strip up to the board-edge traces
            M[side][1300:1340, cx - 4:cx + 5] |= A[side][1300:1340, cx - 4:cx + 5, 1] >= 92
    L = {}
    for side in 'cs': L[side] = label(M[side], N8)[0]
    # union-find over (side, label)
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b): parent[find(a)] = find(b)
    for (x, y) in list(pins.values()) + vias:
        a, b = ('c', L['c'][int(y), int(x)]), ('s', L['s'][int(y), int(x)])
        if a[1] and b[1]: union(a, b)
    nodes = collections.defaultdict(list)
    for key, (x, y) in pins.items():
        for side in 'cs':
            l = L[side][int(y), int(x)]
            if l: nodes[find((side, l))].append(key); break
    for side in 'cs':
        for i, cx in enumerate(fingers[side]):
            l = L[side][1420, int(cx)]
            if l: nodes[find((side, l))].append(('P1' + side, i + 1))
    nets = [sorted(set(v)) for v in nodes.values()]
    nets.sort(key=lambda v: -len(v))
    with open(os.path.join(outdir, 'nets_photo.tsv'), 'w') as f:
        f.write('net\tref\tpin\n')
        for i, v in enumerate(nets):
            for ref, pin in v: f.write(f'N{i + 1}\t{ref}\t{pin}\n')
    print(f'{len(vias)} vias, fingers per side {[len(fingers[s]) for s in "cs"]}, {len(nets)} nets '
          f'({sum(len(v) > 1 for v in nets)} with 2+ pins)')
    for i, v in enumerate(nets[:6]): print(f'  N{i + 1}: {len(v)} pins: {v[:24]}{" ..." if len(v) > 24 else ""}')
    # sanity: 20-pin chip power pins
    where = {k: i for i, v in enumerate(nets) for k in v}
    g = {where.get((r, 10)) for r, d in parts.DIPS.items() if d[0] == 20}
    vc = {where.get((r, 20)) for r, d in parts.DIPS.items() if d[0] == 20}
    print('pin-10 nets of the 20-pin chips:', g, ' pin-20 nets:', vc, ' merged:', bool(g & vc))
    im = c.copy(); d = ImageDraw.Draw(im)
    for (x, y) in vias: d.ellipse((x - 5, y - 5, x + 5, y + 5), outline=(255, 0, 255), width=2)
    im.save(os.path.join(outdir, 'vias_overlay.jpg'), quality=85)
    np.save(os.path.join(outdir, 'lab_c.npy'), L['c']); np.save(os.path.join(outdir, 'lab_s.npy'), L['s'])

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
