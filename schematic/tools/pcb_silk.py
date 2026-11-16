#!/usr/bin/env python3
"""Reference labels on the clone PCB's silkscreen (system python with pcbnew 10): each footprint's reference goes to
the first candidate spot around its outline (below first, as on the original, then above, right, left, corners;
horizontal, or vertical beside tall parts) that keeps clear of every pad (and its mask opening), every footprint's
silkscreen graphics, every label already placed and the board edge. Text only: safe on a routed board.
usage: python3 pcb_silk.py BOARD.kicad_pcb
"""
import os, sys
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_gen import BOARD

MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
SIZE, THICK, GAP, PADM = 1.0, 0.15, 0.25, 0.3      # text height/stroke, gap to the outline, clearance to pads (mm)

def box(b, m=0.0):
    return (TOMM(b.GetLeft()) - m, TOMM(b.GetTop()) - m, TOMM(b.GetRight()) + m, TOMM(b.GetBottom()) + m)

def hit(a, c): return not (a[2] <= c[0] or c[2] <= a[0] or a[3] <= c[1] or c[3] <= a[1])

def inside(bx):
    x1, y1, x2, y2 = bx; m = 0.4
    if x1 < m or y1 < m or x2 > BOARD['W'] - m: return False
    return y2 <= BOARD['Hs'] - m or (x1 >= BOARD['Tx'] + m and y2 <= BOARD['Ht'] - m)

def main(path):
    b = pcbnew.LoadBoard(path)
    fps = list(b.GetFootprints())
    pads = [box(p.GetBoundingBox(), PADM) for f in fps for p in f.Pads()]
    silk = {}
    for f in fps:
        silk[f.GetReference()] = [box(g.GetBoundingBox(), 0.1) for g in f.GraphicalItems()
                                  if g.GetLayer() == pcbnew.F_SilkS and g.Type() != pcbnew.PCB_TEXT_T]
    allsilk = [bx for v in silk.values() for bx in v]
    texts = [box(t.GetBoundingBox(), 0.2) for t in b.GetDrawings() if t.Type() == pcbnew.PCB_TEXT_T]
    placed, moved, failed = [], 0, []
    # big parts first: they have fewer good spots
    for f in sorted(fps, key=lambda f: -TOMM(f.GetBoundingBox(False).GetWidth()) * TOMM(f.GetBoundingBox(False).GetHeight())):
        ref = f.Reference(); name = f.GetReference()
        if name == 'P1' or name.startswith('H'):
            ref.SetVisible(False); continue
        ref.SetVisible(True); ref.SetLayer(pcbnew.F_SilkS)
        ref.SetTextSize(pcbnew.VECTOR2I(MM(SIZE), MM(SIZE))); ref.SetTextThickness(MM(THICK))
        own = silk[name] + [box(p.GetBoundingBox()) for p in f.Pads()]
        x1 = min(o[0] for o in own); y1 = min(o[1] for o in own); x2 = max(o[2] for o in own); y2 = max(o[3] for o in own)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        h = SIZE / 2 + GAP
        cands = [(cx, y2 + h, 0), (cx, y1 - h, 0), (x2 + h, cy, 90), (x1 - h, cy, 90),
                 (x2, y2 + h, 0), (x1, y2 + h, 0), (x2, y1 - h, 0), (x1, y1 - h, 0),
                 (x2 + h, y2 - 1.5, 90), (x1 - h, y2 - 1.5, 90), (x2 + h, y1 + 1.5, 90), (x1 - h, y1 + 1.5, 90)]
        for step in (0, 1.0, 2.0):                 # then the same spots pushed further out
            done = False
            for x, y, ang in cands:
                if step:
                    dx = step if x > cx + 0.01 else -step if x < cx - 0.01 else 0
                    dy = step if y > cy + 0.01 else -step if y < cy - 0.01 else 0
                    x, y = x + dx, y + dy
                ref.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
                ref.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
                bx = box(ref.GetBoundingBox(), 0.05)
                if inside(bx) and not any(hit(bx, o) for o in pads + allsilk + placed + texts):
                    placed.append(bx); moved += 1; done = True; break
            if done: break
        else:
            failed.append(name)
            x, y, ang = cands[0]
            ref.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T)); ref.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
            placed.append(box(ref.GetBoundingBox(), 0.05))
    labels(b, pads + allsilk + placed + texts)
    b.Save(path)
    print(f'silkscreen: {moved} references placed' + (f'; no clear spot for {failed} (left below the part)' if failed else ''))

# functional labels, as on the original: jumper meanings, connector pin functions, the edge-connector pin ends
def labels(b, blocked):
    fp = {f.GetReference(): f for f in b.GetFootprints()}
    def pad(ref, n):
        p = next(p for p in fp[ref].Pads() if p.GetNumber() == str(n)); return TOMM(p.GetPosition().x), TOMM(p.GetPosition().y)
    out, skipped = 0, []
    def add(text, x, y, just, layer=pcbnew.F_SilkS, size=0.9, ang=0, mirror=False, alt=()):
        """Place a label at (x, y, just), else at the first clear alternative (x, y, just) in alt."""
        nonlocal out
        for ax, ay, aj in [(x, y, just)] + list(alt):
            if try_add(text, ax, ay, aj, layer, size, ang, mirror, last=(ax, ay, aj) == ([(x, y, just)] + list(alt))[-1]): return
    def try_add(text, x, y, just, layer, size, ang, mirror, last):
        nonlocal out
        tx = pcbnew.PCB_TEXT(b); tx.SetText(text); tx.SetLayer(layer)
        tx.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size))); tx.SetTextThickness(MM(0.14))
        tx.SetHorizJustify({'l': pcbnew.GR_TEXT_H_ALIGN_LEFT, 'r': pcbnew.GR_TEXT_H_ALIGN_RIGHT,
                            'c': pcbnew.GR_TEXT_H_ALIGN_CENTER}[just])
        tx.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T)); tx.SetMirrored(mirror)
        tx.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        bx = box(tx.GetBoundingBox(), 0.05)
        if layer == pcbnew.F_SilkS and (not inside(bx) or any(hit(bx, o) for o in blocked)):
            if os.environ.get('SILK_DEBUG'):
                print('  ', text, [round(v, 1) for v in bx], 'inside' if inside(bx) else 'OUTSIDE',
                      [[round(v, 1) for v in o] for o in blocked if hit(bx, o)][:3])
            if last: skipped.append(text)
            return False
        b.Add(tx); blocked.append(bx); out += 1
        return True
    def outline(ref):                                    # the part's silkscreen + pads extent
        f = fp[ref]
        bs = [box(g.GetBoundingBox()) for g in f.GraphicalItems() if g.GetLayer() == pcbnew.F_SilkS and g.Type() != pcbnew.PCB_TEXT_T]
        bs += [box(p.GetBoundingBox()) for p in f.Pads()]
        return min(o[0] for o in bs), min(o[1] for o in bs), max(o[2] for o in bs), max(o[3] for o in bs)
    G = 0.5                                              # gap between a label and its part's outline
    # J1: pins 1-6 = ID0 ID1 ID2 GAME B A (column facing U7), 7-12 GND opposite; labels left of the header
    x1, y1, x2, y2 = outline('J1')
    for k, name in enumerate(['ID0', 'ID1', 'ID2', 'GAME', 'B', 'A'], 1):
        x, y = pad('J1', 6 + k); add(name, x1 - G, y, 'r')
    add('fitted = 0', (x1 + x2) / 2, y1 - G - 0.5, 'c', size=0.8)
    x1, y1, x2, y2 = outline('P4')
    add('DMA LED', (x1 + x2) / 2, y1 - G - 2.0, 'c', alt=[(x2 + G, (y1 + y2) / 2, 'l'), (x1 - G, (y1 + y2) / 2, 'r')])
    x1, y1, x2, y2 = outline('P5')
    for n, name in zip(range(1, 5), ['+12V', 'GND', 'GND', '+5V']):
        x, y = pad('P5', n); add(name, x2 + G, y, 'l', size=0.8)
    add('DRIVE PWR', (x1 + x2) / 2, y1 - G - 0.5, 'c', size=0.8)
    x, y = pad('P1', 100); add('100', x - 0.6, BOARD['Hs'] - 2.6, 'l', size=0.8)
    add('99', x - 0.6, BOARD['Hs'] - 2.6, 'r', layer=pcbnew.B_SilkS, size=0.8, mirror=True)
    x1, y1, x2, y2 = outline('P3'); add('SCSI', (x1 + x2) / 2, y1 - G - 0.6, 'c')
    x1, y1, x2, y2 = outline('P2'); add('SCSI DB25 (IDC)', (x1 + x2) / 2, y1 - G - 0.5, 'c', size=0.8)
    print(f'functional labels: {out} placed' + (f', skipped (no room): {skipped}' if skipped else ''))

if __name__ == '__main__':
    main(sys.argv[1])
