"""Build the traced artwork and measure it against the reference."""
import bpy, numpy as np, json, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
REF = os.path.normpath(os.path.join(HERE, "..", "..", "reference", "nuggy-canon.webp"))

CX, CY, S = 153.0, 163.5, 3.5 / 306.0

ZORDER = ["silhouette", "skinfill", "rim", "shade_deep", "shade", "amber", "gold_deep",
          "gold_mid", "gold_base", "gold_light", "gold_pale", "eye_shadow",
          "eye_white", "mouth_dk", "tongue", "iris", "pupil", "ink"]


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mat(name, hexcol):
    m = bpy.data.materials.get(name)
    if m:
        return m
    h = hexcol.lstrip("#")
    rgb = tuple(srgb_to_linear(int(h[i:i+2], 16) / 255.0) for i in (0, 2, 4))
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = rgb + (1.0,)
    nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
    m.diffuse_color = rgb + (1.0,)
    return m


def to_blender(pt):
    return ((pt[0] - CX) * S, (CY - pt[1]) * S)


def add_curve(name, rings, color, z, parent, coll):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.materials.append(mat("M_" + color.lstrip("#"), color))
    for ring in rings:
        sp = cu.splines.new("POLY")
        sp.points.add(len(ring) - 1)
        for i, p in enumerate(ring):
            x, y = to_blender(p)
            sp.points[i].co = (x, y, 0.0, 1.0)
        sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    ob.parent = parent
    ob.matrix_parent_inverse.identity()
    ob.location = (0.0, 0.0, z)
    return ob


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            pass
    data = json.load(open(os.path.join(OUT, "trace.json")))
    W, H = data["size"]

    scene.render.resolution_x, scene.render.resolution_y = W, H
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"

    cd = bpy.data.cameras.new("CAM")
    cd.type = "ORTHO"
    cd.ortho_scale = max(W, H) * S
    cam = bpy.data.objects.new("CAM", cd)
    cam.location = (0.0, -10.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    root = bpy.data.objects.new("ROOT", None)
    scene.collection.objects.link(root)
    root.rotation_euler = (math.radians(90), 0.0, 0.0)

    slots = sorted({s["slot"] for s in data["shapes"]})
    grouped = {}
    for s in data["shapes"]:
        grouped.setdefault((s["slot"], s["layer"]), []).append(s)
    for (slot, layer), group in grouped.items():
        zi = ZORDER.index(layer) if layer in ZORDER else 0
        bias = slots.index(slot) * 0.0005
        rings = [r for s in group for r in s["rings"]]
        add_curve("%s_%s" % (slot, layer), rings, group[0]["color"],
                  0.02 + zi * 0.01 + bias, root, scene.collection)

    out = os.path.join(OUT, "render.png")
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)

    # ---- diff against the reference
    def load(path, non_color=True):
        im = bpy.data.images.load(path)
        if non_color:
            im.colorspace_settings.name = "Non-Color"
        w, h = im.size
        return np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]

    ref = load(REF)
    got = load(out)
    ra, ga = ref[:, :, 3] > 0.5, got[:, :, 3] > 0.5
    union = ra | ga
    both = ra & ga
    iou = both.sum() / max(union.sum(), 1)
    d = np.abs(ref[:, :, :3] - got[:, :, :3])[both].mean() * 255
    print("\nFIDELITY  silhouette IoU %.4f   mean colour err %.2f/255   "
          "ref-only %d  new-only %d"
          % (iou, d, int((ra & ~ga).sum()), int((ga & ~ra).sum())))


main()
