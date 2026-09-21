"""Raster helpers shared by the tracing stages.

All of this runs under Blender's Python, which ships numpy. Morphology is done
with summed-area tables rather than a real structuring element, so a box erode
or dilate of any radius costs the same as one of radius 1.
"""
import numpy as np


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


def dilate(m, r=1):
    return box_sum(m, r) > 0.5


def erode(m, r=1):
    return box_sum(m, r) >= (2 * r + 1) ** 2 - 0.5


def close(m, r):
    return erode(dilate(m, r), r)


def open_(m, r):
    return dilate(erode(m, r), r)


def grow(cur, mask):
    """Flood `cur` through `mask` until it stops changing."""
    while True:
        n = cur.copy()
        n[1:, :] |= cur[:-1, :]
        n[:-1, :] |= cur[1:, :]
        n[:, 1:] |= cur[:, :-1]
        n[:, :-1] |= cur[:, 1:]
        n &= mask
        if n.sum() == cur.sum():
            return cur
        cur = n


def flood(mask, seeds):
    cur = np.zeros_like(mask)
    for x, y in seeds:
        cur[y, x] = True
    return grow(cur & mask, mask)


def fill_holes(m):
    out = np.zeros_like(m)
    out[0, :] = out[-1, :] = out[:, 0] = out[:, -1] = True
    return ~grow(out & ~m, ~m)


def polygon_mask(pts, w, h, scale=1):
    """Even-odd scanline fill, so this needs no image library."""
    m = np.zeros((h, w), dtype=bool)
    n = len(pts)
    for y in range(h):
        xs = []
        for i in range(n):
            x0, y0 = pts[i][0] * scale, pts[i][1] * scale
            x1, y1 = pts[(i + 1) % n][0] * scale, pts[(i + 1) % n][1] * scale
            if (y0 > y) != (y1 > y):
                xs.append(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
        xs.sort()
        for a, b in zip(xs[0::2], xs[1::2]):
            m[y, max(0, int(a)):max(0, int(b) + 1)] = True
    return m


def hsv(rgb):
    mx = rgb.max(-1)
    mn = rgb.min(-1)
    d = mx - mn + 1e-6
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    h = np.zeros_like(mx)
    m = mx == r
    h[m] = (((g - b) / d) % 6)[m]
    m = mx == g
    h[m] = (((b - r) / d) + 2)[m]
    m = mx == b
    h[m] = (((r - g) / d) + 4)[m]
    return h * 60, np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0), mx


def area_resize(a, ow, oh):
    """Area-average downsample. Doubles as the grain filter."""
    h, w = a.shape[:2]
    flat = a.ndim == 2
    if flat:
        a = a[:, :, None]
    ys = (np.arange(oh + 1) * h / oh).round().astype(int)
    xs = (np.arange(ow + 1) * w / ow).round().astype(int)
    cs = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0), (0, 0))), 0), 1)
    out = (cs[ys[1:, None], xs[None, 1:]] - cs[ys[:-1, None], xs[None, 1:]]
           - cs[ys[1:, None], xs[None, :-1]] + cs[ys[:-1, None], xs[None, :-1]])
    cnt = ((ys[1:] - ys[:-1])[:, None] * (xs[1:] - xs[:-1])[None, :])[:, :, None]
    out = out / cnt
    return out[:, :, 0] if flat else out


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
    squeeze = a.ndim == 2
    if squeeze:
        a = a[:, :, None]
    r = (a[y0c][:, x0c] * (1 - wy) * (1 - wx) + a[y0c][:, x1c] * (1 - wy) * wx
         + a[y1c][:, x0c] * wy * (1 - wx) + a[y1c][:, x1c] * wy * wx)
    return r[:, :, 0] if squeeze else r


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


def load_image(bpy, path):
    """Raw sRGB pixels, top row first."""
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    return px[::-1]                    # Blender's buffers are bottom-up


def save_image(bpy, path, rgba, name="out"):
    h, w = rgba.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.colorspace_settings.name = "Non-Color"
    img.alpha_mode = "STRAIGHT"
    img.pixels = rgba[::-1].ravel().tolist()
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
