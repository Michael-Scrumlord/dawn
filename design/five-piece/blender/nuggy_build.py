"""Build Nuggy as a flat 2D cutout rig in Blender, traced from the canon art.

The artwork is not drawn by hand here. `trace/quantize.py` posterizes
`reference/nuggy-canon.webp` into named flat colour layers and `trace/contours.py`
turns those into polygons; this script reads the resulting `trace/out/trace.json`
and builds the scene. Every shape is a filled 2D curve, stacked on the local Z
axis and parented to a root empty that stands the whole thing upright, so
numpad-1 (front view) looks straight at him.

Features hang off socket empties: move `SOCKET_mouth` and the mouth moves,
Mr. Potatohead style. Each socket also has a show/hide property on NUGGY_CTRL.

    blender -b -P nuggy_build.py
    blender -b -P nuggy_build.py -- --render out.png --set mouth=0

Re-run it any time; it rebuilds the .blend from scratch.
"""

import bpy
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profiles import PROFILES

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE = os.path.join(HERE, "trace", "out", "trace.json")
BLEND_PATH = os.path.join(HERE, "nuggy.blend")   # overridden by --profile

# Reference-image pixel -> Blender unit. CX/CY put the character's own centre
# at the origin so sockets and the camera share one frame.
CX, CY, S = 153.0, 163.5, 3.5 / 306.0

# Back to front. Regions are exact and disjoint, so this only decides which
# side of a shared edge wins the quarter-pixel overlap the tracer adds.
ZORDER = ["silhouette", "skinfill", "rim", "shade_deep", "shade", "amber", "gold_deep",
          "gold_mid", "gold_base", "gold_light", "gold_pale", "eye_shadow",
          "eye_white", "mouth_dk", "tongue", "iris", "pupil", "ink"]
ZSTEP = 0.01
LID_Z = len(ZORDER) * ZSTEP          # eyelids sit in front of every traced layer

# Slots the rig can move, hide or replace. "body" is the static remainder.
SLOTS = ["eye_L", "eye_R", "mouth", "sweat", "arm_L", "arm_R", "leg_L", "leg_R"]

SLOT_HELP = {
    "eye_L": "left eye, brow and lashes (0 hide, 1 show)",
    "eye_R": "right eye, brow and lashes (0 hide, 1 show)",
    "mouth": "mouth, teeth and tongue (0 hide, 1 show)",
    "sweat": "sweat drops (0 hide, 1 show)",
    "arm_L": "left arm and mitt (0 hide, 1 show)",
    "arm_R": "right arm and fist (0 hide, 1 show)",
    "leg_L": "left leg and foot (0 hide, 1 show)",
    "leg_R": "right leg and foot (0 hide, 1 show)",
}


# --------------------------------------------------------------------- utils

def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def get_mat(hexcol):
    """Flat emission material: no lighting, so rendered colour == the hex."""
    name = "NUG_" + hexcol.lstrip("#")
    m = bpy.data.materials.get(name)
    if m:
        return m
    h = hexcol.lstrip("#")
    rgb = tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))
    m = bpy.data.materials.new(name)
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
    return m


def signed_area(pts):
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))


def to_blender(pt):
    return ((pt[0] - CX) * S, (CY - pt[1]) * S)


def new_coll(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def add_empty(name, loc, parent, coll, size=0.14, kind="SPHERE"):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = kind
    e.empty_display_size = size
    coll.objects.link(e)
    if parent:
        e.parent = parent
        e.matrix_parent_inverse.identity()
    e.location = loc
    return e


def add_curve(name, rings, color, z, origin, parent, coll, prof=None):
    """One curve object holding every ring of one colour in one slot.

    Rings are drawn relative to `origin` (the slot's socket) so moving the
    socket carries the whole feature.
    """
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.materials.append(get_mat(prof.color(color) if prof else color))
    for ring in rings:
        sp = cu.splines.new("POLY")
        sp.points.add(len(ring) - 1)
        for i, p in enumerate(ring):
            x, y = to_blender(p)
            sp.points[i].co = (x - origin[0], y - origin[1], 0.0, 1.0)
        sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    ob.parent = parent
    ob.matrix_parent_inverse.identity()
    ob.location = (0.0, 0.0, z)
    return ob


def add_eyelid(slot, group, origin, socket, coll, prof=None):
    """A skin-coloured lid that closes over one eye.

    Not traced -- the reference has both eyes open, so there is no closed
    drawing to lift. The lid is a copy of that eye's own sclera outline, so it
    closes with the eye's real curve instead of a rectangle, and it is sized to
    the sclera rather than the whole eye group so the brow stays put.

    Two copies are stacked: a dark one, and a gold one nudged up by a few
    pixels. Scaling both from their shared top edge leaves a thin dark crescent
    along the bottom, which is the lash line. scale.y 0 is open, 1 is shut.

    Everything is in reference-image pixels; add_curve() maps to Blender units.
    """
    white = [sh for sh in group if sh["layer"] == "eye_white"]
    if not white:
        return []
    ring = max((r for sh in white for r in sh["rings"]),
               key=lambda r: abs(signed_area(r)))
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    grown = [(cx + (p[0] - cx) * 1.12, cy + (p[1] - cy) * 1.34) for p in ring]
    top = min(p[1] for p in grown)
    lash = (max(p[1] for p in grown) - top) * 0.10

    anchor = to_blender((cx, top))
    made = []
    for name, col, dy, dz in (("lash", "#281108", 0.0, 0.0),
                              ("lid", "#EBA126", -lash, 0.002)):
        ob = add_curve("%s_%s" % (slot, name),
                       [[(x, y + dy) for x, y in grown]],
                       col, LID_Z + dz, anchor, socket, coll, prof)
        ob.location = (anchor[0] - origin[0], anchor[1] - origin[1], LID_Z + dz)
        ob.scale = (1.0, 0.0, 1.0)           # height 0 == eye open
        made.append(ob)
    return made


def add_prop(ctrl, name, desc, default=1):
    ctrl[name] = default
    ctrl.id_properties_ui(name).update(min=0, max=1, soft_min=0, soft_max=1,
                                       default=default, description=desc)


def drive_hidden(objs, ctrl, prop):
    """Hide these objects whenever ctrl[prop] is 0."""
    for ob in objs:
        for path in ("hide_viewport", "hide_render"):
            d = ob.driver_add(path).driver
            d.type = "SCRIPTED"
            v = d.variables.new()
            v.name = "on"
            v.type = "SINGLE_PROP"
            v.targets[0].id_type = "OBJECT"
            v.targets[0].id = ctrl
            v.targets[0].data_path = '["%s"]' % prop
            d.expression = "on < 1"


# --------------------------------------------------------------------- build

def setup_scene(scene, ortho=4.0):
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
    # flat art wants raw colour, not a filmic tone curve
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    scene.view_settings.look = "None"

    cd = bpy.data.cameras.new("NUGGY_CAM")
    cd.type = "ORTHO"
    cd.ortho_scale = ortho
    cam = bpy.data.objects.new("NUGGY_CAM", cd)
    cam.location = (0.0, -10.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam


def build(prof=None):
    prof = prof or PROFILES["nuggy"]
    data = json.load(open(TRACE))
    shapes = data["shapes"]
    pivots = data.get("pivots", {})

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    setup_scene(scene, prof.ortho)

    top = new_coll("NUGGY", scene.collection)
    c_sock = new_coll("Sockets", top)
    c_feat = new_coll("Features", top)

    root = add_empty("NUGGY_ROOT", (0, 0, 0), None, c_sock, size=0.5, kind="ARROWS")
    root.rotation_euler = (math.radians(90), 0.0, 0.0)
    ctrl = add_empty("NUGGY_CTRL", (0.0, -2.15, 0.0), root, c_sock,
                     size=0.25, kind="SPHERE")

    by_slot = {}
    for sh in shapes:
        by_slot.setdefault(sh["slot"], []).append(sh)

    zindex = {layer: i for i, layer in enumerate(ZORDER)}
    # Slot pieces of the same layer overlap slightly where the tracer cut a
    # limb off the torso; a tiny bias keeps them from z-fighting there.
    bias_of = {s: i * 0.0005 for i, s in enumerate(["body"] + SLOTS)}
    counts = {}

    for slot in ["body"] + SLOTS:
        group = by_slot.get(slot)
        if not group:
            continue

        # Limbs pivot where they meet the torso; everything else pivots at the
        # middle of its own bounding box. Pixel space throughout, because the
        # profile's warp and slot transforms are defined there.
        px = [p for sh in group for r in sh["rings"] for p in r]
        bx = [p[0] for p in px]
        by = [p[1] for p in px]
        if slot in pivots:
            pivot = tuple(pivots[slot])
        else:
            pivot = ((min(bx) + max(bx)) / 2, (min(by) + max(by)) / 2)

        # The warp moves every pivot, so limbs and face follow the torso even
        # though their own artwork is left alone.
        socket_at = prof.warp(pivot)
        warp_geom = slot == "body"
        origin = (0.0, 0.0) if slot == "body" else to_blender(pivot)
        socket_loc = (0.0, 0.0) if slot == "body" else to_blender(socket_at)

        if slot == "body":
            parent, coll = root, new_coll("Body", top)
        else:
            parent = add_empty("SOCKET_" + slot,
                               (socket_loc[0], socket_loc[1], 0.0), root, c_sock)
            coll = new_coll(slot, c_feat)

        by_layer = {}
        for sh in group:
            by_layer.setdefault(sh["layer"], []).append(sh)

        def shape(ring):
            out = ring
            if warp_geom:
                out = [prof.warp(p) for p in out]
            if slot in prof.slots:
                out = [prof.slot_xform(slot, p, pivot) for p in out]
            return out

        objs = []
        for layer, group_shapes in by_layer.items():
            rings = [shape(r) for sh in group_shapes for r in sh["rings"]]
            objs.append(add_curve(
                "%s_%s" % (slot, layer), rings, group_shapes[0]["color"],
                zindex.get(layer, 0) * ZSTEP + bias_of[slot],
                origin, parent, coll, prof))
        counts[slot] = (len(objs), sum(len(r) for sh in group for r in sh["rings"]))

        if slot in ("eye_L", "eye_R"):
            objs += add_eyelid(slot, group, origin, parent, coll, prof)

        if slot != "body":
            add_prop(ctrl, slot, SLOT_HELP[slot])
            drive_hidden(objs, ctrl, slot)

    for k, (n, p) in sorted(counts.items()):
        print("  %-7s %2d layers  %6d points" % (k, n, p))

    bpy.context.view_layer.update()
    return ctrl


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = argv[argv.index("--profile") + 1] if "--profile" in argv else "nuggy"
    prof = PROFILES[name]
    print("profile: %s -- %s" % (prof.name, prof.notes))
    ctrl = build(prof)

    if "--set" in argv:
        for pair in argv[argv.index("--set") + 1].split(","):
            k, val = pair.split("=")
            ctrl[k.strip()] = int(val)
        # Assigning an ID property from Python does not tag the depsgraph, so
        # the visibility drivers would otherwise still read the old value.
        ctrl.update_tag()

    if "--no-save" not in argv:
        out = os.path.join(HERE, prof.blend)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print("saved", out)

    if "--render" in argv:
        bpy.context.view_layer.update()
        bpy.context.scene.render.filepath = os.path.abspath(
            argv[argv.index("--render") + 1])
        bpy.ops.render.render(write_still=True)
        print("rendered", bpy.context.scene.render.filepath)


if __name__ == "__main__":
    main()
