#!/usr/bin/env python3
"""Write KiCad DRC exclusions for the warnings listed in schematic/kicad/drc_accepted.tsv (type, pad REF.PIN, reason).
Exclusions are keyed on item uuids, which change whenever the board is regenerated, so they are rebuilt from the
current DRC each time (last step of pcb_finish.sh). Format (KiCad 10, found by test):
  "<type>|<x nm>|<y nm>|<zone uuid>|<pad uuid>|<layer>"   with the reason as the exclusion comment.
usage: python3 pcb_exclude.py BOARD.kicad_pcb [drc_accepted.tsv]
"""
import csv, json, os, re, subprocess, sys, tempfile

def main(board, tsv):
    acc = {(r['type'], r['pad']): r['reason'] for r in csv.DictReader((l for l in open(tsv) if not l.startswith('#')), delimiter='\t')}
    pro = os.path.splitext(board)[0] + '.kicad_pro'
    p = json.load(open(pro)); p['board']['design_settings']['drc_exclusions'] = []    # see every violation first
    json.dump(p, open(pro, 'w'), indent=2)
    out = os.path.join(tempfile.mkdtemp(), 'drc.json')
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-error', '--severity-warning', '-o', out, board],
                   capture_output=True)
    excl, used = [], set()
    for v in json.load(open(out)).get('violations', []):
        pads = [i for i in v['items'] if re.match(r'(PTH )?[Pp]ad ', i['description'])]
        if not pads: continue
        m = re.search(r'[Pp]ad (\S+) \[[^\]]*\] of (\S+)', pads[0]['description'])
        key = (v['type'], f'{m.group(2)}.{m.group(1)}') if m else None
        if key not in acc: continue
        other = [i for i in v['items'] if i is not pads[0]]
        lay = re.search(r'layer (\w+\.Cu)', v['description'])
        s = f"{v['type']}|{round(pads[0]['pos']['x'] * 1e6)}|{round(pads[0]['pos']['y'] * 1e6)}|" \
            f"{other[0]['uuid'] if other else ''}|{pads[0]['uuid']}" + (f"|{lay.group(1)}" if lay else '')
        excl.append([s, acc[key]]); used.add(key)
    p = json.load(open(pro)); p['board']['design_settings']['drc_exclusions'] = excl
    json.dump(p, open(pro, 'w'), indent=2)
    missing = sorted(set(acc) - used)
    print(f'DRC exclusions: {len(excl)} written' + (f'; listed but not found (fixed?): {missing}' if missing else ''))

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, '..', 'kicad', 'drc_accepted.tsv'))
