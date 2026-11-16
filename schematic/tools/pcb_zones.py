#!/usr/bin/env python3
"""GND pours on both layers of the clone PCB (main card area, not the finger tab), then fill.
usage: python3 pcb_zones.py BOARD.kicad_pcb   (system python with pcbnew). If GND zones exist they are only refilled
(removing zones through the Python API breaks pcbnew's SWIG types on this install: regenerate the board instead)."""
import sys, pcbnew
MM = pcbnew.FromMM
b = pcbnew.LoadBoard(sys.argv[1])
if any(z.GetNetname() == 'GND' for z in b.Zones()):
    pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(sys.argv[1]); print('GND zones refilled'); sys.exit(0)
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_gen import BOARD                      # same outline numbers the board was generated from (scan + calipers)
W, shoulder = BOARD['W'], BOARD['Hs']          # the pour stops at the shoulder: no copper fill on the finger tab
gnd = b.FindNet('GND')
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNet(gnd); z.SetZoneName(f'GND {b.GetLayerName(layer)}')
    o = z.Outline(); o.NewOutline()
    # 0.7 mm into the finger tab: the pour reaches the top of the Zorro GND fingers (they end 0.1 mm below the
    # shoulder line), as the ground copper does on the original; other fingers keep the pour clearance
    for x, y in [(0, 0), (W, 0), (W, shoulder + 0.7), (BOARD['Tx'], shoulder + 0.7), (BOARD['Tx'], shoulder), (0, shoulder)]:
        o.Append(MM(x), MM(y))
    z.SetLocalClearance(MM(0.25)); z.SetMinThickness(MM(0.25))
    z.SetThermalReliefGap(MM(0.4)); z.SetThermalReliefSpokeWidth(MM(0.5))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL); z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(0)
    b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(sys.argv[1])
print(f'GND pours on F.Cu and B.Cu, {W:.2f} x {shoulder:.2f} mm, filled')
