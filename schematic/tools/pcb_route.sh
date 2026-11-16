#!/usr/bin/env bash
# Autoroute the clone PCB's signals with Freerouting; GND is left to the pours (pcb_finish.sh).
#   generate -> reserve GND escapes (lone Zorro GND fingers 13/25, H4 stubs, finger bridges, P2 GND pins) ->
#   Specctra DSN with the GND net reduced to one pin (nothing to route; its escapes stay as obstacles) -> Freerouting
# usage: [OPT=true] pcb_route.sh KICAD_DIR OUT.ses [PASSES]   (about 15 minutes, + 2-3 h with OPT=true: Freerouting's
#        optimizer straightens the routing; then: pcb_finish.sh KICAD_DIR OUT.ses)
set -euo pipefail
T="$(cd "$(dirname "$0")" && pwd)"; D="$1"; SES="$(realpath -m "$2")"; PASSES="${3:-100}"
W="$(mktemp -d)"; cd "$D"
/usr/bin/python3 "$T/pcb_gen.py" . --replace-routed | grep -E "^board|wrote"
/usr/bin/python3 "$T/pcb_fanout.py" adscsi2000.kicad_pcb --only 13,25
/usr/bin/python3 "$T/pcb_fanout.py" adscsi2000.kicad_pcb --holes-only
/usr/bin/python3 "$T/pcb_fanout.py" adscsi2000.kicad_pcb --bridges
/usr/bin/python3 "$T/pcb_fanout.py" adscsi2000.kicad_pcb --pad P2.2:1.27,1.27 --pad P2.6:1.27,1.27 --pad P2.10:1.27,1.27 \
    --pad P2.22:1.27,1.27 --pad P2.13:-1.27,1.27 --pad P2.17:-1.27,1.27
/usr/bin/python3 -c "import pcbnew; assert pcbnew.ExportSpecctraDSN(pcbnew.LoadBoard('adscsi2000.kicad_pcb'), '$W/raw.dsn')"
python3 - "$W/raw.dsn" "$W/in.dsn" <<'PY'
import re, sys
t = open(sys.argv[1]).read()
m = re.search(r'\(net GND\s*\(pins([^)]*)\)\s*\)', t)
open(sys.argv[2], 'w').write(t[:m.start()] + '(net GND (pins P1-1))' + t[m.end():])
PY
java -jar /usr/lib/freerouting/freerouting-executable.jar -de "$W/in.dsn" -do "$SES" -mp "$PASSES" \
    --gui.enabled=false --router.optimizer.enabled="${OPT:-false}" > "$W/freerouting.log" 2>&1
grep -E "Auto-routing stage completed|Optimization stage completed" "$W/freerouting.log" | sed 's/.*INFO *//'
cp "$W/freerouting.log" "${SES%.ses}.freerouting.log"
echo "session: $SES"
