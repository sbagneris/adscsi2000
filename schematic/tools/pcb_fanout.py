#!/usr/bin/env python3
"""GND fan-out of the Zorro edge (system python with pcbnew 10): each GND finger gets a stub on its own layer straight
up past the card's shoulder, ending in a via, so the GND pours of both layers reach every ground finger. Run before
autorouting (the stubs are obstacles for the signals) and again after importing the routing (idempotent: adds only
what is missing, e.g. if the session import replaced all tracks).

usage: python3 pcb_fanout.py BOARD.kicad_pcb [--holes-only] [--only 13,25]
  --only: fan out just these GND fingers (the ones the signal routing would otherwise box in)
  --pad REF.PIN:DX,DY: GND escape for any pad: stub from the pad to a via at offset (DX, DY) mm (e.g. P2.6:1.27,1.27,
  the diagonal between header pins), reserved before routing when the signals would otherwise ring the pad
  --bridges: join adjacent GND fingers on the same side with a short track across the gap near their top (as the
  original's merged ground fingers); nothing else runs in that gap, so it is always clear
  --holes-only: only the stubs from GND fingers under a GND mounting hole up into its ring (as on the original, where
  the hole ring runs into the end fingers); safe to add to an already routed board.
"""
import math, os, sys
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_gen import BOARD

MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
STUB_W, VIA_D, VIA_DRILL = 0.5, 0.8, 0.4
VIA_ABOVE_SHOULDER = 1.6          # mm: via centre above the tab's top line (fingers end ~0.1 mm below it)

def main(path, holes_only=False, only=None, bridges=False, pad_escapes=()):
    b = pcbnew.LoadBoard(path)
    gnd = b.FindNet('GND').GetNetCode()
    p1 = next(fp for fp in b.GetFootprints() if fp.GetReference() == 'P1')
    have = {(round(TOMM(t.GetPosition().x), 3), round(TOMM(t.GetPosition().y), 3)) for t in b.GetTracks()
            if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == gnd}
    added = 0
    for pad in p1.Pads():
        if pad.GetNetCode() != gnd: continue
        layer = pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        x = TOMM(pad.GetPosition().x); top = TOMM(pad.GetPosition().y) - TOMM(pad.GetSize().y) / 2
        vy = BOARD['Hs'] - VIA_ABOVE_SHOULDER
        if (round(x, 3), round(vy, 3)) in have: continue
        hole = next(((i, hx, hy) for i, (hx, hy) in enumerate(BOARD['holes']) if (x - hx) ** 2 + (vy - hy) ** 2 < 3.5 ** 2), None)
        if hole:
            i, hx, hy = hole
            if BOARD.get('hole_nets', {}).get(f'H{i + 1}') == 'GND':
                ring_bottom = hy + math.sqrt(max(0.0, 2.6 ** 2 - (x - hx) ** 2))   # inside the 5.4 mm ring
                if not any(t.GetNetCode() == gnd and t.Type() == pcbnew.PCB_TRACE_T and
                           abs(TOMM(t.GetStart().x) - x) < 0.01 and t.IsOnLayer(layer) and
                           abs(TOMM(t.GetEnd().y) - ring_bottom) < 0.01 for t in b.GetTracks()):
                    t = pcbnew.PCB_TRACK(b); t.SetLayer(layer); t.SetWidth(MM(STUB_W)); t.SetNetCode(gnd)
                    t.SetStart(pcbnew.VECTOR2I(MM(x), MM(top + 0.4))); t.SetEnd(pcbnew.VECTOR2I(MM(x), MM(ring_bottom)))
                    t.SetLocked(True); b.Add(t); added += 1
            continue
        if holes_only or bridges or pad_escapes or (only and pad.GetNumber() not in only): continue
        t = pcbnew.PCB_TRACK(b); t.SetLayer(layer); t.SetWidth(MM(STUB_W)); t.SetNetCode(gnd)
        t.SetStart(pcbnew.VECTOR2I(MM(x), MM(top + 0.4))); t.SetEnd(pcbnew.VECTOR2I(MM(x), MM(vy))); t.SetLocked(True)
        b.Add(t)
        v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(vy))); v.SetWidth(MM(VIA_D))
        v.SetDrill(MM(VIA_DRILL)); v.SetNetCode(gnd); v.SetLocked(True); b.Add(v)
        added += 1
    for spec in pad_escapes:
        ref, rest = spec.split('.', 1); pin, off = rest.split(':'); dx, dy = map(float, off.split(','))
        fp = next(f for f in b.GetFootprints() if f.GetReference() == ref)
        pad = next(p for p in fp.Pads() if p.GetNumber() == pin)
        x, y = TOMM(pad.GetPosition().x), TOMM(pad.GetPosition().y); vx, vy = x + dx, y + dy
        if (round(vx, 3), round(vy, 3)) in have: continue
        t = pcbnew.PCB_TRACK(b); t.SetLayer(pcbnew.F_Cu); t.SetWidth(MM(0.4)); t.SetNetCode(gnd); t.SetLocked(True)
        t.SetStart(pad.GetPosition()); t.SetEnd(pcbnew.VECTOR2I(MM(vx), MM(vy))); b.Add(t)
        v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(MM(vx), MM(vy))); v.SetWidth(MM(VIA_D))
        v.SetDrill(MM(VIA_DRILL)); v.SetNetCode(gnd); v.SetLocked(True); b.Add(v); added += 1
    if bridges:
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            g = sorted((TOMM(p.GetPosition().x), p) for p in p1.Pads() if p.GetNetCode() == gnd and p.IsOnLayer(layer))
            for (xa, pa), (xb, pb) in zip(g, g[1:]):
                if abs(xb - xa - 2.54) > 0.05: continue                     # not adjacent
                y = TOMM(pa.GetPosition().y) - TOMM(pa.GetSize().y) / 2 + 1.0  # 1 mm below the finger tops
                if any(t.GetNetCode() == gnd and t.Type() == pcbnew.PCB_TRACE_T and t.IsOnLayer(layer) and
                       abs(TOMM(t.GetStart().y) - y) < 0.01 and abs(TOMM(t.GetStart().x) - xa) < 0.01 for t in b.GetTracks()):
                    continue
                t = pcbnew.PCB_TRACK(b); t.SetLayer(layer); t.SetWidth(MM(STUB_W)); t.SetNetCode(gnd); t.SetLocked(True)
                t.SetStart(pcbnew.VECTOR2I(MM(xa), MM(y))); t.SetEnd(pcbnew.VECTOR2I(MM(xb), MM(y))); b.Add(t); added += 1
    b.Save(path)
    print(f'GND fan-out: {added} finger stubs/bridges added')

if __name__ == '__main__':
    only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
    pads = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--pad']
    main(sys.argv[1], '--holes-only' in sys.argv, only, '--bridges' in sys.argv, pads)
