#!/usr/bin/env python3
"""Generate the AdSCSI 2000 KiCad schematic from the measured netlist (schematic/netlist/merged.csv).

Label-based: every pin gets a short wire stub and a global label named after its net (power pins get power
symbols, unconnected pins a no-connect flag). Symbols are built here from the verified pinouts (pinouts.py) into
a project-local library embedded in each sheet, so the schematic does not depend on KiCad's libraries.
Written in the KiCad 8 format (20231120); run `kicad-cli sch upgrade` afterwards for the current format.
UUIDs are derived from names: regenerating gives identical files.

usage: python3 kicad_gen.py OUTDIR      (then: kicad_check.py compares the exported netlist with merged.csv)
"""
import csv, os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from footprints import FOOTPRINT
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinouts import ZORRO2, NCR5380, EPROM27C256, LS245, LS374, F521

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PROJECT = 'adscsi2000'
LIB = 'adscsi'
G = 2.54
NS = uuid.UUID('6f1c2a50-3d1e-4b55-9a0e-0ad5c5150000')
def uid(*k): return str(uuid.uuid5(NS, '/'.join(map(str, k))))
def q(s): return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'
def f(v): return f'{v:.4f}'.rstrip('0').rstrip('.') if isinstance(v, float) else str(v)
FONT = '(effects (font (size 1.27 1.27)))'
FONT_H = '(effects (font (size 1.27 1.27)) hide)'

# ---------------------------------------------------------------------------------------------------------------
# symbols
class Sym:
    def __init__(self, name, left, right, top=(), bottom=(), ref='U', width=None, power=False, desc='', hide_names=False):
        self.name, self.ref, self.desc, self.hide_names = name, ref, desc, hide_names
        self.left, self.right, self.top, self.bottom = list(left), list(right), list(top), list(bottom)
        n = max(len(self.left), len(self.right), 1)
        longest = max([len(p[1]) for p in self.left + self.right if p] + [2])
        import math
        hw = width / 2 if width else max(2 * G, longest * 0.8 + 1.5)
        self.hw = math.ceil(round(hw / G, 6)) * G
        self.ytop = (n - 1) // 2 * G + G if n > 1 else G
        self.ybot = self.ytop - (n + 1) * G
        self.power = power
        self.pins = {}                       # number -> (x, y, angle) connection point in symbol coordinates
        for i, p in enumerate(self.left):
            if p: self.pins[p[0]] = (-self.hw - G, self.ytop - G - i * G, 0)
        for i, p in enumerate(self.right):
            if p: self.pins[p[0]] = (self.hw + G, self.ytop - G - i * G, 180)
        if self.top: self.ytop += G          # keep power pin names clear of the side pin names
        if self.bottom: self.ybot -= G
        for i, p in enumerate(self.top):
            x = (i - (len(self.top) - 1) / 2) * 2 * G
            self.pins[p[0]] = (x, self.ytop + G, 270)
        for i, p in enumerate(self.bottom):
            x = (i - (len(self.bottom) - 1) / 2) * 2 * G
            self.pins[p[0]] = (x, self.ybot - G, 90)
        self.types = {p[0]: p for p in self.left + self.right + self.top + self.bottom if p}

    def sexpr(self):
        n = self.name
        out = [f'(symbol {q(LIB + ":" + n)}' + (' (power)' if self.power else '') +
               (' (pin_names (offset 1.016) hide)' if self.hide_names else ' (pin_names (offset 1.016))') +
               ' (exclude_from_sim no) (in_bom yes) (on_board yes)',
               f'  (property "Reference" {q(self.ref)} (at 0 {f(self.ytop + 2 * G)} 0) {FONT})',
               f'  (property "Value" {q(n)} (at 0 {f(self.ybot - 2 * G)} 0) {FONT})',
               f'  (property "Footprint" "" (at 0 0 0) {FONT_H})',
               f'  (property "Datasheet" "" (at 0 0 0) {FONT_H})',
               f'  (property "Description" {q(self.desc)} (at 0 0 0) {FONT_H})',
               f'  (symbol {q(n + "_0_1")} (rectangle (start {f(-self.hw)} {f(self.ytop)}) (end {f(self.hw)} {f(self.ybot)})'
               ' (stroke (width 0.254) (type default)) (fill (type background))))',
               f'  (symbol {q(n + "_1_1")}']
        for num, (x, y, a) in self.pins.items():
            _, name, et = self.types[num][:3]
            out.append(f'    (pin {et} line (at {f(x)} {f(y)} {a}) (length {G})'
                       f' (name {q(name)} {FONT}) (number {q(num)} {FONT}))')
        out.append('  ))')
        return '\n'.join(out)

def power_sym(name):
    body = {'GND': '(polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27))',
            }.get(name, '(polyline (pts (xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27)) (stroke (width 0) (type default)) (fill (type none))) '
                        '(polyline (pts (xy 0 0) (xy 0 2.54))')
    vy = -3.81 if name == 'GND' else 3.556
    return (f'(symbol {q(LIB + ":" + name)} (power) (pin_names (offset 0)) (exclude_from_sim no) (in_bom yes) (on_board yes)\n'
            f'  (property "Reference" "#PWR" (at 0 0 0) {FONT_H})\n'
            f'  (property "Value" {q(name)} (at 0 {vy} 0) {FONT})\n'
            f'  (property "Footprint" "" (at 0 0 0) {FONT_H})\n  (property "Datasheet" "" (at 0 0 0) {FONT_H})\n'
            f'  (property "Description" "power port" (at 0 0 0) {FONT_H})\n'
            f'  (symbol {q(name + "_0_1")} {body} (stroke (width 0) (type default)) (fill (type none))))\n'
            f'  (symbol {q(name + "_1_1")} (pin power_in line (at 0 0 {270 if name == "GND" else 90}) (length 0) hide'
            f' (name {q(name)} {FONT}) (number "1" {FONT}))))')

PWR_FLAG = (f'(symbol {q(LIB + ":PWR_FLAG")} (power) (pin_numbers hide) (pin_names (offset 0) hide) (exclude_from_sim no) (in_bom yes) (on_board yes)\n'
            f'  (property "Reference" "#FLG" (at 0 1.905 0) {FONT_H})\n  (property "Value" "PWR_FLAG" (at 0 3.81 0) {FONT})\n'
            f'  (property "Footprint" "" (at 0 0 0) {FONT_H})\n  (property "Datasheet" "" (at 0 0 0) {FONT_H})\n'
            f'  (property "Description" "power flag" (at 0 0 0) {FONT_H})\n'
            f'  (symbol "PWR_FLAG_0_0" (pin power_out line (at 0 0 90) (length 0) (name "pwr" {FONT}) (number "1" {FONT})))\n'
            f'  (symbol "PWR_FLAG_0_1" (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27))'
            f' (stroke (width 0) (type default)) (fill (type none)))))')

def pl(d, nums, et): return [(str(n), d[n], et) for n in nums]

def build_symbols():
    S = {}
    S['74LS245'] = Sym('74LS245', pl(LS245, [1, 19], 'input') + [None] + pl(LS245, range(2, 10), 'bidirectional'),
                       [None, None, None] + pl(LS245, range(18, 10, -1), 'bidirectional'),
                       top=pl(LS245, [20], 'power_in'), bottom=pl(LS245, [10], 'power_in'), desc='octal bus transceiver')
    S['74LS374'] = Sym('74LS374', pl(LS374, [3, 4, 7, 8, 13, 14, 17, 18], 'input') + [None] + pl(LS374, [11, 1], 'input'),
                       pl(LS374, [2, 5, 6, 9, 12, 15, 16, 19], 'tri_state'),
                       top=pl(LS374, [20], 'power_in'), bottom=pl(LS374, [10], 'power_in'), desc='octal D flip-flop, 3-state')
    S['74F521'] = Sym('74F521', pl(F521, [2, 4, 6, 8, 11, 13, 15, 17], 'input') + [None] + pl(F521, [1], 'input'),
                      pl(F521, [3, 5, 7, 9, 12, 14, 16, 18], 'input') + [None] + pl(F521, [19], 'output'),
                      top=pl(F521, [20], 'power_in'), bottom=pl(F521, [10], 'power_in'), desc='8-bit identity comparator')
    gal = {1: 'I/CLK', **{n: f'I{n - 1}' for n in range(2, 10)}, 11: 'I/~{OE}', **{n: f'IO{n - 12}' for n in range(12, 20)},
           10: 'GND', 20: 'VCC'}
    S['GAL16V8'] = Sym('GAL16V8', pl(gal, [1, 2, 3, 4, 5, 6, 7, 8, 9, 11], 'input'), pl(gal, range(12, 20), 'bidirectional'),
                       top=pl(gal, [20], 'power_in'), bottom=pl(gal, [10], 'power_in'), desc='GAL16V8 (secured original; fitted equations in gals/)')
    S['27C256'] = Sym('27C256', pl(EPROM27C256, [10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2, 26, 27], 'input') + [None] +
                      pl(EPROM27C256, [20, 22, 1], 'input'),
                      pl(EPROM27C256, [11, 12, 13, 15, 16, 17, 18, 19], 'tri_state'),
                      top=pl(EPROM27C256, [28], 'power_in'), bottom=pl(EPROM27C256, [14], 'power_in'), desc='32K x 8 EPROM (boot ROM)')
    nc = {k: v.replace('/', '~{', 1) + '}' if v.startswith('/') else v for k, v in NCR5380.items()}
    nc[17], nc[18] = '~{I/O}', '~{C/D}'
    S['NCR5380'] = Sym('NCR5380', pl(nc, [1, 40, 39, 38, 37, 36, 35, 34], 'bidirectional') + [None] + pl(nc, [30, 32, 33], 'input') + [None] +
                       pl(nc, [21, 24, 29, 26, 28, 27], 'input') + [None] + pl(nc, [22, 23, 25], 'output'),
                       pl(nc, [9, 8, 7, 6, 5, 4, 3, 2, 10], 'bidirectional') + [None] + pl(nc, [12, 13, 14, 15, 16, 17, 18, 19, 20], 'bidirectional'),
                       top=pl(nc, [31], 'power_in'), bottom=pl(nc, [11], 'power_in'), width=30.48, desc='NCR 5380 SCSI bus controller')
    z = {k: (v.replace('/', '~{', 1) + '}' if v.startswith('/') else v) for k, v in ZORRO2.items()}
    S['ZORRO2'] = Sym('ZORRO2', pl(z, range(1, 101, 2), 'passive'), pl(z, range(2, 101, 2), 'passive'), ref='P', width=20.32,
                      desc='Zorro II 100-pin slot (Amiga HRM pin names)')
    def hdr(rows, name, desc):
        return Sym(name, [(str(2 * r + 1), str(2 * r + 1), 'passive') for r in range(rows)],
                   [(str(2 * r + 2), str(2 * r + 2), 'passive') for r in range(rows)], ref='P', width=5.08, desc=desc, hide_names=True)
    S['CONN_2x25'] = hdr(25, 'CONN_2x25', '50-pin IDC header (SCSI-1)')
    S['CONN_2x13'] = hdr(13, 'CONN_2x13', '26-pin IDC header (to the DB25)')
    S['JUMPER_2x6'] = Sym('JUMPER_2x6', [(str(k), str(k), 'passive') for k in range(1, 7)], [(str(6 + k), str(6 + k), 'passive') for k in range(1, 7)],
                          ref='J', width=5.08, desc='2x6 jumper block: pin k (signal) opposite pin 6+k (GND)', hide_names=True)
    for n in (3, 4):
        S[f'CONN_1x{n}'] = Sym(f'CONN_1x{n}', [(str(k), str(k), 'passive') for k in range(1, n + 1)], [], ref='P', width=5.08, hide_names=True)
    S['RNET_COMMON'] = None
    def rnet(n, name, desc):
        return Sym(name, [('1', 'COM', 'passive')], [(str(k), f'R{k - 1}', 'passive') for k in range(2, n + 1)], ref='RN', width=7.62, desc=desc)
    S['RNET6'] = rnet(6, 'RNET6', 'SIP-6 resistor network, pin 1 common')
    S['RNET8'] = rnet(8, 'RNET8', 'SIP-8 resistor network, pin 1 common')
    S['RTERM10'] = Sym('RTERM10', [('10', 'TPWR', 'passive'), ('1', 'GND', 'passive')], [(str(k), f'T{k - 1}', 'passive') for k in range(2, 10)],
                       ref='RN', width=7.62, desc='SCSI terminator SIP-10: 220 ohm to pin 10, 330 ohm to pin 1 (GND)')
    S['R'] = Sym('R', [('1', '1', 'passive')], [('2', '2', 'passive')], ref='R', width=5.08, hide_names=True)
    S['FUSE'] = Sym('FUSE', [('1', '1', 'passive')], [('2', '2', 'passive')], ref='F', width=5.08, hide_names=True)
    S['DIODE'] = Sym('DIODE', [('2', 'A', 'passive')], [('1', 'K', 'passive')], ref='D', width=5.08, desc='pin 1 = cathode (band)')
    S['CP'] = Sym('CP', [('1', '+', 'passive')], [('2', '-', 'passive')], ref='C', width=5.08, desc='polarised capacitor, pin 1 = +')
    S['C3'] = Sym('C3', [('1', '1', 'passive')], [('2', '2', 'passive'), ('3', '3', 'passive')], ref='C', width=5.08,
                  desc='decoupling capacitor footprint with two lead spacings (holes 2 and 3 in parallel)')
    del S['RNET_COMMON']
    return S

# ---------------------------------------------------------------------------------------------------------------
# board: which part, which symbol, which sheet, where (mm, top-left origin)
PARTS = {   # ref: (symbol, value, sheet, x, y)
    'P1': ('ZORRO2', 'Zorro II slot', 'zorro', 60.96, 88.9),
    'U1': ('74F521', '74F521', 'zorro', 157.48, 76.2), 'U2': ('74LS374', '74LS374', 'zorro', 157.48, 157.48),
    'RP1': ('RNET6', 'RP1 pull-ups (base address $E8)', 'zorro', 241.3, 63.5), 'RP2': ('RNET6', 'RP2 pull-downs (base address $E8)', 'zorro', 241.3, 101.6),
    'U3': ('GAL16V8', 'GAL16V8 U3 decode/autoconfig', 'zorro', 254.0, 165.1),
    'U8': ('74LS245', '74LS245', 'bus', 63.5, 76.2), 'U9': ('74LS245', '74LS245', 'bus', 63.5, 165.1),
    'U10': ('74LS374', '74LS374', 'bus', 157.48, 76.2), 'U11': ('74LS374', '74LS374', 'bus', 157.48, 165.1),
    'U7': ('74LS245', '74LS245 status', 'bus', 254.0, 76.2), 'J1': ('JUMPER_2x6', 'J1 ID/GAME/B/A', 'bus', 342.9, 63.5),
    'RP3': ('RNET8', 'RP3 pull-ups', 'bus', 342.9, 111.76),
    'U4': ('GAL16V8', 'GAL16V8 U4 5380 CS / pseudo-DMA', 'control', 76.2, 88.9),
    'U5': ('GAL16V8', 'GAL16V8 U5 bus sequencer', 'control', 190.5, 88.9),
    'J2': ('CONN_1x3', 'J2 U4 clock (1-2 bridged)', 'control', 76.2, 165.1),
    'P4': ('CONN_1x3', 'P4 DMA LED', 'control', 190.5, 165.1), 'R1': ('R', 'R1 LED', 'control', 254.0, 165.1),
    'U6': ('NCR5380', 'NCR 5380', 'scsi', 101.6, 101.6),
    'P3': ('CONN_2x25', 'P3 SCSI internal', 'scsi', 241.3, 101.6), 'P2': ('CONN_2x13', 'P2 SCSI external (DB25)', 'scsi', 330.2, 76.2),
    'RP4': ('RTERM10', 'RP4 220/330', 'scsi', 330.2, 152.4), 'RP5': ('RTERM10', 'RP5 220/330', 'scsi', 330.2, 200.66),
    'R2': ('R', 'R2 ATN pull-up', 'scsi', 101.6, 190.5), 'R3': ('R', 'R3 RST pull-up', 'scsi', 101.6, 213.36),
    'D1': ('DIODE', 'D1', 'scsi', 190.5, 228.6), 'F1': ('FUSE', 'F1 TERMPWR', 'scsi', 254.0, 228.6),
    'U12': ('27C256', '27C256 boot ROM (rev 1.7)', 'rom', 127.0, 101.6),
    'P5': ('CONN_1x4', 'P5 drive power', 'power', 50.8, 63.5),
    'CE1': ('CP', 'CE1', 'power', 50.8, 114.3), 'CE2': ('CP', 'CE2', 'power', 50.8, 139.7),
    **{f'DC{n}': ('C3', f'DC{n} 0.1u', 'power', 127.0 + ((n - 1) % 4) * 50.8, 63.5 + ((n - 1) // 4) * 38.1) for n in range(1, 13)},
}
# Real component values (read off Stephane's card, 2026-11-15) and each part's function (shown under the value)
VALUES = {
    'U1': ('74F521', 'address comparator'), 'U2': ('74LS374', 'base address latch'),
    'U10': ('74LS374', 'read latch (D8-D15)'), 'U11': ('74LS374', 'write latch (D0-D7)'),
    'U7': ('74LS245', 'status buffer'), 'U8': ('74LS245', 'bus buffer D8-D15'), 'U9': ('74LS245', 'read buffer D0-D7'),
    'U3': ('GAL16V8', 'decode / Autoconfig (gals/u3)'), 'U4': ('GAL16V8', '5380 /CS, pseudo-DMA (gals/u4)'),
    'U5': ('GAL16V8', 'bus sequencer (gals/u5)'), 'U6': ('NCR 5380', 'SCSI controller'), 'U12': ('27C256', 'boot ROM (rev 1.7)'),
    'RP1': ('1k x5 bussed 2% (CG102G)', 'pull-ups, base address $E8'),
    'RP2': ('1k x5 bussed 2% (CG102G)', 'pull-downs, base address $E8'),
    'RP3': ('10k x7 bussed 2% (8C103G)', 'pull-ups (J1, /EOP)'),
    'RP4': ('220/330 x8 terminator', 'SCSI termination'), 'RP5': ('220/330 x8 terminator', 'SCSI termination'),
    'R1': ('100R 5%', 'DMA LED'), 'R2': ('1k 5%', '/ATN pull-up'), 'R3': ('1k 5%', '/RST pull-up'),
    'D1': ('1N5395', 'TERMPWR (a 1N5817/5818 Schottky gives ~0.5 V more)'), 'F1': ('1A fuse', 'TERMPWR'),
    'CE1': ('47uF 16V', 'bulk decoupling'), 'CE2': ('47uF 16V', 'bulk decoupling'),
    **{f'DC{n}': ('0.1uF', 'decoupling') for n in range(1, 13)},
    'J1': ('2x6 pin header', 'ID / GAME / B / A jumpers'), 'J2': ('1x3 pin header', 'U4 clock (1-2 bridged)'),
    'P2': ('2x13 box header', 'SCSI external (DB25 via IDC)'), 'P3': ('2x25 box header', 'SCSI internal'),
    'P4': ('1x3 pin header', 'DMA LED'), 'P5': ('4-pin floppy power, male', 'drive power'),
}

SHEETS = [('zorro', 'Zorro interface, decode and Autoconfig'), ('bus', 'Data buffers, latches and status'),
          ('control', '5380 control and bus sequencing'), ('scsi', 'SCSI controller, connectors and termination'),
          ('rom', 'Boot ROM'), ('power', 'Drive power and decoupling')]
POWER = {'GND': 'GND', 'VCC': 'VCC', 'P12V': '+12V'}

def load_nets():
    pin2net = {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'netlist', 'merged.csv'))):
        for m in r['members'].split(): pin2net[m] = r['net']
    return pin2net

def gen(outdir):
    S = build_symbols(); pin2net = load_nets()
    root_uuid = uid('root')
    sheet_uuid = {s: uid('sheetblock', s) for s, _ in SHEETS}
    libs = '\n'.join([s.sexpr() for s in S.values()] + [power_sym('GND'), power_sym('VCC'), power_sym('+12V'), PWR_FLAG])
    pwr_n = [0]
    for si, (sheet, title) in enumerate(SHEETS):
        items = []; path = f'/{root_uuid}/{sheet_uuid[sheet]}'
        def place(lib_id, ref, value, x, y, pins, hide_ref=False, angle=0, ytop=3.0, ybot=-3.0, hide_value=False):
            u = uid('sym', sheet, ref)
            ry, vy = y - ytop - 1.27, y - ybot + 2.54          # reference above the body, value below
            items.append(f'(symbol (lib_id {q(LIB + ":" + lib_id)}) (at {f(x)} {f(y)} {angle}) (unit 1)'
                         f' (exclude_from_sim no) (in_bom {"no" if hide_ref else "yes"}) (on_board {"no" if hide_ref else "yes"}) (dnp no)\n'
                         f'  (uuid {q(u)})\n'
                         f'  (property "Reference" {q(ref)} (at {f(x)} {f(ry)} 0) {FONT_H if hide_ref else FONT})\n'
                         f'  (property "Value" {q(VALUES[ref][0] if ref in VALUES else value)} (at {f(x)} {f(vy)} 0) {FONT_H if hide_value else FONT})\n'
                         + (f'  (property "Function" {q(VALUES[ref][1])} (at {f(x)} {f(vy + 2.54)} 0) {FONT})\n' if ref in VALUES else '') +
                         f'  (property "Footprint" {q(("adscsi:" + FOOTPRINT[ref]) if ref in FOOTPRINT else "")} (at {f(x)} {f(y)} 0) {FONT_H})\n'
                         f'  (property "Datasheet" "" (at {f(x)} {f(y)} 0) {FONT_H})\n'
                         + ''.join(f'  (pin {q(p)} (uuid {q(uid("pin", sheet, ref, p))}))\n' for p in pins) +
                         f'  (instances (project {q(PROJECT)} (path {q(path)} (reference {q(ref)}) (unit 1)))))')
        def wire(x1, y1, x2, y2, k):
            items.append(f'(wire (pts (xy {f(x1)} {f(y1)}) (xy {f(x2)} {f(y2)})) (stroke (width 0) (type default)) (uuid {q(uid("w", sheet, k))}))')
        def glabel(name, x, y, angle, k):
            just = 'left' if angle in (0, 90) else 'right'
            items.append(f'(global_label {q(name)} (shape bidirectional) (at {f(x)} {f(y)} {angle}) (fields_autoplaced yes)'
                         f' (effects (font (size 1.27 1.27)) (justify {just})) (uuid {q(uid("gl", sheet, k))})'
                         f' (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {f(x)} {f(y)} 0)'
                         f' (effects (font (size 1.27 1.27)) (justify {just}) hide)))')
        def power(name, x, y, k, side=None):
            pwr_n[0] += 1; ref = f'#PWR{pwr_n[0]:03d}'
            # GND graphic hangs below its pin, the others stand above it; rotate (CCW) to point away from the part
            up = name != 'GND'
            angle = {'left': 90 if up else 270, 'right': 270 if up else 90,
                     'top': 0 if up else 180, 'bottom': 180 if up else 0}.get(side, 0)
            place(name, ref, name, x, y, ['1'], hide_ref=True, angle=angle, hide_value=side in ('left', 'right'))
        for ref, (sym, value, sh, X, Y) in PARTS.items():
            if sh != sheet: continue
            s = S[sym]
            place(sym, ref, value, X, Y, list(s.pins), ytop=s.ytop + (G if s.top else 0), ybot=s.ybot - (G if s.bottom else 0))
            for num, (px, py, a) in s.pins.items():
                cx, cy = X + px, Y - py                          # schematic Y grows downward
                dx, dy = {0: (-G, 0), 180: (G, 0), 270: (0, -G), 90: (0, G)}[a]
                ex, ey = cx + dx, cy + dy
                net = pin2net.get(f'{ref}.{num}')
                k = f'{ref}.{num}'
                if net is None:
                    items.append(f'(no_connect (at {f(cx)} {f(cy)}) (uuid {q(uid("nc", sheet, k))}))'); continue
                wire(cx, cy, ex, ey, k)
                if net in POWER:
                    power(POWER[net], ex, ey, k, side={0: 'left', 180: 'right', 270: 'top', 90: 'bottom'}[a])
                else:
                    langle = {0: 180, 180: 0, 270: 90, 90: 270}[a]
                    glabel(net, ex, ey, langle, k)
        if sheet == 'power':                               # PWR_FLAGs: the supplies come in through P1 (passive pins)
            for i, (pname, x) in enumerate((('GND', 330.2), ('VCC', 355.6), ('+12V', 381.0))):
                place('PWR_FLAG', f'#FLG{i + 1:02d}', 'PWR_FLAG', x, 63.5, ['1'], hide_ref=True)
                wire(x, 63.5, x, 69.85, f'flag{i}')
                power(pname, x, 69.85, f'flagp{i}')
        txt = (f'(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")\n'
               f'  (uuid {q(uid("file", sheet))})\n  (paper "A3")\n'
               f'  (title_block (title {q(title)}) (company "ICD Inc. AdSCSI 2000 / Advantage 2000 (reverse engineered)")'
               f' (comment 1 "Generated by schematic/tools/kicad_gen.py from schematic/netlist/merged.csv (measured continuity)"))\n'
               f'  (lib_symbols\n{libs}\n  )\n' + '\n'.join(items) + '\n)\n')
        open(os.path.join(outdir, f'{sheet}.kicad_sch'), 'w').write(txt)
    blocks = []
    for i, (sheet, title) in enumerate(SHEETS):
        x, y = 25.4 + (i % 3) * 127.0, 50.8 + (i // 3) * 76.2
        blocks.append(f'(sheet (at {f(x)} {f(y)}) (size 101.6 38.1) (fields_autoplaced yes)'
                      f' (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid {q(sheet_uuid[sheet])})\n'
                      f'  (property "Sheetname" {q(title)} (at {f(x)} {f(y - 0.7116)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))\n'
                      f'  (property "Sheetfile" {q(sheet + ".kicad_sch")} (at {f(x)} {f(y + 38.6716)} 0) (effects (font (size 1.27 1.27)) (justify left top)))\n'
                      f'  (instances (project {q(PROJECT)} (path {q("/" + root_uuid)} (page {q(str(i + 2))})))))')
    root = (f'(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")\n'
            f'  (uuid {q(root_uuid)})\n  (paper "A4")\n'
            f'  (title_block (title "ICD AdSCSI 2000 (Advantage 2000) - Zorro II SCSI controller")'
            f' (comment 1 "Reverse engineered 2026 (preservation): netlist measured by continuity on Stephane\'s card")'
            f' (comment 2 "GAL equations: gals/uN/uN_named.pld (fitted from the secured originals)"))\n'
            f'  (lib_symbols)\n' + '\n'.join(blocks) +
            '\n  (sheet_instances (path "/" (page "1")))\n)\n')
    open(os.path.join(outdir, f'{PROJECT}.kicad_sch'), 'w').write(root)
    # the same symbols as a project library (+ table), so KiCad can find and edit them
    lib = libs.replace(f'(symbol {q(LIB + ":")}', '(symbol "')
    open(os.path.join(outdir, f'{LIB}.kicad_sym'), 'w').write(
        f'(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor") (generator_version "8.0")\n{lib}\n)\n')
    open(os.path.join(outdir, 'sym-lib-table'), 'w').write(
        f'(sym_lib_table\n  (version 7)\n  (lib (name "{LIB}") (type "KiCad") (uri "${{KIPRJMOD}}/{LIB}.kicad_sym") (options "")'
        f' (descr "AdSCSI 2000 symbols generated by kicad_gen.py from the verified pinouts"))\n)\n')
    print('wrote', len(SHEETS) + 1, 'sheets to', outdir)

if __name__ == '__main__':
    gen(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'kicad'))
