#!/usr/bin/env python3
"""Find solder-tinned pads (bright, unsaturated blobs) on the registered solder-side photo.
Writes pads_detected.tsv: id, x, y (component-side photo coordinates), area. Plots an overlay for inspection."""
import os, sys
from collections import deque
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photo

def blobs(mask, amin, amax):
    H, W = mask.shape; lab = np.zeros(mask.shape, np.int32); out = []; n = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]: continue
        n += 1; q = deque([(y0, x0)]); lab[y0, x0] = n; ys = []; xs = []
        while q:
            y, x = q.popleft(); ys.append(y); xs.append(x)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n; q.append((ny, nx))
        if amin <= len(xs) <= amax:
            out.append((float(np.mean(xs)), float(np.mean(ys)), len(xs), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1))
    return out

if __name__ == '__main__':
    outdir = sys.argv[1]
    c, s = photo.images()
    a = np.asarray(s).astype(int)
    mx, mn = a.max(axis=2), a.min(axis=2)
    silver = (mn > 120) & (mx - mn < 70)
    found = blobs(silver, 40, 2000)
    pads = [b for b in found if b[3] <= 40 and b[4] <= 40]
    with open(os.path.join(outdir, 'pads_detected.tsv'), 'w') as f:
        f.write('id\tx\ty\tarea\tw\th\n')
        for i, (x, y, ar, w, h) in enumerate(sorted(pads, key=lambda p: (round(p[1] / 8), p[0]))):
            f.write(f'{i}\t{x:.1f}\t{y:.1f}\t{ar}\t{w}\t{h}\n')
    im = s.copy(); d = ImageDraw.Draw(im)
    for (x, y, ar, w, h) in pads:
        d.ellipse((x - 7, y - 7, x + 7, y + 7), outline=(255, 0, 255), width=2)
    im.save(os.path.join(outdir, 'pads_overlay.jpg'), quality=85)
    print(len(found), 'silver blobs,', len(pads), 'pad-sized; areas', sorted(int(p[2]) for p in pads)[::max(1, len(pads)//20)])
