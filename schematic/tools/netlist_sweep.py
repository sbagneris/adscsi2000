#!/usr/bin/env python3
"""Continuity sweep sheet for a round of parts: every pin whose net is not known yet (schematic/netlist/*.csv),
with its function (pinouts.py), what the design predicts, and blank found/notes columns.
usage: python3 netlist_sweep.py ROUND_NAME U12 U6 ..."""
import csv, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinouts import PARTS, ZORRO2
HERE = os.path.dirname(os.path.abspath(__file__))
NETDIR = os.path.join(HERE, '..', 'netlist')
CONT = os.path.join(HERE, '..', 'continuity')
ZA = {v: k for k, v in ZORRO2.items()}

def known():
    k = {}
    for f in glob.glob(os.path.join(NETDIR, '*.csv')):
        for n in csv.DictReader(open(f)):
            for m in n['members'].split(): k[m] = n['net']
    return k

INTERNAL = 'internal data bus: expect {other} D0-D7, U10/U11 D or Q pins, U8/U9 B side, U7 B side'
def expect(ref, pin, fn):
    if ref == 'U12':
        if fn.startswith('A'):
            za = f'A{int(fn[1:]) + 1}'                      # EPROM on the even byte lane: ROM An = Zorro A(n+1)
            return f'Zorro {za}: P1.{ZA[za]}', f'confirm P1.{ZA[za]}; then sweep for further endpoints'
        if fn.startswith('D'): return INTERNAL.format(other='U6'), 'sweep U8/U9, U10/U11, U6 socket first'
        if fn == 'VPP': return 'VCC', 'check against U2.20 (VCC)'
        if fn == '/CE': return 'GND or a GAL output', 'check against U2.10 (GND); else sweep'
        if fn in ('GND', 'VCC'): return fn, f'check against U2.{10 if fn == "GND" else 20}'
    if ref == 'U6':
        if fn in ('GND', 'VDD'): return fn, f'check against U2.{10 if fn == "GND" else 20}'
        if fn.startswith('D'): return INTERNAL.format(other='U12'), 'sweep U8/U9, U10/U11, U12 socket first'
        if fn.startswith('/') and fn[1:] in ('DB0', 'DB1', 'DB2', 'DB3', 'DB4', 'DB5', 'DB6', 'DB7', 'DBP', 'SEL', 'BSY',
                                              'ACK', 'ATN', 'RST', 'I/O', 'C/D', 'MSG', 'REQ'):
            return 'SCSI bus: P3 (50-pin, internal) and P2 (26-pin, external) + a terminator pin on RP4/RP5', \
                   'sweep P3, P2, RP4, RP5 (note the P3 and P2 pin numbers carefully)'
        if fn in ('READY', '/EOP'): return 'unused? (pull-up, GND or open)', 'sweep everything; note if nothing'
    if fn in ('GND', 'VCC'): return fn, f'check against U12.{14 if fn == "GND" else 28} (EPROM socket)'
    if ref == 'U8' and fn.startswith('B'):                    # even byte lane: internal Dk <-> Zorro D(8+k)
        k = int(fn[1:]) - 1; z = f'D{8 + k}'
        return f'Zorro {z}: P1.{ZA[z]}', f'confirm P1.{ZA[z]}; then sweep for further endpoints'
    if ref == 'U1':
        if fn == '/G': return 'GND (comparator always enabled) or a GAL output', 'check against U12.14 (GND); else sweep'
        side = fn[0]; k = int(fn[1:])
        return (f'Zorro A16-A23 (P1.45 47 52 54 56 58 57 59) or U2 Q outputs (base address latch)',
                'sweep P1 fingers 45-59 and U2 first')
    if ref == 'U2' and fn.endswith('Q'): return 'U1 P or Q input (latched board base address)', 'sweep U1 first'
    if ref == 'U7':
        jm = {2: 'J1 ID0', 3: 'J1 ID1', 4: 'J1 ID2', 5: 'J1 GAME', 6: 'J1 B', 7: 'J1 A'}
        if pin in jm: return f'{jm[pin]} (earlier continuity) + a pull-up pin of RP3', 'sweep J1 and RP3 first; note the J1 pin numbers'
        if fn == 'DIR': return 'GND or VCC (fixed direction: status in -> data bus out)', 'check GND/VCC; else sweep'
        if fn.startswith('B'): return 'internal data bus or U10 Q (U7.14 = U10.12 measured earlier)', 'sweep U10 first, then U11, U9'
    if ref == 'U9' and fn.startswith('B'): return 'Zorro D0-D7 (P1.75 77 79 81 83 86 84 82: 16-bit data port $20/$38), U10 Q or U11 D', 'sweep P1 fingers 75-86, then U10, U11'
    if ref == 'U9' and fn == 'DIR': return 'GND, VCC or ZREAD', 'check GND/VCC, then U8.1 (ZREAD)'
    if ref == 'U10' and fn.endswith('Q'): return 'U7 B side, U9 B side or Zorro D0-D7 (P1.75 77 79 81 83 86 84 82: 16-bit data port $20/$38)', 'sweep U7, U9, then P1 fingers 75-86'
    if ref == 'U11' and fn.endswith('D'): return 'U9 B side or Zorro D0-D7 (P1.75 77 79 81 83 86 84 82: 16-bit data port $20/$38)', 'sweep U9, then P1 fingers 75-86'
    return '', 'sweep'

def main():
    name, refs = sys.argv[1], sys.argv[2:]
    k = known(); rows = []
    for ref in refs:
        for pin, fn in sorted(PARTS[ref].items()):
            key = f'{ref}.{pin}'
            if key in k: continue
            e, todo = expect(ref, pin, fn)
            rows.append([key, fn, e, todo, '', ''])
    out = os.path.join(CONT, f'sweep_{name}.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(['pin', 'function', 'expected', 'todo', 'found', 'notes'])
        w.writerows(rows)
    print(out, len(rows), 'rows;', sum(1 for r in refs for p in PARTS[r] if f'{r}.{p}' in k), 'pins already known (skipped)')

if __name__ == '__main__':
    main()
