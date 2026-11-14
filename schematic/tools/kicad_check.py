#!/usr/bin/env python3
"""Compare the KiCad schematic's exported netlist with the measured netlist (schematic/netlist/merged.csv).
usage: python3 kicad_check.py adscsi2000.net"""
import csv, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
RENAME = {'+12V': 'P12V'}

def parse_kicad_net(path):
    t = open(path).read()
    t = t[t.index('(nets'):]
    nets = {}
    for block in re.split(r'\(net\s*\(code', t)[1:]:
        name = re.search(r'\(name\s+"([^"]*)"\)', block).group(1).lstrip('/')
        nodes = {f'{r}.{p}' for r, p in re.findall(r'\(ref\s+"([^"]+)"\)\s*\(pin\s+"([^"]+)"\)', block)}
        nodes = {n for n in nodes if not n.startswith('#')}
        if nodes: nets[RENAME.get(name, name)] = nodes
    return nets

def main():
    kn = parse_kicad_net(sys.argv[1])
    meas = {r['net']: set(r['members'].split()) for r in csv.DictReader(open(os.path.join(ROOT, 'netlist', 'merged.csv')))}
    ok = bad = 0
    for name, mem in sorted(meas.items()):
        k = kn.get(name)
        if k == mem: ok += 1; continue
        bad += 1
        print(f'MISMATCH {name}: measured-only {sorted(mem - (k or set()))}, schematic-only {sorted((k or set()) - mem)}')
    extra = {n: m for n, m in kn.items() if n not in meas and len(m) > 1}
    for n, m in extra.items(): print(f'EXTRA schematic net {n}: {sorted(m)}'); bad += 1
    singles = sum(1 for n, m in kn.items() if n not in meas and len(m) == 1)
    print(f'{ok} nets identical, {bad} differences; {singles} single-pin (unconnected) nets in the schematic')
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
