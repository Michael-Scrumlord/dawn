# Blender todo

Open work for `design/five-piece/blender`. How the pipeline works is in
`README.md`, including the traps worth not rediscovering. This file is only what
is left.

## Where it stands

Three characters are traced from their art and rebuilt as flat vector curves on
a socket rig.

| | groups | shapes | fidelity |
|---|---|---|---|
| Nuggy | 9 | 1342 | IoU 0.9984, mean error 11.3/255, median 7 |
| Miss Nuggette | 10 | 1899 | IoU 0.9833, mean error 14.9/255, median 7 |
| Chic-Li | 8 | 906 | IoU 0.9980, mean error 12.4/255, median 10 |

Miss Nuggette is 5.25 units tall against Nuggy's 3.50, the 1.5x that was asked
for. Her build regrades the VHS cast out of her reference and onto Nuggy's
ramp, and her blush survives now that it has its own layer.

Nuggette's medians match Nuggy's. Her mean and tail are worse because her
reference is a painted VHS screengrab with film grain in it, and the grain is
what the flat regions cannot follow. Sweeps on speck removal and
simplification moved her mean error by less than 0.2/255 while cutting her
shape count by two thirds, which is how we know the floor is the source and
not the tracer.

Chic-Li's numbers sit between the two: her reference is a rendered scene
illustration rather than flat cel art or a VHS screengrab, so it has real
shading gradients but no grain. See "Chic-Li build notes" below for how she
was traced and what her numbers mean.

## Open items

**Blink quality.** The lid closes on the eye's real curve, but the traced ink
outline stays visible behind it, so a held-closed pose looks wrong. It reads
fine at 24fps. Tune `grown` and `lash` in `add_eyelid()`.

**Feature ghosting.** Hiding an eye or the mouth leaves a faint outline behind.
Shading immediately around those features traces as body rather than as the
feature. Fixing it means tightening the slot boxes in `characters.py` or
hand-assigning the leftover shapes.

**No brow slot.** Brow and upper lid are one connected black mass in every
drawing so far, so each eye slot owns both. Splitting them needs a cut line
drawn by hand, the same way Miss Nuggette's limb cuts are.

**Miss Nuggette and Chic-Li have no clips.** `nuggy_animate.py` is still
written against Nuggy's slot names. Both rigs take keyframes the same way, but
the clips have to be written for what each actually has: Miss Nuggette's two
pigtails to swing, a raised fist to slam, and no sweat drops; Chic-Li's single
leg, an earring and a shuriken to keep steady while everything else moves.

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

**How fierce Miss Nuggette is.** The palette and blush now pull her back
towards bubbly, but the pose is still a battle cry: brows down, fist up, mouth
open. That works as her action pose. What she does not have is a resting one,
and the crew shot in `00-style-guide.md` probably wants her calm. A second
reference in a relaxed pose would trace through the same spec in about an
hour, since her colour seeds, feature boxes and limb cuts are all reusable.

## Crew status

| # | Name | Role | State |
|---|---|---|---|
| 1 | Nuggy | leader | traced, rigged, animated |
| 2 | Nuggesita | co-leader | art exists, not traced |
| 3 | Chic-Li | stealth | traced, rigged (`chicli.blend`); not animated |
| 4 | Nugward | tech | not started |
| 5 | Miss Nuggette | tank | traced and rigged, no clips yet |

`00-style-guide.md` still lists the old five with Tender-Li and Nugsage. It needs
updating for Chic-Li and Miss Nuggette, and the group-shot layout in it refers to
characters that are changing.

## Chic-Li build notes

Traced from `chic-li-1.jpeg` in `../../reference-media/`, a full scene
illustration (a moody tavern shot, not flat cel art like Nuggy's canon art or
a VHS screengrab like Miss Nuggette's). `reference/chic-li-cutout.png` is a
hand-isolated cutout of her made with a bespoke fence+seed matte, done once
and saved rather than wired into `trace/matte.py` -- her scene has none of
the same-hue-as-the-character ground problem that stage exists for, so a
purpose-built script was faster than generalizing that one too.

Chic-Li and Miss Nuggette were traced independently and in parallel, each
proving out the same generalized `--char` pipeline (`characters.py`,
`trace/quantize.py`, `trace/contours.py`, `build.py`) against a different
kind of source art on the way through: Miss Nuggette needed the VHS regrade
and hand-drawn limb cuts, Chic-Li needed a bespoke matte and a face slot
whose features are boxed but built from ordinary body-colour layers
(`slot_layers`, for the earring and the shuriken).

Her palette stays in Nuggy's exact golden family and eye colours per
`00-style-guide.md` ("stay inside the golden family"); the hood, cloak and
shuriken are new tones built at the same value tiers as his gold ramp. There
is no mouth slot -- the scarf covers it in the source art -- and only one
`leg` slot, not `leg_L`/`leg_R`, since the other leg is hidden under the
cloak in the reference pose.

`ink_lum` didn't end up mattering: the moody scene lighting means a lot of
true shadow, not just linework, sits close enough to black in the source
photo that nearest-colour matching alone puts it in the ink layer regardless
of the reclaim threshold. It reads fine as heavy shadow on a stealth
character, and her measured fidelity (IoU 0.9980) confirms it isn't costing
silhouette accuracy; leaving it rather than fighting the source art's own
lighting.

One live-session trap worth logging: driving `build.py` through a running
Blender via MCP rather than a throwaway `blender -b -P` process, its scene
reset used to call `bpy.ops.wm.read_factory_settings()`, which tore down the
MCP add-on's own connection along with the scene. `build()` now clears the
scene by removing every object, collection and orphaned data-block by hand
instead, which reaches the same empty scene without reloading the file.

## 3D

`model3d.py` inflates a trace into a mesh: `nuggy-3d.blend` and
`nuggette-3d.blend`, both built, both with the baked maps packed in. Square on
and out to about 40 degrees they hold up. See the README for how and why.

What is left on this path:

**The side.** Past 40 degrees the rim takes over the frame and it is flat
breading colour, because the front projection has nothing to say there. Three
ways forward, in ascending cost: paint a side strip by hand and project it onto
the rim; generate a side-view reference and blend two projections; or sculpt.

**Nobody has opened these in the UI yet.** They were built and rendered
headless. Worth a look before anything gets built on them.

**No rig.** The 2D rig's sockets did not carry over; the mesh is one object per
character. Bones replacing the sockets is the natural next step, and the limb
cuts already say where the joints are.

**Turntable GIF is 1MB.** Fine for a preview, not for a page.
