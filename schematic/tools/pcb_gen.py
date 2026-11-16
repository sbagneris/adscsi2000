#!/usr/bin/env python3
"""1:1 clone PCB of the AdSCSI 2000: board outline, mounting holes and every part at the original position, nets
from the measured netlist (netlist/merged.csv), footprints from pcb_lib.py, paths linked to the generated schematic.
Routing is done afterwards (Freerouting via Specctra DSN/SES); this script never touches tracks of an existing board.

Geometry source: the reference scan (inputs/board_component_side.jpg, 2031x1485). The scanner scaled the image
differently along its axes: 11.512 px/mm horizontally and 11.808 px/mm vertically, found as the scales that put the
41 parts (one point each) on a common 0.05" grid (coherence 0.37 against 0.04 for random points; consistent with the
Zorro finger pitch, 29.215 px = 2.54 mm by FFT, and with 30 px per 0.1" between DIP pins); the card sits rotated
0.134 deg clockwise. Part positions come
from schematic/pins.tsv (pin centres on the same scan) fitted to each footprint's pad pattern (rotation in 90 deg
steps, least squares), then snapped to a common 0.05" grid. BOARD below holds the mechanical dimensions measured
on the scan: replace them with caliper measurements of the real card (see the comments) and rerun.

usage (system python with pcbnew):  python3 pcb_gen.py OUTDIR      (writes adscsi2000.kicad_pcb, adscsi.pretty,
                                                                    fp-lib-table into OUTDIR = schematic/kicad)
"""
import csv, json, math, os, re, subprocess, sys
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcb_lib
import kicad_gen

HERE = os.path.dirname(os.path.abspath(__file__))
SX, SY, THETA = 11.512, 11.808, 0.00234           # px/mm horizontal, vertical; rotation (rad, clockwise in the scan)
CORNER_PX = (11.28, 7.92)                          # board top-left corner on the scan (fitted edge lines)
GRID = 0.635                                       # 0.025" placement grid (U2-U3 are 29 x 0.025" apart: not on 0.05")

def _px2mm_linear(x, y):
    mx, my = x / SX - CORNER_PX[0] / SX, y / SY - CORNER_PX[1] / SY
    c, s = math.cos(THETA), math.sin(THETA)
    return c * mx + s * my, -s * mx + c * my

# The scan squeezes the card's right-hand side horizontally (calipers, 2026-11-14): the left side matches the measured
# holes within 0.05 mm, but the right edge and right-hand holes read up to ~1 mm short at the top and ~0.2 mm near the
# fingers. Correction dx = (x / W) * (A + B * y / H), zero on the left, fitted below to scan points whose true x is
# known: the right edge (W = tab start + tab length) and the right-hand hole centres (3.39 mm from it, calipers).
# Tab length: 129.26 mm, the Zorro III mechanical spec (+/-0.1; Zorro II cards share the edge) and exactly the scan's
# tab; the worn original measures 129.40 with calipers, just outside the tolerance.
_W_TRUE, _HOLE_R = 44.59 + 129.26, 44.59 + 129.26 - 3.39
_FIT_PTS = [((2002.2, 100), _W_TRUE), ((2003.0, 300), _W_TRUE), ((2007.4, 1200), _W_TRUE), ((2009.0, 1440), _W_TRUE),
            ((1958.4, 48.0), _HOLE_R), ((1968.0, 1351.1), _HOLE_R), ((97.9, 44.4), 7.56), ((94.0, 1349.5), 7.56)]
def _fit_correction(H=116.85):
    rows = []
    for (px, py), xt in _FIT_PTS:
        x, y = _px2mm_linear(px, py); u = x / _W_TRUE
        rows.append((u, u * y / H, xt - x))
    s11 = sum(a * a for a, b, r in rows); s12 = sum(a * b for a, b, r in rows); s22 = sum(b * b for a, b, r in rows)
    t1 = sum(a * r for a, b, r in rows); t2 = sum(b * r for a, b, r in rows); det = s11 * s22 - s12 * s12
    return (t1 * s22 - t2 * s12) / det, (s11 * t2 - s12 * t1) / det, H
_CA, _CB, _CH = _fit_correction()

def px2mm(x, y):
    x0, y0 = _px2mm_linear(x, y)
    return x0 + (x0 / _W_TRUE) * (_CA + _CB * y0 / _CH), y0

# Mechanical dimensions in mm, origin = board top-left corner, y down. Scan values; CALIPERS should replace them.
_E = lambda pts: [px2mm(*p) for p in pts]
BOARD = dict(
    W=sum(x for x, _ in _E([(2002.2, 100), (2003.0, 300), (2007.4, 1200)])) / 3,  # overall width (right edge)
    Hs=sum(y for _, y in _E([(100, 1383.9), (300, 1384.3), (450, 1384.6)])) / 3,  # top edge to the shoulder (left of tab)
    Ht=sum(y for _, y in _E([(700, 1474.7), (1300, 1475.8), (1900, 1476.9)])) / 3,  # top edge to the finger tips
    Tx=px2mm(521.2, 1430)[0],                                                     # left edge to the start of the tab
    finger0=px2mm(558.4, 1440)[0],                                                # left edge to the pin 100 finger centre
    holes=_E([(97.9, 44.4), (1958.4, 48.0), (94.0, 1349.5), (1968.0, 1351.1)]),   # TL, TR, BL, BR centres
    hole_drill=3.8,                     # 3.83 mm measured, plated through (pcb_lib.mounting_hole)
    hole_nets={'H4': 'GND'},            # scan: H4's ring runs into the merged GND fingers 1-4 on both sides
)
OVERRIDE = os.path.join(HERE, '..', 'board_measured.json')                        # caliper values, if present
if os.path.exists(OVERRIDE): BOARD.update(json.load(open(OVERRIDE)))

TEXT = ['AdSCSI 2000 compatible  -  clone r1', 'github.com/sbagneris/adscsi2000  CERN-OHL-S-2.0']

def load_pins():
    pins = {}
    for r in csv.DictReader(open(os.path.join(HERE, '..', 'pins.tsv')), delimiter='\t'):
        pins.setdefault(r['ref'], {})[r['pin']] = px2mm(float(r['x']), float(r['y']))
    return pins

def load_nets(outdir):
    """Pad nets from the schematic itself (kicad-cli netlist export), so names match exactly (+12V, the
    unconnected-(...) single-pin nets). The schematic is checked against netlist/merged.csv by kicad_check.py."""
    net = os.path.join(outdir, '.pcb_gen.net')
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', net,
                    os.path.join(outdir, 'adscsi2000.kicad_sch')], check=True, capture_output=True)
    t = open(net).read(); t = t[t.index('(nets'):]; os.remove(net)
    nets = {}
    for block in re.split(r'\(net\s*\(code', t)[1:]:
        name = re.search(r'\(name\s+"([^"]*)"\)', block).group(1)
        for r, p in re.findall(r'\(ref\s+"([^"]+)"\)\s*\(pin\s+"([^"]+)"\)', block):
            if not r.startswith('#'): nets[(r, p)] = name
    return nets

NETCLASSES = {'Default': dict(track_width=0.25, clearance=0.2, via_diameter=0.7, via_drill=0.35),
              'Power': dict(track_width=0.5, clearance=0.2, via_diameter=0.8, via_drill=0.4)}   # card draws < 1 A
RULES = dict(min_track_width=0.127, min_clearance=0.15, min_copper_edge_clearance=0.5, min_via_diameter=0.6,
             min_through_hole_diameter=0.3, min_hole_clearance=0.25, min_hole_to_hole=0.25)   # common 2-layer fab limits
EDGE_KEEPOUT = 0.6                                     # no tracks or vias this close to the board edge (Freerouting)
POWER_NETS = ['GND', 'VCC', '+12V', 'TPWRI', 'TERMPWR']

def write_project_rules(outdir):
    pro = os.path.join(outdir, 'adscsi2000.kicad_pro'); p = json.load(open(pro))
    base = dict(microvia_diameter=0.3, microvia_drill=0.1, diff_pair_width=0.2, diff_pair_gap=0.25, diff_pair_via_gap=0.25,
                wire_width=6, bus_width=12, line_style=0, pcb_color='rgba(0, 0, 0, 0.000)', schematic_color='rgba(0, 0, 0, 0.000)')
    p['net_settings'] = dict(meta=dict(version=4), net_colors=None, netclass_assignments=None,
        classes=[dict(base, name=n, priority=(2147483647 if n == 'Default' else 0), **v) for n, v in NETCLASSES.items()],
        netclass_patterns=[dict(netclass='Power', pattern=n) for n in POWER_NETS])
    p.setdefault('board', {}).setdefault('design_settings', {})['rules'] = dict(RULES)
    # a pad whose only thermal spoke on one layer lands in a small fill fragment is still connected on the other
    # layer: report it, but as a warning
    p['board']['design_settings'].setdefault('rule_severities', {})['starved_thermal'] = 'warning'
    json.dump(p, open(pro, 'w'), indent=2)
    open(os.path.join(outdir, 'adscsi2000.kicad_dru'), 'w').write(
        '(version 1)\n'
        '(rule "Zorro edge fingers reach the card edge"\n  (condition "A.memberOfFootprint(\'P1\')")\n'
        '  (constraint edge_clearance (min 0mm)))\n'
        '(rule "Mounting hole rings (centres 3.1 mm from the edge on the original)"\n'
        '  (condition "A.memberOfFootprint(\'H*\')")\n  (constraint edge_clearance (min 0.3mm)))\n')
    # (a min_resolved_spokes rule here makes KiCad 10 ignore the whole file: starved thermals are demoted to
    #  warnings in the project's rule severities instead)

def fit(fp, meas):
    """Best orientation (0/90/180/270) and position of fp so its pads match the measured pin centres."""
    best = None
    for ang in (0, 90, 180, 270):
        fp.SetOrientationDegrees(ang); fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        rel = {p.GetNumber(): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads()}
        common = [k for k in meas if k in rel]
        if len(common) < 1: continue
        tx = sum(meas[k][0] - rel[k][0] for k in common) / len(common)
        ty = sum(meas[k][1] - rel[k][1] for k in common) / len(common)
        rms = math.sqrt(sum((meas[k][0] - rel[k][0] - tx) ** 2 + (meas[k][1] - rel[k][1] - ty) ** 2 for k in common) / len(common))
        if best is None or rms < best[0]: best = (rms, ang, tx, ty, len(common))
    return best

def grid_offset(points):
    """Common grid origin (ox, oy) minimising the snapping distance of all points (circular mean per axis)."""
    def axis(vals):
        a = sum(math.cos(2 * math.pi * v / GRID) for v in vals); b = sum(math.sin(2 * math.pi * v / GRID) for v in vals)
        return (math.atan2(b, a) / (2 * math.pi)) * GRID % GRID
    return axis([p[0] for p in points]), axis([p[1] for p in points])

def snap(v, o): return round((v - o) / GRID) * GRID + o

def main(outdir):
    libdir = os.path.join(outdir, 'adscsi.pretty')
    pcb_lib.write_library(libdir)
    io = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    board.SetCopperLayerCount(2)
    ds.SetBoardThickness(pcbnew.FromMM(1.6))

    pins, nets = load_pins(), load_nets(outdir)
    netobj = {}
    for n in sorted(set(nets.values())):
        ni = pcbnew.NETINFO_ITEM(board, n); board.Add(ni); netobj[n] = ni

    # schematic links: footprint path = /<sheet uuid>/<symbol uuid> (kicad_gen.py's deterministic uuids)
    sheet_uuid = {s: kicad_gen.uid('sheetblock', s) for s, _ in kicad_gen.SHEETS}
    report, placed = [], {}
    for ref, fpname in pcb_lib.FOOTPRINT.items():
        if ref == 'P1': continue
        fp = io.FootprintLoad(libdir, fpname); fp.SetFPID(pcbnew.LIB_ID('adscsi', fpname))
        meas = pins.get(ref, {})
        rms, ang, tx, ty, n = fit(fp, meas)
        placed[ref] = (fp, ang, tx, ty)
        report.append((ref, fpname, ang, rms, n, len(list(fp.Pads()))))
    ox, oy = grid_offset([(tx, ty) for fp, ang, tx, ty in placed.values()])
    shifts = {}
    for ref, (fp, ang, tx, ty) in placed.items():
        x, y = snap(tx, ox), snap(ty, oy); shifts[ref] = math.hypot(x - tx, y - ty)
        fp.SetOrientationDegrees(ang); fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    # Zorro edge: finger of pin 100 at the measured position, on the same grid in x, at the card edge in y
    fp = io.FootprintLoad(libdir, 'Zorro2_Edge_100'); fp.SetFPID(pcbnew.LIB_ID('adscsi', 'Zorro2_Edge_100'))
    # not snapped to the parts grid: the finger row is a mechanical feature (measured from the tab edge)
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(BOARD['finger0']), pcbnew.FromMM(BOARD['Ht'])))
    placed['P1'] = (fp, 0, 0, 0); shifts['P1'] = 0.0

    for ref, (fp, *_ ) in placed.items():
        sym = kicad_gen.PARTS[ref]
        fp.SetReference(ref); fp.SetValue(kicad_gen.VALUES[ref][0] if ref in kicad_gen.VALUES else sym[1])
        if ref in kicad_gen.VALUES:                      # same fields as the symbol (KiCad 10 parity checks them)
            fp.SetField('Function', kicad_gen.VALUES[ref][1])
            fld = fp.GetField('Function'); fld.SetVisible(False); fld.SetLayer(pcbnew.F_Fab)
        fp.SetPath(pcbnew.KIID_PATH(f'/{sheet_uuid[sym[2]]}/{kicad_gen.uid("sym", sym[2], ref)}'))
        board.Add(fp)
        for p in fp.Pads():
            n = nets.get((ref, p.GetNumber()))
            if n: p.SetNet(netobj[n])
            elif ref != 'P1': print(f'  note: {ref}.{p.GetNumber()} has no net in the schematic')
    for i, (hx, hy) in enumerate(BOARD['holes']):
        fp = io.FootprintLoad(libdir, 'MountingHole_3.8mm_Pad5.4'); fp.SetFPID(pcbnew.LIB_ID('adscsi', 'MountingHole_3.8mm_Pad5.4'))
        fp.SetReference(f'H{i + 1}'); fp.SetValue('mounting hole')
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(hx), pcbnew.FromMM(hy))); board.Add(fp)
        n = BOARD.get('hole_nets', {}).get(f'H{i + 1}')
        if n:
            for p in fp.Pads(): p.SetNet(netobj[n])

    # outline: rectangle with the edge-connector tab along the bottom, flush with the right edge
    W, Hs, Ht, Tx = BOARD['W'], BOARD['Hs'], BOARD['Ht'], BOARD['Tx']
    pts = [(0, 0), (W, 0), (W, Ht), (Tx, Ht), (Tx, Hs), (0, Hs), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1))); s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        s.SetWidth(pcbnew.FromMM(0.1)); board.Add(s)
    # keep-out ring along the outline (rule areas: no tracks, no vias; pours and pads allowed) for the autorouter
    k = EDGE_KEEPOUT
    for x1, y1, x2, y2 in [(0, 0, W, k), (0, 0, k, Hs), (W - k, 0, W, Ht), (0, Hs - k, Tx, Hs), (Tx, Hs, Tx + k, Ht),
                           (Tx, Ht - k, W, Ht)]:
        z = pcbnew.ZONE(board); z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(False); z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu); z.SetLayerSet(ls)
        o = z.Outline(); o.NewOutline()
        for x, y in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]: o.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        board.Add(z)
    for i, t in enumerate(TEXT):
        tx = pcbnew.PCB_TEXT(board); tx.SetText(t); tx.SetLayer(pcbnew.F_SilkS)
        tx.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(60), pcbnew.FromMM(Hs - 9 + i * 2.6)))
        tx.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.6 if i == 0 else 1.2), pcbnew.FromMM(1.6 if i == 0 else 1.2)))
        board.Add(tx)

    write_project_rules(outdir)
    out = os.path.join(outdir, 'adscsi2000.kicad_pcb')
    if os.path.exists(out) and '--replace-routed' not in sys.argv:
        old = pcbnew.LoadBoard(out)
        if len(old.GetTracks()):
            sys.exit(f'{out} already has {len(old.GetTracks())} tracks/vias: not overwriting routed work (--replace-routed)')
    board.Save(out)
    tbl = os.path.join(outdir, 'fp-lib-table')
    open(tbl, 'w').write('(fp_lib_table\n  (version 7)\n  (lib (name "adscsi")(type "KiCad")(uri "${KIPRJMOD}/adscsi.pretty")'
                         '(options "")(descr "AdSCSI 2000 clone footprints (generated by pcb_lib.py)"))\n)\n')
    print(f'board {W:.2f} x {Hs:.2f} mm (tips {Ht:.2f}), tab from {Tx:.2f}; fingers {BOARD["finger0"]:.2f}..'
          f'{BOARD["finger0"] + 49 * 2.54:.2f}; scan correction A {_CA:+.3f} B {_CB:+.3f} mm; grid origin ({ox:.3f}, {oy:.3f})')
    print(f'{"ref":5s} {"footprint":28s} ang  fit-rms  pins  snap')
    for ref, fpname, ang, rms, n, npads in sorted(report, key=lambda r: -r[3]):
        print(f'{ref:5s} {fpname:28s} {ang:3d}  {rms:6.3f}  {n:2d}/{npads:<2d} {shifts[ref]:5.3f}')
    print(f'P1    Zorro2_Edge_100              finger 0 snap {shifts["P1"]:.3f}')
    print('wrote', out)

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    main(args[0] if args else os.path.join(HERE, '..', 'kicad'))
