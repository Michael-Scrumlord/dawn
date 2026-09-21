"""Stage 1: posterize the reference into named flat colour layers.

Per-character: every constant below (source image, seed colours, feature
boxes, thresholds) comes from one `Character` in `characters.py`, picked with
`--char`. The algorithm is shared; only the measurements differ.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P trace/quantize.py -- --char nuggy

Three things stop a naive nearest-colour match from working here.

The source is only a few hundred px wide, so ink strokes are one to three
pixels and classifying them at native size gives jagged, broken linework.
Upsampling first turns the anti-aliased edges into ramps, and the class
boundary then lands on the sub-pixel position the artist actually drew.

Feature colours (eyes, a mouth, a star, an earring) are often near-duplicates
of the body's dark shading, so each is only allowed inside the boxes where
that feature lives (`Character.allow`).

The body is airbrushed rather than cel-shaded, so posterizing it speckles; a
mode filter restricted to the non-feature tones (`Character.gold`) cleans
that up without eating the thin ink lines that draw the breading.
"""
import bpy, numpy as np, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from characters import CHARACTERS

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "nuggy"
ch = CHARACTERS[CHAR]

REF = ch.reference
OUT = ch.out_dir()
os.makedirs(OUT, exist_ok=True)

SRC = ch.src              # upsample factor applied before classifying
INK = 0
INK_LUM = ch.ink_lum       # below this, a body-tone pixel is really linework

SEEDS = ch.seeds
NAMES = ch.names
GOLD = list(ch.gold)       # every layer that isn't ink or a boxed feature

ALLOW = ch.allow

# The rim is an edge-only tone in Nuggy's palette (the dark olive he's inked
# with); characters without one just omit it from seeds and this is a no-op.
# It is fenced out of every ROI box, or it eats fine feature linework that
# fades into body colour through the same tone (a brow tip against the rim,
# say).
RIM_BAND = ch.rim_band     # reference px inward from the silhouette edge
ROI_BOXES = [box for _, box in ch.roi]


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def box_sum(a, r=1):
    k = 2 * r + 1
    p = np.pad(a.astype(np.float32), r)
    c = np.cumsum(np.cumsum(p, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    h, w = a.shape
    return (c[k:k + h, k:k + w] - c[0:h, k:k + w]
            - c[k:k + h, 0:w] + c[0:h, 0:w])


def erode(m, r):
    return box_sum(m, r) >= (2 * r + 1) ** 2 - 0.5


def dilate(m, r):
    return box_sum(m, r) > 0.5


def edge_extend(rgb, opaque, iters=4):
    """Bleed the artwork outward into transparent pixels.

    Without this the upsample pulls the transparent background into the rim
    and lightens the outline all the way around the character.
    """
    out = rgb.copy()
    known = opaque.copy()
    for _ in range(iters):
        if known.all():
            break
        n = box_sum(known, 1)
        acc = np.stack([box_sum(out[:, :, c] * known, 1) for c in range(3)], -1)
        fill = (~known) & (n > 0)
        out[fill] = acc[fill] / n[fill][:, None]
        known |= fill
    return out


def upscale(a, f):
    """Bilinear upsample; recovers sub-pixel edges from the anti-aliasing."""
    h, w = a.shape[:2]
    yy = (np.arange(h * f) + 0.5) / f - 0.5
    xx = (np.arange(w * f) + 0.5) / f - 0.5
    y0 = np.floor(yy).astype(int)
    x0 = np.floor(xx).astype(int)
    wy = (yy - y0).reshape(-1, 1, 1)
    wx = (xx - x0).reshape(1, -1, 1)
    y0c, y1c = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    x0c, x1c = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
    if a.ndim == 2:
        a = a[:, :, None]
        squeeze = True
    else:
        squeeze = False
    r = (a[y0c][:, x0c] * (1 - wy) * (1 - wx) + a[y0c][:, x1c] * (1 - wy) * wx
         + a[y1c][:, x0c] * wy * (1 - wx) + a[y1c][:, x1c] * wy * wx)
    return r[:, :, 0] if squeeze else r


def load_ref():
    img = bpy.data.images.load(REF)
    img.colorspace_settings.name = "Non-Color"   # raw sRGB, not linear
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    return px[::-1]                               # Blender buffers are bottom-up


def main():
    px = load_ref()
    rgb0, a0 = px[:, :, :3], px[:, :, 3]
    op0 = a0 > 0.5
    print("source %dx%d  opaque %d" % (rgb0.shape[1], rgb0.shape[0], int(op0.sum())))

    rgb = upscale(edge_extend(rgb0, op0), SRC)
    opaque = upscale(a0, SRC) > 0.5
    h, w = opaque.shape
    print("upsampled %dx%d  opaque %d" % (w, h, int(opaque.sum())))

    # Per-seed loop rather than one (h, w, n_seeds, 3) broadcast: a high-res
    # character (Chic-Li's cutout is 3x Nuggy's width) times SRC=4 times a
    # couple dozen seeds blows well past what a broadcast array can hold in
    # memory, and this needs none of it -- (h, w, n_seeds) is the only shape
    # that has to exist at once.
    seeds = np.stack([hex_rgb(c) for _, c in SEEDS]).astype(np.float32)
    dist = np.empty((h, w, len(SEEDS)), dtype=np.float32)
    for i in range(len(SEEDS)):
        d = rgb - seeds[i]
        dist[:, :, i] = (d * d).sum(-1)

    yy, xx = np.mgrid[0:h, 0:w]

    def box_mask(boxes):
        ok = np.zeros((h, w), dtype=bool)
        for x0, y0, x1, y1 in boxes:
            ok |= ((xx >= x0 * SRC) & (xx <= x1 * SRC)
                   & (yy >= y0 * SRC) & (yy <= y1 * SRC))
        return ok

    for name, boxes in ALLOW.items():
        dist[:, :, NAMES.index(name)][~box_mask(boxes)] = np.inf

    if "rim" in NAMES:
        edge_band = opaque & ~erode(opaque, RIM_BAND * SRC)
        dist[:, :, NAMES.index("rim")][~(edge_band & ~box_mask(ROI_BOXES))] = np.inf

    labels = dist.argmin(-1).astype(np.int16)
    labels[~opaque] = -1

    # Mode filter, gold tones only, so the airbrushed body stops speckling.
    for _ in range(2):
        is_gold = np.isin(labels, GOLD)
        counts = np.stack([box_sum(labels == g, SRC // 2) for g in GOLD])
        best = np.array(GOLD)[counts.argmax(0)]
        labels = np.where(is_gold, best, labels).astype(np.int16)
        labels[~opaque] = -1

    # Reclaim dark pixels the gold tones stole, then close small gaps so the
    # outlines read as continuous strokes instead of dashes.
    lum = rgb.max(-1)
    is_gold = np.isin(labels, GOLD)
    labels = np.where(is_gold & (lum < INK_LUM) & opaque, INK, labels).astype(np.int16)
    ink = labels == INK
    closed = erode(dilate(ink, SRC // 2), SRC // 2)
    labels = np.where(closed & ~ink & np.isin(labels, GOLD), INK,
                      labels).astype(np.int16)
    labels[~opaque] = -1

    tot = int((labels >= 0).sum())
    for i, n in enumerate(NAMES):
        c = int((labels == i).sum())
        print("  %-11s %8d  %5.2f%%" % (n, c, 100 * c / tot))

    np.save(os.path.join(OUT, "labels.npy"), labels)
    with open(os.path.join(OUT, "meta.txt"), "w") as f:
        f.write("%d\n" % SRC)

    prev = np.ones((h, w, 4), dtype=np.float32)
    for i in range(len(SEEDS)):
        prev[labels == i, :3] = seeds[i]
    prev[labels < 0] = (1, 1, 1, 1)
    out = bpy.data.images.new("prev", w, h, alpha=True)
    out.colorspace_settings.name = "Non-Color"
    out.pixels = prev[::-1].ravel().tolist()
    out.filepath_raw = os.path.join(OUT, "quantized.png")
    out.file_format = "PNG"
    out.save()
    print("wrote", OUT)


main()
