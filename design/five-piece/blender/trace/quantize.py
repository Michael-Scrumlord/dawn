"""Stage 1: posterize a reference into named flat colour layers.

Run with Blender's Python (it has numpy; the system Python does not):
    /Applications/Blender.app/Contents/MacOS/Blender -b -P trace/quantize.py -- --char nuggy

Three things stop a naive nearest-colour match from working.

Ink strokes are only a few pixels wide, so classifying at native size gives
jagged, broken linework. Upsampling first turns the anti-aliased edges into
ramps, and the class boundary then lands on the sub-pixel position the artist
actually drew.

The eye and mouth colours are near-duplicates of the body's dark shading, so
they are only allowed inside the boxes where those features live. Those boxes,
and every colour seed, are measured per character and live in characters.py.

The breading is airbrushed rather than cel-shaded, so posterizing it speckles;
a mode filter restricted to the breading tones cleans that up without eating
the thin ink lines.
"""
import bpy, numpy as np, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from characters import CHARACTERS
from raster import (box_sum, dilate, erode, edge_extend, upscale,
                    load_image, save_image)

INK = 0


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ch = CHARACTERS[argv[argv.index("--char") + 1] if "--char" in argv else "nuggy"]
    out_dir = ch.out_dir()
    os.makedirs(out_dir, exist_ok=True)
    names, src = ch.names, ch.src

    px = load_image(bpy, ch.reference)
    rgb0, a0 = px[:, :, :3], px[:, :, 3]
    op0 = a0 > 0.5
    print("%s: source %dx%d  opaque %d"
          % (ch.name, rgb0.shape[1], rgb0.shape[0], int(op0.sum())))

    rgb = upscale(edge_extend(rgb0, op0), src)
    opaque = upscale(a0, src) > 0.5
    h, w = opaque.shape

    # Per-seed loop rather than one (h, w, n_seeds, 3) broadcast: a high-res
    # character (a full-scene cutout, several times Nuggy's width) times a 4x
    # upsample times a couple dozen seeds blows well past what a broadcast
    # array can hold in memory, and this needs none of it -- (h, w, n_seeds)
    # is the only shape that has to exist at once.
    seeds = np.stack([hex_rgb(c) for _, c in ch.seeds]).astype(np.float32)
    dist = np.empty((h, w, len(ch.seeds)), dtype=np.float32)
    for i in range(len(ch.seeds)):
        d = rgb - seeds[i]
        dist[:, :, i] = (d * d).sum(-1)

    yy, xx = np.mgrid[0:h, 0:w]

    def box_mask(boxes):
        ok = np.zeros((h, w), dtype=bool)
        for x0, y0, x1, y1 in boxes:
            ok |= ((xx >= x0 * src) & (xx <= x1 * src)
                   & (yy >= y0 * src) & (yy <= y1 * src))
        return ok

    for name, boxes in ch.allow.items():
        dist[:, :, names.index(name)][~box_mask(boxes)] = np.inf

    # The rim is the dark olive some artwork edges the silhouette with. It is
    # only ever an edge tone: left unfenced it eats the brow tips, where ink
    # fades into gold through the same olive range.
    if "rim" in names:
        band = opaque & ~erode(opaque, ch.rim_band * src)
        feature_boxes = [b for bs in ch.allow.values() for b in bs]
        dist[:, :, names.index("rim")][~(band & ~box_mask(feature_boxes))] = np.inf

    labels = dist.argmin(-1).astype(np.int16)
    labels[~opaque] = -1

    # Mode filter, breading tones only, so the airbrushed body stops speckling.
    gold = ch.gold
    for _ in range(ch.mode_passes):
        is_gold = np.isin(labels, gold)
        counts = np.stack([box_sum(labels == g, src // 2) for g in gold])
        best = np.array(gold)[counts.argmax(0)]
        labels = np.where(is_gold, best, labels).astype(np.int16)
        labels[~opaque] = -1

    # Reclaim dark pixels the breading tones stole, then close small gaps so
    # the outlines read as continuous strokes instead of dashes.
    lum = rgb.max(-1)
    is_gold = np.isin(labels, gold)
    labels = np.where(is_gold & (lum < ch.ink_lum) & opaque, INK,
                      labels).astype(np.int16)
    ink = labels == INK
    closed = erode(dilate(ink, src // 2), src // 2)
    labels = np.where(closed & ~ink & np.isin(labels, gold), INK,
                      labels).astype(np.int16)
    labels[~opaque] = -1

    tot = int((labels >= 0).sum())
    for i, n in enumerate(names):
        c = int((labels == i).sum())
        print("  %-11s %8d  %5.2f%%" % (n, c, 100 * c / tot))

    np.save(os.path.join(out_dir, "labels.npy"), labels)

    prev = np.ones((h, w, 4), dtype=np.float32)
    for i in range(len(ch.seeds)):
        prev[labels == i, :3] = seeds[i]
    prev[labels < 0] = (1, 1, 1, 1)
    save_image(bpy, os.path.join(out_dir, "quantized.png"), prev, "quantized")
    print("wrote", out_dir)


main()
