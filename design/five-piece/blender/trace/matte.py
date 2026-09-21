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
sys.path.insert(0, HERE)
from characters import CHARACTERS
from raster import (close, dilate, fill_holes, flood, hsv, open_,
                    polygon_mask, area_resize, load_image, save_image)


# --------------------------------------------------------------------- main

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = argv[argv.index("--char") + 1] if "--char" in argv else "nuggette"
    ch = CHARACTERS[name]
    cut = ch.cutout
    assert cut, "%s needs no matte; its reference is already a cutout" % name

    px = load_image(bpy, cut.source)
    H, W = px.shape[:2]
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
    # a margin all round.
    f = cut.height / (y1 - y0 + 1)
    pad = int(round(cut.margin / f))
    cx0, cy0 = x0 - pad, y0 - pad
    cw, ch_ = (x1 - x0 + 1) + 2 * pad, (y1 - y0 + 1) + 2 * pad
    ow, oh = int(round(cw * f)), int(round(ch_ * f))
    print("derived crop=(%d, %d, %d, %d), out=(%d, %d)   # freezes the frame"
          % (cx0, cy0, cw, ch_, ow, oh))
    if cut.crop:
        cx0, cy0, cw, ch_ = cut.crop
        ow, oh = cut.out
        f = ow / cw

    sub = (slice(max(0, cy0), cy0 + ch_), slice(max(0, cx0), cx0 + cw))
    a = m[sub].astype(np.float32)
    # Premultiply before averaging, or the scene bleeds into the edge pixels.
    pm = rgb[sub] * a[:, :, None]
    ad = area_resize(a, ow, oh)
    cd = area_resize(pm, ow, oh) / np.maximum(ad, 1e-4)[:, :, None]
    out = np.concatenate([np.clip(cd, 0, 1), ad[:, :, None]], -1)
    print("cutout %dx%d  scale %.4f" % (ow, oh, f))

    save_image(bpy, ch.reference, out, "cutout")
    print("wrote", ch.reference)


main()
