#!/usr/bin/env bash
# Rebuild the clone PCB from the autorouter session, reproducibly:
#   generate (pcb_gen) -> import the Freerouting session (signals; GND left to the pours) -> GND stubs into the
#   grounded mounting hole -> GND pours on both layers -> stitch stranded GND pads (stubs / maze / DRC-checked trials)
# usage: pcb_finish.sh KICAD_DIR SESSION.ses      (KiCad must not have the board open)
set -euo pipefail
T="$(cd "$(dirname "$0")" && pwd)"; D="$1"; SES="$(realpath "$2")"
cd "$D"
/usr/bin/python3 "$T/pcb_gen.py" . --replace-routed | grep -E "^board|wrote"
/usr/bin/python3 -c "import pcbnew; b = pcbnew.LoadBoard('adscsi2000.kicad_pcb'); assert pcbnew.ImportSpecctraSES(b, '$SES'); b.Save('adscsi2000.kicad_pcb'); print('session imported')"
/usr/bin/python3 "$T/pcb_fanout.py" adscsi2000.kicad_pcb --only 13,25   # same reservations as the routing run that produced the session (re-added after import)
/usr/bin/python3 "$T/pcb_fanout.py" adscsi2000.kicad_pcb --holes-only
/usr/bin/python3 "$T/pcb_fanout.py" adscsi2000.kicad_pcb --bridges
/usr/bin/python3 "$T/pcb_fanout.py" adscsi2000.kicad_pcb --pad P2.2:1.27,1.27 --pad P2.6:1.27,1.27 --pad P2.10:1.27,1.27 --pad P2.22:1.27,1.27 --pad P2.13:-1.27,1.27 --pad P2.17:-1.27,1.27   # P2 GND escapes, reserved before routing
/usr/bin/python3 "$T/pcb_zones.py" adscsi2000.kicad_pcb
/usr/bin/python3 "$T/pcb_stitch.py" adscsi2000.kicad_pcb --rounds 8 2>&1 | grep -vE "Debug:"
/usr/bin/python3 "$T/pcb_stitch.py" adscsi2000.kicad_pcb --trial 2>&1 | grep -vE "Debug:"
/usr/bin/python3 "$T/pcb_stitch.py" adscsi2000.kicad_pcb --grid 5 2>&1 | grep -vE "Debug:"
/usr/bin/python3 "$T/pcb_stitch.py" adscsi2000.kicad_pcb --groups 2>&1 | grep -vE "Debug:"
/usr/bin/python3 "$T/pcb_manual.py" adscsi2000.kicad_pcb 2>&1 | grep -vE "Debug:"     # hand edits (manual_vias.tsv)
/usr/bin/python3 "$T/pcb_cleanup.py" adscsi2000.kicad_pcb 2>&1 | grep -vE "Debug:"
/usr/bin/python3 "$T/pcb_silk.py" adscsi2000.kicad_pcb 2>&1 | grep -vE "Debug:"
/usr/bin/python3 "$T/pcb_exclude.py" adscsi2000.kicad_pcb                                  # accepted warnings (drc_accepted.tsv)
