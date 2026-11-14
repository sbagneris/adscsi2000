#!/usr/bin/env python3
"""Solder-side connectivity from the solder mosaic (3 px per board px): teal copper + pad/via discs, 8-connected.
Prints, for chosen parts, each pin's solder-side piece: the other pins and the vias on it."""
import csv, os, sys
import numpy as np, cv2
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
SC = 3.0

def load_points():
    pins = {(r['ref'], int(r['pin'])): (float(r['x']), float(r['y'])) for r in csv.DictReader(open(os.path.join(ROOT, 'schematic', 'pins.tsv')), delimiter='\t')}
    vias = {r['via']: (float(r['x']), float(r['y'])) for r in csv.DictReader(open(os.path.join(ROOT, 'schematic', 'vias.tsv')), delimiter='\t')}
    return pins, vias

def copper(side='solder', thr=35):
    """Copper = clearly brighter (green channel) than the local substrate (median over ~124 px): robust to the
    lighting differences between tiles. Large fills are absorbed into the background."""
    m = cv2.imread(os.path.join(ROOT, 'schematic', f'mosaic_{side}.jpg'))
    g = m[..., 1]
    small = cv2.resize(g, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    bg = cv2.resize(cv2.medianBlur(small, 31), (g.shape[1], g.shape[0]), interpolation=cv2.INTER_LINEAR)
    d = g.astype(int) - bg.astype(int)
    gr = g.astype(int) - m[..., 2].astype(int)
    return (d > thr) | ((gr > 60) & (d > 10))      # bright, or clearly teal and somewhat brighter (shaded traces)

def solder_labels(pad_r=10, via_r=5):
    cu = copper('solder').astype(np.uint8)
    pins, vias = load_points()
    for (x, y) in pins.values(): cv2.circle(cu, (int(x * SC), int(y * SC)), int(pad_r * SC), 1, -1)
    for (x, y) in vias.values(): cv2.circle(cu, (int(x * SC), int(y * SC)), int(via_r * SC), 1, -1)
    n, lab = cv2.connectedComponents(cu, connectivity=8)
    return lab, pins, vias

def pieces(lab, pins, vias):
    at = lambda p: int(lab[int(p[1] * SC), int(p[0] * SC)])
    by = {}
    for k, p in pins.items(): by.setdefault(at(p), {'pins': [], 'vias': []})['pins'].append(k)
    for k, p in vias.items(): by.setdefault(at(p), {'pins': [], 'vias': []})['vias'].append(k)
    return by, at

if __name__ == '__main__':
    lab, pins, vias = solder_labels()
    by, at = pieces(lab, pins, vias)
    refs = sys.argv[1:] or ['U3', 'U4', 'U5']
    big = sorted(by.items(), key=lambda kv: -len(kv[1]['pins']))[:3]
    print('largest pieces:', [(len(v['pins']), len(v['vias'])) for _, v in big])
    for ref in refs:
        for pin in range(1, 21):
            l = at(pins[(ref, pin)]); e = by[l]
            others = [f'{r}.{p}' for r, p in sorted(e['pins']) if (r, p) != (ref, pin)]
            print(f'{ref}.{pin:<3} piece {l:6d}: pins {others[:12]}{" +" + str(len(others) - 12) if len(others) > 12 else ""}  vias {sorted(e["vias"])[:8]}{" +" + str(len(e["vias"]) - 8) if len(e["vias"]) > 8 else ""}')
