"""Render the current scene at reference resolution and measure the match.

Against a saved .blend:
    blender -b nuggy.blend -P trace/verify.py -- --char nuggy

Against a trace you have not saved yet, in one session:
    blender -b -P build.py -P trace/verify.py -- --char nuggy --no-save
"""
import bpy, numpy as np, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from characters import CHARACTERS

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ch = CHARACTERS[argv[argv.index("--char") + 1] if "--char" in argv else "nuggy"]
out = os.path.join(ch.out_dir(), "verify.png")


def load(p):
    im = bpy.data.images.load(p)
    im.colorspace_settings.name = "Non-Color"
    w, h = im.size
    return np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]


ref = load(ch.reference)
H, W = ref.shape[:2]

sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.camera.data.ortho_scale = max(W, H) * ch.scale
sc.render.filepath = out
bpy.ops.render.render(write_still=True)

got = load(out)
ra, ga = ref[:, :, 3] > 0.5, got[:, :, 3] > 0.5
both, union = ra & ga, ra | ga
err = np.abs(ref[:, :, :3] - got[:, :, :3])[both] * 255
print("\nVERIFY %s  %dx%d  IoU %.4f  mean err %.2f  median %.2f  p95 %.2f  >32: %.1f%%"
      % (ch.name, W, H, both.sum() / union.sum(), err.mean(), np.median(err),
         np.percentile(err, 95), 100 * (err.mean(-1) > 32).mean()))
