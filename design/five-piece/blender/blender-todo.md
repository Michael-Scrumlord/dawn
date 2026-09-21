# Blender todo

Open work for `design/five-piece/blender`. How the pipeline works is in
`README.md`, including the traps worth not rediscovering. This file is only what
is left.

## Where it stands

Two characters are traced from their art and rebuilt as flat vector curves on a
socket rig.

| | groups | shapes | fidelity |
|---|---|---|---|
| Nuggy | 9 | 1342 | IoU 0.9984, mean error 11.3/255, median 7 |
| Miss Nuggette | 10 | 1899 | IoU 0.9833, mean error 14.9/255, median 7 |

She is 5.25 units tall against his 3.50, the 1.5x that was asked for. Her build
regrades the VHS cast out of her reference and onto Nuggy's ramp, and her blush
survives now that it has its own layer.

The medians match. Her mean and tail are worse because her reference is a
painted VHS screengrab with film grain in it, and the grain is what the flat
regions cannot follow. Sweeps on speck removal and simplification moved her mean
error by less than 0.2/255 while cutting her shape count by two thirds, which is
how we know the floor is the source and not the tracer.

## Open items

**Blink quality.** The lid closes on the eye's real curve, but the traced ink
outline stays visible behind it, so a held-closed pose looks wrong. It reads
fine at 24fps. Tune `grown` and `lash` in `add_eyelid()`.

**Feature ghosting.** Hiding an eye or the mouth leaves a faint outline behind.
Shading immediately around those features traces as body rather than as the
feature. Fixing it means tightening the slot boxes in `characters.py` or
hand-assigning the leftover shapes.

**No brow slot.** Brow and upper lid are one connected black mass in both
drawings, so each eye slot owns both. Splitting them needs a cut line drawn by
hand, the same way her limb cuts are.

**Miss Nuggette has no clips.** `nuggy_animate.py` is still written against
Nuggy's slot names. Her rig takes keyframes the same way, but the clips have to
be written for what she actually has: two pigtails to swing, a raised fist to
slam, and no sweat drops.

**Expression variants.** `legacy/nuggy_parametric.py` holds four brows, five
mouths, three arm poses and two leg poses, all drawn in the old loose style.
They do not match the traced art, so they are not in the build. Redrawing them
in the traced style has not started. This is also what limited animation needs
if we ever want to cut between drawings mid-clip.

**Export formats.** Renders come out as a transparent PNG sequence and nothing
else is wired up. A sprite sheet stepped with CSS is probably what the storefront
wants. WebM keeps alpha if a character has to sit over a page.

**Lattice deformation.** A body can only scale right now. A lattice cage would
let it bend and wobble, which is the next real jump in animation quality.

## Decisions waiting on you

**How fierce she is.** The palette and blush now pull her back towards bubbly,
but the pose is still a battle cry: brows down, fist up, mouth open. That works
as her action pose. What she does not have is a resting one, and the crew shot
in `00-style-guide.md` probably wants her calm. A second reference in a relaxed
pose would trace through the same spec in about an hour, since her colour seeds,
feature boxes and limb cuts are all reusable.

## Crew status

| # | Name | Role | State |
|---|---|---|---|
| 1 | Nuggy | leader | traced, rigged, animated |
| 2 | Nuggesita | co-leader | art exists, not traced |
| 3 | Chic-Li | stealth | redesign of Tender-Li, art exists, not traced |
| 4 | Nugward | tech | not started |
| 5 | Miss Nuggette | tank | traced and rigged, no clips yet |

`00-style-guide.md` still lists the old five with Tender-Li and Nugsage. It needs
updating for Chic-Li and Miss Nuggette, and the group-shot layout in it refers to
characters that are changing.

## 3D

Nothing started. The layer split is the groundwork. Each `zorder` layer is a
separate closed 2D curve, so extruding per layer with an offset gives a relief
version, and the per-slot cut means limbs are already separate objects. The
animation is all socket transforms, so it survives the move.
