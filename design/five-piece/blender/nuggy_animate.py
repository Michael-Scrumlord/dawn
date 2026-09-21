"""Animate the Nuggy cutout rig.

Cutout animation: nothing is redrawn, the sockets are just moved over time,
the same way a paper puppet is posed under a camera. Every clip here is pure
keyframes on socket transforms, so it costs no extra geometry and survives a
re-trace of the artwork.

Clips live on one timeline, each with a marker, so switching between them is
just changing the frame range:

    idle    1-60    breathing, arm sway, a blink
    run    71-94    leg and arm cycle with a two-beat body bob
    shout 101-130   battle-cry burst, anticipate then hit then settle

    blender -b -P nuggy_animate.py
    blender -b -P nuggy_animate.py -- --clip run --render out/run_ --res 512
"""

import bpy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_IN = os.path.join(HERE, "nuggy.blend")
BLEND_OUT = os.path.join(HERE, "nuggy-animated.blend")

TAU = math.pi * 2
D = math.radians

CLIPS = {           # name: (start, length)
    "idle":  (1, 60),
    "run":   (71, 24),
    "shout": (101, 30),
}


# --------------------------------------------------------------------- utils

def key(ob, frame, loc=None, rot=None, scale=None, scale_abs=None):
    """Keyframe a socket.

    loc/rot/scale are relative to the rig's rest pose. scale_abs is absolute,
    which the eyelids need: they rest at scale.y 0 (open), so a relative scale
    would multiply by zero and never move.
    """
    rest = ob["_rest"]
    if scale_abs is not None:
        ob.scale = scale_abs
        ob.keyframe_insert("scale", frame=frame)
    if loc is not None:
        ob.location = (rest[0][0] + loc[0], rest[0][1] + loc[1],
                       rest[0][2] + loc[2])
        ob.keyframe_insert("location", frame=frame)
    if rot is not None:
        ob.rotation_euler = (rest[1][0] + rot[0], rest[1][1] + rot[1],
                             rest[1][2] + rot[2])
        ob.keyframe_insert("rotation_euler", frame=frame)
    if scale is not None:
        ob.scale = (rest[2][0] * scale[0], rest[2][1] * scale[1],
                    rest[2][2] * scale[2])
        ob.keyframe_insert("scale", frame=frame)


def snapshot(obs):
    for ob in obs.values():
        ob["_rest"] = (tuple(ob.location), tuple(ob.rotation_euler),
                       tuple(ob.scale))


def iter_fcurves(action):
    """Blender 4.4+ moved f-curves into layered "slotted" actions."""
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                yield from cb.fcurves


def ease(kind="BEZIER"):
    for ob in bpy.data.objects:
        ad = ob.animation_data
        if not ad or not ad.action:
            continue
        for fc in iter_fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = kind


# --------------------------------------------------------------------- clips

def clip_idle(R, start, n):
    """Breathing, a little arm drift, and one blink."""
    for i in range(n + 1):                       # one past the end so it loops
        f = start + i
        p = TAU * i / n
        key(R["root"], f,
            loc=(0, 0, 0.022 * math.sin(p)),
            scale=(1 - 0.009 * math.sin(p), 1 + 0.013 * math.sin(p), 1))
        key(R["arm_L"], f, rot=(0, 0, D(3.5) * math.sin(p)))
        key(R["arm_R"], f, rot=(0, 0, D(-4.0) * math.sin(p + 0.7)))
        key(R["sweat"], f, loc=(0, -0.018 * (0.5 - 0.5 * math.cos(p)), 0))

    # A blink draws the lids down and back up. Lids are separate objects with
    # their origin on the top edge, so scale.y 0 is open and 1 is shut.
    b = start + int(n * 0.62)
    for eye in ("eye_L", "eye_R"):
        for ob in (R[eye + "_lid"], R[eye + "_lash"]):
            key(ob, start, scale_abs=(1, 0, 1))
            key(ob, b - 3, scale_abs=(1, 0, 1))
            key(ob, b, scale_abs=(1, 1, 1))
            key(ob, b + 3, scale_abs=(1, 0, 1))
            key(ob, start + n, scale_abs=(1, 0, 1))


def clip_run(R, start, n):
    """Legs and arms in opposite phase, body bobbing twice per stride."""
    for i in range(n + 1):
        f = start + i
        p = TAU * i / n
        key(R["leg_L"], f, rot=(0, 0, D(27) * math.sin(p)))
        key(R["leg_R"], f, rot=(0, 0, D(27) * math.sin(p + math.pi)))
        key(R["arm_L"], f, rot=(0, 0, D(22) * math.sin(p + math.pi)))
        key(R["arm_R"], f, rot=(0, 0, D(-17) * math.sin(p)))
        # two bounces per stride, squashing at each contact
        bob = -0.055 * math.cos(2 * p)
        key(R["root"], f,
            loc=(0, 0, bob),
            rot=(0, D(4) + D(2.5) * math.sin(p), 0),
            scale=(1 + 0.02 * math.cos(2 * p), 1 - 0.03 * math.cos(2 * p), 1))
        key(R["sweat"], f, loc=(-0.02 * math.sin(p), -0.03 * math.cos(2 * p), 0))
        key(R["mouth"], f, scale=(1, 1 + 0.05 * math.cos(2 * p), 1))


def clip_shout(R, start, n):
    """Anticipate, hit, settle -- the classic three beats."""
    a, hit, s1, s2 = start, start + 6, start + 14, start + n

    key(R["root"], a, loc=(0, 0, 0), scale=(1, 1, 1))
    key(R["root"], a + 4, loc=(0, 0, -0.045), scale=(1.05, 0.93, 1))   # crouch
    key(R["root"], hit, loc=(0, 0, 0.075), scale=(0.94, 1.09, 1))      # burst
    key(R["root"], s1, loc=(0, 0, -0.012), scale=(1.02, 0.97, 1))
    key(R["root"], s2, loc=(0, 0, 0), scale=(1, 1, 1))

    key(R["mouth"], a, scale=(1, 1, 1))
    key(R["mouth"], a + 4, scale=(0.88, 0.80, 1))
    key(R["mouth"], hit, scale=(1.22, 1.30, 1))
    key(R["mouth"], s1, scale=(1.05, 1.06, 1))
    key(R["mouth"], s2, scale=(1, 1, 1))

    for eye, sgn in (("eye_L", 1), ("eye_R", -1)):
        key(R[eye], a, scale=(1, 1, 1), rot=(0, 0, 0))
        key(R[eye], a + 4, scale=(0.95, 0.88, 1), rot=(0, 0, D(2) * sgn))
        key(R[eye], hit, scale=(1.10, 1.12, 1), rot=(0, 0, D(-3) * sgn))
        key(R[eye], s2, scale=(1, 1, 1), rot=(0, 0, 0))

    for arm, sgn in (("arm_L", 1), ("arm_R", -1)):
        key(R[arm], a, rot=(0, 0, 0))
        key(R[arm], a + 4, rot=(0, 0, D(10) * sgn))
        key(R[arm], hit, rot=(0, 0, D(-16) * sgn))
        key(R[arm], s1, rot=(0, 0, D(5) * sgn))
        key(R[arm], s2, rot=(0, 0, 0))

    key(R["sweat"], a, loc=(0, 0, 0))
    key(R["sweat"], hit, loc=(-0.05, 0.06, 0))
    key(R["sweat"], s2, loc=(0, -0.02, 0))


# ---------------------------------------------------------------------- main

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv else default

    bpy.ops.wm.open_mainfile(filepath=BLEND_IN)

    R = {"root": bpy.data.objects["NUGGY_ROOT"]}
    for slot in ("eye_L", "eye_R", "mouth", "sweat",
                 "arm_L", "arm_R", "leg_L", "leg_R"):
        R[slot] = bpy.data.objects["SOCKET_" + slot]
    for eye in ("eye_L", "eye_R"):
        for part in ("lid", "lash"):
            R["%s_%s" % (eye, part)] = bpy.data.objects["%s_%s" % (eye, part)]
    snapshot(R)

    for name, fn in (("idle", clip_idle), ("run", clip_run), ("shout", clip_shout)):
        start, n = CLIPS[name]
        fn(R, start, n)
        mk = bpy.context.scene.timeline_markers.new(name, frame=start)
        mk.select = False
    ease()

    for ob in R.values():
        del ob["_rest"]

    clip = arg("--clip", "idle")
    start, n = CLIPS[clip]
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.frame_current = start, start + n - 1, start
    sc.render.fps = 24

    if "--no-save" not in argv:
        bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
        print("saved", BLEND_OUT)

    out = arg("--render")
    if out:
        res = int(arg("--res", "512"))
        sc.render.resolution_x = sc.render.resolution_y = res
        sc.render.filepath = os.path.abspath(out)
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGBA"
        bpy.ops.render.render(animation=True)
        print("rendered %s frames %d-%d -> %s"
              % (clip, sc.frame_start, sc.frame_end, out))


if __name__ == "__main__":
    main()
