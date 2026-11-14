#!/usr/bin/env python3
"""Copper masks for both board sides (component-side coordinates)."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photo

def masks(g_min_s=92, g_min_c=92):
    c, s = photo.images()
    out = {}
    for side, im, gmin in (('c', c, g_min_c), ('s', s, g_min_s)):
        a = np.asarray(im).astype(int); r, g, b = a[..., 0], a[..., 1], a[..., 2]
        trace = (g >= gmin) & (r < 90) & (g > b - 10)          # lighter green/teal under solder mask
        silver = (np.minimum(np.minimum(r, g), b) > 120) & (a.max(axis=2) - a.min(axis=2) < 70)
        out[side] = trace | silver
    return out

if __name__ == '__main__':
    from PIL import Image
    box = tuple(int(v) for v in sys.argv[1].split(',')); outp = sys.argv[2]
    m = masks()
    x0, y0, x1, y1 = box
    tiles = [Image.fromarray((m[k][y0:y1, x0:x1] * 255).astype(np.uint8)).resize(((x1 - x0) * 2, (y1 - y0) * 2)) for k in 'cs']
    canvas = Image.new('L', (tiles[0].width * 2 + 10, tiles[0].height), 128)
    canvas.paste(tiles[0], (0, 0)); canvas.paste(tiles[1], (tiles[0].width + 10, 0)); canvas.save(outp)
