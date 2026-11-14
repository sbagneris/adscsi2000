#!/usr/bin/env python3
"""Board photo helpers: register the solder-side photo onto component-side coordinates and crop both sides.

Registration: perspective transform fitted on the four mounting holes (centres found as enclosed blue blobs,
values below). The solder side is seen from the back, so its top-left hole is the component side's top-right.
All coordinates in this project are component-side photo pixels (2031 x 1485, origin top-left).
"""
import os, sys
import numpy as np
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
COMP = os.path.join(ROOT, 'inputs', 'board_component_side.jpg')
SOLD = os.path.join(ROOT, 'inputs', 'board_solder_side.jpg')
# mounting hole centres (x, y): component side TL, TR, BL, BR, and the matching holes on the raw solder photo
HOLES_C = [(97.9, 44.4), (1958.4, 48.0), (94.0, 1349.5), (1968.0, 1351.1)]
HOLES_S = [(1955.0, 49.5), (53.5, 48.5), (1960.5, 1354.5), (54.5, 1353.1)]   # solder TR, TL, BR, BL

def homography(src, dst):
    A, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    h = np.linalg.solve(np.array(A, float), np.array(b, float))
    return np.append(h, 1).reshape(3, 3)

H_C2S = homography(HOLES_C, HOLES_S)          # component-side coords -> raw solder photo coords

def c2s(x, y):
    p = H_C2S @ np.array([x, y, 1.0]); return p[0] / p[2], p[1] / p[2]

_cache = {}
def images():
    if not _cache:
        comp = Image.open(COMP).convert('RGB')
        sold = Image.open(SOLD).convert('RGB')
        # PIL's PERSPECTIVE maps each output (component) pixel to an input (solder) pixel: coefficients of H_C2S
        h = H_C2S
        coeffs = (h[0, 0], h[0, 1], h[0, 2], h[1, 0], h[1, 1], h[1, 2], h[2, 0], h[2, 1])
        _cache['c'] = comp
        _cache['s'] = sold.transform(comp.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    return _cache['c'], _cache['s']

def crop_pair(box, out, scale=2, marks=()):
    """Side by side: component side (left) and registered solder side (right) of box = (x0, y0, x1, y1).
    marks: [(x, y, label)] drawn on both halves (component-side coordinates)."""
    from PIL import ImageDraw
    c, s = images()
    x0, y0, x1, y1 = box
    w, h = (x1 - x0) * scale, (y1 - y0) * scale
    canvas = Image.new('RGB', (2 * w + 10, h), (255, 255, 255))
    for i, im in enumerate((c, s)):
        part = im.crop(box).resize((w, h), Image.LANCZOS)
        d = ImageDraw.Draw(part)
        for (mx, my, lab) in marks:
            px, py = (mx - x0) * scale, (my - y0) * scale
            d.ellipse((px - 4, py - 4, px + 4, py + 4), outline=(255, 0, 255), width=2)
            if lab: d.text((px + 6, py - 6), str(lab), fill=(255, 0, 255))
        canvas.paste(part, (i * (w + 10), 0))
    canvas.save(out)
    return out

if __name__ == '__main__':
    c, s = images()
    out = sys.argv[1] if len(sys.argv) > 1 else 'solder_registered.png'
    s.save(out)
    for (x, y) in HOLES_C:
        print(f'hole ({x}, {y}) -> solder photo {tuple(round(v, 1) for v in c2s(x, y))}')
