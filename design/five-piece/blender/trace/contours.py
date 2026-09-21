"""Stage 2: turn the quantized layers into simplified polygons.

Each colour mask is upsampled and smoothed, then its boundary is walked as
directed pixel edges (inside kept on one side), which chains into closed loops
and gives holes the opposite winding for free. Loops are simplified with
Douglas-Peucker and rounded with Chaikin, then grouped into feature slots by
region of interest so the rig can still swap eyes, brows and mouth.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P trace/contours.py
"""
import bpy, numpy as np, json, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

UP = 1              # extra upsample (the source is already at SRC scale)
SRC = 4             # scale of the label map relative to the reference image
MIN_AREA_PX = 2.4   # drop specks smaller than this, in source pixels
MIN_AREA_INK = 0.7  # keep fine linework: the breading detail is tiny strokes
RDP_EPS = 1.2       # in label-map pixels
CHAIKIN = 2
BLUR_R = 0          # mask smoothing radius, in label-map pixels

NAMES = ["ink", "gold_pale", "gold_light", "gold_base", "gold_mid", "gold_deep",
         "amber", "shade", "shade_deep", "rim", "eye_white", "eye_shadow",
         "iris", "pupil", "mouth_dk", "tongue"]

COLORS = {
    "ink": "#281108", "gold_pale": "#F7E3A0", "gold_light": "#F1BA40",
    "gold_base": "#EBA126", "gold_mid": "#DD9127", "amber": "#A96E25",
    "shade": "#9C5B1D", "shade_deep": "#834315", "gold_deep": "#C98426",
    "rim": "#6A5507", "skinfill": "#EBA126", "eye_white": "#FAF6D1",
    "eye_shadow": "#D9C199", "iris": "#8A5A28", "pupil": "#3A1E0C",
    "mouth_dk": "#4A1A18", "tongue": "#D9736E",
}

# Face slots, as boxes in source-image pixels: (x0, y0, x1, y1). A contour
# joins the first box that contains its centroid. Brow and upper lid are one
# connected black mass in this artwork, so each eye slot owns both.
ROI = [
    ("sweat",  ( 90,  85, 126, 200)),
    ("sweat",  (216, 184, 244, 218)),
    ("eye_L",  (118,  84, 202, 166)),
    ("eye_R",  (198,  96, 250, 174)),
    ("mouth",  (150, 168, 220, 226)),
]

# Which layers each slot may claim. Without this the big gold shading regions
# of the torso, whose centres fall near the face, get swallowed by an eye. The
# sweat drops are the exception that needs gold_pale: the artist painted their
# highlights in the same cream as the body's.
FACE_LAYERS = {"ink", "eye_white", "eye_shadow", "iris", "pupil",
               "mouth_dk", "tongue"}
SLOT_LAYERS = {"sweat": FACE_LAYERS | {"gold_pale"}}

# Limbs are found geometrically rather than boxed: anything outside the body
# core (the silhouette with thin parts opened away) belongs to the nearest
# limb anchor. Boxes get ambiguous where the raised fist passes the eye.
LIMB_ANCHORS = {
    "arm_L": (85, 178), "arm_R": (268, 168),
    "leg_L": (105, 285), "leg_R": (238, 265),
}
OPEN_R = 22        # erosion radius (reference px) that opens limbs away
# The bumpy crown also survives the opening in places, and those crumbs would
# otherwise join whichever limb is nearest. The farthest real limb piece is a
# hand at 82px from its anchor, so anything past this is not a limb.
LIMB_MAX_DIST = 110


# ---------------------------------------------------------------- mask utils

def box_sum(a, r=1):
    k = 2 * r + 1
    p = np.pad(a.astype(np.float32), r)
    c = np.cumsum(np.cumsum(p, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    h, w = a.shape
    return (c[k:k + h, k:k + w] - c[0:h, k:k + w]
            - c[k:k + h, 0:w] + c[0:h, 0:w])


def box_blur(a, r=1):
    return box_sum(a, r) / ((2 * r + 1) ** 2)


def erode(m, r):
    k = 2 * r + 1
    return box_sum(m, r) >= k * k - 0.5


def dilate(m, r):
    return box_sum(m, r) > 0.5


def upsample_smooth(mask, f=UP, grow=2):
    """Upsample, round off the staircase, then grow by a hair.

    The growth matters: adjacent colour regions are traced from complementary
    masks and simplification makes their shared edge diverge slightly, which
    would leave hairline gaps. Overlapping by a quarter source pixel closes
    them well below anything visible at render size.
    """
    up = np.repeat(np.repeat(mask.astype(np.float32), f, 0), f, 1)
    if BLUR_R:
        up = box_blur(box_blur(up, BLUR_R), BLUR_R) > 0.5
    else:
        up = up > 0.5
    return dilate(up, grow) if grow else up


# ------------------------------------------------------------- contour trace

def trace_loops(mask):
    """All closed boundary loops of a binary mask, as pixel-corner polygons.

    Walks directed unit edges with the filled side kept consistently on one
    hand, so outer boundaries and holes come out with opposite winding.
    """
    h, w = mask.shape
    p = np.zeros((h + 2, w + 2), dtype=bool)
    p[1:-1, 1:-1] = mask

    inside = p[1:-1, 1:-1]
    up = ~p[0:-2, 1:-1]
    dn = ~p[2:, 1:-1]
    lf = ~p[1:-1, 0:-2]
    rt = ~p[1:-1, 2:]

    nxt = {}

    def add(sr, sc, er, ec):
        nxt.setdefault((sc, sr), []).append((ec, er))

    for r, c in np.argwhere(inside & up):
        add(r, c, r, c + 1)
    for r, c in np.argwhere(inside & rt):
        add(r, c + 1, r + 1, c + 1)
    for r, c in np.argwhere(inside & dn):
        add(r + 1, c + 1, r + 1, c)
    for r, c in np.argwhere(inside & lf):
        add(r + 1, c, r, c)

    loops = []
    for start in list(nxt.keys()):
        while nxt.get(start):
            loop = [start]
            cur = start
            while True:
                opts = nxt.get(cur)
                if not opts:
                    break
                nd = opts.pop()
                if not opts:
                    del nxt[cur]
                if nd == start:
                    break
                loop.append(nd)
                cur = nd
            if len(loop) >= 4:
                loops.append(loop)
    return loops


def signed_area(pts):
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))


def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = (abs(dy * px - dx * py + bx * ay - by * ax) / L) if L > 1e-9 \
                else math.hypot(px - ax, py - ay)
            if d > best:
                best, bi = d, i
        if best > eps:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def chaikin(pts, iters=CHAIKIN):
    for _ in range(iters):
        out = []
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        pts = out
    return pts


def point_in(poly, pt):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xx = x0 + (y - y0) / (y1 - y0) * (x1 - x0)
            if xx > x:
                inside = not inside
    return inside


# --------------------------------------------------------------------- main

def slot_for(layer, pts, limb_mask, region):
    """Which rig slot a traced shape belongs to.

    Membership is by containment, not by centre: a shape joins a face slot
    only if it fits entirely inside that slot's box, and joins a limb only if
    nearly all of it sits outside the body core.
    """
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0b, y0b, x1b, y1b = min(xs), min(ys), max(xs), max(ys)

    for name, (x0, y0, x1, y1) in ROI:
        if layer not in SLOT_LAYERS.get(name, FACE_LAYERS):
            continue
        if x0b >= x0 and y0b >= y0 and x1b <= x1 and y1b <= y1:
            return name

    if region == "limb":
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        best = min(LIMB_ANCHORS,
                   key=lambda k: (LIMB_ANCHORS[k][0] - cx) ** 2
                                 + (LIMB_ANCHORS[k][1] - cy) ** 2)
        ax, ay = LIMB_ANCHORS[best]
        if (ax - cx) ** 2 + (ay - cy) ** 2 <= LIMB_MAX_DIST ** 2:
            return best
    return "body"


def main():
    labels = np.load(os.path.join(OUT, "labels.npy"))
    h, w = labels.shape
    opaque = labels >= 0
    body_core = dilate(erode(opaque, OPEN_R * SRC), OPEN_R * SRC)
    limb_mask = opaque & ~body_core
    print("labels %dx%d (=%dx%d ref)  body core %d  limbs %d"
          % (w, h, w // SRC, h // SRC, int(body_core.sum()), int(limb_mask.sum())))

    sil = upsample_smooth(opaque, grow=0)

    # A single gold region runs unbroken from the torso out into an arm, so no
    # per-shape rule can separate them. Cut every layer along the body-core
    # boundary first and trace the two sides independently; the grow step then
    # makes the pieces overlap slightly so the cut leaves no seam.
    regions = [("body", ~limb_mask), ("limb", limb_mask)]

    shapes = []
    # silhouette gives the crisp dark rim; skinfill sits just inside it so a
    # feature switched off shows skin underneath instead of a dark hole.
    for li, name in enumerate(["silhouette", "skinfill"] + NAMES):
        if name == "silhouette":
            raw = opaque
        elif name == "skinfill":
            raw = erode(opaque, 2 * SRC)
        else:
            raw = labels == li - 2
        parts = [(rn, raw & rm) for rn, rm in regions]

        outers, holes = [], []
        loops = []
        part_of = {}
        for rname, rmask in parts:
            if not rmask.any():
                continue
            m = upsample_smooth(rmask, grow=0 if name == "silhouette" else 1) & sil
            for lp in trace_loops(m):
                part_of[id(lp)] = rname
                loops.append(lp)
        for lp in loops:
            a = signed_area(lp)
            floor = MIN_AREA_INK if name == "ink" else MIN_AREA_PX
            if abs(a) < floor * (UP * SRC) ** 2:
                continue
            pts = chaikin(rdp(lp, RDP_EPS))
            if a > 0:
                outers.append((abs(a), pts, part_of[id(lp)]))
            else:
                holes.append((abs(a), pts))

        # nest each hole under the smallest outer that contains it
        assigned = [[] for _ in outers]
        for _, hp in holes:
            probe = hp[0]
            best, bi = None, -1
            for i, (oa, op, _rn) in enumerate(outers):
                if point_in(op, probe) and (best is None or oa < best):
                    best, bi = oa, i
            if bi >= 0:
                assigned[bi].append(hp)

        for i, (area, op, rname) in enumerate(outers):
            ref_pts = [(p[0] / (UP * SRC), p[1] / (UP * SRC)) for p in op]
            cx = sum(p[0] for p in ref_pts) / len(ref_pts)
            cy = sum(p[1] for p in ref_pts) / len(ref_pts)
            shapes.append({
                "layer": name,
                "color": COLORS.get(name, "#281108"),
                "slot": slot_for(name, ref_pts, limb_mask, rname),
                "area": area / (UP * SRC) ** 2,
                "centroid": [cx, cy],
                "rings": [[[p[0] / (UP * SRC), p[1] / (UP * SRC)] for p in op]]
                         + [[[p[0] / (UP * SRC), p[1] / (UP * SRC)] for p in hp]
                            for hp in assigned[i]],
            })
        print("  %-11s loops=%-4d outers=%-4d holes=%d"
              % (name, len(loops), len(outers), len(holes)))

    # Where each limb joins the torso. Deriving this from the attachment mask
    # does not work: the bumpy silhouette leaves opened-away crumbs all round
    # the body, they get assigned to whichever limb is nearest, and they drag
    # the centroid off the joint. Taking the limb's own points nearest the body
    # centre is stable, and it lands on the cut, which is what a limb has to
    # rotate and scale about if it is to stay attached.
    bpts = [p for sh in shapes if sh["slot"] == "body"
            for r in sh["rings"] for p in r]
    bcx = sum(p[0] for p in bpts) / len(bpts)
    bcy = sum(p[1] for p in bpts) / len(bpts)

    pivots = {}
    for slot in LIMB_ANCHORS:
        pts = [p for sh in shapes if sh["slot"] == slot
               for r in sh["rings"] for p in r]
        if not pts:
            continue
        pts.sort(key=lambda p: (p[0] - bcx) ** 2 + (p[1] - bcy) ** 2)
        near = pts[:max(8, len(pts) // 10)]
        pivots[slot] = [sum(p[0] for p in near) / len(near),
                        sum(p[1] for p in near) / len(near)]
    print("body centre (%.0f,%.0f)  pivots: %s"
          % (bcx, bcy, {k: [round(v) for v in p] for k, p in pivots.items()}))

    from collections import Counter
    print("\nby slot:", dict(Counter(s["slot"] for s in shapes)))
    print("total shapes:", len(shapes),
          " total points:", sum(len(r) for s in shapes for r in s["rings"]))

    with open(os.path.join(OUT, "trace.json"), "w") as f:
        json.dump({"size": [w // SRC, h // SRC], "pivots": pivots,
                   "shapes": shapes}, f)
    print("wrote trace.json")


main()
