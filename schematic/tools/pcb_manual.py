#!/usr/bin/env python3
"""Replay hand edits made in KiCad onto a regenerated clone PCB (system python with pcbnew 10), so the build stays
reproducible: vias from schematic/kicad/manual_vias.tsv (net, x, y, diameter, drill), added only if not present,
and pad zone-connection overrides from schematic/kicad/manual_pads.tsv (pad REF.PIN, connection solid/thermal/none).
usage: python3 pcb_manual.py BOARD.kicad_pcb [manual_vias.tsv]
"""
import csv, os, sys
import pcbnew

def main(path, tsv):
    b = pcbnew.LoadBoard(path)
    have = {(round(pcbnew.ToMM(t.GetPosition().x), 3), round(pcbnew.ToMM(t.GetPosition().y), 3))
            for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T}
    rows = csv.DictReader((l for l in open(tsv) if not l.startswith('#')), delimiter='\t')
    added = 0
    for r in rows:
        x, y = float(r['x']), float(r['y'])
        if (round(x, 3), round(y, 3)) in have: continue
        v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(float(r['diameter']))); v.SetDrill(pcbnew.FromMM(float(r['drill'])))
        v.SetNetCode(b.FindNet(r['net']).GetNetCode()); v.SetLocked(True); b.Add(v); added += 1
    pads_tsv = os.path.join(os.path.dirname(tsv), 'manual_pads.tsv')
    conn = {'solid': pcbnew.ZONE_CONNECTION_FULL, 'thermal': pcbnew.ZONE_CONNECTION_THERMAL, 'none': pcbnew.ZONE_CONNECTION_NONE}
    npads = 0
    if os.path.exists(pads_tsv):
        fps = {f.GetReference(): f for f in b.GetFootprints()}
        for r in csv.DictReader((l for l in open(pads_tsv) if not l.startswith('#')), delimiter='\t'):
            ref, pin = r['pad'].split('.')
            pad = next(p for p in fps[ref].Pads() if p.GetNumber() == pin)
            pad.SetLocalZoneConnection(conn[r['connection']]); npads += 1
    pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(path)
    print(f'manual vias: {added} added; pad zone-connection overrides: {npads}')

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, '..', 'kicad', 'manual_vias.tsv'))
