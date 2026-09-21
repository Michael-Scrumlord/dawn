"""Per-character tracing and build settings.

Every number here was measured off one specific piece of artwork. Colour
seeds, feature boxes, limb anchors and speck floors do not carry from one
character to the next, which is why they live in a spec rather than at the top
of the scripts. The pipeline itself is shared.

    trace/matte.py     scene illustration -> clean RGBA cutout   (stage 0)
    trace/quantize.py  cutout             -> named colour layers (stage 1)
    trace/contours.py  colour layers      -> polygons + slots    (stage 2)
    build.py           polygons           -> a rigged .blend     (stage 3)
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.normpath(os.path.join(HERE, "..", "reference"))


class Cutout:
    """Stage 0. Only for a character drawn into a full scene.

    `fence` is a hand-drawn polygon, loose except where the character touches
    scenery of the same colour. `seeds` are points known to be inside her.
    `height` is the silhouette height the cutout is scaled to, which is what
    sets tracing detail; world size is set separately by Character.scale.
    """

    def __init__(self, source, fence, seeds, height, margin=6,
                 hue=(8, 58), pink_hue=325, grow_steps=60, open_r=7):
        self.source = os.path.join(REF, source)
        self.fence = fence
        self.seeds = seeds
        self.height = height
        self.margin = margin
        self.hue = hue
        self.pink_hue = pink_hue
        self.grow_steps = grow_steps
        self.open_r = open_r


class Character:
    def __init__(self, name, reference, blend, seeds, centre, scale,
                 slots, zorder=None, allow=None, roi=(), limb_anchors=None,
                 slot_help=None, slot_layers=None, cutout=None, src=4,
                 ink_lum=0.30, rim_band=4, mode_passes=2, open_r=22,
                 limb_max_dist=110, min_area=2.4, min_area_ink=0.7,
                 rdp_eps=1.2, chaikin=2, blur_r=0, ortho=4.0, notes=""):
        self.name = name
        self.reference = os.path.join(REF, reference)
        self.blend = blend
        self.cutout = cutout
        self.seeds = seeds                  # [(layer name, hex)]
        # Paint order, back to front, for build.py's Z-stack. Defaults to
        # seed order with "ink" moved last, which is wrong for any character
        # whose seeds aren't already authored back-to-front (Nuggy's are;
        # write an explicit one for anyone else).
        self.zorder = zorder or (
            ["silhouette", "skinfill"]
            + [n for n, _ in seeds if n != "ink"] + ["ink"])
        self.allow = allow or {}            # layer -> [boxes it may appear in]
        self.roi = list(roi)                # [(slot, box)] in reference px
        self.limb_anchors = limb_anchors or {}
        self.slots = list(slots)
        self.slot_help = slot_help or {}
        # slot -> {layer names it may claim}. A slot missing here falls back
        # to "ink" plus every colour layer that is ALLOW-restricted anywhere,
        # which is what a face feature wants. A slot built from body-colour
        # layers (an earring in gold, a star in steel) needs its own set, or
        # the big skin/fabric shapes near it would never lose to it and it
        # would never win containment either -- see slot_for() in contours.py.
        self.slot_layers = slot_layers or {}
        self.centre = centre                # reference px mapped to the origin
        self.scale = scale                  # Blender units per reference px
        self.ortho = ortho
        self.src = src
        self.ink_lum = ink_lum
        self.rim_band = rim_band
        self.mode_passes = mode_passes
        self.open_r = open_r
        self.limb_max_dist = limb_max_dist
        self.min_area = min_area
        self.min_area_ink = min_area_ink
        self.rdp_eps = rdp_eps
        self.chaikin = chaikin
        self.blur_r = blur_r
        self.notes = notes

    @property
    def names(self):
        return [n for n, _ in self.seeds]

    @property
    def colors(self):
        c = dict(self.seeds)
        c["skinfill"] = c.get("gold_base", "#EBA126")
        c["silhouette"] = c["ink"]
        return c

    @property
    def gold(self):
        """Breading tones: everything that is neither ink nor a feature."""
        feat = set(self.allow) | {"ink"}
        return [i for i, n in enumerate(self.names) if n not in feat]

    def out_dir(self):
        return os.path.join(HERE, "trace", "out", self.name)


# --------------------------------------------------------------------- nuggy

NUGGY = Character(
    "nuggy", "nuggy-canon.webp", "nuggy.blend",
    notes="Canon leader. Clean cutout art, so no matte stage.",
    seeds=[
        ("ink",        "#281108"),
        ("gold_pale",  "#F7E3A0"),
        ("gold_light", "#F1BA40"),
        ("gold_base",  "#EBA126"),
        ("gold_mid",   "#DD9127"),
        ("gold_deep",  "#C98426"),
        ("amber",      "#A96E25"),
        ("shade",      "#9C5B1D"),
        ("shade_deep", "#834315"),
        ("rim",        "#6A5507"),
        ("eye_white",  "#FAF6D1"),
        ("eye_shadow", "#D9C199"),
        ("iris",       "#8A5A28"),
        ("pupil",      "#3A1E0C"),
        ("mouth_dk",   "#4A1A18"),
        ("tongue",     "#D9736E"),
    ],
    zorder=["silhouette", "skinfill", "rim", "shade_deep", "shade", "amber",
            "gold_deep", "gold_mid", "gold_base", "gold_light", "gold_pale",
            "eye_shadow", "eye_white", "mouth_dk", "tongue", "iris", "pupil",
            "ink"],
    allow={
        "eye_white":  [(118, 96, 252, 178), (146, 164, 224, 230),
                       (96, 98, 132, 196), (216, 184, 244, 218)],
        "eye_shadow": [(118, 96, 252, 178), (146, 164, 224, 230)],
        "iris":       [(118, 96, 252, 178)],
        "pupil":      [(118, 96, 252, 178)],
        "mouth_dk":   [(146, 164, 224, 230)],
        "tongue":     [(146, 164, 224, 230)],
    },
    roi=[
        ("sweat", (90, 85, 126, 200)),
        ("sweat", (216, 184, 244, 218)),
        ("eye_L", (118, 84, 202, 166)),
        ("eye_R", (198, 96, 250, 174)),
        ("mouth", (150, 168, 220, 226)),
    ],
    limb_anchors={"arm_L": (85, 178), "arm_R": (268, 168),
                  "leg_L": (105, 285), "leg_R": (238, 265)},
    slots=["eye_L", "eye_R", "mouth", "sweat",
           "arm_L", "arm_R", "leg_L", "leg_R"],
    slot_help={
        "eye_L": "left eye, brow and lashes (0 hide, 1 show)",
        "eye_R": "right eye, brow and lashes (0 hide, 1 show)",
        "mouth": "mouth, teeth and tongue (0 hide, 1 show)",
        "sweat": "sweat drops (0 hide, 1 show)",
        "arm_L": "left arm and mitt (0 hide, 1 show)",
        "arm_R": "right arm and fist (0 hide, 1 show)",
        "leg_L": "left leg and foot (0 hide, 1 show)",
        "leg_R": "right leg and foot (0 hide, 1 show)",
    },
    centre=(153.0, 163.5), scale=3.5 / 306.0, ortho=4.0,
)


# ------------------------------------------------------------------ nuggette

# Fence for the matte: loose around the top and sides, hugging along the
# bottom where she sits in the frying oil, which is her exact colour.
NUGGETTE_FENCE = [
    (165, 190), (185, 160), (210, 143), (240, 128), (270, 116), (300, 114),
    (330, 120), (358, 134), (385, 152), (405, 175), (418, 196),
    (432, 168), (448, 142), (468, 118), (492, 95), (520, 62), (560, 44),
    (600, 40), (640, 46), (662, 120), (672, 172),
    (740, 166), (820, 162), (900, 164), (980, 158), (1060, 150), (1140, 162),
    (1235, 190), (1312, 245), (1318, 302), (1240, 352), (1196, 400),
    (1180, 442), (1236, 495), (1242, 560), (1202, 612), (1162, 652),
    (1142, 702), (1116, 752), (1078, 800), (1020, 814), (960, 802),
    (900, 776), (820, 758), (740, 757), (660, 768), (580, 786), (500, 800),
    (440, 814), (425, 800), (400, 758), (388, 706), (384, 656), (390, 606),
    (394, 556), (385, 512), (390, 470), (378, 435), (345, 410), (305, 385),
    (268, 358), (230, 330), (190, 302), (148, 270), (138, 215), (150, 192),
]

NUGGETTE = Character(
    "nuggette", "miss-nuggette-cutout.png", "nuggette.blend",
    notes="Tank. Traced from a scene illustration, so she needs the matte "
          "stage first. Built 1.5x Nuggy's height.",
    cutout=Cutout(
        "miss-nuggette-1.png", NUGGETTE_FENCE,
        seeds=[(760, 600), (300, 200), (1140, 540), (560, 250), (1100, 300),
               (1000, 200), (470, 700), (820, 700), (570, 120), (1050, 340)],
        height=400, grow_steps=30,
    ),
    # measured after the cutout exists
    seeds=[("ink", "#281108")],
    slots=[],
    centre=(328.0, 206.0), scale=1.5 * 3.502 / 400.0, ortho=6.5,
)



# --------------------------------------------------------------------- chicli

# Boxes in CHIC_LI's own reference pixels (chic-li-cutout.png, 874x1276), read
# off a 50px grid overlaid on the cutout. Unlike Nuggy's eyes there is no
# mouth box: the scarf covers it, so there is no mouth slot at all. The
# earring and the shuriken are boxed the same way a face feature is, even
# though their fill colour is the shared gold or steel family rather than a
# feature-only colour -- see slot_layers below for why that needs its own
# entry per slot instead of the FACE_LAYERS default.
EYE_L = (130, 370, 390, 545)
EYE_R = (390, 370, 650, 545)
EARRING = (615, 375, 760, 500)
STAR = (390, 670, 710, 970)

FACE = {"ink", "eye_white", "eye_shadow", "iris", "pupil"}

CHIC_LI = Character(
    "chicli", "chic-li-cutout.png", "chicli.blend",
    notes="Stealth. Redesign of Tender-Li. Traced from a hand-isolated cutout "
          "of a full scene illustration (chic-li-1.jpeg), so no matte stage: "
          "background removal was done once by a bespoke fence+seed matte and "
          "the result saved as reference/chic-li-cutout.png. Reuses Nuggy's "
          "golden breading family and eye palette per 00-style-guide.md "
          "('stay inside the golden family'); the hood, cloak and shuriken "
          "are new tones built at the same value tiers as Nuggy's gold ramp "
          "so the cel-shaded look matches. Only one leg is visible in the "
          "source art -- the other is under the cloak -- so there is a "
          "single 'leg' slot, not leg_L/leg_R.",
    seeds=[
        ("ink",         "#281108"),
        ("gold_pale",   "#F7E3A0"),
        ("gold_light",  "#F1BA40"),
        ("gold_base",   "#EBA126"),
        ("gold_mid",    "#DD9127"),
        ("gold_deep",   "#C98426"),
        ("amber",       "#A96E25"),
        ("shade",       "#9C5B1D"),
        ("shade_deep",  "#834315"),
        ("rim",         "#6A5507"),
        ("eye_white",   "#FAF6D1"),
        ("eye_shadow",  "#D9C199"),
        ("iris",        "#8A5A28"),
        ("pupil",       "#3A1E0C"),
        ("hood_pale",   "#BD9ADB"),
        ("hood_light",  "#9772B8"),
        ("hood_base",   "#745094"),
        ("hood_deep",   "#52366B"),
        ("hood_shadow", "#311E42"),
        ("metal_light", "#D9D2D2"),
        ("metal_mid",   "#8C8585"),
        ("metal_dark",  "#524B4B"),
    ],
    # Body breading first, then the cloak (worn over it, so it should win any
    # overlap at the neck wrap), then the star (sits on top of the cloak),
    # then the face features, ink last.
    zorder=["silhouette", "skinfill", "rim", "shade_deep", "shade", "amber",
            "gold_deep", "gold_mid", "gold_base", "gold_light", "gold_pale",
            "hood_shadow", "hood_deep", "hood_base", "hood_light", "hood_pale",
            "metal_dark", "metal_mid", "metal_light",
            "eye_shadow", "eye_white", "iris", "pupil", "ink"],
    allow={
        "eye_white":  [EYE_L, EYE_R],
        "eye_shadow": [EYE_L, EYE_R],
        "iris":       [EYE_L, EYE_R],
        "pupil":      [EYE_L, EYE_R],
        "metal_light": [STAR],
        "metal_mid":   [STAR],
        "metal_dark":  [STAR],
    },
    roi=[
        ("eye_L", EYE_L),
        ("eye_R", EYE_R),
        ("earring", EARRING),
        ("star", STAR),
    ],
    slot_layers={
        "eye_L": FACE, "eye_R": FACE,
        "earring": {"ink", "gold_pale", "gold_light", "gold_base"},
        "star": {"ink", "metal_light", "metal_mid", "metal_dark"},
    },
    limb_anchors={"arm_L": (130, 830), "arm_R": (680, 820), "leg": (270, 1100)},
    slots=["eye_L", "eye_R", "earring", "star", "arm_L", "arm_R", "leg"],
    slot_help={
        "eye_L": "left eye and brow (0 hide, 1 show)",
        "eye_R": "right eye and brow (0 hide, 1 show)",
        "earring": "gold hoop earring (0 hide, 1 show)",
        "star": "shuriken on the chest (0 hide, 1 show)",
        "arm_L": "left arm and fist (0 hide, 1 show)",
        "arm_R": "right arm and fist (0 hide, 1 show)",
        "leg": "the one visible leg and foot (0 hide, 1 show)",
    },
    # cutout is 874x1276; centre is its exact midpoint, same convention as
    # Nuggy. scale maps her full cutout height to about the same world size
    # as Nuggy so the crew reads as one scale (00-style-guide.md has no
    # ratio for her yet since she isn't in the original five).
    centre=(437.0, 638.0), scale=3.5 / 1276.0, ortho=4.0,
    ink_lum=0.08,             # the scene art is moodier/darker than Nuggy's
    rim_band=11, open_r=63, limb_max_dist=314,   # scaled ~2.86x for the 874px cutout
    min_area=20, min_area_ink=6, rdp_eps=3.4,
)


CHARACTERS = {c.name: c for c in (NUGGY, NUGGETTE, CHIC_LI)}
