"""Inflate a traced 2D character into a 3D mesh.

There is only ever one reference image, drawn face on, so there is no side or
back view to model from. What there is, exactly, is the front: a silhouette
measured to within 0.2% of the art, and a colour for every pixel inside it.
This builds the roundest solid consistent with that front.

    front surface  y = -h(x, z)
    back surface   y = +h(x, z)

where h falls to zero at the silhouette edge, so the two sheets meet there and
the outline stays the traced one from any angle.

h has two parts. A **puff**, which is a blurred copy of the silhouette mask run
through a circular profile: rounded at the rim, plump in the middle, the cross
section of a nugget. And **relief**, taken from the artwork's own luminance.
That second one is not a trick: the breading tones are a shading ramp, so where
the artist painted a tone darker they were drawing a crevice, and where they
painted it lighter they were drawing a bump catching the light. Reading tone
back as height recovers the lumps they drew, in the places they drew them.

Colour comes from rendering the 2D rig through the same orthographic camera and
projecting that image straight down the view axis, so the front view of the
model is pixel-identical to the 2D build. The back gets a second render with
the face slots switched off, or it would wear a mirrored face.

    blender -b -P model3d.py -- --char nuggy
    blender -b -P model3d.py -- --char nuggy --turntable previews/nuggy-3d
"""

import bpy
import bmesh
import math
import numpy as np
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "trace"))

import build as build2d
from characters import CHARACTERS
from profiles import Profile
from raster import box_blur, dilate, erode, save_image

TEX = 2048          # albedo resolution
GRID = 420          # mesh vertices across the frame
DEPTH = 0.12        # half-thickness at the plateau, as a fraction of size
ROLLOFF = 0.055     # how far in from the rim the puff reaches, fraction of size
RELIEF = 0.45       # breading depth, as a fraction of DEPTH
# |N.y| band over which the artwork fades to flat breading. Aggressive on
# purpose: the front projection is already unreliable well before the surface
# is edge on, and a flat side is a smaller lie than a smeared one. The cost is
# a thin flat ring around the front view, which reads as the form turning.
RIM_FADE = (0.80, 0.99)
OUTLINE = 0.004     # inverted-hull thickness, in Blender units


# ------------------------------------------------------------------ textures

def render_to_array(scene, path, res, ortho):
    scene.render.resolution_x = scene.render.resolution_y = res
    scene.camera.data.ortho_scale = ortho
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    # Two datablocks off the same file. The measuring copy is read raw, the
    # shading copy is read as sRGB, and mixing them up washes the colour out.
    raw = bpy.data.images.load(path)
    raw.colorspace_settings.name = "Non-Color"
    px = np.array(raw.pixels[:], dtype=np.float32).reshape(res, res, 4)
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "sRGB"
    img.name = os.path.basename(path)
    return px[::-1], img                       # Blender buffers are bottom-up


def bake_textures(ch, out_dir, res, ortho):
    """Front and back albedo, straight off the 2D rig's own camera."""
    prof = Profile("identity", ch.name)
    ctrl = build2d.build(ch, prof)
    scene = bpy.context.scene
    front, front_img = render_to_array(
        scene, os.path.join(out_dir, "albedo-front.png"), res, ortho)

    # The back cannot wear the face. Hiding the face slots leaves the skin fill
    # that is already built underneath every feature for exactly this reason.
    for slot in ch.slots:
        if slot in ("eye_L", "eye_R", "mouth", "sweat"):
            ctrl[slot] = 0
    ctrl.update_tag()
    bpy.context.view_layer.update()
    back, back_img = render_to_array(
        scene, os.path.join(out_dir, "albedo-back.png"), res, ortho)
    return front, back, front_img, back_img


# -------------------------------------------------------------------- height

def height_field(front, res, ortho, size_px, depth=None, rolloff=None, relief=None):
    """Half-thickness at every texture pixel, in Blender units."""
    mask = front[:, :, 3] > 0.5
    unit = ortho / res                          # Blender units per pixel

    # Puff. Blurring the mask and reading the result as "how far inside am I"
    # gives a falloff that is smooth and has no corners, which repeated erosion
    # does not. Through a circular profile it becomes a rounded rim and a flat
    # middle, which is the cross section a nugget has.
    depth_f = DEPTH if depth is None else depth
    roll_f = ROLLOFF if rolloff is None else rolloff
    relief_f = RELIEF if relief is None else relief
    # Three box blurs of radius r reach about 3r, so the radius is a third of
    # the rolloff asked for. Getting this wrong spreads the shoulder six times
    # wider than intended and the whole side of the model turns to smear.
    r = max(2, int(roll_f * size_px / 3))
    soft = box_blur(box_blur(box_blur(mask.astype(np.float32), r), r), r)
    t = np.clip(soft * 2.0 - 0.35, 0.0, 1.0)
    puff = np.sqrt(np.clip(1.0 - (1.0 - t) ** 2, 0.0, 1.0))

    # Relief. Luminance of the artwork, centred on the median of the breading
    # so the mid tone sits at the surface and the ramp cuts in and out from it.
    lum = front[:, :, :3].max(-1)
    mid = np.median(lum[mask])
    rel = np.clip((lum - mid) / 0.45, -1.0, 1.0)
    # Ink is a drawn line, not a crevice, so keep it from cutting a trench.
    rel = np.where(lum < 0.22, 0.0, rel)
    # Blur to something the mesh can actually carry. The breading lumps are
    # tens of pixels across; anything finer than a couple of grid cells just
    # makes the normals thrash and the surface sparkle.
    rel = box_blur(box_blur(rel * mask, max(2, res // 80)), max(2, res // 160))

    depth = depth_f * size_px * unit
    h = depth * (puff + relief_f * rel * puff)

    # The surface normal of the puff alone, in object space. Taking it from
    # the finished surface instead picks up every breading bump and the mask
    # thrashes; the puff is the form, the relief is texture on it, and it is
    # the form that decides whether the front projection still has anything to
    # say here. The front sheet faces -Y, so its normal is (-dh/dx, -1, dh/dz)
    # before normalising.
    gz, gx = np.gradient(depth * puff, unit)
    n = np.stack([-gx, -np.ones_like(gx), gz], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return np.where(mask, np.maximum(h, 0.0), 0.0), mask, n


# ---------------------------------------------------------------------- mesh

def build_mesh(name, h, mask, res, ortho, grid):
    """Two heightfield sheets over the silhouette, welded at the rim.

    Faces are emitted for any cell touching the mask rather than only cells
    fully inside it, so the mesh runs a little past the artwork. The material
    clips on the texture's own alpha, which puts the visible edge back exactly
    where the trace put it, at whatever angle you view from.
    """
    step = res / grid
    idx = np.clip((np.arange(grid + 1) * step).astype(int), 0, res - 1)
    hs = h[np.ix_(idx, idx)]
    ms = dilate(mask, 1)[np.ix_(idx, idx)]

    u = (idx + 0.5) / res
    x = (u - 0.5) * ortho
    z = (0.5 - u) * ortho

    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    verts = {}
    for side, sgn in (("F", -1.0), ("B", 1.0)):
        for i in range(grid + 1):
            for j in range(grid + 1):
                v = bm.verts.new((x[j], sgn * float(hs[i, j]), z[i]))
                verts[(side, i, j)] = v
    bm.verts.index_update()

    for side, flip in (("F", False), ("B", True)):
        for i in range(grid):
            for j in range(grid):
                if not (ms[i, j] or ms[i + 1, j] or ms[i, j + 1] or ms[i + 1, j + 1]):
                    continue
                q = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
                if flip:
                    q = q[::-1]
                f = bm.faces.new([verts[(side, a, b)] for a, b in q])
                for loop, (a, b) in zip(f.loops, q):
                    loop[uv].uv = (u[b], 1.0 - u[a])

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    return ob


# ------------------------------------------------------------------ material

def albedo_material(name, img, rim_img, rim_hex, fade=None, backfacing=False):
    """Flat emission from the baked artwork, clipped on its alpha.

    The traced colours already carry the shading the artist painted, so adding
    a light would apply it twice. The form is read from the silhouette turning
    and from the relief, not from a lambert term.

    The projection is along the object's own Y, so it carries no information
    for the rim: stretch a front view over a turning edge and it smears into
    streaks. Near the silhouette this fades to a flat breading tone instead.
    A plain side wall is a much smaller lie than a smeared one.
    """
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mix = nt.nodes.new("ShaderNodeMixShader")
    em = nt.nodes.new("ShaderNodeEmission")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "CLIP"

    # Keyed to |N.y| of the underlying form, baked here in object space. Not
    # to the view: rotate the model and a receding shoulder turns to face the
    # camera, so a view-dependent fade lights up exactly the band it is meant
    # to suppress. How far round the form a point is does not depend on where
    # you stand, and that is the question being asked.
    rimtex = nt.nodes.new("ShaderNodeTexImage")
    rimtex.image = rim_img
    rimtex.extension = "EXTEND"
    dec = nt.nodes.new("ShaderNodeVectorMath")
    dec.operation = "MULTIPLY_ADD"
    dec.inputs[1].default_value = (2.0, 2.0, 2.0)
    dec.inputs[2].default_value = (-1.0, -1.0, -1.0)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    absd = nt.nodes.new("ShaderNodeMath")
    absd.operation = "ABSOLUTE"
    face = nt.nodes.new("ShaderNodeMapRange")
    lo, hi = fade or RIM_FADE
    face.inputs["From Min"].default_value = lo
    face.inputs["From Max"].default_value = hi
    face.clamp = True
    rim = nt.nodes.new("ShaderNodeRGB")
    h = rim_hex.lstrip("#")
    rim.outputs[0].default_value = tuple(
        build2d.srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)) + (1.0,)
    blend = nt.nodes.new("ShaderNodeMixRGB")
    nt.links.new(rimtex.outputs["Color"], dec.inputs[0])
    nt.links.new(dec.outputs["Vector"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Y"], absd.inputs[0])
    nt.links.new(absd.outputs[0], face.inputs["Value"])
    nt.links.new(face.outputs["Result"], blend.inputs["Fac"])
    nt.links.new(rim.outputs[0], blend.inputs[1])
    nt.links.new(tex.outputs["Color"], blend.inputs[2])

    nt.links.new(blend.outputs[0], em.inputs["Color"])
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[1])
    nt.links.new(em.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    # EEVEE Next: BLENDED does not write depth, so two stacked sheets sort at
    # random and whichever draws last wins. DITHERED writes depth, and the
    # alpha here is all but binary, so the dither never shows.
    for attr, val in (("surface_render_method", "DITHERED"),
                      ("blend_method", "CLIP")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass
    m.use_backface_culling = False
    return m


def outline_material(hexcol):
    h = hexcol.lstrip("#")
    rgb = tuple(build2d.srgb_to_linear(int(h[i:i + 2], 16) / 255.0)
                for i in (0, 2, 4))
    m = bpy.data.materials.new("OUTLINE")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = rgb + (1.0,)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.use_backface_culling = True
    try:
        m.surface_render_method = "DITHERED"
    except (AttributeError, TypeError):
        pass
    return m


def add_outline(ob, ch, width):
    """Inverted hull: a slightly fattened copy with its normals flipped and
    front faces culled, so only the sliver past the silhouette is ever seen.
    Freestyle looks better and costs a render pass; this is free and survives
    into any engine."""
    hull = ob.copy()
    hull.data = ob.data.copy()
    hull.name = ob.name + "_outline"
    bpy.context.scene.collection.objects.link(hull)
    hull.data.materials.clear()
    hull.data.materials.append(outline_material(ch.colors["ink"]))
    sol = hull.modifiers.new("hull", "SOLIDIFY")
    sol.thickness = width
    sol.offset = 1.0
    sol.use_flip_normals = True
    sol.use_rim = False
    return hull


# ---------------------------------------------------------------------- main

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    ch = CHARACTERS[arg("--char", "nuggy")]
    res = int(arg("--res", TEX))
    grid = int(arg("--grid", GRID))
    out_dir = ch.out_dir()
    os.makedirs(out_dir, exist_ok=True)

    # Square frame big enough for the whole character, in the 2D rig's units.
    import json
    data = json.load(open(os.path.join(out_dir, "trace.json")))
    pts = [p for sh in data["shapes"] if sh["layer"] == "silhouette"
           for r in sh["rings"] for p in r]
    w = (max(p[0] for p in pts) - min(p[0] for p in pts)) * ch.scale
    ht = (max(p[1] for p in pts) - min(p[1] for p in pts)) * ch.scale
    ortho = max(w, ht) * 1.06
    # Depth and rolloff scale with the *smaller* dimension. A nugget is as deep
    # as it is narrow; scaling off the larger one makes a wide character like
    # Miss Nuggette come out as deep as she is tall.
    size_px = int(round(min(w, ht) / ortho * res))
    print("%s: frame %.3f units, character %.2f x %.2f" % (ch.name, ortho, w, ht))

    front, back, front_img, back_img = bake_textures(ch, out_dir, res, ortho)
    h, mask, normal = height_field(front, res, ortho, size_px,
                           float(arg("--depth", DEPTH)),
                           float(arg("--rolloff", ROLLOFF)),
                           float(arg("--relief", RELIEF)))
    print("thickness %.3f units peak, silhouette %d px" % (h.max() * 2, mask.sum()))

    rim_path = os.path.join(out_dir, "form-normal.png")
    rgba = np.concatenate([normal * 0.5 + 0.5,
                           np.ones(normal.shape[:2] + (1,), np.float32)], -1)
    save_image(bpy, rim_path, rgba, "form-normal")
    rim_img = bpy.data.images.load(rim_path, check_existing=False)
    rim_img.colorspace_settings.name = "Non-Color"

    # Drop the flat build; from here the scene is the model.
    for ob in list(bpy.data.objects):
        if ob.type != "CAMERA":
            bpy.data.objects.remove(ob, do_unlink=True)

    ob = build_mesh(ch.name.upper() + "_3D", h, mask, res, ortho, grid)
    # A mid breading tone, not the darkest: the side is turning away, so it
    # should sit a step down from the front, not read as a shadow slab.
    rim_hex = ch.color(ch.colors.get("gold_deep", ch.colors["skinfill"]))
    fade = tuple(float(v) for v in arg("--fade", "%g,%g" % RIM_FADE).split(","))
    ob.data.materials.append(
        albedo_material("ALBEDO_FRONT", front_img, rim_img, rim_hex, fade))
    ob.data.materials.append(
        albedo_material("ALBEDO_BACK", back_img, rim_img, rim_hex, fade))
    half = len(ob.data.polygons) // 2
    for i, poly in enumerate(ob.data.polygons):
        poly.material_index = 0 if i < half else 1
    width = float(arg("--outline", OUTLINE))
    if width > 0:
        add_outline(ob, ch, width)
    print("mesh %d verts  %d faces" % (len(ob.data.vertices), len(ob.data.polygons)))

    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.camera.data.ortho_scale = ortho

    blend = os.path.join(HERE, "%s-3d.blend" % ch.name)
    if "--no-save" not in argv:
        # Pack the baked maps in. They are regenerable, so they are not
        # committed, and a .blend that opens pink on someone else's machine is
        # not much of a deliverable.
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        print("saved", blend)

    turn = arg("--turntable")
    if turn:
        turn = os.path.abspath(turn)
        os.makedirs(os.path.dirname(turn) or ".", exist_ok=True)
        pivot = bpy.data.objects.new("PIVOT", None)
        scene.collection.objects.link(pivot)
        for o in (ob, bpy.data.objects[ob.name + "_outline"]):
            o.parent = pivot
        n = int(arg("--frames", "24"))
        for i in range(n):
            pivot.rotation_euler = (0, 0, math.radians(360 * i / n))
            scene.render.filepath = "%s%02d.png" % (turn, i)
            bpy.ops.render.render(write_still=True)
        print("turntable ->", turn)

    if "--render" in argv:
        base = os.path.abspath(arg("--render"))
        pivot = bpy.data.objects.get("PIVOT")
        if not pivot:
            pivot = bpy.data.objects.new("PIVOT", None)
            scene.collection.objects.link(pivot)
            for o in list(bpy.data.objects):
                if o.type == "MESH":
                    o.parent = pivot
        for ang in [float(a) for a in arg("--angle", "0").split(",")]:
            pivot.rotation_euler = (0, 0, math.radians(ang))
            scene.render.filepath = base.replace(
                ".png", "-%d.png" % round(ang)) if len(argv) else base
            bpy.ops.render.render(write_still=True)
            print("rendered", scene.render.filepath)


if __name__ == "__main__":
    main()
