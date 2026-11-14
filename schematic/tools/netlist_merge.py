#!/usr/bin/env python3
"""Merge schematic/netlist/*.csv by shared members (union-find). Reports nets joined under different names
(a contradiction somewhere), the merged netlist, and pins of the known parts that are on no net yet.
Writes schematic/netlist/merged.csv."""
import collections, csv, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pinouts import PARTS
import parts as boardparts
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'netlist')

def main():
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    names = collections.defaultdict(set); meaning = {}
    for f in sorted(glob.glob(os.path.join(D, '*.csv'))):
        if f.endswith('merged.csv'): continue
        for n in csv.DictReader(open(f)):
            ms = n['members'].split()
            if n['net'] == 'NC':
                for m in ms: names[m].add('NC')
                continue
            anchor = 'NET:' + n['net']                     # same name in several files = same net
            for m in ms: parent.setdefault(m, m); parent[find(m)] = find(anchor); names[m].add(n['net'])
            meaning.setdefault(n['net'], n['meaning'])
    groups = collections.defaultdict(set)
    for m in list(parent):
        if not m.startswith('NET:'): groups[find(m)].add(m)
    merged, conflicts = [], []
    for root, ms in groups.items():
        nm = set().union(*(names[m] for m in ms)) - {'NC'}
        if len(nm) > 1: conflicts.append((sorted(nm), sorted(ms)))
        merged.append(('/'.join(sorted(nm)), sorted(ms)))
    merged.sort()
    with open(os.path.join(D, 'merged.csv'), 'w', newline='') as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL); w.writerow(['net', 'members', 'meaning'])
        for n, ms in merged: w.writerow([n, ' '.join(ms), meaning.get(n.split('/')[0], '')])
    print(len(merged), 'nets after merging;', 'conflicts:' if conflicts else 'no conflicts')
    for c in conflicts: print('  ', c)
    known = {m for m in parent if not m.startswith('NET:')} | {m for m, s in names.items() if 'NC' in s}
    allpins = {f'{r}.{p}' for r, d in PARTS.items() for p in d}
    allpins |= {f'{r}.{p}' for r in ('U3', 'U4', 'U5') for p in range(1, 21)}
    allpins |= {f'{r}.{p}' for (r, p) in boardparts.pins() if not r.startswith('U')}
    left = collections.defaultdict(list)
    for p in sorted(allpins - known, key=lambda s: (s.split('.')[0], int(s.split('.')[1]))): left[p.split('.')[0]].append(int(p.split('.')[1]))
    print('pins on no net yet:', {k: v for k, v in left.items()})

if __name__ == '__main__':
    main()
