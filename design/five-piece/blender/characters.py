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
                 crop=None, out=None,
                 hue=(8, 58), pink_hue=325, grow_steps=60, open_r=7):
        self.source = os.path.join(REF, source)
        self.fence = fence
        self.seeds = seeds
        self.height = height
        self.margin = margin
        # (x0, y0, w, h) in source pixels. Without it the crop is derived from
        # the measured silhouette, so every tweak to the fence shifts the whole
        # coordinate system and every measured feature box with it. matte.py
        # prints the rect it derived; pasting it here freezes it.
        self.crop = crop
        self.out = out
        self.hue = hue
        self.pink_hue = pink_hue
        self.grow_steps = grow_steps
        self.open_r = open_r


class Character:
    def __init__(self, name, reference, blend, seeds, centre, scale,
                 slots, allow=None, roi=(), limb_anchors=None, slot_help=None,
                 slot_layers=None, zorder=None, limb_polys=None, pivots=None,
                 palette=None, fine_layers=None,
                 cutout=None, src=4, ink_lum=0.30, rim_band=4, mode_passes=2,
                 open_r=22, limb_max_dist=110, min_area=2.4, min_area_ink=0.7,
                 rdp_eps=1.2, chaikin=2, blur_r=0, ortho=4.0, notes=""):
        self.name = name
        self.reference = os.path.join(REF, reference)
        self.blend = blend
        self.cutout = cutout
        self.seeds = seeds                  # [(layer name, hex)]
        self.allow = allow or {}            # layer -> [boxes it may appear in]
        self.roi = list(roi)                # [(slot, box)] in reference px
        self.limb_anchors = limb_anchors or {}
        self.slots = list(slots)
        self.slot_help = slot_help or {}
        self.slot_layers = slot_layers or {}
        self._zorder = zorder
        self.limb_polys = limb_polys or {}
        self.pivots = pivots or {}
        self.palette = palette or {}
        # Layers whose detail is thin strokes, so they keep the lower speck floor.
        self.fine_layers = fine_layers or {"ink"}
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

    def color(self, hexcol):
        """The colour this layer is built in, which need not be the colour it
        was matched on. See NUGGETTE_PALETTE."""
        return self.palette.get(hexcol.upper(), hexcol)

    @property
    def zorder(self):
        """Back to front. Regions are exact and disjoint, so this only decides
        which side of a shared edge wins the quarter-pixel overlap the tracer
        adds. Breading dark to light, then features, then ink on top."""
        if self._zorder:
            return self._zorder
        feat = [n for n in self.names if n in self.allow]
        return (["silhouette", "skinfill"]
                + [n for n in self.names if n not in self.allow and n != "ink"]
                + feat + ["ink"])

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
    zorder=["silhouette", "skinfill", "rim", "shade_deep", "shade", "amber",
            "gold_deep", "gold_mid", "gold_base", "gold_light", "gold_pale",
            "eye_shadow", "eye_white", "mouth_dk", "tongue", "iris", "pupil",
            "ink"],
    slot_layers={"sweat": {"ink", "eye_white", "eye_shadow", "iris", "pupil",
                           "mouth_dk", "tongue", "gold_pale"}},
    # Spelled out rather than left to the defaults, so a sweep on one
    # character cannot quietly move another.
    ink_lum=0.30, mode_passes=2, rim_band=4,
    open_r=22, limb_max_dist=110,
    min_area=2.4, min_area_ink=0.7, rdp_eps=1.2, chaikin=2, blur_r=0,
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
    (440, 814), (420, 795), (392, 762), (368, 722), (374, 676), (402, 646),
    (420, 598), (414, 548), (404, 498), (392, 458), (378, 432), (345, 410), (305, 385),
    (268, 358), (230, 330), (190, 302), (148, 270), (138, 215), (150, 192),
]

# Feature boxes, measured off miss-nuggette-cutout.png. Her eye, mouth and bow
# colours all have near-twins somewhere in the breading, so each is fenced to
# the box where that feature actually lives.
N_EYES = (240, 92, 466, 268)
N_MOUTH = (286, 210, 364, 306)
N_BOW_L = (200, 38, 310, 122)
N_BOW_R = (462, 96, 548, 200)
N_CHEEK_L = (236, 188, 298, 224)
N_CHEEK_R = (372, 216, 446, 260)

# Her reference is graded like a 1995 VHS tape: every tone sits a stop darker
# and a shade greyer than the crew's house palette. That grade is an artifact of
# the art direction, not of her, so the build puts it back.
#
# The breading is not eyeballed. Her nine tones, ordered dark to light, are
# resampled onto Nuggy's eight, so she comes out on exactly his ramp rather than
# near it. Her face and ink take his values outright. The bows are the one place
# that is a choice rather than a transfer: the reference paints them a dusty
# rose, and the crew reads her as bubblegum.
NUGGETTE_PALETTE = {
    "#1B120D": "#281108",   # ink          -> Nuggy's ink
    "#4C230F": "#834315",   # shade_deep   -.
    "#652D0F": "#99581C",   # shade         |
    "#803B13": "#A66923",   # amber         |
    "#964813": "#BD7C26",   # gold_deep     +- his ramp, resampled to nine steps
    "#A95717": "#D38A27",   # gold_mid      |
    "#C47821": "#E29727",   # gold_base     |
    "#D1892A": "#ECA72C",   # gold_light    |
    "#DEA73B": "#F2C04C",   # gold_pale     |
    "#E9C77E": "#F7E3A0",   # gold_cream   -'
    "#CBBDB6": "#FAF6D1",   # eye_white    -.
    "#8F7A80": "#D9C199",   # eye_shadow    |
    "#583A22": "#8A5A28",   # iris          +- his face
    "#2A1810": "#3A1E0C",   # pupil         |
    "#291410": "#4A1A18",   # mouth_dk      |
    "#B05A50": "#D9736E",   # tongue       -'
    "#B84E57": "#F56E92",   # bow          -. her accent
    "#85282E": "#C43C6B",   # bow_dark     -'
    "#B85326": "#EF8C86",   # blush
}

NUGGETTE = Character(
    "nuggette", "miss-nuggette-cutout.png", "nuggette.blend",
    notes="Tank. Traced from a scene illustration, so she needs the matte "
          "stage first. Built 1.5x Nuggy's height.",
    cutout=Cutout(
        "miss-nuggette-1.png", NUGGETTE_FENCE,
        seeds=[(760, 600), (300, 200), (1140, 540), (560, 250), (1100, 300),
               (1000, 200), (470, 700), (820, 700), (570, 120), (1050, 340)],
        height=400, grow_steps=70,
        crop=(132, 44, 1196, 751), out=(656, 412),
    ),
    # Measured off the cutout, not borrowed from Nuggy. Her reference is a
    # VHS-styled screengrab, so every tone sits darker and greyer than his.
    # profiles.py has a regrade that lifts her into his range.
    seeds=[
        ("ink",        "#1B120D"),
        ("shade_deep", "#4C230F"),
        ("shade",      "#652D0F"),
        ("amber",      "#803B13"),
        ("gold_deep",  "#964813"),
        ("gold_mid",   "#A95717"),
        ("gold_base",  "#C47821"),
        ("gold_light", "#D1892A"),
        ("gold_pale",  "#DEA73B"),
        ("gold_cream", "#E9C77E"),
        ("eye_white",  "#CBBDB6"),
        ("eye_shadow", "#8F7A80"),
        ("iris",       "#583A22"),
        ("pupil",      "#2A1810"),
        ("mouth_dk",   "#291410"),
        ("tongue",     "#B05A50"),
        ("bow",        "#B84E57"),
        ("bow_dark",   "#85282E"),
        ("blush",      "#B85326"),
    ],
    allow={
        "eye_white":  [N_EYES],
        "eye_shadow": [N_EYES],
        "iris":       [N_EYES],
        "pupil":      [N_EYES],
        "mouth_dk":   [N_MOUTH],
        "tongue":     [N_MOUTH],
        "bow":        [N_BOW_L, N_BOW_R],
        "bow_dark":   [N_BOW_L, N_BOW_R],
        "blush":      [N_CHEEK_L, N_CHEEK_R],
    },
    roi=[
        ("eye_L", (240, 92, 360, 220)),
        ("eye_R", (352, 140, 466, 268)),
        ("mouth", N_MOUTH),
    ],
    # Hand-drawn cuts rather than anchors. Each polygon takes what it covers,
    # first listed wins the overlap, and the torso is the remainder. The
    # pigtails carry the bows, so they are one slot each rather than hair and
    # ribbon separately -- swinging a pigtail has to take its bow along.
    limb_polys={
        "arm_L": [(0, 0), (172, 0), (198, 70), (214, 120), (224, 168),
                  (212, 206), (176, 234), (110, 254), (0, 262)],
        "pig_L": [(172, 0), (300, 0), (312, 64), (298, 116), (216, 122),
                  (198, 70)],
        "pig_R": [(458, 40), (656, 40), (656, 214), (500, 212), (468, 160)],
        "arm_R": [(480, 214), (656, 214), (656, 345), (505, 348), (468, 282)],
        "leg_L": [(105, 330), (200, 338), (275, 352), (290, 412), (95, 412)],
        "leg_R": [(432, 340), (500, 322), (552, 302), (570, 412), (420, 412)],
    },
    # The joint each slot turns about. Derived pivots land on the cut, which is
    # right for a limb that grows out of the torso; a pigtail should swing from
    # where it is tied instead, and a raised arm from the shoulder.
    pivots={"arm_L": (214, 188), "arm_R": (482, 258),
            "pig_L": (255, 112), "pig_R": (478, 168)},
    slots=["eye_L", "eye_R", "mouth", "pig_L", "pig_R",
           "arm_L", "arm_R", "leg_L", "leg_R"],
    slot_help={
        "eye_L": "left eye, brow and lashes (0 hide, 1 show)",
        "eye_R": "right eye, brow and lashes (0 hide, 1 show)",
        "mouth": "mouth and tongue (0 hide, 1 show)",
        "pig_L": "left pigtail and bow (0 hide, 1 show)",
        "pig_R": "right pigtail and bow (0 hide, 1 show)",
        "arm_L": "raised arm and fist (0 hide, 1 show)",
        "arm_R": "lowered arm and fist (0 hide, 1 show)",
        "leg_L": "left foot (0 hide, 1 show)",
        "leg_R": "right foot (0 hide, 1 show)",
    },
    # Her whole palette is darker, so the threshold below which a breading
    # pixel is really linework has to drop with it; at Nuggy's 0.30 her
    # deepest shadow tone would all turn to ink.
    zorder=["silhouette", "skinfill", "shade_deep", "shade", "amber",
            "gold_deep", "gold_mid", "gold_base", "gold_light", "gold_pale",
            "gold_cream", "blush", "eye_shadow", "eye_white", "mouth_dk",
            "tongue", "iris", "pupil", "bow_dark", "bow", "ink"],
    fine_layers={"ink", "blush"},
    ink_lum=0.19, mode_passes=3,
    min_area=12.0, min_area_ink=3.0, rdp_eps=2.0,
    palette=NUGGETTE_PALETTE,
    centre=(330.5, 206.0), scale=1.5 * 3.502 / 400.0, ortho=9.0,
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

CHICLI_FACE = {"ink", "eye_white", "eye_shadow", "iris", "pupil"}

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
        "eye_L": CHICLI_FACE, "eye_R": CHICLI_FACE,
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
    # Body breading first, then the cloak (worn over it, so it should win any
    # overlap at the neck wrap), then the star (sits on top of the cloak),
    # then the face features, ink last.
    zorder=["silhouette", "skinfill", "rim", "shade_deep", "shade", "amber",
            "gold_deep", "gold_mid", "gold_base", "gold_light", "gold_pale",
            "hood_shadow", "hood_deep", "hood_base", "hood_light", "hood_pale",
            "metal_dark", "metal_mid", "metal_light",
            "eye_shadow", "eye_white", "iris", "pupil", "ink"],
    # cutout is 874x1276; centre is its exact midpoint, same convention as
    # Nuggy. scale maps her full cutout height to about the same world size
    # as Nuggy so the crew reads as one scale (00-style-guide.md has no
    # ratio for her yet since she isn't in the original five).
    centre=(437.0, 638.0), scale=3.5 / 1276.0, ortho=4.0,
    ink_lum=0.08,             # the scene art is moodier/darker than Nuggy's;
                              # nearest-colour match puts deep shadow in ink
                              # regardless of this -- see blender-todo.md.
    rim_band=11, open_r=63, limb_max_dist=314,   # scaled ~2.86x for the 874px cutout
    min_area=20, min_area_ink=6, rdp_eps=3.4,
)


CHARACTERS = {c.name: c for c in (NUGGY, NUGGETTE, CHIC_LI)}
