"""Pose and palette variants built on top of a traced character.

A profile takes one character's trace and warps it: the torso through a
free-form function, each slot through a transform about its own pivot, and the
palette through a recolour. The identity profile gives geometry identical to
building the character directly, which is what keeps this honest.

Only the body slot is warped. Limbs and face keep their drawn shape and follow
their pivot to wherever the warp moved it, so a limb stays attached to a torso
that has changed shape underneath it.

This started as the way to make the whole crew out of Nuggy's one trace. It is
not that any more -- each character gets traced from their own art, which is
far better -- so what it is for now is pose variants of a character who has
already been traced, and palette experiments.
"""

import colorsys

DEG = 1.0


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


def regrade(hexcol, dh=0.0, ds=1.0, dv=1.0, gamma=1.0, toward=None, pull=0.0):
    """Shift one colour in HSV. `toward` pulls the hue to a target degree."""
    r, g, b = hex_to_rgb(hexcol)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if toward is not None:
        h += (toward / 360.0 - h) * pull
    h = (h + dh) % 1.0
    s = max(0.0, min(1.0, s * ds))
    v = max(0.0, min(1.0, (v ** gamma) * dv))
    return rgb_to_hex(colorsys.hsv_to_rgb(h, s, v))


class Profile:
    def __init__(self, name, character, blend=None, warp=None, slots=None,
                 palette=None, ortho=None, notes=""):
        self.name = name
        self.character = character
        self.blend = blend
        self.warp_fn = warp
        self.slots = slots or {}
        self.palette = palette
        self.ortho = ortho
        self.notes = notes

    def warp(self, pt):
        return self.warp_fn(pt[0], pt[1]) if self.warp_fn else (pt[0], pt[1])

    def color(self, hexcol, ch):
        """A profile with no palette of its own defers to the character's.
        `palette="identity"` forces the raw traced colours instead."""
        if self.palette == "identity":
            return hexcol
        if self.palette:
            return self.palette(hexcol)
        return ch.color(hexcol)

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


# ------------------------------------------------------------------- variants

PROFILES = {
    "nuggette-flat": Profile(
        "nuggette-flat", "nuggette", blend="nuggette-flat.blend",
        palette="identity",
        notes="Miss Nuggette in the colours actually measured off her "
              "reference, VHS grade and all. This is the build her fidelity "
              "numbers are measured on.",
    ),
}
