"""Stage 0: cut a character out of a full illustration.

Nuggy's reference was already a clean cutout on transparency, so the tracer
could key the silhouette straight off the alpha channel. Miss Nuggette's is a
painted scene: fryer, oil swirls, Japanese titling, VHS grain, and a ground
that is the same golden-brown as she is. This stage produces the cutout the
rest of the pipeline expects.

Colour alone cannot do it. The ground under her feet, the dipping-sauce swirls
and the bright rim glow all sit in her exact hue and saturation range. Three
things together do work:

  1. A hand-drawn fence polygon, loose everywhere except along the bottom
     where she meets the ground. It only has to separate her from scenery that
     colour cannot, so it is a dozen-odd points, not a traced silhouette.
  2. A tight core mask flooded from seed points inside her, which finds the
     lit breading and stops at the ink outline.
  3. Geodesic growth of that core through a looser mask, capped at a fixed
     number of steps. This reaches her shadowed parts -- the right pigtail, the
     underside of the body -- without being able to run off into the scene,
     because growth has to start from somewhere already known to be her.

Then an opening removes the thin glowing tendrils that growth picked up along
the rim, and the largest component is kept.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P trace/matte.py -- --char nuggette
"""
import bpy, numpy as np, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from characters import CHARACTERS


# ------------------------------------------------------------------- raster

def box_sum(a, r=1):
    k = 2 * r + 1
    p = np.pad(a.astype(np.float32), r)
    c = np.cumsum(np.cumsum(p, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    h, w = a.shape
    return (c[k:k + h, k:k + w] - c[0:h, k:k + w]
            - c[k:k + h, 0:w] + c[0:h, 0:w])


def dilate(m, r=1):
    return box_sum(m, r) > 0.5


def erode(m, r=1):
    return box_sum(m, r) >= (2 * r + 1) ** 2 - 0.5


def close(m, r):
    return erode(dilate(m, r), r)


def open_(m, r):
    return dilate(erode(m, r), r)


def grow(cur, mask):
    """Flood `cur` through `mask` until it stops changing."""
    while True:
        n = cur.copy()
        n[1:, :] |= cur[:-1, :]
        n[:-1, :] |= cur[1:, :]
        n[:, 1:] |= cur[:, :-1]
        n[:, :-1] |= cur[:, 1:]
        n &= mask
        if n.sum() == cur.sum():
            return cur
        cur = n


def flood(mask, seeds):
    cur = np.zeros_like(mask)
    for x, y in seeds:
        cur[y, x] = True
    return grow(cur & mask, mask)


def fill_holes(m):
    out = np.zeros_like(m)
    out[0, :] = out[-1, :] = out[:, 0] = out[:, -1] = True
    return ~grow(out & ~m, ~m)


def polygon_mask(pts, w, h):
    """Even-odd scanline fill, so this needs no image library."""
    m = np.zeros((h, w), dtype=bool)
    n = len(pts)
    for y in range(h):
        xs = []
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            if (y0 > y) != (y1 > y):
                xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            m[y, max(0, int(a)):max(0, int(b) + 1)] = True
    return m


def hsv(rgb):
    mx = rgb.max(-1)
    mn = rgb.min(-1)
    d = mx - mn + 1e-6
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    h = np.zeros_like(mx)
    m = mx == r
    h[m] = (((g - b) / d) % 6)[m]
    m = mx == g
    h[m] = (((b - r) / d) + 2)[m]
    m = mx == b
    h[m] = (((r - g) / d) + 4)[m]
    return h * 60, np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0), mx


def area_resize(a, ow, oh):
    """Area-average downsample. Doubles as the grain filter."""
    h, w = a.shape[:2]
    flat = a.ndim == 2
    if flat:
        a = a[:, :, None]
    ys = (np.arange(oh + 1) * h / oh).round().astype(int)
    xs = (np.arange(ow + 1) * w / ow).round().astype(int)
    cs = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0), (0, 0))), 0), 1)
    out = (cs[ys[1:, None], xs[None, 1:]] - cs[ys[:-1, None], xs[None, 1:]]
           - cs[ys[1:, None], xs[None, :-1]] + cs[ys[:-1, None], xs[None, :-1]])
    cnt = ((ys[1:] - ys[:-1])[:, None] * (xs[1:] - xs[:-1])[None, :])[:, :, None]
    out = out / cnt
    return out[:, :, 0] if flat else out


# --------------------------------------------------------------------- main

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = argv[argv.index("--char") + 1] if "--char" in argv else "nuggette"
    ch = CHARACTERS[name]
    cut = ch.cutout
    assert cut, "%s needs no matte; its reference is already a cutout" % name

    img = bpy.data.images.load(cut.source)
    img.colorspace_settings.name = "Non-Color"
    W, H = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[::-1]
    rgb = px[:, :, :3]
    hue, sat, val = hsv(rgb)
    print("source %dx%d" % (W, H))

    fence = polygon_mask(cut.fence, W, H)
    warm = (hue > cut.hue[0]) & (hue < cut.hue[1])
    pink = ((hue > cut.pink_hue) | (hue < cut.hue[0])) & (sat > 0.30)

    core = flood(((warm & (sat > 0.55) & (val > 0.40))
                  | (pink & (val > 0.35))) & fence, cut.seeds)
    loose = ((warm & (sat > 0.50) & (val > 0.15))
             | (pink & (val > 0.18))) & fence
    m = core
    for _ in range(cut.grow_steps):
        m = dilate(m, 1) & loose
    m = fill_holes(close(m, 5))
    m = flood(open_(m, cut.open_r), cut.seeds)
    m = fill_holes(close(m, cut.open_r))

    ys, xs = np.where(m)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    print("silhouette %dx%d at (%d,%d)" % (x1 - x0 + 1, y1 - y0 + 1, x0, y0))

    # Scale so the silhouette lands at the height the trace is tuned for, with
    # a margin all round, then snap the crop to that exact aspect.
    f = cut.height / (y1 - y0 + 1)
    pad = int(round(cut.margin / f))
    cx0, cy0 = x0 - pad, y0 - pad
    cw, ch_ = (x1 - x0 + 1) + 2 * pad, (y1 - y0 + 1) + 2 * pad
    ow, oh = int(round(cw * f)), int(round(ch_ * f))

    sub = (slice(max(0, cy0), cy0 + ch_), slice(max(0, cx0), cx0 + cw))
    a = m[sub].astype(np.float32)
    # Premultiply before averaging, or the scene bleeds into the edge pixels.
    pm = rgb[sub] * a[:, :, None]
    ad = area_resize(a, ow, oh)
    cd = area_resize(pm, ow, oh) / np.maximum(ad, 1e-4)[:, :, None]
    out = np.concatenate([np.clip(cd, 0, 1), ad[:, :, None]], -1)
    print("cutout %dx%d  scale %.4f" % (ow, oh, f))

    im = bpy.data.images.new("cutout", ow, oh, alpha=True)
    im.colorspace_settings.name = "Non-Color"
    im.alpha_mode = "STRAIGHT"
    im.pixels = out[::-1].ravel().tolist()
    im.filepath_raw = ch.reference
    im.file_format = "PNG"
    im.save()
    print("wrote", ch.reference)


main()
