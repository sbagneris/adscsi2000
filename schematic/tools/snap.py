#!/usr/bin/env python3
"""Snap predicted part pins to detected pads; report misses and leftover (unassigned) pads."""
import csv, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parts
pads = [(int(r['id']), float(r['x']), float(r['y']), int(r['area'])) for r in csv.DictReader(open(sys.argv[1]), delimiter='\t')]
pads = [p for p in pads if p[2] < 1360]                      # drop edge-finger glints
used, miss, snapped = set(), [], {}
# snap each part's pins in pin order, carrying the offset found on the previous pin (photo drift along long rows)
pp = parts.pins(); byref = {}
for (ref, pin), xy in pp.items(): byref.setdefault(ref, []).append((pin, xy))
for ref, lst in sorted(byref.items()):
    off = {}                                        # per column (rounded x) drift
    for pin, (x, y) in sorted(lst):
        col = round(x / 10); dx, dy = off.get(col, (0.0, 0.0)); px, py = x + dx, y + dy
        best = min(pads, key=lambda p: (p[1] - px) ** 2 + (p[2] - py) ** 2)
        d = math.hypot(best[1] - px, best[2] - py)
        if d <= 12 and best[0] not in used:
            used.add(best[0]); snapped[(ref, pin)] = (best[1], best[2]); off[col] = (best[1] - x, best[2] - y)
        else:
            miss.append(((ref, pin), round(px), round(py), round(d, 1)))
print(f'{len(snapped)} pins snapped, {len(miss)} missed')
for m in miss: print('  miss', m)
left = [p for p in pads if p[0] not in used]
print(f'{len(left)} pads not assigned:')
for p in sorted(left, key=lambda p: (round(p[2] / 15), p[1])): print(f'   ({p[1]:.0f}, {p[2]:.0f}) area {p[3]}')
with open(sys.argv[2], 'w') as f:
    f.write('ref\tpin\tx\ty\n')
    for (ref, pin), (x, y) in sorted(snapped.items()): f.write(f'{ref}\t{pin}\t{x:.1f}\t{y:.1f}\n')
