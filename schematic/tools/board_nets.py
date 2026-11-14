#!/usr/bin/env python3
"""Two-sided connectivity from the mosaics: solder pieces (solder_nets.py) + component pieces, joined only at
pads and vias (union-find). Component side: copper brighter than the local substrate AND teal (G well above R:
excludes white silkscreen and silver pins), parts masked out; each DIP pad gets a thin horizontal band where
traces run in under the socket/package edge.
usage: python3 board_nets.py U3 U4 U5     (prints each pin's net)"""
import collections, os, sys
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solder_nets as sn, tiles, parts
SC = sn.SC

def bridge_silkscreen(m, cu, k=9):
    """Traces crossing white silkscreen lines are cut in the copper mask: close small gaps, but only inside a
    narrow zone around the silkscreen, so traces cross the line without being joined along it."""
    b, g, r = (m[..., i].astype(int) for i in range(3))
    silk = ((r > 165) & (g > 165) & (b > 165)).astype(np.uint8)
    zone = cv2.dilate(silk, np.ones((5, 5), np.uint8)) > 0
    closed = cv2.morphologyEx(cu.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
    return cu | (closed & zone)

def component_labels(thr=30, teal=35, band=(42, 5), pad_r=10, via_r=5):
    m = cv2.imread(os.path.join(sn.ROOT, 'schematic', 'mosaic_component.jpg'))
    g, r = m[..., 1].astype(int), m[..., 2].astype(int)
    cu = sn.copper('component', thr) & ((g - r) > teal)
    pm = cv2.resize(tiles.part_mask(margin=6, skip=tiles.REMOVED), (m.shape[1], m.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    cu = bridge_silkscreen(m, cu)
    cu &= pm
    cu = cu.astype(np.uint8)
    pins, vias = sn.load_points()
    dips = set(parts.DIPS) | {'U12'}
    for (ref, pin), (x, y) in pins.items():
        cv2.circle(cu, (int(x * SC), int(y * SC)), int(pad_r * SC), 1, -1)
        if ref in dips and ref not in tiles.REMOVED:   # outward only: inward runs under the package (not resolvable here)
            L, W = band
            if ref == 'U12':
                y0, y1 = (y, y + L) if pin <= 14 else (y - L, y)          # bottom row down, top row up
                rect = (x - W, y0, x + W, y1)
            else:
                n = parts.DIPS[ref][0]
                x0, x1 = (x, x + L) if pin <= n // 2 else (x - L, x)     # right column right, left column left
                rect = (x0, y - W, x1, y + W)
            cv2.rectangle(cu, (int(rect[0] * SC), int(rect[1] * SC)), (int(rect[2] * SC), int(rect[3] * SC)), 1, -1)
    for (x, y) in vias.values(): cv2.circle(cu, (int(x * SC), int(y * SC)), int(via_r * SC), 1, -1)
    n, lab = cv2.connectedComponents(cu, connectivity=8)
    return lab

def nets():
    ls, pins, vias = sn.solder_labels()
    lc = component_labels()
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b): parent[find(a)] = find(b)
    pts = {('pin',) + k: p for k, p in pins.items()}; pts.update({('via', k): p for k, p in vias.items()})
    for key, (x, y) in pts.items():
        X, Y = int(x * SC), int(y * SC)
        a, b = ('s', int(ls[Y, X])), ('c', int(lc[Y, X]))
        union(('pt',) + key, a); union(('pt',) + key, b)
    groups = collections.defaultdict(list)
    for key in pts: groups[find(('pt',) + key)].append(key)
    return groups, pins, vias

if __name__ == '__main__':
    groups, pins, vias = nets()
    where = {k: g for g, ks in groups.items() for k in ks}
    sizes = sorted(((sum(1 for k in ks if k[0] == 'pin'), g) for g, ks in groups.items()), reverse=True)
    print('largest nets (pins):', [s for s, _ in sizes[:8]])
    for ref in sys.argv[1:] or ['U3', 'U4', 'U5']:
        for pin in range(1, 21):
            g = where[('pin', ref, pin)]
            others = sorted(f'{k[1]}.{k[2]}' for k in groups[g] if k[0] == 'pin' and (k[1], k[2]) != (ref, pin))
            nv = sum(1 for k in groups[g] if k[0] == 'via')
            print(f'{ref}.{pin:<3} {len(others):3d} pins, {nv:2d} vias: {" ".join(others[:16])}{" ..." if len(others) > 16 else ""}')
