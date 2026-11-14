#!/usr/bin/env python3
"""Continuity checklist for the GAL sockets (U3, U4, U5), from the two-sided photo connectivity.

Component-side copper pieces (no pad bands) are joined with solder-side pieces at pads and vias. For each GAL,
a strip just outside each socket edge is examined: a trace reaching it at a pin's height connects to that pin
(CONFIRM item); a trace reaching it between two pins runs under the socket (HIDDEN item): it most likely ends on
the far-column pin of one of the two adjacent rows, else on one of the two near pins. Traces running along the
strip (vertical) are ignored. Solder-side pad-to-pad links are CONFIRM items too.
Output: schematic/continuity/gal_checklist.tsv (result columns to fill: beep = y/n)."""
import collections, csv, os, sys
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solder_nets as sn, tiles, parts
SC = sn.SC
GALS = ('U3', 'U4', 'U5')

def component_pieces(thr=30, teal=35, pad_r=10, via_r=5):
    m = cv2.imread(os.path.join(sn.ROOT, 'schematic', 'mosaic_component.jpg'))
    g, r = m[..., 1].astype(int), m[..., 2].astype(int)
    cu = sn.copper('component', thr) & ((g - r) > teal)
    pm = cv2.resize(tiles.part_mask(margin=6), (m.shape[1], m.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    raw = (cu & pm).astype(np.uint8)
    pins, vias = sn.load_points()
    for (x, y) in vias.values(): cv2.circle(raw, (int(x * SC), int(y * SC)), int(via_r * SC), 1, -1)
    for (x, y) in pins.values(): cv2.circle(raw, (int(x * SC), int(y * SC)), int(pad_r * SC), 1, -1)
    n, lab = cv2.connectedComponents(raw, connectivity=8)
    return lab

def build():
    ls, pins, vias = sn.solder_labels()
    lc = component_pieces()
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b): parent[find(a)] = find(b)
    pts = {('pin',) + k: p for k, p in pins.items()}; pts.update({('via', k): p for k, p in vias.items()})
    for key, (x, y) in pts.items():
        X, Y = int(x * SC), int(y * SC)
        if ls[Y, X]: union(key, ('s', int(ls[Y, X])))
        if lc[Y, X]: union(key, ('c', int(lc[Y, X])))
    members = collections.defaultdict(list)
    for key in pts: members[find(key)].append(key)
    return ls, lc, pins, vias, find, members

def net_pins(root, members, exclude_ref):
    return sorted(f'{k[1]}.{k[2]}' for k in members.get(root, []) if k[0] == 'pin' and k[1] != exclude_ref)

def edge_entries(lc, pins, ref, inner=16, outer=34):
    n, xr, xl, yb, yt = parts.DIPS[ref]
    h = n // 2
    rows = {'R': [(p, pins[(ref, p)][1]) for p in range(1, h + 1)], 'L': [(p, pins[(ref, p)][1]) for p in range(h + 1, n + 1)]}
    far = {'R': 'L', 'L': 'R'}
    out = []
    for side, xs in (('R', (xr + inner, xr + outer)), ('L', (xl - outer, xl - inner))):
        y0, y1 = min(yt, yb) - 20, max(yt, yb) + 20
        sub = lc[int(y0 * SC):int(y1 * SC), int(xs[0] * SC):int(xs[1] * SC)]
        for l in np.unique(sub):
            if l == 0: continue
            ys = (np.nonzero(sub == l)[0] / SC) + y0
            if ys.max() - ys.min() > 22: continue                     # runs along the edge: not entering
            ye = float(np.median(ys))
            near = min(rows[side], key=lambda pr: abs(pr[1] - ye)); dy = ye - near[1]
            if abs(dy) <= 6:
                out.append(('direct', side, int(l), ye, [near[0]], []))
            elif abs(dy) <= 21:
                a = near[0]; ya = near[1]
                # the other adjacent near-column pin (above or below)
                other = min((pr for pr in rows[side] if pr[0] != a), key=lambda pr: abs(pr[1] - (ya + 2 * dy)))
                nb = [a, other[0]]
                farpins = [min(rows[far[side]], key=lambda pr: abs(pr[1] - pins[(ref, p)][1]))[0] for p in nb]
                out.append(('hidden', side, int(l), ye, nb, farpins))
    return out

def main():
    ls, lc, pins, vias, find, members = build()
    items = []
    for ref in GALS:
        # solder-side pad-to-pad links and full nets of each pin (photo): CONFIRM
        for p in range(1, 21):
            root = find(('pin', ref, p))
            for other in net_pins(root, members, ref):
                items.append((ref, p, other, 'CONFIRM', 'photo: same copper (pads/vias joined)'))
            same = [k for k in members.get(root, []) if k[0] == 'pin' and k[1] == ref and k[2] != p]
            for k in same:
                if k[2] > p: items.append((ref, p, f'{ref}.{k[2]}', 'CONFIRM', 'photo: two pins of the same GAL joined'))
        for kind, side, l, ye, near, far in edge_entries(lc, pins, ref):
            root = find(('c', l)); dest = net_pins(root, members, ref)
            nv = sum(1 for k in members.get(root, []) if k[0] == 'via')
            if not dest: dest_txt = f'(trace goes to {nv} via(s), no pin found: probe the via)' if nv else '(no destination found)'
            if kind == 'direct':
                pin = near[0]
                for d in dest:
                    if not any(it[0] == ref and it[1] == pin and it[2] == d for it in items):
                        items.append((ref, pin, d, 'CONFIRM', f'photo: trace at the {side} socket edge at pin {pin} height'))
                if not dest: items.append((ref, pin, '?', 'FIND', f'trace at pin {pin} height, {dest_txt}'))
            else:
                cands = far + near
                for d in dest or ['?']:
                    for c in cands:
                        items.append((ref, c, d, 'HIDDEN', f'trace enters the {side} edge between pins {near[0]} and {near[1]} '
                                      f'(y {ye:.0f}); candidates far {far}, near {near}' + ('' if dest else f'; {dest_txt}')))
    os.makedirs(os.path.join(sn.ROOT, 'schematic', 'continuity'), exist_ok=True)
    out = os.path.join(sn.ROOT, 'schematic', 'continuity', 'gal_checklist.tsv')
    with open(out, 'w') as f:
        f.write('id\tgal_hole\tprobe_to\ttype\treason\tbeep\tnote\n')
        for i, (ref, p, d, t, why) in enumerate(items):
            f.write(f'C{i + 1:03d}\t{ref}.{p}\t{d}\t{t}\t{why}\t\t\n')
    print(out, len(items), 'items:', dict(collections.Counter(t for *_, t, _ in items)))
    covered = collections.defaultdict(set)
    for ref, p, d, t, why in items: covered[ref].add(p)
    for ref in GALS: print(ref, 'pins with no item:', [p for p in range(1, 21) if p not in covered[ref]])

if __name__ == '__main__':
    main()
