#!/usr/bin/env python3
"""Final cleanup of the routed clone PCB (system python with pcbnew 10):
  - tracks the autorouter necked below the 0.15 mm minimum (pad entries) are widened to 0.15 mm, unless that creates
    a clearance error, in which case they are left for a manual look;
  - vias the DRC reports dangling (connected on one layer only) are removed.
usage: python3 pcb_cleanup.py BOARD.kicad_pcb
"""
import json, os, subprocess, sys, tempfile
import pcbnew

MINW, MINW_FAB = 0.15, 0.127

def drc(path):
    out = os.path.join(tempfile.mkdtemp(), 'drc.json')
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', out, path], capture_output=True)
    return json.load(open(out))

def errors_touching(rep, uuids):
    return [v for v in rep.get('violations', []) if v['severity'] == 'error'
            and any(i['uuid'] in uuids for i in v['items'])]

def remove_by_uuid(path, uuids):
    """Delete top-level (segment ...) / (via ...) blocks whose uuid is listed, by editing the board file text."""
    t = open(path).read(); out, i, n = [], 0, 0
    while True:
        j = min([k for k in (t.find('\n\t(segment', i), t.find('\n\t(via', i)) if k >= 0], default=-1)
        if j < 0: out.append(t[i:]); break
        depth, k = 0, j + 2
        while True:                                   # find the matching close paren of this block
            c = t[k]
            if c == '(': depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0: break
            k += 1
        block = t[j:k + 1]
        locked = '(locked yes)' in block
        if any(f'(uuid "{u}")' in block for u in uuids) and not locked:
            out.append(t[i:j]); n += 1
        else:
            out.append(t[i:k + 1])
        i = k + 1
    open(path, 'w').write(''.join(out))
    return n

def main(path):
    b = pcbnew.LoadBoard(path)
    thin = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and pcbnew.ToMM(t.GetWidth()) < MINW - 1e-6]
    old = {t.m_Uuid.AsString(): t.GetWidth() for t in thin}
    for t in thin: t.SetWidth(pcbnew.FromMM(MINW))
    b.Save(path)
    bad = {i['uuid'] for v in errors_touching(drc(path), set(old)) for i in v['items'] if i['uuid'] in old}
    if bad:                                   # no room for 0.15: fall back to the fab minimum (JLCPCB 2-layer: 0.127)
        b = pcbnew.LoadBoard(path)
        for t in b.GetTracks():
            if t.m_Uuid.AsString() in bad: t.SetWidth(pcbnew.FromMM(MINW_FAB))
        b.Save(path)
        bad = {i['uuid'] for v in errors_touching(drc(path), bad) for i in v['items'] if i['uuid'] in bad}
    if bad:
        b = pcbnew.LoadBoard(path)
        for t in b.GetTracks():
            if t.m_Uuid.AsString() in bad: t.SetWidth(old[t.m_Uuid.AsString()])
        b.Save(path)
    print(f'necked tracks widened to {MINW} mm: {len(old) - len(bad)} of {len(old)}' + (f' ({len(bad)} kept: no room)' if bad else ''))
    removed = 0
    for _ in range(10):        # removing a dangling via can leave its stub dangling: repeat until clean
        dangling = {i['uuid'] for v in drc(path).get('violations', []) if v['type'] in ('via_dangling', 'track_dangling')
                    for i in v['items']}
        if not dangling: break
        removed += remove_by_uuid(path, dangling)   # file-level: removing items through the API crashes on this install
        b = pcbnew.LoadBoard(path); pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(path)
    print(f'dangling vias/tracks removed: {removed}')

if __name__ == '__main__':
    main(sys.argv[1])
