# Continuity measurements

## gal_sweep.csv (GAL sockets U3, U4, U5)

The GAL sockets are removed: put one probe in the bare GAL pad hole (`gal_pin`), use the other one as `todo` says.

- `photo_reading` / `conf`: what the socketless high-res photo shows (gal_photo_readings.tsv), high / medium / low.
- `todo`, in order:
  - **confirm X**: one beep expected (an established link). No beep is worth a note: it may be damage on this card.
  - **beep X**: settles a specific doubt (U3.7-U3.15 junction, U3.11-U4.13, U4.15-V23, the staircase inside U5).
  - **sweep ... first**: drag the other probe along whole rows of pins, starting with the side of the board the
    trace heads to, then everything else: other GAL footprints, U6 socket, U12 socket, U2, U10, U11 (74LS374),
    U7, U8, U9 (74LS245), U1 (74F521), RP1-RP5, J1, J2, P1 edge fingers (both sides), P2, P3.
  - **power**: pins 10 (GND) and 20 (VCC): only check against U2.10 / U2.20.
- `found`: every pin that beeps, space separated (e.g. `U6.22 U7.8 RP3.1`); `GND` / `VCC` for power; `none` if nothing.
- `notes`: anything odd.

Tips: soldered chips can be probed on their legs from the top or on the solder-side pads; each edge finger is its
own pin and the two sides are different pins; resistor packs (220/330/1k/10k) do not beep, only a direct copper
link to a pack pin does. A pin that beeps on pin 10 or 20 of several chips is tied to GND or VCC.

Regenerate with `python3 schematic/tools/gal_sweep.py` (hints from gal_photo_readings.tsv).

## sweep_roundN.csv (rest of the netlist, one round of parts at a time)

Columns: `pin` (part.pin), `function` (datasheet name), `expected` (what the design predicts), `todo`, then fill
`found` and `notes` the same way as for the GALs. Pins already on a known net are left out; each next round only
lists what is still unknown.

Pin numbering reminders (every DIP on this board has its notch toward the edge connector):
- **Vertical DIPs** (U1-U11, and the U6 socket): pin 1 is **bottom-right**, pins go **up** the right column, then
  **down** the left column. U6 (40 pins): pin 1 bottom-right, pin 20 top-right, pin 21 top-left, pin 40 bottom-left.
  Opposite pins on the same row add up to 41 (21 for the 20-pin chips): handy to catch a column mix-up.
- **U12** (EPROM socket, horizontal): pin 1 is **bottom-left**, pins 1-14 left to right along the bottom row,
  15-28 right to left along the top row.
- Round 1 = U12 and U6 (both sockets empty): 5380 pin functions from the NCR design manual (A0-A2 = 30/32/33,
  D0 = 1, D1-D7 = 40..34, SCSI /DB0-/DB7 = 9..2).
