"""Stage 1: posterize the reference into named flat colour layers.

Run with Blender's Python (it has numpy; the system Python does not):
    /Applications/Blender.app/Contents/MacOS/Blender -b -P trace/quantize.py

Three things stop a naive nearest-colour match from working here.

The source is only 306px wide, so the ink strokes are one to three pixels and
classifying them at native size gives jagged, broken linework. Upsampling first
turns the anti-aliased edges into ramps, and the class boundary then lands on
the sub-pixel position the artist actually drew.

The eye and mouth colours are near-duplicates of the body's dark shading, so
they are only allowed inside the boxes where those features live.

The body is airbrushed rather than cel-shaded, so posterizing it speckles; a
mode filter restricted to the gold tones cleans that up without eating the thin
ink lines that draw the breading.
"""
import bpy, numpy as np, os

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.normpath(os.path.join(HERE, "..", "..", "reference", "nuggy-canon.webp"))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

SRC = 4            # upsample factor applied before classifying
INK = 0
INK_LUM = 0.30     # below this, a "gold" pixel is really linework

SEEDS = [
    ("ink",        "#281108"),
    ("gold_pale",  "#F7E3A0"),
    ("gold_light", "#F1BA40"),
    ("gold_base",  "#EBA126"),
    ("gold_mid",   "#DD9127"),
    ("gold_deep",  "#C98426"),
    ("amber",      "#A96E25"),
    ("shade",      "#9C5B1D"),
    ("shade_deep", "#834315"),
    ("rim",        "#6A5507"),
    ("eye_white",  "#FAF6D1"),
    ("eye_shadow", "#D9C199"),
    ("iris",       "#8A5A28"),
    ("pupil",      "#3A1E0C"),
    ("mouth_dk",   "#4A1A18"),
    ("tongue",     "#D9736E"),
]
NAMES = [n for n, _ in SEEDS]
GOLD = [NAMES.index(n) for n in
        ("gold_pale", "gold_light", "gold_base", "gold_mid", "gold_deep",
         "amber", "shade", "shade_deep", "rim")]

# Boxes (x0, y0, x1, y1) in ORIGINAL source pixels, read off the reference.
EYES = (118, 96, 252, 178)
MOUTH = (146, 164, 224, 230)
SWEAT = [(96, 98, 132, 196), (216, 184, 244, 218)]

ALLOW = {
    "eye_white":  [EYES, MOUTH] + SWEAT,
    "eye_shadow": [EYES, MOUTH],
    "iris":       [EYES],
    "pupil":      [EYES],
    "mouth_dk":   [MOUTH],
    "tongue":     [MOUTH],
}

# The rim is the dark olive the artist edged the silhouette with. It is only
# ever an edge tone: left unfenced it eats the brow tips, where the ink fades
# into gold through the same olive range.
RIM_BAND = 4       # reference px inward from the silhouette edge


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

    seeds = np.stack([hex_rgb(c) for _, c in SEEDS])
    dist = ((rgb[:, :, None, :] - seeds[None, None, :, :]) ** 2).sum(-1)

    yy, xx = np.mgrid[0:h, 0:w]

    def box_mask(boxes):
        ok = np.zeros((h, w), dtype=bool)
        for x0, y0, x1, y1 in boxes:
            ok |= ((xx >= x0 * SRC) & (xx <= x1 * SRC)
                   & (yy >= y0 * SRC) & (yy <= y1 * SRC))
        return ok

    for name, boxes in ALLOW.items():
        dist[:, :, NAMES.index(name)][~box_mask(boxes)] = np.inf

    edge_band = opaque & ~erode(opaque, RIM_BAND * SRC)
    dist[:, :, NAMES.index("rim")][~(edge_band & ~box_mask([EYES, MOUTH]))] = np.inf

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
