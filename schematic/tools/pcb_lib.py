#!/usr/bin/env python3
"""Footprint library for the AdSCSI 2000 clone (schematic/kicad/adscsi.pretty), built with KiCad's pcbnew API.
Run with the system python that has pcbnew (KiCad 10). Pad patterns follow the original board (photo + calipers);
pin 1 of every footprint is at the footprint origin (the Zorro edge: finger of pin 100, at the card edge).

Kept generic and data-driven so the compact SMD version can reuse the same mechanism.
"""
import os, sys
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MM = pcbnew.FromMM
def V(x, y): return pcbnew.VECTOR2I(MM(x), MM(y))

def _pad(fp, num, x, y, shape='circle', size=1.6, drill=0.8, kind='pth', layer=None, h=None):
    p = pcbnew.PAD(fp)
    p.SetNumber(str(num))
    sx, sy = (size, h if h else size) if not isinstance(size, tuple) else size
    p.SetSize(V(sx, sy))
    p.SetShape({'circle': pcbnew.PAD_SHAPE_CIRCLE, 'rect': pcbnew.PAD_SHAPE_RECT, 'oval': pcbnew.PAD_SHAPE_OVAL,
                'roundrect': pcbnew.PAD_SHAPE_ROUNDRECT}[shape])
    if kind == 'pth':
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH); p.SetDrillSize(V(drill, drill)); p.SetLayerSet(pcbnew.PAD.PTHMask())
    elif kind == 'npth':
        p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH); p.SetDrillSize(V(drill, drill)); p.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
    elif kind == 'finger':                       # edge-connector finger: copper + mask on one side, no paste
        p.SetAttribute(pcbnew.PAD_ATTRIB_CONN)
        ls = pcbnew.LSET(); ls.AddLayer(layer); ls.AddLayer(pcbnew.F_Mask if layer == pcbnew.F_Cu else pcbnew.B_Mask)
        p.SetLayerSet(ls)
    p.SetFPRelativePosition(V(x, y))
    fp.Add(p)
    return p

def _line(fp, x1, y1, x2, y2, layer=pcbnew.F_SilkS, w=0.12):
    s = pcbnew.PCB_SHAPE(fp); s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(V(x1, y1)); s.SetEnd(V(x2, y2)); s.SetLayer(layer); s.SetWidth(MM(w)); fp.Add(s)

def _rect(fp, x1, y1, x2, y2, layer=pcbnew.F_SilkS, w=0.12):
    for a in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)): _line(fp, *a, layer=layer, w=w)

def _circle(fp, cx, cy, r, layer=pcbnew.F_SilkS, w=0.12):
    s = pcbnew.PCB_SHAPE(fp); s.SetShape(pcbnew.SHAPE_T_CIRCLE)
    s.SetCenter(V(cx, cy)); s.SetEnd(V(cx + r, cy)); s.SetLayer(layer); s.SetWidth(MM(w)); fp.Add(s)

def _box(fp, x1, y1, x2, y2, silk=True, margin=0.25):
    """Fab outline, courtyard (+margin, 0.05 grid) and optional silk outline."""
    _rect(fp, x1, y1, x2, y2, pcbnew.F_Fab, 0.1)
    c = lambda v, s: round((v + s * margin) * 20) / 20
    _rect(fp, c(x1, -1), c(y1, -1), c(x2, 1), c(y2, 1), pcbnew.F_CrtYd, 0.05)
    if silk: _rect(fp, x1 - 0.11, y1 - 0.11, x2 + 0.11, y2 + 0.11)

def _new(name, desc):
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('adscsi', name)); fp.SetLibDescription(desc)
    fp.Reference().SetPosition(V(0, -2.5)); fp.Reference().SetLayer(pcbnew.F_SilkS)
    fp.Value().SetLayer(pcbnew.F_Fab)
    fp.SetAttributes(pcbnew.FP_THROUGH_HOLE)
    return fp

# ---- footprints ------------------------------------------------------------------------------------------------
def dip(n, w, socket=False):
    name = f'DIP-{n}_W{w:.2f}mm' + ('_Socket' if socket else '')
    fp = _new(name, f'{n}-pin DIP, {w} mm row spacing' + (', socketed' if socket else ''))
    h = n // 2
    for i in range(h):
        _pad(fp, i + 1, 0, i * 2.54, 'rect' if i == 0 else 'oval', (1.6, 1.6))
        _pad(fp, n - i, w, i * 2.54, 'oval', (1.6, 1.6))
    L = (h - 1) * 2.54
    if socket: _box(fp, -1.27, -1.33, w + 1.27, L + 1.33)
    else:
        _rect(fp, 0.635, -1.27, w - 0.635, L + 1.27, pcbnew.F_Fab, 0.1)
        _box(fp, -1.0, -1.33, w + 1.0, L + 1.33, silk=False)
        _rect(fp, 0.9, -1.33, w - 0.9, L + 1.33)
    _line(fp, w / 2 - 1.0, -1.33, w / 2, -0.4); _line(fp, w / 2, -0.4, w / 2 + 1.0, -1.33)   # notch mark at pin-1 end
    return fp

def sip(n, name=None):
    fp = _new(name or f'SIP-{n}_P2.54mm', f'{n}-pin SIP (resistor network), pin 1 = common')
    for i in range(n): _pad(fp, i + 1, i * 2.54, 0, 'rect' if i == 0 else 'oval', (1.6, 1.8))
    _box(fp, -1.29, -1.0, (n - 1) * 2.54 + 1.29, 1.0, margin=0.2)   # thin: RP1/RP2 stand 2.54 mm apart on the original
    _line(fp, 1.27, -1.11, 1.27, -0.95); _line(fp, 1.27, 0.95, 1.27, 1.11)   # pin-1 segment marks
    return fp

def header(rows, cols, name, desc, box=False, drill=1.0, pad=1.7):
    """rows x cols on 2.54 mm; pin numbering row-major (2xN: 1,2 on the first row)."""
    fp = _new(name, desc)
    for r in range(rows):
        for c in range(cols):
            k = r * cols + c + 1
            _pad(fp, k, c * 2.54, r * 2.54, 'rect' if k == 1 else 'oval', (pad, pad), drill)
    x2, y2 = (cols - 1) * 2.54, (rows - 1) * 2.54
    if box:                                       # shrouded IDC header: 8.9 mm wide, 7.62 mm longer than the pins
        cx = x2 / 2
        _box(fp, cx - 4.45, -3.81, cx + 4.45, y2 + 3.81)
        _line(fp, cx + 4.45, y2 / 2 - 2.25, cx + 3.55, y2 / 2 - 2.25)   # key slot on the even-pin side
        _line(fp, cx + 3.55, y2 / 2 - 2.25, cx + 3.55, y2 / 2 + 2.25)
        _line(fp, cx + 3.55, y2 / 2 + 2.25, cx + 4.45, y2 / 2 + 2.25)
    else:
        _box(fp, -1.27, -1.27, x2 + 1.27, y2 + 1.27)
    return fp

def header_cols(rows, name, desc, drill=1.0, pad=1.7):
    """2 x rows, column-numbered: 1..rows down the first column, rows+1..2*rows down the second (k+rows opposite k)."""
    fp = _new(name, desc)
    for r in range(rows):
        _pad(fp, r + 1, 0, r * 2.54, 'rect' if r == 0 else 'oval', (pad, pad), drill)
        _pad(fp, rows + r + 1, 2.54, r * 2.54, 'oval', (pad, pad), drill)
    _box(fp, -1.27, -1.27, 3.81, (rows - 1) * 2.54 + 1.27)
    return fp

def axial(pitch, name, desc, drill=0.8, band=False):
    fp = _new(name, desc)
    _pad(fp, 1, 0, 0, 'rect' if band else 'circle', 1.6, drill); _pad(fp, 2, pitch, 0, 'circle', 1.6, drill)
    _box(fp, 1.5, -1.25, pitch - 1.5, 1.25)
    if band: _line(fp, 2.3, -1.25, 2.3, 1.25, w=0.3)
    return fp

def disc3(name='C_Disc_3pad_P2.54_P10.16'):
    """Original decoupling footprint: pad 1 (VCC), pads 2 and 3 (GND) at 2.54 and 10.16 mm: a 0.1" or 0.4" cap."""
    fp = _new(name, 'ceramic disc capacitor, pad 1 + pad 2 (2.54 mm) or pad 3 (10.16 mm)')
    _pad(fp, 1, 0, 0, 'rect', 1.6); _pad(fp, 2, 2.54, 0, 'circle', 1.6); _pad(fp, 3, 10.16, 0, 'circle', 1.6)
    _box(fp, -1.3, -1.6, 11.46, 1.6)
    return fp

def radial(pitch, d, name):
    fp = _new(name, f'radial electrolytic, {pitch} mm pitch, {d} mm body')
    _pad(fp, 1, 0, 0, 'rect', 1.6); _pad(fp, 2, pitch, 0, 'circle', 1.6)
    _circle(fp, pitch / 2, 0, d / 2 + 0.12); _circle(fp, pitch / 2, 0, d / 2, pcbnew.F_Fab, 0.1)
    _circle(fp, pitch / 2, 0, d / 2 + 0.4, pcbnew.F_CrtYd, 0.05)
    _line(fp, -1.6, -1.8, -0.6, -1.8); _line(fp, -1.1, -2.3, -1.1, -1.3)       # + mark
    return fp

def zorro_edge(name='Zorro2_Edge_100'):
    """Amiga Zorro II card edge, 2 x 50 fingers on 2.54 mm. Origin = pin 100 finger centre at the card edge (tip).
    Component side (F.Cu) carries the even pins, 100 at the left end down to 2; the solder side (B.Cu) the odd pins,
    99 behind 100 down to 1 behind 2 (labels "100" / "99" at that end on the original)."""
    fp = _new(name, 'Amiga Zorro II 100-pin card edge (0.1" pitch, gold fingers, bevelled)')
    fp.SetAttributes(pcbnew.FP_SMD)
    for k in range(50):
        x = k * 2.54
        _pad(fp, 100 - 2 * k, x, -3.8, 'rect', (1.78, 7.0), kind='finger', layer=pcbnew.F_Cu)
        _pad(fp, 99 - 2 * k, x, -3.8, 'rect', (1.78, 7.0), kind='finger', layer=pcbnew.B_Cu)
    _rect(fp, -1.27, -7.6, 49 * 2.54 + 1.27, 0, pcbnew.F_Fab, 0.1)
    fp.Reference().SetPosition(V(-3.0, -4.0))
    return fp

def mounting_hole(drill=3.8, pad=5.4, name=None):
    """Plated mounting hole (the original's are plated through, 3.83 mm measured, centres 3.1 mm from the top edge,
    so the ring is kept small: 0.3 mm from the edge, allowed by a rule in the .kicad_dru). No net."""
    fp = _new(name or f'MountingHole_{drill}mm_Pad{pad}', f'plated mounting hole {drill} mm, {pad} mm ring, no net')
    _pad(fp, '1', 0, 0, 'circle', pad, drill)
    _circle(fp, 0, 0, pad / 2 + 0.25, pcbnew.F_CrtYd, 0.05)
    fp.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    fp.Reference().SetVisible(False)
    return fp

from footprints import FOOTPRINT   # ref -> footprint name

def build():
    fps = [dip(20, 7.62), dip(20, 7.62, True), dip(40, 15.24, True), dip(28, 15.24, True),
           sip(6), sip(8), sip(10),
           header(25, 2, 'IDC-Box_2x25_P2.54mm', 'shrouded 2x25 header (SCSI-1 internal)', box=True),
           header(13, 2, 'IDC-Box_2x13_P2.54mm', 'shrouded 2x13 header (DB25 SCSI via IDC cable)', box=True),
           header_cols(6, 'PinHeader_2x06_P2.54mm_ColNumbered', '2x6 jumper header, pins 1-6 / 7-12 by column (J1)'),
           header(3, 1, 'PinHeader_1x03_P2.54mm', '1x3 header'),
           header(4, 1, 'DrivePower_1x04_P2.54mm', '4-pin drive power header (pitch to be confirmed on the card)'),
           axial(10.16, 'Axial_P10.16mm', 'axial resistor, 0.4" pitch'),
           axial(10.16, 'Axial_P10.16mm_D1.0', 'axial part with 1 mm drill (fuse)', drill=1.0),
           axial(10.16, 'Diode_Axial_P10.16mm', 'axial diode, 0.4" pitch, pad 1 = cathode (band)', drill=1.0, band=True),
           disc3(), radial(2.54, 5.0, 'CP_Radial_P2.54_D5.0'), zorro_edge(), mounting_hole()]
    return {fp.GetFPID().GetLibItemName().wx_str(): fp for fp in fps}

def write_library(path):
    """Write the footprints; a file is replaced only when its content changes (KiCad gives every item a fresh
    random uuid on each save, which would otherwise rewrite the whole library on every run)."""
    import re, shutil, tempfile
    os.makedirs(path, exist_ok=True)
    io = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    fps = build()
    tmp = tempfile.mkdtemp(suffix='.pretty')
    for name, fp in fps.items(): io.FootprintSave(tmp, fp)
    norm = lambda s: re.sub(r'\(uuid "[^"]*"\)', '', s)
    for fn in os.listdir(tmp):
        new, old = os.path.join(tmp, fn), os.path.join(path, fn)
        if not os.path.exists(old) or norm(open(old).read()) != norm(open(new).read()): shutil.copy(new, old)
    shutil.rmtree(tmp)
    return fps

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'adscsi.pretty'
    fps = write_library(out)
    print(f'wrote {len(fps)} footprints to {out}: {", ".join(sorted(fps))}')
