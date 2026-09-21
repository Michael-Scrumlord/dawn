# Blender todo

Open work for `design/five-piece/blender`. How the pipeline works is in
`README.md`, including the traps worth not rediscovering. This file is only
what is left.

## Where it stands

Nuggy is traced from the canon art and rebuilt as flat vector curves. Measured
against the reference at 306x327 he scores IoU 0.9984 with a median pixel error
of 7/255. Nine groups move independently. Three animation clips run off socket
keyframes.

The remaining 4.6% of pixels that differ by more than 32/255 are almost all
posterization. The original is airbrushed and the trace is flat regions. Adding
more gold tones would close some of that gap at the cost of more shapes, but
flat regions are what makes the art usable as geometry, so I would leave it.

## Open items

**Blink quality.** The lid closes on the eye's real curve, but the traced ink
outline stays visible behind it, so a held-closed pose looks wrong. It reads
fine at 24fps. Tune `grown` and `lash` in `add_eyelid()`.

**Feature ghosting.** Hiding an eye or the mouth leaves a faint outline behind.
Shading immediately around those features traces as body rather than as the
feature. Fixing it means tightening the slot boxes in `contours.py` or
hand-assigning the leftover shapes.

**No brow slot.** Brow and upper lid are one connected black mass in this
artwork, so each eye slot owns both. Splitting them needs a cut line drawn by
hand.

**Expression variants.** `legacy/nuggy_parametric.py` holds four brows, five
mouths, three arm poses and two leg poses, all drawn in the old loose style.
They do not match the traced art, so they are not in the build. Redrawing them
in the traced style has not started. This is also what limited animation needs
if we ever want to cut between drawings mid-clip.

**Export formats.** Renders come out as a transparent PNG sequence and nothing
else is wired up. A sprite sheet stepped with CSS is probably what the
storefront wants. WebM keeps alpha if he needs to sit over a page.

**Animation coverage.** Three clips exist. Wave, land, stagger and point are all
the same technique and roughly an hour each.

**Lattice deformation.** The body can only scale right now. A lattice cage would
let it bend and wobble, which is the next real jump in animation quality.

## Next up

Nuggette, the tank. The profile system is in (`profiles.py`) and Nuggy is the
identity profile, verified to still score 0.9984 through it. Her body is blocked
out by warping Nuggy's torso wide through the chest and pinched at the waist,
scaling both arms 1.75x about their joints, and leaving the legs alone. See
`preview-nuggette.png`.

That body is a placeholder. The real next step is generating Nuggette art from
the prompt in `../nuggette.md` and tracing it the way Nuggy was traced. The
tracer will need her own colour seeds, face boxes and limb anchors, since all of
those are measured off the specific image.

The warp work is not wasted either way. It is how pose variants get made, and
how the rest of the crew reuses one trace.

Decided so far. Golden breading with pink as the accent only, which follows
`00-style-guide.md`. A pink-breading version was built and rejected. Her prop is
a pink bow.

## Crew status

| # | Name | Role | State |
|---|---|---|---|
| 1 | Nuggy | leader | traced, rigged, animated |
| 2 | Nuggesita | co-leader | art exists, not traced |
| 3 | Chic-Li | stealth | redesign of Tender-Li, art exists, not traced |
| 4 | Nugward | tech | not started |
| 5 | Nuggette | tank | body blocked out, face not generated |

`00-style-guide.md` still lists the old five with Tender-Li and Nugsage. It
needs updating for Chic-Li and Nuggette, and the group-shot layout in it refers
to characters that are changing.

## 3D

Nothing started. The layer split is the groundwork. Each `ZORDER` layer is a
separate closed 2D curve, so extruding per layer with an offset gives a relief
version, and the per-slot cut means arms and legs are already separate objects.
The animation is all socket transforms, so it survives the move.
