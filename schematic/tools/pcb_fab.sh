#!/usr/bin/env bash
# Fabrication outputs for the clone PCB: gerbers, Excellon drills, BOM, previews, order notes, one zip.
# usage: pcb_fab.sh KICAD_DIR     (writes KICAD_DIR/fab/; refuses if DRC finds errors or warnings)
set -euo pipefail
D="$(cd "$1" && pwd)"; F="$D/fab"; B="$D/adscsi2000.kicad_pcb"
kicad-cli pcb drc --schematic-parity --severity-error --severity-warning --exit-code-violations -o /dev/null "$B" >/dev/null \
  || { echo "DRC not clean: fix or accept (drc_accepted.tsv) before making fab outputs"; exit 1; }
rm -rf "$F"; mkdir -p "$F/gerbers"
kicad-cli pcb export gerbers -o "$F/gerbers" --check-zones --subtract-soldermask \
  -l F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts "$B" >/dev/null
kicad-cli pcb export drill -o "$F/gerbers" --format excellon --excellon-units mm --excellon-separate-th \
  --generate-map --map-format gerberx2 "$B" >/dev/null
kicad-cli sch export bom -o "$F/adscsi2000_bom.csv" --fields 'Reference,Value,Footprint,Function,${QUANTITY}' \
  --labels 'Refs,Value,Footprint,Function,Qty' --group-by 'Value,Footprint,Function' "$D/adscsi2000.kicad_sch" >/dev/null
for side in front back; do
  L="F.Cu,F.SilkS,F.Mask,Edge.Cuts"; M=""; [ $side = back ] && L="B.Cu,B.SilkS,B.Mask,Edge.Cuts" && M="--mirror"
  kicad-cli pcb export svg -l "$L" --mode-single --fit-page-to-board --exclude-drawing-sheet $M -o "$F/$side.svg" "$B" >/dev/null
  rsvg-convert -w 2000 -b white "$F/$side.svg" -o "$F/$side.png" && rm "$F/$side.svg"
done
cat > "$F/ORDER_NOTES.txt" <<'TXT'
AdSCSI 2000 compatible - clone r1 (Amiga Zorro II SCSI card)
Board: 2 layers, FR-4, 1.6 mm (Zorro II card edge), 173.85 x 116.85 mm (124.26 mm over the edge-connector tab)
Copper: 1 oz both sides. Min track 0.127 mm (a few pad entries; 0.15 / 0.25 / 0.5 mm otherwise), min clearance 0.2 mm
        (0.15 mm board minimum), vias 0.7/0.35 mm (stitching and signal), 0.8/0.4 mm (GND escapes).
Holes: PTH (DIP 0.8 mm, headers 1.0 mm, mounting 3.8 mm plated) and NPTH files separate (Excellon, mm).
Edge connector: 100 gold fingers (2 x 50, 2.54 mm pitch) on the bottom tab, both sides: order GOLD FINGERS (hard gold)
        and a BEVELLED edge (30-45 degrees, 20 deg also fine) on the finger edge only. Fingers stop 0.3 mm short of the edge.
Finish: HASL (lead-free) or ENIG for the rest; solder mask green (or any), silkscreen white.
Assembly: through-hole, by hand. Sockets for U3/U4/U5 (GAL16V8), U6 (5380), U12 (27C256).
TXT
( cd "$F/gerbers" && python3 -m zipfile -c ../adscsi2000_gerbers.zip * )
echo "fab outputs in $F:"; ls "$F" "$F/gerbers"
