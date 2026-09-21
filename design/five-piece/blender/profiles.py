"""Character profiles.

Every nugget in the crew is the same traced artwork put through a different
profile. A profile can warp the torso, transform a limb about its own pivot,
and re-tint the palette. Nuggy is the identity profile, so building him through
this path gives byte-identical geometry to building him directly.

Only the body slot is warped. Limbs and face keep their drawn shape and simply
follow their pivot to wherever the warp moved it, which is what lets Nuggette
have Nuggy's legs on a completely different torso.
"""

import colorsys

# Body slot extents in reference pixels, measured off the trace.
BODY_TOP, BODY_BOT, BODY_CX = 12.0, 278.0, 151.5


def smoothstep(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def curve(points, t):
    """Piecewise smooth interpolation through (t, value) control points."""
    if t <= points[0][0]:
        return points[0][1]
    for i in range(len(points) - 1):
        t0, v0 = points[i]
        t1, v1 = points[i + 1]
        if t <= t1:
            return v0 + (v1 - v0) * smoothstep((t - t0) / (t1 - t0))
    return points[-1][1]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c * 255))) for c in rgb)


def tint_breading(hexcol, dh, ds=1.0, dv=1.0):
    """Shift a breading tone's hue, leaving ink, whites and the tongue alone.

    No profile uses this right now. Nuggette was tried with pink breading and
    rejected: the style guide keeps every nugget in the golden family with one
    accent colour, and once one leaves, the crew stops reading as a set. Kept
    because the toastier and paler crew members will want it.

    The test is on the source colour rather than a hand-written map, so new
    tones added to the tracer get tinted too instead of silently staying gold.
    """
    r, g, b = hex_to_rgb(hexcol)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if not (0.04 <= h <= 0.18 and s >= 0.30):
        return hexcol
    h = (h + dh) % 1.0
    s = max(0.0, min(1.0, s * ds))
    v = max(0.0, min(1.0, v * dv))
    return rgb_to_hex(colorsys.hsv_to_rgb(h, s, v))


class Profile:
    def __init__(self, name, blend, warp=None, slots=None, palette=None,
                 ortho=4.0, notes=""):
        self.name = name
        self.blend = blend
        self._warp = warp
        self.slots = slots or {}
        self._palette = palette
        self.ortho = ortho          # camera width; she is wider than Nuggy
        self.notes = notes

    def warp(self, pt):
        return self._warp(pt[0], pt[1]) if self._warp else (pt[0], pt[1])

    def color(self, hexcol):
        return self._palette(hexcol) if self._palette else hexcol

    def slot_xform(self, slot, pt, pivot):
        """Scale and rotate a point about its slot's pivot, in pixel space."""
        x = self.slots.get(slot)
        if not x:
            return pt
        import math
        sx, sy, rot, dx, dy = x
        px, py = pt[0] - pivot[0], pt[1] - pivot[1]
        px, py = px * sx, py * sy
        if rot:
            a = math.radians(rot)
            c, s = math.cos(a), math.sin(a)
            px, py = px * c - py * s, px * s + py * c
        return (pivot[0] + px + dx, pivot[1] + py + dy)


# --------------------------------------------------------------- nuggette

# Horizontal scale by height. Wide through the chest, pinched at the waist.
# She is the crew's deformed-huge-nugget, so the chest goes well past anything
# a real nugget would do.
NUGGETTE_WIDTH = [
    (0.00, 1.00),   # crown
    (0.10, 1.10),
    (0.28, 1.34),   # shoulders and chest, widest
    (0.46, 1.27),
    (0.62, 1.05),
    (0.80, 0.86),   # waist
    (1.00, 0.90),
]


def nuggette_warp(x, y):
    t = (y - BODY_TOP) / (BODY_BOT - BODY_TOP)
    sx = curve(NUGGETTE_WIDTH, t)
    ny = BODY_TOP + (y - BODY_TOP) * 1.04          # a touch taller overall
    return BODY_CX + (x - BODY_CX) * sx, ny


PROFILES = {
    "nuggy": Profile(
        "nuggy", "nuggy.blend",
        notes="Canon. Identity profile: no warp, no tint.",
    ),
    "nuggette": Profile(
        "nuggette", "nuggette.blend",
        warp=nuggette_warp,
        slots={
            # slot: (scale_x, scale_y, rotation_deg, dx, dy) about the pivot.
            # Rotation is in pixel space, where y points down, so a positive
            # angle turns clockwise on screen.
            "arm_L": (1.75, 1.75, 0, 0, 0),
            "arm_R": (1.75, 1.75, 0, 0, 0),
        },
        ortho=5.0,
        notes="Tank. Nuggy's legs and face on a bodybuilder torso, huge arms.",
    ),
}
