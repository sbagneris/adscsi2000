#!/usr/bin/env python3
"""Continuity sweep sheet for the GAL sockets: one row per GAL pin with the photo hint (unverified) and blank
result columns. Most GAL traces disappear under sockets/packages on the component side, so destinations are found
by sweeping: one probe in the GAL socket hole, the other dragged along each row of pins in SWEEP order.
Output: schematic/continuity/gal_sweep.csv (instructions in continuity/README.md)"""
import collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SWEEP = ('other GALs (U3/U4/U5 sockets), U6 socket (5380), U12 socket (EPROM), U2, U10, U11 (74LS374), '
         'U7, U8, U9 (74LS245), U1 (74F521), RP1-RP5, J1, J2, P1 edge fingers (both sides), P2, P3')
ROLE = {}   # from the GAL characterisation (gals/uN)
ROLE.update({('U3', 10): 'GND', ('U4', 10): 'GND', ('U5', 10): 'GND', ('U3', 20): 'VCC', ('U4', 20): 'VCC', ('U5', 20): 'VCC',
             ('U4', 1): 'CLK (registered mode)', ('U4', 11): '/OE (registered mode)'})
for ref, ins, outs in (('U3', [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 17, 18], [12, 13, 14, 15, 16, 19]),
                       ('U4', [2, 3, 4, 5, 6, 7, 8, 9, 19], [12, 13, 14, 15, 16, 17, 18]),
                       ('U5', [1, 2, 3, 4, 5, 6, 7, 8, 9, 11], [13, 14, 15, 16, 17, 18, 19])):
    for p in ins: ROLE.setdefault((ref, p), 'input')
    for p in outs: ROLE[(ref, p)] = 'output'
ROLE[('U4', 12)] = ROLE[('U4', 15)] = ROLE[('U4', 16)] = 'registered output'
ROLE[('U3', 14)] = ROLE[('U3', 16)] = 'output (latch)'; ROLE[('U5', 17)] = 'output (latch)'
ROLE[('U5', 12)] = 'never driven (unused?)'; ROLE[('U5', 19)] = 'output (tri-state)'; ROLE[('U4', 9)] = 'input (unused by the logic)'
ROLE[('U4', 13)] = ROLE[('U4', 14)] = 'output (latch?)'

READINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'continuity', 'gal_photo_readings.tsv')

def load_readings():
    import csv, re
    out = {}
    rows = [l for l in open(READINGS) if not l.startswith('#')]
    for r in csv.DictReader(rows, delimiter='\t'):
        m = re.match(r'(U\d)\.(.*)', r['pin'])
        pins = []
        for part in m.group(2).split(','):
            a, _, b = part.partition('-')
            pins += [f'{m.group(1)}.{n}' for n in range(int(a), int(b or a) + 1)]
        for p in pins: out[p] = (r['reading'], r['conf'])
    return out

L = 'sweep left side first: U2, U1, RP1, RP2, J1, P1 fingers'
R = 'sweep right side first: U5 and U6 sockets, U12 socket, U11, then the rest'
D = 'bottom row first: U8, U9, U10, U11, U7, then the rest'
A = 'sweep everything (may be unconnected)'
F = 'sweep for further endpoints'
TODO = {   # written from gal_photo_readings.tsv (2026-11-08)
 'U3.1': f'confirm U8.1; {R}', 'U3.2': f'{R}', 'U3.3': f'confirm U4.3; {F}', 'U3.4': f'confirm U4.4; {F}',
 'U3.5': f'confirm U4.5; {R}', 'U3.6': A, 'U3.7': f'beep U3.15 (junction); {R}', 'U3.8': f'confirm U12.27; check U12.28 (VCC?); {F}',
 'U3.9': L, 'U3.11': f'beep U4.13 (possible merge); {R}', 'U3.12': f'confirm DC12.2; {F}', 'U3.13': f'confirm U4.14; {R}',
 'U3.14': f'{F} (solder side to V44, V75)', 'U3.15': f'beep U3.7 (junction); {R}', 'U3.16': f'{L} (solder trace heads up-left)',
 'U3.17': f'{F} (solder side to V45)', 'U3.18': f'confirm U4.7; {L} (also goes left to V35)', 'U3.19': L,
 'U4.1': f'confirm J2.2 J2.3; {F}', 'U4.2': f'{F} (solder side to V11, V69)', 'U4.3': f'confirm U3.3; {F}', 'U4.4': f'confirm U3.4; {F}',
 'U4.5': f'confirm U3.5; {R}', 'U4.6': R, 'U4.7': f'confirm U3.18; {R}', 'U4.8': R, 'U4.9': A,
 'U4.11': 'confirm U4.10 (GND): /OE tied low', 'U4.12': f'{L} (trace crosses over U3 from the far left)',
 'U4.13': f'beep U3.11 (possible merge); {R}', 'U4.14': f'confirm U3.13; {F}', 'U4.15': f'beep V23 first; {A}',
 'U4.16': A, 'U4.17': A, 'U4.18': A, 'U4.19': A,
 'U5.1': f'{R} (goes to V48)', 'U5.2': f'{R} (goes to V42)', 'U5.4': L, 'U5.11': L, 'U5.16': f'{F} (goes to V26)',
 'U5.17': f'confirm U11.1; {F}', 'U5.18': f'confirm U11.11; {F}',
}
for p in (3, 5, 6, 7, 8, 9, 12, 13, 14, 15, 19):
    other = 'U5.11-U5.15' if p <= 9 else 'U5.5-U5.9'
    TODO[f'U5.{p}'] = f'staircase inside U5: beep against {other} first; then {R}'

def todo_for(pin, reading, conf, role):
    if role in ('GND', 'VCC'):
        return 'power: check against ' + ('U2.10 (GND)' if role == 'GND' else 'U2.20 (VCC)') + ' only'
    return TODO.get(pin, F)

def main():
    rd = load_readings()
    rows = []
    for ref in ('U3', 'U4', 'U5'):
        for p in range(1, 21):
            pin = f'{ref}.{p}'; role = ROLE.get((ref, p), '')
            reading, conf = rd.get(pin, ('-', ''))
            rows.append((pin, role, reading, conf, todo_for(pin, reading, conf, role)))
    import csv
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'continuity')
    out = os.path.join(d, 'gal_sweep.csv')
    with open(out, 'w', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(['gal_pin', 'role', 'photo_reading', 'conf', 'todo', 'found', 'notes'])
        for r in rows: w.writerow(list(r) + ['', ''])
    old = os.path.join(d, 'gal_sweep.tsv')
    if os.path.exists(old): os.remove(old)
    print(out)

if __name__ == '__main__':
    main()
