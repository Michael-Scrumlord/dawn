"""Stage 2: turn the quantized layers into simplified polygons.

Each colour mask is upsampled and smoothed, then its boundary is walked as
directed pixel edges (inside kept on one side), which chains into closed loops
and gives holes the opposite winding for free. Loops are simplified with
Douglas-Peucker and rounded with Chaikin, then grouped into rig slots.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P trace/contours.py -- --char nuggy
"""
import bpy, numpy as np, json, os, math, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from characters import CHARACTERS
from raster import box_blur, dilate, erode, polygon_mask

UP = 1              # extra upsample (the source is already at ch.src scale)

# Which layers a face slot may claim. Without this the big breading regions of
# the torso, whose centres fall near the face, get swallowed by an eye.
FACE_LAYERS = {"ink", "eye_white", "eye_shadow", "iris", "pupil",
               "mouth_dk", "tongue", "bow", "bow_dark"}


# ---------------------------------------------------------------- mask utils

def upsample_smooth(mask, blur_r, f=UP, grow=2):
    """Upsample, round off the staircase, then grow by a hair.

    The growth matters: adjacent colour regions are traced from complementary
    masks and simplification makes their shared edge diverge slightly, which
    would leave hairline gaps. Overlapping by a quarter source pixel closes
    them well below anything visible at render size.
    """
    up = np.repeat(np.repeat(mask.astype(np.float32), f, 0), f, 1)
    up = (box_blur(box_blur(up, blur_r), blur_r) > 0.5) if blur_r else (up > 0.5)
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


def chaikin(pts, iters):
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
            if x0 + (y - y0) / (y1 - y0) * (x1 - x0) > x:
                inside = not inside
    return inside


# --------------------------------------------------------------------- main

def slot_for(ch, layer, pts, region):
    """Which rig slot a traced shape belongs to.

    Membership is by containment, not by centre: a shape joins a face slot
    only if it fits entirely inside that slot's box, and joins a limb only if
    it sits outside the body core and near that limb's joint.
    """
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0b, y0b, x1b, y1b = min(xs), min(ys), max(xs), max(ys)

    for name, (x0, y0, x1, y1) in ch.roi:
        if layer not in ch.slot_layers.get(name, FACE_LAYERS):
            continue
        if x0b >= x0 and y0b >= y0 and x1b <= x1 and y1b <= y1:
            return name

    if region not in ("body", "limb"):
        return region
    if region == "limb" and ch.limb_anchors:
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        best = min(ch.limb_anchors,
                   key=lambda k: (ch.limb_anchors[k][0] - cx) ** 2
                                 + (ch.limb_anchors[k][1] - cy) ** 2)
        ax, ay = ch.limb_anchors[best]
        if (ax - cx) ** 2 + (ay - cy) ** 2 <= ch.limb_max_dist ** 2:
            return best
    return "body"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ch = CHARACTERS[argv[argv.index("--char") + 1] if "--char" in argv else "nuggy"]
    out_dir = ch.out_dir()
    src, names, colors = ch.src, ch.names, ch.colors

    labels = np.load(os.path.join(out_dir, "labels.npy"))
    h, w = labels.shape
    opaque = labels >= 0
    print("%s: labels %dx%d (=%dx%d ref)" % (ch.name, w, h, w // src, h // src))

    # Two ways to split limbs off the torso.
    #
    # Morphological: open the silhouette and call whatever that removes a
    # limb, then hand each piece to the nearest joint. It costs nothing to set
    # up and works on a figure whose limbs are obviously thinner than its body.
    #
    # Explicit: draw the cut. Nuggette is one huge round mass with limbs as
    # thick as an arm of the torso, so no radius separates them -- opening
    # either leaves the arms welded on or shaves every popcorn bump off the
    # perimeter. Where the cut goes is a rigging decision anyway, the same one
    # you make cutting a paper puppet apart, so it is better made by hand.
    if ch.limb_polys:
        regions, claimed = [], np.zeros_like(opaque)
        for slot, poly in ch.limb_polys.items():
            m = polygon_mask(poly, w, h, src) & opaque & ~claimed
            claimed |= m
            regions.append((slot, m))
            print("  cut %-6s %7d px" % (slot, int(m.sum())))
        regions.insert(0, ("body", opaque & ~claimed))
    else:
        body_core = dilate(erode(opaque, ch.open_r * src), ch.open_r * src)
        regions = [("body", body_core | ~opaque), ("limb", opaque & ~body_core)]
        print("  body core %d  limbs %d"
              % (int(regions[0][1].sum()), int(regions[1][1].sum())))

    sil = upsample_smooth(opaque, ch.blur_r, grow=0)

    shapes = []
    # silhouette gives the crisp dark rim; skinfill sits just inside it so a
    # feature switched off shows skin underneath instead of a dark hole.
    for li, name in enumerate(["silhouette", "skinfill"] + names):
        if name == "silhouette":
            raw = opaque
        elif name == "skinfill":
            raw = erode(opaque, 2 * src)
        else:
            raw = labels == li - 2

        outers, holes, loops, part_of = [], [], [], {}
        for rname, rmask in regions:
            m = raw & rmask
            if not m.any():
                continue
            m = upsample_smooth(m, ch.blur_r,
                                grow=0 if name == "silhouette" else 1) & sil
            for lp in trace_loops(m):
                part_of[id(lp)] = rname
                loops.append(lp)
        for lp in loops:
            a = signed_area(lp)
            floor = ch.min_area_ink if name in ch.fine_layers else ch.min_area
            if abs(a) < floor * (UP * src) ** 2:
                continue
            pts = chaikin(rdp(lp, ch.rdp_eps), ch.chaikin)
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
            def ref(p):
                return [p[0] / (UP * src), p[1] / (UP * src)]
            rings = [[ref(p) for p in op]] + [[ref(p) for p in hp]
                                              for hp in assigned[i]]
            cx = sum(p[0] for p in rings[0]) / len(rings[0])
            cy = sum(p[1] for p in rings[0]) / len(rings[0])
            shapes.append({
                "layer": name,
                "color": colors.get(name, colors["ink"]),
                "slot": slot_for(ch, name, rings[0], rname),
                "region": rname,
                "area": area / (UP * src) ** 2,
                "centroid": [cx, cy],
                "rings": rings,
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

    pivots = {k: list(v) for k, v in ch.pivots.items()}
    for slot in (ch.limb_polys or ch.limb_anchors):
        if slot in pivots:
            continue
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

    with open(os.path.join(out_dir, "trace.json"), "w") as f:
        json.dump({"size": [w // src, h // src], "pivots": pivots,
                   "shapes": shapes}, f)
    print("wrote trace.json")


main()
