"""Build Nuggy as a flat 2D cutout rig in Blender.

The character is drawn as filled 2D curves stacked on the local Z axis and
parented to a root empty that is rotated upright, so numpad-1 (front view)
looks straight at him. Every face part hangs off a socket empty -- move the
socket and the part follows, Mr. Potatohead style -- and each socket has
several variants whose visibility is driven by a custom property on NUGGY_CTRL.

    blender -b -P nuggy_build.py
    blender -b -P nuggy_build.py -- --render out.png --set eyes=2,mouth=4

Run it again any time; it rebuilds the .blend from scratch.
"""

import bpy
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(HERE, "nuggy.blend")

# --------------------------------------------------------------------------
# palette (read off design/five-piece/reference/nuggy-canon.jpg)
# --------------------------------------------------------------------------

PALETTE = {
    "line":        "#2A1708",
    "bread":       "#E8A324",
    "bread_lit":   "#F7CB5C",
    "bread_shade": "#C27610",
    "speck":       "#A25D0E",
    "crumb":       "#FBDB8E",
    "white":       "#FFFFFF",
    "iris":        "#A9651B",
    "iris_deep":   "#6B3A0B",
    "mouth":       "#7C1220",
    "tongue":      "#E8637A",
    "tongue_dk":   "#C4405A",
    "tooth":       "#FFF6E2",
    "sweat":       "#BFE4F7",
    "accent":      "#D22A2A",
}

# local-Z stacking order; larger = closer to camera
Z = {
    "limb":      -0.10,
    "body":       0.00,
    "shade":      0.05,
    "speck":      0.08,
    "face_back":  0.15,
    "face_mid":   0.20,
    "face_top":   0.25,
    "brow":       0.30,
    "front":      0.40,
}

# Limb width profiles. Holding the noodle thin and flaring only over the last
# fifth is what makes the round end cap read as a hand rather than a blob.
FIST = [0.140, 0.128, 0.120, 0.118, 0.122, 0.190, 0.215]
MITT = [0.140, 0.128, 0.120, 0.116, 0.120, 0.175, 0.198]
FOOT = [0.168, 0.155, 0.146, 0.142, 0.148, 0.185, 0.205]

OUTLINE_W = 0.035   # default outline thickness
DZ = 0.004          # how far an outline sits behind its fill

# body silhouette
BODY_CX, BODY_CY = 0.0, 0.05
BODY_RX, BODY_RY = 1.00, 1.30


# --------------------------------------------------------------------------
# color / material
# --------------------------------------------------------------------------

def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(srgb_to_linear(c) for c in srgb)


MATS = {}


def get_mat(key):
    """Flat emission material -- no lighting, so the render is pure 2D color."""
    if key in MATS:
        return MATS[key]
    rgb = hex_to_linear(PALETTE[key])
    m = bpy.data.materials.new("NUG_" + key)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = rgb + (1.0,)
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.diffuse_color = rgb + (1.0,)
    m.roughness = 1.0
    MATS[key] = m
    return m


# --------------------------------------------------------------------------
# 2D geometry
# --------------------------------------------------------------------------

def signed_area(pts):
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))


def ccw(pts):
    return pts if signed_area(pts) > 0 else pts[::-1]


def offset_poly(pts, w):
    """Grow a closed polygon outward by w along the vertex bisectors."""
    pts = ccw(pts)
    n = len(pts)

    def edge_normal(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        return (dy / L, -dx / L)

    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        n1 = edge_normal(p0, p1)
        n2 = edge_normal(p1, p2)
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        L = math.hypot(mx, my)
        if L < 1e-6:
            mx, my, L = n2[0], n2[1], 1.0
        mx, my = mx / L, my / L
        miter = w / max(mx * n1[0] + my * n1[1], 0.35)
        out.append((p1[0] + mx * miter, p1[1] + my * miter))
    return out


def ellipse(cx, cy, rx, ry, rot=0.0, n=48, a0=0.0, a1=2 * math.pi, closed=True):
    pts = []
    steps = n if closed else n + 1
    for i in range(steps):
        a = a0 + (a1 - a0) * (i / n)
        x, y = rx * math.cos(a), ry * math.sin(a)
        if rot:
            c, s = math.cos(rot), math.sin(rot)
            x, y = x * c - y * s, x * s + y * c
        pts.append((cx + x, cy + y))
    return pts


def circle(cx, cy, r, n=40):
    return ellipse(cx, cy, r, r, n=n)


def stroke(path, widths, ncap=10, round_start=True, round_end=True):
    """Closed outline of a tapered brush stroke down `path`.

    Ramping the width up at the last point and letting the round cap close it
    off is what turns a noodle arm into a mitten hand in one polygon -- one
    polygon means one clean outline, with no seam where a hand was glued on.
    """
    n = len(path)
    tang = []
    for i in range(n):
        if i == 0:
            a, b = path[0], path[1]
        elif i == n - 1:
            a, b = path[-2], path[-1]
        else:
            a, b = path[i - 1], path[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        tang.append((dx / L, dy / L))

    left = [(path[i][0] - tang[i][1] * widths[i], path[i][1] + tang[i][0] * widths[i])
            for i in range(n)]
    right = [(path[i][0] + tang[i][1] * widths[i], path[i][1] - tang[i][0] * widths[i])
             for i in range(n)]

    def cap(center, start_pt, r):
        a0 = math.atan2(start_pt[1] - center[1], start_pt[0] - center[0])
        return [(center[0] + r * math.cos(a0 - math.pi * k / ncap),
                 center[1] + r * math.sin(a0 - math.pi * k / ncap))
                for k in range(1, ncap)]

    pts = list(left)
    if round_end:
        pts += cap(path[-1], left[-1], widths[-1])
    pts += right[::-1]
    if round_start:
        pts += cap(path[0], right[0], widths[0])
    return pts


def resample(path, n):
    """Even-arc-length resample so taper widths spread smoothly down a path."""
    segs = [math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1])
            for i in range(len(path) - 1)]
    total = sum(segs)
    out = []
    for i in range(n):
        d = total * i / (n - 1)
        acc = 0.0
        for j, s in enumerate(segs):
            if acc + s >= d or j == len(segs) - 1:
                t = (d - acc) / (s or 1e-9)
                t = max(0.0, min(1.0, t))
                out.append((path[j][0] + (path[j + 1][0] - path[j][0]) * t,
                            path[j][1] + (path[j + 1][1] - path[j][1]) * t))
                break
            acc += s
    return out


def smooth_path(path, n=24):
    """Catmull-Rom through the control points, then resampled."""
    p = [path[0]] + list(path) + [path[-1]]
    dense = []
    for i in range(len(p) - 3):
        p0, p1, p2, p3 = p[i], p[i + 1], p[i + 2], p[i + 3]
        for k in range(12):
            t = k / 12.0
            t2, t3 = t * t, t * t * t
            dense.append((
                0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
            ))
    dense.append(path[-1])
    return resample(dense, n)


def taper(path_ctrl, w_profile, n=26, **kw):
    """Smooth a control path, spread a width profile over it, return the outline."""
    path = smooth_path(path_ctrl, n)
    widths = resample([(i / (len(w_profile) - 1), w) for i, w in enumerate(w_profile)],
                      n)
    return stroke(path, [w for _, w in widths], **kw)


def lens(rx, ry, open_amt, tilt, n=30):
    """Eye/mouth aperture: fixed lower arc plus a lid curve across the top.

    Returns (closed outline, top edge left->right) so the lid stroke and the
    tooth band can reuse the exact same edge.
    """
    bottom = [(rx * math.cos(math.pi + math.pi * i / n),
               ry * math.sin(math.pi + math.pi * i / n)) for i in range(n + 1)]
    top = []
    for i in range(n + 1):
        t = 1.0 - i / n
        top.append((rx * (2 * t - 1),
                    ry * math.sin(math.pi * t) * (open_amt + tilt * (2 * t - 1))))
    return bottom + top[1:-1], list(reversed(top))


def teardrop(cx, cy, r, h, rot=0.0, n=24):
    pts = ellipse(0, 0, r, r, n=n, a0=math.radians(158), a1=math.radians(382),
                  closed=False)
    pts.append((0.0, h))
    out = []
    c, s = math.cos(rot), math.sin(rot)
    for x, y in pts:
        out.append((cx + x * c - y * s, cy + x * s + y * c))
    return out


def mirror(pts):
    return [(-x, y) for x, y in pts][::-1]


def body_pt(a):
    """Point on the lumpy nugget silhouette at angle a."""
    bump = (1.0
            + 0.040 * math.sin(7.0 * a + 0.9)
            + 0.021 * math.sin(11.0 * a + 2.3)
            + 0.009 * math.sin(17.0 * a + 5.1))
    return (BODY_CX + BODY_RX * bump * math.cos(a),
            BODY_CY + BODY_RY * bump * math.sin(a))


def bow(p0, p1, bulge, n=30):
    """Quadratic-bezier arc p0 -> p1, bowed left of the chord by `bulge`."""
    mx, my = (p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1e-9
    cx, cy = mx - dy / L * bulge * L, my + dx / L * bulge * L
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u * u * p0[0] + 2 * u * t * cx + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * cy + t * t * p1[1]))
    return pts


def cel_region(a_start, a_end, bulge, n=60):
    """Silhouette arc closed off by a bowed terminator -- a hard cel edge."""
    arc = [body_pt(a_start + (a_end - a_start) * i / n) for i in range(n + 1)]
    return arc + bow(arc[-1], arc[0], bulge)[1:-1]


# --------------------------------------------------------------------------
# scene plumbing
# --------------------------------------------------------------------------

def new_coll(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def add_curve(name, shapes, z, coll, parent):
    """One curve object; `shapes` is [(points, material key), ...]."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    slot = {}
    for pts, key in shapes:
        if key not in slot:
            cu.materials.append(get_mat(key))
            slot[key] = len(slot)
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, (x, y) in enumerate(pts):
            sp.points[i].co = (x, y, 0.0, 1.0)
        sp.use_cyclic_u = True
        sp.material_index = slot[key]
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    ob.parent = parent
    ob.matrix_parent_inverse.identity()
    ob.location = (0.0, 0.0, z)
    return ob


def add_part(name, pts, key, z, coll, parent, outline=OUTLINE_W):
    """Filled shape plus, just behind it, a fattened dark copy for the ink line."""
    objs = []
    if outline:
        objs.append(add_curve(name + "_ink", [(offset_poly(pts, outline), "line")],
                              z - DZ, coll, parent))
    objs.append(add_curve(name, [(pts, key)], z, coll, parent))
    return objs


def add_empty(name, loc, parent, coll, size=0.18, kind="PLAIN_AXES"):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = kind
    e.empty_display_size = size
    coll.objects.link(e)
    if parent:
        e.parent = parent
        e.matrix_parent_inverse.identity()
    e.location = loc
    return e


def drive_hidden(objs, ctrl, prop, idx):
    """Hide every object unless ctrl[prop] == idx."""
    for ob in objs:
        for path in ("hide_viewport", "hide_render"):
            fc = ob.driver_add(path)
            d = fc.driver
            d.type = "SCRIPTED"
            v = d.variables.new()
            v.name = "i"
            v.type = "SINGLE_PROP"
            v.targets[0].id_type = "OBJECT"
            v.targets[0].id = ctrl
            v.targets[0].data_path = '["%s"]' % prop
            d.expression = "i != %d" % idx


def add_prop(ctrl, name, count, desc, default=0):
    ctrl[name] = default
    ui = ctrl.id_properties_ui(name)
    ui.update(min=0, max=count - 1, soft_min=0, soft_max=count - 1,
              default=default, description=desc)


# --------------------------------------------------------------------------
# the character
# --------------------------------------------------------------------------

def build_body(coll, root):
    silhouette = [body_pt(2 * math.pi * i / 150) for i in range(150)]
    add_part("BODY", silhouette, "bread", Z["body"], coll, root, outline=0.045)

    add_curve("BODY_shade",
              [(cel_region(math.radians(40), math.radians(-122), -0.10),
                "bread_shade")],
              Z["shade"], coll, root)
    add_curve("BODY_light",
              [(cel_region(math.radians(198), math.radians(96), -0.46),
                "bread_lit")],
              Z["shade"] + 0.01, coll, root)

    # breading texture: dark specks with a few pale crumbs on top
    rng = random.Random(7)
    specks, crumbs = [], []
    placed = []
    while len(placed) < 74:
        a = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.uniform(0, 1)) * 0.86
        ex, ey = body_pt(a)
        x = BODY_CX + (ex - BODY_CX) * rr
        y = BODY_CY + (ey - BODY_CY) * rr
        if any(math.hypot(x - px, y - py) < 0.15 for px, py in placed):
            continue
        placed.append((x, y))
        r = rng.uniform(0.016, 0.042)
        shape = ellipse(x, y, r, r * rng.uniform(0.6, 1.0),
                        rot=rng.uniform(0, math.pi), n=12)
        (crumbs if len(placed) % 5 == 0 else specks).append((shape, None))

    add_curve("BODY_specks", [(s, "speck") for s, _ in specks], Z["speck"], coll, root)
    add_curve("BODY_crumbs", [(s, "crumb") for s, _ in crumbs],
              Z["speck"] + 0.01, coll, root)


def eye_variant(name, coll, socket, *, open_amt, tilt, lid_w, iris,
                pupil, glint, rx=0.30, ry=0.335, spread=0.355, lean=0.10):
    """One eye drawn at the origin, then mirrored for the other side."""
    objs = []
    shape, top = lens(rx, ry, open_amt, tilt)

    for side in (-1, 1):
        dx = spread * side
        tw = math.radians(lean * 12.0) * -side

        def place(pts):
            c, s = math.cos(tw), math.sin(tw)
            return [(dx + x * c - y * s, x * s + y * c) for x, y in
                    ([(px * side, py) for px, py in pts] if side < 0 else pts)]

        tag = "L" if side < 0 else "R"
        objs += add_part("%s_%s" % (name, tag), place(shape), "white",
                         Z["face_back"], coll, socket, outline=0.030)
        if iris:
            objs += [add_curve("%s_%s_iris" % (name, tag),
                               [(place(ellipse(iris[0], iris[1], iris[2], iris[3])),
                                 "iris")], Z["face_mid"], coll, socket)]
            objs += [add_curve("%s_%s_pupil" % (name, tag),
                               [(place(ellipse(pupil[0], pupil[1], pupil[2],
                                               pupil[3])), "iris_deep")],
                               Z["face_mid"] + 0.01, coll, socket)]
        if glint:
            objs += [add_curve("%s_%s_glint" % (name, tag),
                               [(place(circle(*g)), "white") for g in glint],
                               Z["face_top"], coll, socket)]
        if lid_w:
            objs += [add_curve("%s_%s_lid" % (name, tag),
                               [(place(stroke(resample(top, 18),
                                              [lid_w] * 18)), "line")],
                               Z["face_top"] + 0.01, coll, socket)]
    return objs


def build_eyes(coll, socket, ctrl):
    """Canon angry stare first -- index 0 is always the reference look."""
    add_prop(ctrl, "eyes", 4,
             "0 angry (canon)  1 wide  2 tired  3 squeezed shut")

    v = new_coll("eyes_0_angry", coll)
    drive_hidden(eye_variant("eyes_angry", v, socket,
                             open_amt=0.86, tilt=0.30, lid_w=0.055,
                             iris=(0.012, 0.015, 0.160, 0.170),
                             pupil=(0.012, 0.010, 0.085, 0.092),
                             glint=[(-0.055, 0.085, 0.052), (0.075, -0.055, 0.026)]),
                 ctrl, "eyes", 0)

    v = new_coll("eyes_1_wide", coll)
    drive_hidden(eye_variant("eyes_wide", v, socket,
                             open_amt=1.02, tilt=0.0, lid_w=0.040, lean=0.0,
                             rx=0.315, ry=0.355,
                             iris=(0.0, 0.0, 0.175, 0.185),
                             pupil=(0.0, 0.0, 0.080, 0.086),
                             glint=[(-0.065, 0.100, 0.060), (0.080, -0.070, 0.030)]),
                 ctrl, "eyes", 1)

    v = new_coll("eyes_2_tired", coll)
    drive_hidden(eye_variant("eyes_tired", v, socket,
                             open_amt=0.42, tilt=-0.12, lid_w=0.062, lean=0.04,
                             iris=(0.0, -0.030, 0.150, 0.095),
                             pupil=(0.0, -0.035, 0.072, 0.052),
                             glint=[(-0.060, -0.010, 0.036)]),
                 ctrl, "eyes", 2)

    v = new_coll("eyes_3_shut", coll)
    objs = []
    for side in (-1, 1):
        arc = [(-0.26, -0.04), (-0.13, 0.11), (0.0, 0.17), (0.13, 0.11), (0.26, -0.04)]
        arc = [(x * side + 0.355 * side, y) for x, y in arc]
        objs.append(add_curve("eyes_shut_%s" % ("L" if side < 0 else "R"),
                              [(taper(arc, [0.030, 0.062, 0.062, 0.030], n=22), "line")],
                              Z["face_top"], v, socket))
    drive_hidden(objs, ctrl, "eyes", 3)


def build_brows(coll, socket, ctrl):
    add_prop(ctrl, "brows", 4,
             "0 furrowed (canon)  1 raised  2 flat  3 worried")

    # (inner point, outer point, inner half-width, outer half-width)
    specs = [
        ("0_furrowed", (0.10, -0.115), (0.42, 0.055), (0.58, 0.150), 0.090, 0.042),
        ("1_raised",   (0.12, 0.085), (0.40, 0.215), (0.58, 0.170), 0.072, 0.038),
        ("2_flat",     (0.10, 0.030), (0.38, 0.062), (0.58, 0.058), 0.074, 0.042),
        ("3_worried",  (0.10, 0.145), (0.40, 0.045), (0.58, -0.048), 0.084, 0.040),
    ]
    for idx, (vname, p0, p1, p2, wi, wo) in enumerate(specs):
        v = new_coll("brows_" + vname, coll)
        objs = []
        for side in (-1, 1):
            path = [(p0[0] * side, p0[1]), (p1[0] * side, p1[1]), (p2[0] * side, p2[1])]
            shape = taper(path, [wi, (wi + wo) * 0.5, wo], n=20)
            objs.append(add_curve("brow_%s_%s" % (vname, "L" if side < 0 else "R"),
                                  [(shape, "line")], Z["brow"], v, socket))
        drive_hidden(objs, ctrl, "brows", idx)


def build_mouths(coll, socket, ctrl):
    add_prop(ctrl, "mouth", 5,
             "0 battle cry (canon)  1 grin  2 smirk  3 small o  4 tongue out")

    # 0 - battle cry: open maw, tooth band along the lid, tongue at the bottom
    v = new_coll("mouth_0_battlecry", coll)
    shape, top = lens(0.44, 0.40, 0.52, 0.10)
    objs = add_part("mouth_cry", shape, "mouth", Z["face_back"], v, socket,
                    outline=0.042)
    objs.append(add_curve("mouth_cry_teeth",
                          [(stroke(resample([(x, y - 0.040) for x, y in top], 16),
                                   [0.022] * 16), "tooth")],
                          Z["face_mid"], v, socket))
    objs += add_part("mouth_cry_tongue",
                     ellipse(0.02, -0.235, 0.255, 0.150), "tongue",
                     Z["face_mid"] + 0.01, v, socket, outline=0.026)
    objs.append(add_curve("mouth_cry_tongue_groove",
                          [(taper([(0.02, -0.105), (0.02, -0.325)],
                                  [0.016, 0.022], n=10), "tongue_dk")],
                          Z["face_top"], v, socket))
    drive_hidden(objs, ctrl, "mouth", 0)

    # 1 - grin
    v = new_coll("mouth_1_grin", coll)
    shape, top = lens(0.46, 0.26, 0.10, 0.0)
    objs = add_part("mouth_grin", shape, "mouth", Z["face_back"], v, socket,
                    outline=0.040)
    objs.append(add_curve("mouth_grin_teeth",
                          [(stroke(resample([(x, y - 0.022) for x, y in top], 16),
                                   [0.046] * 16), "tooth")],
                          Z["face_mid"], v, socket))
    drive_hidden(objs, ctrl, "mouth", 1)

    # 2 - smirk
    v = new_coll("mouth_2_smirk", coll)
    objs = [add_curve("mouth_smirk",
                      [(taper([(-0.30, 0.02), (0.0, -0.10), (0.30, 0.06)],
                              [0.026, 0.050, 0.026], n=20), "line")],
                      Z["face_mid"], v, socket)]
    drive_hidden(objs, ctrl, "mouth", 2)

    # 3 - small o
    v = new_coll("mouth_3_smallo", coll)
    objs = add_part("mouth_smallo", ellipse(0.0, -0.06, 0.135, 0.175), "mouth",
                    Z["face_back"], v, socket, outline=0.034)
    drive_hidden(objs, ctrl, "mouth", 3)

    # 4 - tongue out, exhausted
    v = new_coll("mouth_4_tongueout", coll)
    shape, _ = lens(0.36, 0.26, 0.34, -0.16)
    objs = add_part("mouth_lolly", shape, "mouth", Z["face_back"], v, socket,
                    outline=0.038)
    objs += add_part("mouth_lolly_tongue",
                     ellipse(0.10, -0.26, 0.170, 0.215, rot=math.radians(-14)),
                     "tongue", Z["face_mid"], v, socket, outline=0.028)
    drive_hidden(objs, ctrl, "mouth", 4)


def build_arms(coll, socket, ctrl):
    add_prop(ctrl, "arms", 3, "0 charge fist (canon)  1 victory  2 dangle")

    specs = [
        ("0_charge", [
            ([(0.72, 0.30), (1.02, 0.40), (1.20, 0.66), (1.22, 0.86)], FIST),
            ([(-0.70, 0.04), (-1.00, -0.06), (-1.22, -0.22), (-1.30, -0.40)], MITT),
        ]),
        ("1_victory", [
            ([(0.68, 0.44), (0.98, 0.74), (1.08, 1.04), (1.06, 1.26)], FIST),
            ([(-0.68, 0.44), (-0.98, 0.74), (-1.08, 1.04), (-1.06, 1.26)], FIST),
        ]),
        ("2_dangle", [
            ([(0.80, 0.14), (1.06, -0.18), (1.16, -0.52), (1.18, -0.80)], MITT),
            ([(-0.80, 0.08), (-1.04, -0.24), (-1.12, -0.58), (-1.08, -0.86)], MITT),
        ]),
    ]
    for idx, (vname, arms) in enumerate(specs):
        v = new_coll("arms_" + vname, coll)
        objs = []
        for i, (path, widths) in enumerate(arms):
            objs += add_part("arm_%s_%d" % (vname, i), taper(path, widths, n=26),
                             "bread", Z["limb"], v, socket, outline=0.042)
        drive_hidden(objs, ctrl, "arms", idx)


def build_legs(coll, socket, ctrl):
    add_prop(ctrl, "legs", 2, "0 sprint (canon)  1 stand")

    specs = [
        ("0_sprint", [
            ([(-0.30, -1.02), (-0.48, -1.34), (-0.62, -1.58), (-0.90, -1.70)], FOOT),
            ([(0.28, -1.04), (0.58, -1.24), (0.86, -1.38), (1.10, -1.36)], FOOT),
        ]),
        ("1_stand", [
            ([(-0.34, -1.02), (-0.41, -1.38), (-0.52, -1.64), (-0.78, -1.76)], FOOT),
            ([(0.34, -1.02), (0.41, -1.38), (0.52, -1.64), (0.78, -1.76)], FOOT),
        ]),
    ]
    for idx, (vname, legs) in enumerate(specs):
        v = new_coll("legs_" + vname, coll)
        objs = []
        for i, (path, widths) in enumerate(legs):
            objs += add_part("leg_%s_%d" % (vname, i), taper(path, widths, n=26),
                             "bread", Z["limb"], v, socket, outline=0.042)
        drive_hidden(objs, ctrl, "legs", idx)


def build_sweat(coll, socket, ctrl):
    add_prop(ctrl, "sweat", 2, "0 off  1 on (canon)", default=1)
    v = new_coll("sweat_1_on", coll)
    objs = []
    drops = [(0.0, 0.0, 0.066, 0.17, -0.26),
             (0.15, -0.21, 0.050, 0.13, -0.10),
             (-0.06, -0.26, 0.042, 0.11, -0.42)]
    for i, (x, y, r, h, rot) in enumerate(drops):
        objs += add_part("sweat_%d" % i, teardrop(x, y, r, h, rot), "sweat",
                         Z["front"], v, socket, outline=0.026)
    drive_hidden(objs, ctrl, "sweat", 1)


def build_armband(coll, socket, ctrl):
    add_prop(ctrl, "armband", 2, "0 off  1 on (group art only)")
    v = new_coll("armband_1_on", coll)
    band = taper([(-0.085, 0.0), (0.085, 0.0)], [0.165, 0.165], n=8,
                 round_start=False, round_end=False)
    objs = add_part("armband", band, "accent", Z["front"], v, socket, outline=0.030)
    drive_hidden(objs, ctrl, "armband", 1)


# --------------------------------------------------------------------------
# scene
# --------------------------------------------------------------------------

def setup_scene(scene):
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
    scene.render.resolution_x = 2048
    scene.render.resolution_y = 2048
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    # flat art wants the raw colors, not a filmic tone curve
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    scene.view_settings.look = "None"

    cam_data = bpy.data.cameras.new("NUGGY_CAM")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 4.2
    cam = bpy.data.objects.new("NUGGY_CAM", cam_data)
    cam.location = (0.0, -10.0, -0.22)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    setup_scene(scene)

    top = new_coll("NUGGY", scene.collection)
    c_body = new_coll("Body", top)
    c_sockets = new_coll("Sockets", top)
    c_feat = new_coll("Features", top)

    # Everything is drawn in a flat XY plane; the root stands it up so front
    # view (numpad 1) looks straight at the character.
    root = add_empty("NUGGY_ROOT", (0, 0, 0), None, c_sockets, size=0.5, kind="ARROWS")
    root.rotation_euler = (math.radians(90), math.radians(5), 0.0)

    ctrl = add_empty("NUGGY_CTRL", (0.0, -2.35, 0.0), root, c_sockets,
                     size=0.30, kind="SPHERE")

    build_body(c_body, root)

    # slot -> (x, y, in-plane rotation in degrees)
    sockets = {
        "eyes":    (0.00, 0.40),
        "brows":   (0.00, 0.78),
        "mouth":   (0.02, -0.26),
        "arms":    (0.00, 0.00),
        "legs":    (0.00, 0.00),
        "sweat":   (-0.74, 0.80),
        "armband": (-1.06, -0.20, 36.0),
    }
    builders = {
        "eyes": build_eyes, "brows": build_brows, "mouth": build_mouths,
        "arms": build_arms, "legs": build_legs, "sweat": build_sweat,
        "armband": build_armband,
    }
    for slot, loc in sockets.items():
        sock = add_empty("SOCKET_" + slot, (loc[0], loc[1], 0.0), root, c_sockets,
                         kind="SPHERE")
        if len(loc) > 2:
            sock.rotation_euler = (0.0, 0.0, math.radians(loc[2]))
        builders[slot](new_coll(slot, c_feat), sock, ctrl)

    bpy.context.view_layer.update()
    return ctrl


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ctrl = build()

    out = None
    if "--render" in argv:
        out = argv[argv.index("--render") + 1]
    if "--set" in argv:
        for pair in argv[argv.index("--set") + 1].split(","):
            k, val = pair.split("=")
            ctrl[k.strip()] = int(val)
        # Assigning an ID property from Python does not tag the depsgraph, so
        # the visibility drivers would otherwise still read the old value.
        ctrl.update_tag()

    if "--no-save" not in argv:
        bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
        print("saved %s" % BLEND_PATH)

    if out:
        bpy.context.view_layer.update()
        bpy.context.scene.render.filepath = os.path.abspath(out)
        bpy.ops.render.render(write_still=True)
        print("rendered %s" % out)


if __name__ == "__main__":
    main()
