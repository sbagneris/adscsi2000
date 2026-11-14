#!/usr/bin/env python3
"""Inspection crops: a board box rendered from the best tile of a side, pins numbered (magenta), vias (yellow).
usage: python3 view.py <component|solder> x0 y0 x1 y1 out.jpg [scale] [refs...]"""
import os, sys, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tiles, solder_nets as sn

def view(side, box, out, scale=2.4, refs=None, show_vias=True, tile=None):
    pins, vias = sn.load_points()
    img, t = tiles.render(side, box, scale, tile=tile)
    for (r, p), (x, y) in pins.items():
        if refs and r not in refs: continue
        px, py = int((x - box[0]) * scale), int((y - box[1]) * scale)
        if 0 <= px < img.shape[1] and 0 <= py < img.shape[0]:
            cv2.circle(img, (px, py), int(3 * scale), (255, 0, 255), 1)
            cv2.putText(img, f'{p}' if refs and len(refs) == 1 else f'{r}.{p}', (px - 10, py - int(4 * scale)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)
    if show_vias:
        for k, (x, y) in vias.items():
            px, py = int((x - box[0]) * scale), int((y - box[1]) * scale)
            if 0 <= px < img.shape[1] and 0 <= py < img.shape[0]:
                cv2.circle(img, (px, py), int(2.5 * scale), (0, 255, 255), 1)
                cv2.putText(img, k, (px + 6, py + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
    cv2.imwrite(out, img); return t

if __name__ == '__main__':
    side, x0, y0, x1, y1, out = sys.argv[1], *map(float, sys.argv[2:6]), sys.argv[6]
    scale = float(sys.argv[7]) if len(sys.argv) > 7 else 2.4
    print(view(side, (x0, y0, x1, y1), out, scale, sys.argv[8:] or None))
