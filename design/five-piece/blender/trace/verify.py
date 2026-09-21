"""Render the saved nuggy.blend at reference resolution and measure the match."""
import bpy, numpy as np, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.normpath(os.path.join(HERE, "..", "..", "reference", "nuggy-canon.webp"))
OUT = os.path.join(HERE, "out", "verify.png")
W, H, S = 306, 327, 3.5 / 306.0

sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.camera.data.ortho_scale = max(W, H) * S
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)


def load(p):
    im = bpy.data.images.load(p)
    im.colorspace_settings.name = "Non-Color"
    w, h = im.size
    return np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]


ref, got = load(REF), load(OUT)
ra, ga = ref[:, :, 3] > 0.5, got[:, :, 3] > 0.5
both, union = ra & ga, ra | ga
err = np.abs(ref[:, :, :3] - got[:, :, :3])[both] * 255
print("\nVERIFY  IoU %.4f  mean err %.2f  median %.2f  p95 %.2f  >32: %.1f%%"
      % (both.sum() / union.sum(), err.mean(), np.median(err),
         np.percentile(err, 95), 100 * (err.mean(-1) > 32).mean()))
