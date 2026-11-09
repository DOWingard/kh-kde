"""Colour tokens for both theme variants.

Every colour is taken from the reference material the theme is built around,
so the two variants share one vocabulary:

* the series logo (heart blue, crown gold),
* the Kingdom Key D (blade gold, guard silver, bronze),
* the Organization coat (near-black),
* the first game's command menu, whose five menu colours (blue, red, purple,
  green, orange) supply the semantic colours.

Variants:

* ORG_XIII — dark. Black with white accents; Key D gold only for links and
  the pointer.
* SORA — light. The first game's colours: logo blue for selection and title
  bars, crown gold for ornaments.

Every generated asset is built once per `Palette`, so re-skinning a variant is
a matter of editing its tokens here and rebuilding.
"""

from __future__ import annotations

from dataclasses import dataclass

Color = tuple[str, float]  # (#rrggbb, alpha)

WHITE = "#ffffff"
BLACK = "#000000"


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #rrggbb, got {hex_color!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_csv(hex_color: str) -> str:
    """'r,g,b' as used by KDE .colors files and Konsole schemes."""
    return ",".join(str(c) for c in rgb(hex_color))


def mix(a: str, b: str, t: float) -> str:
    """Linear blend of two colours; t=0 gives a, t=1 gives b."""
    ra, ga, ba = rgb(a)
    rb, gb, bb = rgb(b)
    return "#%02x%02x%02x" % (
        round(ra + (rb - ra) * t),
        round(ga + (gb - ga) * t),
        round(ba + (bb - ba) * t),
    )


@dataclass(frozen=True)
class Palette:
    key: str  # suffix of every theme/file id, e.g. "OrgXIII"
    title: str  # human-readable variant name
    dark: bool
    base_icons: str  # icon theme the variant's icon theme inherits from

    # --- application surfaces ---
    view: str
    view_alt: str
    window: str
    window_alt: str
    button: str
    button_alt: str
    header: str
    header_inactive: str
    tooltip: str
    # Always-dark set used by full-screen shell UI (lock, logout, switcher).
    complementary: str
    complementary_alt: str
    complementary_text: str

    # --- text ---
    text: str
    text_dim: str
    text_faint: str

    # --- selection / interaction ---
    select: str
    select_deep: str
    select_hi: str
    select_text: str
    focus: str
    hover: str

    # --- semantic ---
    link: str
    visited: str
    negative: str
    neutral: str
    positive: str
    info: str

    # --- ornament metal and the active-item indicator ---
    ornament: str
    ornament_pale: str
    ornament_deep: str
    indicator: str

    # --- shell glass (panel, popups, tooltips) ---
    glass_top: str
    glass_bot: str
    # variant name -> (alpha at top, alpha at bottom)
    glass_alpha: dict
    edge_top: Color
    edge_bot: Color
    sheen: Color
    shadow: str
    shadow_strength: float  # multiplier on every shadow's opacity
    # KWin background-contrast tuning behind translucent glass
    contrast: tuple[float, float, float]  # contrast, intensity, saturation

    # --- window title bars ---
    title_top: str
    title_bot: str
    title_text: str
    title_inactive_top: str
    title_inactive_bot: str
    title_inactive_text: str
    glow: Color  # halo around the active window

    # --- title-bar buttons ---
    glyph: str = WHITE  # resting glyph colour on the active title bar
    glyph_inactive: str = WHITE

    # Caption shown on the splash and login screens.
    world: str = ""
    # Wash laid over the wallpaper behind full-screen text: (colour, opacity).
    scrim: Color = (BLACK, 0.4)

    # Shape language of frames. "cut": clipped corners and slanted plates, after
    # the black command menu of the second game. "heading": one rounded and one
    # square corner, after the first game's menu headings.
    corner: str = "cut"

    # Strength of translucent selection fills in shell art (task buttons, list
    # highlights). Labels there keep the normal text colour, so the fill must
    # stay faint enough to read on.
    tint: float = 1.0

    # --- sourced art (file names under assets/) ---
    launcher_art: str = ""  # reference/<file>: the application-launcher emblem
    # Colour to repaint the emblem's whole silhouette with where it is shown as
    # an icon; empty keeps the art's own colours. An outline in the surface
    # colour only thins the shape at icon sizes.
    launcher_flat: str = ""
    loading_art: str = ""  # loading/<file>: animated sprite for busy cursors and splash
    # Outline colours drawn round sourced cursor art so it reads on the
    # variant's own surfaces; empty when the art already carries an outline.
    # The keyblade sprites have black outlines of their own, which vanish on
    # dark surfaces, so the dark variant rims them in light.
    pointer_rim: str = ""
    sprite_rim: str = ""

    # --- mouse cursors: body, outline, small accent details ---
    cursor_fill: str = WHITE
    cursor_line: str = BLACK
    cursor_accent: str = WHITE

    # --- terminal: background, foreground, then ANSI 0-7 normal / bright ---
    term_bg: str = BLACK
    term_fg: str = WHITE
    term_normal: tuple = ()
    term_bright: tuple = ()

    @property
    def theme_id(self) -> str:
        return f"KingdomHearts-{self.key}"

    @property
    def cursor_id(self) -> str:
        # A separate theme directory: cursor inheritance is resolved through
        # index.theme, which for the icon theme already points at Breeze icons.
        return f"{self.theme_id}-Cursors"

    @property
    def decoration_id(self) -> str:
        return f"kwin4_decoration_qml_kingdomhearts_{self.key.lower()}"

    @property
    def theme_name(self) -> str:
        return f"Kingdom Hearts — {self.title}"


# ---------------------------------------------------------------------------
# Reference colours
# ---------------------------------------------------------------------------
LOGO_BLUE = "#0088ce"  # heart of the series logo
CROWN_GOLD = "#efbb05"  # crown of the series logo
KEY_SILVER = "#c8cbcb"  # guard of the Kingdom Key D
KEY_D_GOLD = "#ebc81a"  # blade of the Kingdom Key D
KEY_BRONZE = "#a1673a"  # shaded gold of the Kingdom Key D
COAT = "#1b1f1f"  # Organization coat

# The first game's command menu: (detail, highlight) per menu colour.
MENU_BLUE = ("#263d68", "#567de6")
MENU_RED = ("#69211d", "#c95050")
MENU_PURPLE = ("#413776", "#7663da")
MENU_GREEN = ("#3a5642", "#44ab59")
MENU_ORANGE = ("#7c451f", "#d48725")

# ---------------------------------------------------------------------------
# Organization XIII — dark: black with white accents
# ---------------------------------------------------------------------------
_INK0 = "#060607"
_INK1 = "#0b0b0c"
_INK2 = "#111112"
_INK3 = "#1a1a1c"
_INK4 = "#27272a"
_WHITE_SOFT = "#e9e9ec"
_GREY = "#8b8c90"

ORG_XIII = Palette(
    key="OrgXIII",
    title="Organization XIII",
    dark=True,
    base_icons="breeze-dark",
    view=_INK1,
    view_alt=mix(_INK1, _INK3, 0.45),
    window=_INK2,
    window_alt=mix(_INK2, _INK3, 0.5),
    button=_INK3,
    button_alt=mix(_INK3, _INK4, 0.5),
    header=mix(_INK2, _INK3, 0.5),
    header_inactive=_INK2,
    tooltip=mix(_INK2, _INK3, 0.35),
    complementary=_INK0,
    complementary_alt=_INK1,
    complementary_text="#f4f4f5",
    text="#f4f4f5",
    text_dim="#a3a3a8",
    text_faint="#66666b",
    # Inverse selection: white bar, black text.
    select=_WHITE_SOFT,
    select_deep="#bdbdc2",
    select_hi=WHITE,
    select_text=_INK1,
    focus=WHITE,
    hover=KEY_SILVER,
    link=KEY_D_GOLD,
    visited=mix(KEY_BRONZE, WHITE, 0.35),
    negative=MENU_RED[1],
    neutral=MENU_ORANGE[1],
    positive=MENU_GREEN[1],
    info=MENU_BLUE[1],
    ornament=_WHITE_SOFT,
    ornament_pale=WHITE,
    ornament_deep=_GREY,
    indicator=WHITE,
    glass_top="#171718",
    glass_bot="#09090a",
    glass_alpha={"normal": (0.95, 0.97), "translucent": (0.72, 0.84), "solid": (1.0, 1.0)},
    edge_top=(WHITE, 0.6),
    edge_bot=(WHITE, 0.2),
    sheen=(WHITE, 0.05),
    shadow=BLACK,
    shadow_strength=1.0,
    contrast=(0.25, 0.4, 0.9),
    title_top="#1d1d1f",
    title_bot="#0d0d0e",
    title_text=WHITE,
    title_inactive_top="#151516",
    title_inactive_bot="#0c0c0d",
    title_inactive_text="#77777c",
    glow=(WHITE, 0.14),
    glyph=WHITE,
    glyph_inactive=_GREY,
    world="The World That Never Was",
    scrim=(BLACK, 0.45),
    corner="cut",
    tint=0.3,
    launcher_art="nobody-sigil.png",
    launcher_flat=WHITE,
    loading_art="roxas.gif",
    pointer_rim=_WHITE_SOFT,
    sprite_rim=_WHITE_SOFT,
    cursor_fill=WHITE,
    cursor_line="#101012",
    cursor_accent=KEY_D_GOLD,
    term_bg=_INK1,
    term_fg="#e6e7e9",
    term_normal=(_INK3, MENU_RED[1], MENU_GREEN[1], "#e7aa09", MENU_BLUE[1], MENU_PURPLE[1], "#38a9e6", KEY_SILVER),
    term_bright=("#66666b", "#e07070", "#63c878", KEY_D_GOLD, "#7f9cf0", "#9483e8", "#6cc3ee", WHITE),
)

# ---------------------------------------------------------------------------
# Sora — light: the first game's colours
# ---------------------------------------------------------------------------
_BLUE_DEEP = "#00669c"
_BLUE_HI = "#35a8e8"
_NAVY = "#1a2c4e"  # a darker step of the command menu's blue
_GOLD_DEEP = "#b98a00"
_GOLD_PALE = "#ffe27a"

SORA = Palette(
    key="Sora",
    title="Sora",
    dark=False,
    base_icons="breeze",
    view=WHITE,
    view_alt=mix(WHITE, LOGO_BLUE, 0.04),
    window=mix(WHITE, LOGO_BLUE, 0.055),
    window_alt=mix(WHITE, LOGO_BLUE, 0.1),
    button="#fbfdff",
    button_alt=mix(WHITE, LOGO_BLUE, 0.14),
    header=mix(WHITE, LOGO_BLUE, 0.09),
    header_inactive=mix(WHITE, LOGO_BLUE, 0.055),
    tooltip="#fbfdff",
    complementary=MENU_BLUE[0],
    complementary_alt=mix(MENU_BLUE[0], BLACK, 0.25),
    complementary_text="#f4f8ff",
    text=_NAVY,
    text_dim="#56688a",
    text_faint="#96a5bf",
    select=LOGO_BLUE,
    select_deep=_BLUE_DEEP,
    select_hi=_BLUE_HI,
    select_text=WHITE,
    focus=LOGO_BLUE,
    hover="#e0a800",
    link="#0072b0",
    visited=MENU_PURPLE[1],
    negative="#c23b3b",
    neutral=MENU_ORANGE[1],
    positive="#2f9a48",
    info=LOGO_BLUE,
    ornament=CROWN_GOLD,
    ornament_pale=_GOLD_PALE,
    ornament_deep=_GOLD_DEEP,
    indicator=CROWN_GOLD,
    glass_top=WHITE,
    glass_bot=mix(WHITE, LOGO_BLUE, 0.08),
    glass_alpha={"normal": (0.95, 0.97), "translucent": (0.76, 0.86), "solid": (1.0, 1.0)},
    edge_top=(LOGO_BLUE, 0.7),
    edge_bot=(_BLUE_DEEP, 0.7),
    sheen=(WHITE, 0.9),
    shadow="#0b3550",
    shadow_strength=0.42,
    contrast=(0.2, 1.5, 1.3),
    title_top="#1798dc",
    title_bot="#0077b8",
    title_text=WHITE,
    title_inactive_top="#f6fafd",
    title_inactive_bot=mix(WHITE, LOGO_BLUE, 0.12),
    title_inactive_text="#7d8ea8",
    glow=(LOGO_BLUE, 0.28),
    glyph=WHITE,
    glyph_inactive="#8a9ab3",
    world="Destiny Islands",
    scrim=(WHITE, 0.38),
    corner="heading",
    tint=0.42,
    launcher_art="kh-heart-crown.png",
    loading_art="sora.gif",
    pointer_rim="#12203c",
    cursor_fill=WHITE,
    cursor_line="#12203c",
    cursor_accent=CROWN_GOLD,
    term_bg="#fbfdff",
    term_fg=_NAVY,
    term_normal=(_NAVY, "#c23b3b", "#2f9a48", _GOLD_DEEP, LOGO_BLUE, MENU_PURPLE[1], "#1493a8", "#c9d5e2"),
    term_bright=("#56688a", MENU_RED[1], MENU_GREEN[1], "#e0a800", _BLUE_HI, "#9483e8", "#2ab3c9", WHITE),
)

VARIANTS = (ORG_XIII, SORA)
