#!/usr/bin/env python3
"""Connect GND pads that the pours leave stranded (system python with pcbnew 10).

After the autorouter has routed every other net and pcb_zones.py has poured GND on both layers, some GND pads stay
isolated: the Zorro GND fingers (on the tab, below the pour) and pads boxed in by tracks. For each GND item that
kicad-cli DRC reports unconnected, try the shortest straight stub (0.5 mm, Power class) from the pad centre in 16
directions on each of the pad's copper layers, ending well inside the GND fill of that layer; failing that, a stub
ending in a via that lands in the other layer's fill. Clearance to all other-net copper is checked with KiCad's own
shape collision (0.25 mm, the pour clearance); stubs stay 0.6 mm inside the board outline. Pour islands reported
unconnected to each other get a stitching via where both fills overlap. Repeat (refill, DRC) until nothing changes.

usage: python3 pcb_stitch.py BOARD.kicad_pcb [--rounds N]
"""
import json, math, os, subprocess, sys, tempfile
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb_gen import BOARD

MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
W_STUB, CLR, VIA_D, VIA_DRILL, EDGE = 0.5, 0.25, 0.8, 0.4, 0.6
LENGTHS = [x / 2 for x in range(2, 17)]                       # 1.0 .. 8.0 mm
DIRS = [(math.cos(a * math.pi / 8), math.sin(a * math.pi / 8)) for a in range(16)]

def V(x, y): return pcbnew.VECTOR2I(MM(x), MM(y))

def inside_board(x, y, m=EDGE):
    """Inside the outline (main rectangle or tab) with margin m."""
    if not (m <= x <= BOARD['W'] - m and m <= y): return False
    return y <= BOARD['Hs'] - m or (x >= BOARD['Tx'] + m and y <= BOARD['Ht'] - m)

class Stitcher:
    def __init__(self, path):
        self.path = path
        self.b = pcbnew.LoadBoard(path)
        self.gnd = self.b.FindNet('GND').GetNetCode()
        self.cache = {}; self.clr = CLR; self.w = W_STUB

    def obstacles(self, layer):
        out = []
        for t in self.b.GetTracks():
            if t.GetNetCode() != self.gnd and t.IsOnLayer(layer): out.append(t)
        for fp in self.b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetCode() != self.gnd and p.IsOnLayer(layer): out.append(p)
        return out

    def holes(self):
        """(x, y, drill) of every drilled item, any net: new vias keep hole-to-hole spacing even from GND vias."""
        if 'holes' not in self.cache:
            h = [(TOMM(t.GetPosition().x), TOMM(t.GetPosition().y), TOMM(t.GetDrillValue()))
                 for t in self.b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
            h += [(TOMM(p.GetPosition().x), TOMM(p.GetPosition().y), TOMM(p.GetDrillSize().x))
                  for fp in self.b.GetFootprints() for p in fp.Pads() if p.GetDrillSize().x > 0]
            self.cache['holes'] = h
        return self.cache['holes']

    def via_spaced(self, x, y):
        return all(math.hypot(x - hx, y - hy) >= VIA_DRILL / 2 + d / 2 + 0.35 and
                   math.hypot(x - hx, y - hy) >= VIA_D / 2 + 0.2 + d / 2 for hx, hy, d in self.holes())

    def clear(self, shape, layer, obs):
        bb = shape.BBox(); margin = MM(self.clr + 1.5)
        for o in obs:
            ob = o.GetBoundingBox()
            if ob.GetRight() < bb.GetLeft() - margin or ob.GetLeft() > bb.GetRight() + margin or \
               ob.GetBottom() < bb.GetTop() - margin or ob.GetTop() > bb.GetBottom() + margin: continue
            if o.GetEffectiveShape(layer).Collide(shape, MM(self.clr)): return False
        return True

    MIN_ISLAND = 150.0      # mm2: only the large fill islands count (the main pour); small ones may be orphans

    def big_islands(self, layer):
        key = ('isl', layer)
        if key not in self.cache:
            isl = []
            for z in self.b.Zones():
                if z.GetNetCode() != self.gnd or not z.IsOnLayer(layer): continue
                fp = z.GetFilledPolysList(layer)
                outs = [(abs(fp.Outline(i).Area()) / 1e12, fp.Outline(i)) for i in range(fp.OutlineCount())]
                top = max((a for a, _ in outs), default=0)
                # the main pour: islands of at least a quarter of the largest (strips along the tab can exceed any
                # fixed threshold while still being cut off from the body of the pour)
                isl += [(z, o) for a, o in outs if a >= max(self.MIN_ISLAND, top / 4)]
            self.cache[key] = isl
        return self.cache[key]

    def in_fill(self, layer, x, y, r=0.45):
        pts = [(x, y)] + [(x + r * c, y + r * s) for c, s in DIRS[::4]]
        for z, o in self.big_islands(layer):
            if o.PointInside(V(x, y)) and all(z.HitTestFilledArea(layer, V(px, py)) for px, py in pts): return True
        return False

    def add_track(self, layer, a, b_):
        t = pcbnew.PCB_TRACK(self.b); t.SetLayer(layer); t.SetWidth(MM(self.w))
        t.SetStart(V(*a)); t.SetEnd(V(*b_)); t.SetNetCode(self.gnd); self.b.Add(t)

    def add_via(self, x, y):
        self.cache.pop('holes', None)
        v = pcbnew.PCB_VIA(self.b); v.SetPosition(V(x, y)); v.SetWidth(MM(VIA_D)); v.SetDrill(MM(VIA_DRILL))
        v.SetNetCode(self.gnd); self.b.Add(v)

    def stitch_pad(self, pad):
        pos = pad.GetPosition(); x0, y0 = TOMM(pos.x), TOMM(pos.y)
        layers = [l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if pad.IsOnLayer(l)]
        obs = {l: self.obstacles(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)}
        best = None
        for L in layers:
            other = pcbnew.B_Cu if L == pcbnew.F_Cu else pcbnew.F_Cu
            for d in LENGTHS:
                if best and d >= best[0]: break
                for c, s in DIRS:
                    x, y = x0 + c * d, y0 + s * d
                    if not inside_board(x, y): continue
                    seg = pcbnew.SHAPE_SEGMENT(V(x0, y0), V(x, y), MM(W_STUB))
                    if not self.clear(seg, L, obs[L]): continue
                    if self.in_fill(L, x, y):
                        best = (d, L, (x, y), False); break
                    via = pcbnew.SHAPE_CIRCLE(V(x, y), MM(VIA_D / 2))
                    if (best is None or d + 0.5 < best[0]) and self.in_fill(other, x, y, 0.6) and \
                       self.via_spaced(x, y) and self.clear(via, L, obs[L]) and self.clear(via, other, obs[other]):
                        best = (d + 0.5, L, (x, y), True)          # a via costs a little more than a stub
                if best and best[0] <= d: break
        if not best: return self.maze(pad)
        d, L, end, via = best
        self.add_track(L, (x0, y0), end)
        if via: self.add_via(*end)
        return True

    def maze(self, pad, half=30.0, g=0.25, goal_fn=None):
        """A* on a g-mm grid, both layers, in a window around the pad: from the pad to a cell inside the main GND
        fill of either layer, through cells where a stub-width track clears all other-net copper; vias where a via
        clears both layers. The path becomes tracks (straight runs merged) and vias."""
        import heapq
        x0, y0 = TOMM(pad.GetPosition().x), TOMM(pad.GetPosition().y)
        n = int(2 * half / g) + 1
        LAY = (pcbnew.F_Cu, pcbnew.B_Cu)
        obs = {l: self.obstacles(l) for l in LAY}
        rt = self.w / 2 + g * 0.71                      # track + half a cell diagonal: conservative
        free, viaok, goal = {}, {}, {}
        def xy(i, j): return x0 - half + i * g, y0 - half + j * g
        def isfree(li, i, j):
            k = (li, i, j)
            if k not in free:
                x, y = xy(i, j)
                free[k] = inside_board(x, y) and self.clear(pcbnew.SHAPE_CIRCLE(V(x, y), MM(rt)), LAY[li], obs[LAY[li]])
            return free[k]
        def isvia(i, j):
            if (i, j) not in viaok:
                x, y = xy(i, j); c = pcbnew.SHAPE_CIRCLE(V(x, y), MM(VIA_D / 2))
                viaok[(i, j)] = inside_board(x, y) and self.via_spaced(x, y) and all(self.clear(c, l, obs[l]) for l in LAY)
            return viaok[(i, j)]
        def isgoal(li, i, j):
            k = (li, i, j)
            if k not in goal:
                goal[k] = (goal_fn(LAY[li], *xy(i, j)) if goal_fn else self.in_fill(LAY[li], *xy(i, j), r=W_STUB / 2 + 0.3))
            return goal[k]
        c0 = int(round(half / g))
        start = [(li, c0, c0) for li, l in enumerate(LAY) if pad.IsOnLayer(l)]
        dist = {s: 0.0 for s in start}; prev = {}
        heap = [(0.0, s) for s in start]; end = None; pad_r = TOMM(min(pad.GetSize().x, pad.GetSize().y)) / 2
        while heap:
            dcur, cur = heapq.heappop(heap)
            if dcur > dist.get(cur, 1e9): continue
            li, i, j = cur
            x, y = xy(i, j)
            if dcur > 0 and math.hypot(x - x0, y - y0) > pad_r and isgoal(li, i, j): end = cur; break
            if dcur > 150: break
            steps = [((li, i + di, j + dj), math.hypot(di, dj) * g) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj]
            if isvia(i, j): steps.append(((1 - li, i, j), 2.0))
            for nb, cost in steps:
                nl, ni, nj = nb
                if not (0 <= ni < n and 0 <= nj < n): continue
                nx, ny = xy(ni, nj)
                inpad = math.hypot(nx - x0, ny - y0) <= pad_r and pad.IsOnLayer(LAY[nl])
                if not inpad and not isfree(nl, ni, nj): continue
                nd = dcur + cost
                if nd < dist.get(nb, 1e9): dist[nb] = nd; prev[nb] = cur; heapq.heappush(heap, (nd, nb))
        if end is None: return False
        self.last_end = (LAY[end[0]], *xy(end[1], end[2]))
        path = [end]
        while path[-1] in prev: path.append(prev[path[-1]])
        path.reverse()
        k = 0
        while k < len(path) - 1:                       # emit straight runs per layer, vias at layer changes
            li = path[k][0]; m = k
            if path[k + 1][0] != li:
                self.add_via(*xy(path[k][1], path[k][2])); k += 1; continue
            d0 = (path[k + 1][1] - path[k][1], path[k + 1][2] - path[k][2])
            while m + 1 < len(path) and path[m + 1][0] == li and (path[m + 1][1] - path[m][1], path[m + 1][2] - path[m][2]) == d0: m += 1
            a = (x0, y0) if k == 0 else xy(path[k][1], path[k][2])
            self.add_track(LAY[li], a, xy(path[m][1], path[m][2])); k = m
        return True

    def stitch_zones(self, pos):
        """Stitching via near pos where both layers' GND fills overlap."""
        obs = {l: self.obstacles(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)}
        x0, y0 = pos
        for r in [0] + LENGTHS:
            for c, s in (DIRS if r else [(0, 0)]):
                x, y = x0 + c * r, y0 + s * r
                if not inside_board(x, y): continue
                via = pcbnew.SHAPE_CIRCLE(V(x, y), MM(VIA_D / 2))
                if self.via_spaced(x, y) and all(self.in_fill(l, x, y, 0.6) and self.clear(via, l, obs[l]) for l in (pcbnew.F_Cu, pcbnew.B_Cu)):
                    self.add_via(x, y); return True
        return False

    def refill_save(self):
        pcbnew.ZONE_FILLER(self.b).Fill(self.b.Zones()); self.b.Save(self.path); self.cache = {}

    def unconnected(self):
        out = os.path.join(tempfile.mkdtemp(), 'drc.json')
        subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json', '-o', out, self.path], capture_output=True)
        return json.load(open(out)).get('unconnected_items', [])

def island_at(b, gnd, layer, x, y, min_area=5.0):
    """(layer, index) of the GND fill island containing (x, y), if its area is at least min_area mm2."""
    for z in b.Zones():
        if z.GetNetCode() != gnd or not z.IsOnLayer(layer): continue
        fp = z.GetFilledPolysList(layer)
        for i in range(fp.OutlineCount()):
            o = fp.Outline(i)
            if abs(o.Area()) / 1e12 >= min_area and o.PointInside(V(x, y)) and z.HitTestFilledArea(layer, V(x, y)):
                return (layer, i)
    return None

def trial(path, tries=8):
    """For each pad still stranded: route to the nearest fill island of any size, refill, DRC on a copy; keep the
    change only if the unconnected count drops, else try the next nearest island. Works on file copies (removing
    items through the Python API is unreliable on this install)."""
    import shutil
    pro = os.path.splitext(path)[0]
    tdir = tempfile.mkdtemp(prefix='stitch-trial-')       # same rules: copy the project and rule files next to it
    for ext in ('.kicad_pro', '.kicad_dru'):
        if os.path.exists(pro + ext): shutil.copy(pro + ext, os.path.join(tdir, 'trial' + ext))
    base = Stitcher(path); base.refill_save(); n0 = len(base.unconnected())
    stranded = []
    pads = {p.m_Uuid.AsString(): p for fp in base.b.GetFootprints() for p in fp.Pads()}
    for it in base.unconnected():
        for i in it['items']:
            if i['uuid'] in pads and i['uuid'] not in stranded: stranded.append(i['uuid'])
    print(f'trial mode: {n0} unconnected, {len(stranded)} stranded pads', flush=True)
    for uid in stranded:
        tried = set()
        for k in range(tries):
            tmp = os.path.join(tdir, 'trial.kicad_pcb'); shutil.copy(path, tmp)
            s = Stitcher(tmp)
            pad = next(p for fp in s.b.GetFootprints() for p in fp.Pads() if p.m_Uuid.AsString() == uid)
            mine = {island_at(s.b, s.gnd, l, TOMM(pad.GetPosition().x), TOMM(pad.GetPosition().y))
                    for l in (pcbnew.F_Cu, pcbnew.B_Cu) if pad.IsOnLayer(l)}
            def goal(layer, x, y):
                isl = island_at(s.b, s.gnd, layer, x, y)
                if isl is None or isl in tried or isl in mine: return False
                r = W_STUB / 2 + 0.3                       # the stub end must sit well inside that island
                return all(island_at(s.b, s.gnd, layer, x + r * c, y + r * sn) == isl for c, sn in DIRS[::4])
            if not s.maze(pad, goal_fn=goal):
                s.w, s.clr = 0.25, 0.2                     # fine mode: board default track/clearance, 0.1 mm grid
                if not s.maze(pad, half=8.0, g=0.1, goal_fn=goal):
                    print(f'  {pad.GetParentFootprint().GetReference()}.{pad.GetNumber()}: no more islands'); break
            tried.add(island_at(s.b, s.gnd, *s.last_end))
            s.refill_save(); n = len(s.unconnected())
            ref = f'{pad.GetParentFootprint().GetReference()}.{pad.GetNumber()}'
            if n < n0:
                shutil.move(tmp, path); n0 = n; print(f'  {ref}: island {k + 1} joins the ground ({n} left)', flush=True); break
            print(f'  {ref}: island {k + 1} does not help', flush=True)
    shutil.rmtree(tdir, ignore_errors=True)
    return n0

def grid_stitch(path, pitch=5.0, margin=0.6):
    """GND stitching vias on a pitch-mm grid wherever both layers have GND fill around the spot (margin mm) and a
    via clears all other copper and keeps hole spacing: ties the two pours together across the board (lower ground
    impedance, return paths for the Zorro signals) and reaches fill fragments only joined on one layer."""
    s = Stitcher(path); s.refill_save()
    zs = {l: [z for z in s.b.Zones() if z.GetNetCode() == s.gnd and z.IsOnLayer(l)] for l in (pcbnew.F_Cu, pcbnew.B_Cu)}
    def filled(l, x, y): return any(z.HitTestFilledArea(l, V(x, y)) for z in zs[l])
    obs = {l: s.obstacles(l) for l in (pcbnew.F_Cu, pcbnew.B_Cu)}
    n = 0; x = pitch / 2
    while x < BOARD['W']:
        y = pitch / 2
        while y < BOARD['Ht']:
            ring = [(x, y)] + [(x + (VIA_D / 2 + margin) * c, y + (VIA_D / 2 + margin) * sn) for c, sn in DIRS[::2]]
            if inside_board(x, y, 1.0) and s.via_spaced(x, y) and \
               all(filled(l, px, py) for l in (pcbnew.F_Cu, pcbnew.B_Cu) for px, py in ring):
                via = pcbnew.SHAPE_CIRCLE(V(x, y), MM(VIA_D / 2))
                if all(s.clear(via, l, obs[l]) for l in (pcbnew.F_Cu, pcbnew.B_Cu)):
                    s.add_via(x, y); n += 1
            y += pitch
        x += pitch
    s.refill_save()
    print(f'grid stitching: {n} GND vias on a {pitch} mm grid')

def gnd_groups(b, gnd):
    """Connectivity of GND copper built here (kicad-cli DRC reports a cut-off fill fragment only as 'zone <-> zone' at
    (0, 0)): nodes = fill islands per layer + GND pads, vias, tracks; edges where KiCad's shapes touch. Returns the
    groups, largest first, each a list of items (islands as (layer, outline))."""
    LAY = (pcbnew.F_Cu, pcbnew.B_Cu)
    isl = []
    for z in b.Zones():
        if z.GetNetCode() != gnd: continue
        for L in LAY:
            if z.IsOnLayer(L):
                fp = z.GetFilledPolysList(L); isl += [(L, fp.Outline(i)) for i in range(fp.OutlineCount())]
    items = [t for t in b.GetTracks() if t.GetNetCode() == gnd] + \
            [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetCode() == gnd]
    n = len(isl); par = list(range(n + len(items)))
    def find(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    def apart(p, q): return p.GetRight() < q.GetLeft() or p.GetLeft() > q.GetRight() or p.GetBottom() < q.GetTop() or p.GetTop() > q.GetBottom()
    for k, (L, o) in enumerate(isl):
        bb = o.BBox()
        for j, it in enumerate(items):
            if it.IsOnLayer(L) and not apart(it.GetBoundingBox(), bb) and \
               (it.GetEffectiveShape(L).Collide(o, 0) or o.PointInside(it.GetPosition())): par[find(k)] = find(n + j)
    for a in range(len(items)):
        for c in range(a + 1, len(items)):
            A, C = items[a], items[c]
            L = next((L for L in LAY if A.IsOnLayer(L) and C.IsOnLayer(L)), None)
            if L is not None and not apart(A.GetBoundingBox(), C.GetBoundingBox()) and \
               A.GetEffectiveShape(L).Collide(C.GetEffectiveShape(L), 0): par[find(n + a)] = find(n + c)
    groups = {}
    for k in range(len(par)): groups.setdefault(find(k), []).append(isl[k] if k < n else items[k - n])
    return sorted(groups.values(), key=len, reverse=True)

def join_groups(path, rounds=4):
    """Maze-route a pad of every GND group cut off from the main one (coarse, then fine grid) until all are joined."""
    for rnd in range(rounds):
        s = Stitcher(path); s.refill_save()
        gs = gnd_groups(s.b, s.gnd)
        if len(gs) == 1: print('GND groups: all joined'); return True
        print(f'GND groups: {len(gs) - 1} cut off from the main ground', flush=True)
        joined = 0
        for g in gs[1:]:
            for pad in [x for x in g if not isinstance(x, tuple) and x.Type() == pcbnew.PCB_PAD_T]:
                ok = s.maze(pad)
                if not ok:
                    s.w, s.clr = 0.25, 0.2; ok = s.maze(pad, half=12.0, g=0.1); s.w, s.clr = W_STUB, CLR
                if ok:
                    joined += 1; print(f'  {pad.GetParentFootprint().GetReference()}.{pad.GetNumber()}: joined', flush=True); break
        s.refill_save()
        if not joined: print('  no path found for the remaining groups'); return False
    return False

def main(path, rounds=6):
    s = Stitcher(path)
    for rnd in range(rounds):
        s.refill_save()
        items = s.unconnected()
        gnd_items = [it for it in items if all('[GND]' in i['description'] for i in it['items'])]
        print(f'round {rnd + 1}: {len(items)} unconnected ({len(gnd_items)} GND)', flush=True)
        if not gnd_items: break
        pads = {p.m_Uuid.AsString(): p for fp in s.b.GetFootprints() for p in fp.Pads()}
        done, fixed = set(), 0
        for it in gnd_items:
            targets = [i for i in it['items'] if i['uuid'] in pads]
            if targets:
                for i in targets[:1]:                       # one side of the pair is enough
                    if i['uuid'] in done: continue
                    done.add(i['uuid']); fixed += s.stitch_pad(pads[i['uuid']])
            else:                                           # zone island vs zone island
                p = it['items'][0]['pos']
                if (p['x'], p['y']) == (0.0, 0.0): continue  # KiCad gives zones no position: --groups handles these
                fixed += s.stitch_zones((p['x'], p['y']))
        print(f'  added {fixed} connections', flush=True)
        if not fixed: break
    s.refill_save()
    left = [it for it in s.unconnected()]
    print(f'remaining unconnected: {len(left)}')
    for it in left[:20]: print('  ', ' <-> '.join(i['description'] for i in it['items']))

if __name__ == '__main__':
    rounds = int(sys.argv[sys.argv.index('--rounds') + 1]) if '--rounds' in sys.argv else 6
    if '--groups' in sys.argv: join_groups(sys.argv[1])
    elif '--grid' in sys.argv: grid_stitch(sys.argv[1], float(sys.argv[sys.argv.index('--grid') + 1]))
    elif '--trial' in sys.argv: print('remaining unconnected:', trial(sys.argv[1]))
    else: main(sys.argv[1], rounds)
