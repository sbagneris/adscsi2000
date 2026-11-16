#!/usr/bin/env python3
"""Part placement on the board photos (component-side pixel coordinates) and pin coordinates.

Orientation (confirmed on the card, 2026-11-08): every DIP is vertical with its notch toward the edge connector,
so pin 1 is bottom-right, pins 1..n/2 run UP the right column and n/2+1..n DOWN the left column. U12 (27C256) is
horizontal with pin 1 bottom-left: pins 1..14 left to right on the bottom row, 15..28 right to left on top.
Pitch 0.1" ~ 30 px. P2, P3 and J1 numbering checked electrically (2026-11-13); SIP pin 1 = silkscreen notch.
"""
DIPS = {   # ref: (pins, x right column, x left column, y of pin 1 (bottom), y of top pin)
    'U1': (20, 298, 211, 428, 158), 'U2': (20, 532, 445, 428, 158), 'U3': (20, 743, 656, 428, 158),
    'U4': (20, 955, 868, 428, 158), 'U5': (20, 1173, 1087, 428, 158), 'U6': (40, 1480, 1305, 728, 158),
    'U7': (20, 296, 209, 965, 695), 'U10': (20, 532, 445, 965, 695), 'U8': (20, 743, 656, 965, 695),
    'U9': (20, 955, 868, 965, 695), 'U11': (20, 1173, 1087, 965, 695),
}
VALUES = {'U1': 'MC74F521', 'U2': '74LS374', 'U3': 'GAL16V8', 'U4': 'GAL16V8', 'U5': 'GAL16V8',
          'U6': 'L5380 (NCR 5380)', 'U7': '74LS245', 'U8': '74LS245', 'U9': '74LS245', 'U10': '74LS374',
          'U11': '74LS374', 'U12': '27C256'}
# single rows: ref: (count, x0, y0, x1, y1) pin 1 at (x0, y0) -- provisional pin-1 ends
ROWS = {
    'RP2': (6, 356, 158, 356, 305), 'RP1': (6, 385, 275, 385, 428), 'RP3': (8, 340, 755, 340, 965),
    'RP4': (10, 1643, 503, 1643, 778), 'RP5': (10, 1672, 521, 1672, 791),
    'J2': (3, 1005, 368, 1005, 428), 'P4': (3, 110, 210, 110, 270), 'P5': (4, 1672, 1150, 1672, 1245),
}
# dual-row headers: ref: (rows, x col a, x col b, y first row, y last row); pin 2k-1 in col a, 2k in col b
HEADERS = {   # (rows, x of the odd-pin column, x of the even-pin column, y of the row with pins 1/2, y of the last row)
    'P3': (25, 1963, 1935, 1016, 295),     # pin 1 bottom-right, outer column = odd = GND (confirmed 2026-11-13)
    'P2': (13, 1787, 1817, 460, 820),      # true pin 1 top-left (Stephane's first numbering had each pair swapped)
}
# J1 uses Stephane's numbering: 1-6 = ID0 ID1 ID2 GAME B A (column facing U7, ID0 at the bottom), 7-12 = GND,
# J1.(6+k) opposite J1.k in the outer column
J1 = {**{k: (163, 950 - (k - 1) * 30) for k in range(1, 7)}, **{6 + k: (135, 950 - (k - 1) * 30) for k in range(1, 7)}}

# two- and three-pad passives, pads measured on the photos (left to right / top to bottom; pin order provisional)
PADS = {
    'R1': [(114, 308), (108, 428)], 'R2': [(1537, 162), (1539, 281)], 'R3': [(1586, 162), (1582, 279)],
    'D1': [(1539, 358), (1540, 476)], 'F1': [(1592, 356), (1598, 475)],
    'CE1': [(1864, 1075), (1865, 1108)], 'CE2': [(98, 1222), (98, 1252)],   # CE2 pad 2 below pad 1 (solder side)
    'DC1': [(210, 514), (236, 518), (327, 517)], 'DC2': [(450, 517), (475, 516), (561, 518)],
    'DC3': [(656, 518), (684, 519), (774, 518)], 'DC4': [(869, 518), (897, 515), (984, 519)],
    'DC5': [(1087, 520), (1116, 518), (1202, 520)], 'DC6': [(1330, 790), (1365, 789), (1453, 791)],
    'DC7': [(209, 1059), (238, 1057), (326, 1058)], 'DC10': [(443, 1056), (473, 1059), (560, 1058)],
    'DC8': [(632, 1059), (656, 1055), (743, 1059)], 'DC9': [(867, 1057), (897, 1057), (985, 1059)],
    'DC11': [(1088, 1060), (1117, 1059), (1204, 1060)], 'DC12': [(1320, 938), (1322, 972), (1323, 1059)],
}

def pins():
    out = {}
    for ref, pl in PADS.items():
        for i, xy in enumerate(pl): out[(ref, i + 1)] = xy
    for ref, (n, xr, xl, yb, yt) in DIPS.items():
        h = n // 2; step = (yb - yt) / (h - 1)
        for i in range(h):
            out[(ref, i + 1)] = (xr, yb - i * step)          # up the right column
            out[(ref, h + 1 + i)] = (xl, yt + i * step)      # down the left column
    # U12 horizontal, pin 1 bottom-left
    x0, x1, yb, yt = 1380, 1760, 1084, 908; step = (x1 - x0) / 13
    for i in range(14):
        out[('U12', i + 1)] = (x0 + i * step, yb)
        out[('U12', 15 + i)] = (x1 - i * step, yt)
    for ref, (n, x0, y0, x1, y1) in ROWS.items():
        for i in range(n):
            t = i / (n - 1); out[(ref, i + 1)] = (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
    for ref, (n, xa, xb, y0, y1) in HEADERS.items():
        step = (y1 - y0) / (n - 1)
        for i in range(n):
            out[(ref, 2 * i + 1)] = (xa, y0 + i * step); out[(ref, 2 * i + 2)] = (xb, y0 + i * step)
    for k, xy in J1.items(): out[('J1', k)] = xy
    return out
