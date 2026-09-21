"""Build a character as a flat 2D cutout rig in Blender, from its trace.

The artwork is not drawn by hand here. `trace/quantize.py` posterizes a
character's reference into named flat colour layers and `trace/contours.py`
turns those into polygons; this script reads the resulting
`trace/out/<char>/trace.json` and builds the scene. Every shape is a filled 2D
curve, stacked on the local Z axis and parented to a root empty that stands
the whole thing upright, so numpad-1 (front view) looks straight at it.

Features hang off socket empties: move `SOCKET_mouth` and the mouth moves,
Mr. Potatohead style. Each socket also has a show/hide property on the
character's CTRL empty.

`--char` picks the trace and the geometry frame (CX/CY/S, ortho, slots,
z-order) from `characters.py`. `--profile` picks a warp/tint variant of that
same trace from `profiles.py` and defaults to the identity profile matching
`--char`; Nuggette, for instance, is `--char nuggy --profile nuggette` because
she reuses Nuggy's trace rather than having her own.

    blender -b -P nuggy_build.py -- --char nuggy
    blender -b -P nuggy_build.py -- --char nuggy --profile nuggette
    blender -b -P nuggy_build.py -- --char chicli --render out.png --set star=0

Re-run it any time; it rebuilds the .blend from scratch.
"""

import bpy
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from profiles import PROFILES
from characters import CHARACTERS

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "nuggy"
ch = CHARACTERS[CHAR]
PROFILE = argv[argv.index("--profile") + 1] if "--profile" in argv else CHAR

TRACE = os.path.join(ch.out_dir(), "trace.json")
PREFIX = ch.name.upper()   # object/collection naming, e.g. NUGGY_ROOT, CHICLI_ROOT

# Reference-image pixel -> Blender unit. CX/CY put the character's own centre
# at the origin so sockets and the camera share one frame.
CX, CY, S = ch.centre[0], ch.centre[1], ch.scale

# Back to front. Regions are exact and disjoint, so this only decides which
# side of a shared edge wins the quarter-pixel overlap the tracer adds.
ZORDER = ch.zorder
ZSTEP = 0.01
LID_Z = len(ZORDER) * ZSTEP          # eyelids sit in front of every traced layer

# Slots the rig can move, hide or replace. "body" is the static remainder.
SLOTS = ch.slots
SLOT_HELP = ch.slot_help


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

    cam_name = PREFIX + "_CAM"
    cd = bpy.data.cameras.new(cam_name)
    cd.type = "ORTHO"
    cd.ortho_scale = ortho
    cam = bpy.data.objects.new(cam_name, cd)
    cam.location = (0.0, -10.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam


def clear_scene():
    """Empty the current scene without reloading the .blend file.

    `bpy.ops.wm.read_factory_settings()` looks tempting here (and is what a
    throwaway `blender -b -P script.py` process would use) but it reloads the
    whole file, which tears down anything an add-on registered against the
    old one -- including, when this runs inside a live Blender instance
    driven over MCP, the MCP server's own connection. Removing every object,
    collection and orphaned data-block by hand reaches the same empty scene
    without touching add-on state.
    """
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block_coll in (bpy.data.curves, bpy.data.cameras, bpy.data.lights,
                        bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for block in list(block_coll):
            if block.users == 0:
                block_coll.remove(block)


def build(prof=None):
    prof = prof or PROFILES[CHAR]
    data = json.load(open(TRACE))
    shapes = data["shapes"]
    pivots = data.get("pivots", {})

    clear_scene()
    scene = bpy.context.scene
    setup_scene(scene, prof.ortho)

    top = new_coll(PREFIX, scene.collection)
    c_sock = new_coll("Sockets", top)
    c_feat = new_coll("Features", top)

    root = add_empty(PREFIX + "_ROOT", (0, 0, 0), None, c_sock, size=0.5, kind="ARROWS")
    root.rotation_euler = (math.radians(90), 0.0, 0.0)
    ctrl = add_empty(PREFIX + "_CTRL", (0.0, -2.15, 0.0), root, c_sock,
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
    prof = PROFILES[PROFILE]
    print("char: %s   profile: %s -- %s" % (CHAR, prof.name, prof.notes))
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
