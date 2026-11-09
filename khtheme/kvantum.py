"""Kvantum widget style: application controls in each variant's shape language.

Kvantum draws Qt widgets from an SVG of named elements plus a .kvconfig of
sizes and colours. One Kvantum theme folder holds both variants: Sora as the
theme itself and Organization XIII as its "Dark" twin. Plasma's two style keys
pick between them (`kvantum` loads KingdomHearts, `kvantum-dark` loads
KingdomHeartsDark from the same folder), so the global themes switch widget
look together with everything else.

Shapes follow `Palette.corner` as the window frames and Plasma Style do:

* cut — Organization XIII: clipped corners, hairline white borders, and the
  second game's inverse command bar (white fill, black text) for selections
  and pressed controls.
* heading — Sora: one rounded and one square corner, logo-blue selections with
  the crown-gold bar of the first game's menus down their left side.

Every element the config names is drawn here. Kvantum fills anything missing
from its built-in default theme, which would bring grey stock art into the
middle of the theme, so the build checks the SVG against the ids the config
makes Kvantum ask for.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

from . import log
from .palette import BLACK, LOGO_BLUE, WHITE, Palette, mix
from .svg import PIN, FrameStyle, PathD, Xf, document, fmt, frame_pieces, paint, shadow_pieces, write_text

THEME = "KingdomHearts"
STATES4 = ("normal", "focused", "pressed", "disabled")
SIDES = ("top", "bottom", "left", "right", "topleft", "topright", "bottomleft", "bottomright")
GAP = 6

# --- sizes shared by the SVG and the config -----------------------------------------
MENU_SHADOW = 8
TOOLTIP_SHADOW = 6
SEPARATOR_H = 7  # menu separator element height (menu_separator_height)
SCROLL_W = 10
SLIDER_W = 4
HANDLE = 16
CHECK = 16
ARROW = 10  # canvas size of arrow-like indicators
SPLITTER_W = 7


@dataclass(frozen=True)
class Metrics:
    """Frame widths (= SVG slice sizes, so slices draw 1:1) and corner sizes."""

    button: int  # buttons, combo boxes, line edits, spin boxes, tabs
    button_r: float
    small: int  # frames round views and tab widgets
    small_r: float
    item: int  # view items, menu items
    item_r: float
    popup: int  # menus
    popup_r: float
    tip: int  # tooltips
    tip_r: float
    group: int  # group boxes
    group_r: float


CUT = Metrics(button=5, button_r=4, small=3, small_r=2, item=3, item_r=3, popup=7, popup_r=5, tip=5, tip_r=4,
              group=9, group_r=6)
HEADING = Metrics(button=6, button_r=6, small=4, small_r=3, item=4, item_r=4, popup=8, popup_r=6, tip=6, tip_r=5,
                  group=10, group_r=7)


def metrics(pal: Palette) -> Metrics:
    return CUT if pal.corner == "cut" else HEADING


def theme_name(pal: Palette) -> str:
    return THEME + ("Dark" if pal.dark else "")


def style_key(pal: Palette) -> str:
    """Qt style key that makes Kvantum load this variant."""
    return "kvantum-dark" if pal.dark else "kvantum"


def _shape(pal: Palette, r: float, square: set | frozenset = frozenset()) -> dict:
    if pal.corner == "cut":
        return {"r": r, "cut": True, "square": set(square)}
    return {"r": r, "square": {"topright", "bottomleft"} | set(square)}


def _a(color: str, alpha: float = 1.0) -> tuple[str, float]:
    return (color, alpha)


# --- canvas ------------------------------------------------------------------------
class Canvas:
    """Places element groups on a shelf layout and collects the SVG text."""

    ROW = 1100

    def __init__(self) -> None:
        self.defs: list[str] = []
        self.body: list[str] = []
        self.x = 0.0
        self.y = 0.0
        self.row_h = 0.0
        self.width = 0.0
        self.uid = 0

    def slot(self, w: float, h: float) -> tuple[float, float]:
        if self.x + w > self.ROW and self.x > 0:
            self.x = 0.0
            self.y += self.row_h + GAP
            self.row_h = 0.0
        pos = (self.x, self.y)
        self.x += w + GAP
        self.row_h = max(self.row_h, h)
        self.width = max(self.width, self.x)
        return pos

    def next_uid(self) -> str:
        self.uid += 1
        return f"k{self.uid}"

    def frame(self, prefix: str, style: FrameStyle) -> None:
        """Nine slices named for Kvantum: `<prefix>` is the interior and
        `<prefix>-top` ... `<prefix>-bottomright` the frame."""
        x, y = self.slot(style.size, style.size)
        defs, body = frame_pieces(prefix, x, y, style, self.next_uid())
        self.defs += defs
        self.body += [g.replace(f'id="{prefix}-center"', f'id="{prefix}"', 1) for g in body]

    def shadowed(self, element: str, style: FrameStyle, depth: int, color: str, alpha: float) -> None:
        """`<element>-shadow-*`: the shadow and the frame edge in one set of
        slices, as Kvantum draws composited menus and tooltips, plus the hint
        rectangles that say how much of each slice is pure shadow."""
        c = style.c
        k = depth + c
        x, y = self.slot(2 * k + style.m + 24, 2 * k + style.m)
        uid = self.next_uid()
        sdefs, sbody, size = shadow_pieces(f"{element}-shadow", x, y, depth, c, color, alpha, uid, m=style.m)
        if size != k:
            raise ValueError(f"{element}: shadow slice is {size}px, expected {k}px")
        fdefs, fbody = frame_pieces("edge", x + depth, y + depth, style, uid + "f")
        inner = {}
        for g in fbody:
            name = re.match(r'<g id="edge-([a-z]+)">', g).group(1)
            inner[name] = g[g.index(">") + 1 : -len("</g>")]
        merged = []
        for g in sbody:
            name = re.match(rf'<g id="{re.escape(element)}-shadow-([a-z]+)">', g).group(1)
            if name == "center":
                continue
            merged.append(g[: -len("</g>")] + inner[name] + "</g>")
        self.defs += sdefs + fdefs
        self.body += merged
        hx = x + 2 * k + style.m + 6
        hint = 'fill="#ff00ff" opacity="0.002"'
        self.body += [
            f'<rect id="{element}-shadow-hint-top" x="{fmt(hx)}" y="{fmt(y)}" width="3" height="{depth}" {hint}/>',
            f'<rect id="{element}-shadow-hint-bottom" x="{fmt(hx + 5)}" y="{fmt(y)}" width="3" height="{depth}" {hint}/>',
            f'<rect id="{element}-shadow-hint-left" x="{fmt(hx)}" y="{fmt(y + 20)}" width="{depth}" height="3" {hint}/>',
            f'<rect id="{element}-shadow-hint-right" x="{fmt(hx)}" y="{fmt(y + 26)}" width="{depth}" height="3" {hint}/>',
        ]

    def glyph(self, gid: str, w: float, h: float, draw) -> None:
        """A plain element: `draw(x, y)` returns its shapes in absolute
        coordinates; an invisible rect pins the bounding box to w x h."""
        x, y = self.slot(w, h)
        parts = [f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" {PIN}/>'] + draw(x, y)
        self.body.append(f'<g id="{gid}">{"".join(parts)}</g>')

    def svg(self) -> str:
        return document(self.width, self.y + self.row_h + GAP, self.defs, self.body)


# --- glyph primitives ----------------------------------------------------------------
def _poly(x: float, y: float, points, color: tuple[str, float], width: float, close: bool = False) -> str:
    d = " ".join(("M" if n == 0 else "L") + f"{fmt(x + px)},{fmt(y + py)}" for n, (px, py) in enumerate(points))
    if close:
        d += " Z"
    return (f'<path d="{d}" fill="none" {paint(color, "stroke")} stroke-width="{fmt(width)}" '
            'stroke-linecap="round" stroke-linejoin="round"/>')


def _fill_poly(x: float, y: float, points, color: tuple[str, float]) -> str:
    d = " ".join(("M" if n == 0 else "L") + f"{fmt(x + px)},{fmt(y + py)}" for n, (px, py) in enumerate(points)) + " Z"
    return f'<path d="{d}" {paint(color)}/>'


def _circle(cx: float, cy: float, r: float, fill: tuple[str, float] | None = None,
            stroke: tuple[str, float] | None = None, width: float = 1.0) -> str:
    attrs = paint(fill) if fill else 'fill="none"'
    if stroke:
        attrs += f' {paint(stroke, "stroke")} stroke-width="{fmt(width)}"'
    return f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" {attrs}/>'


def _rect(x: float, y: float, w: float, h: float, color: tuple[str, float]) -> str:
    return f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" {paint(color)}/>'


def _box_d(pal: Palette, x: float, y: float, w: float, h: float, r: float) -> str:
    """Outline of a small box in the variant's corner language."""
    if pal.corner == "cut":
        return (PathD().M(x + r, y).L(x + w - r, y).L(x + w, y + r).L(x + w, y + h - r).L(x + w - r, y + h)
                .L(x + r, y + h).L(x, y + h - r).L(x, y + r).Z().d())
    return (PathD().M(x + r, y).L(x + w, y).L(x + w, y + h - r).A(r, x + w - r, y + h).L(x, y + h).L(x, y + r)
            .A(r, x + r, y).Z().d())


def _box(pal: Palette, x: float, y: float, w: float, h: float, r: float, fill: tuple[str, float] | None,
         stroke: tuple[str, float] | None, width: float = 1.5) -> str:
    attrs = paint(fill) if fill else 'fill="none"'
    if stroke:
        attrs += f' {paint(stroke, "stroke")} stroke-width="{fmt(width)}" stroke-linejoin="round"'
    return f'<path d="{_box_d(pal, x, y, w, h, r)}" {attrs}/>'


# Chevrons on a 10 x 10 canvas.
CHEVRON = {
    "down": [(2, 3.5), (5, 6.5), (8, 3.5)],
    "up": [(2, 6.5), (5, 3.5), (8, 6.5)],
    "left": [(6.5, 2), (3.5, 5), (6.5, 8)],
    "right": [(3.5, 2), (6.5, 5), (3.5, 8)],
}


def _sign(direction: str, x: float, y: float, color: tuple[str, float], width: float = 1.6) -> list[str]:
    if direction in CHEVRON:
        return [_poly(x, y, CHEVRON[direction], color, width)]
    parts = [_poly(x, y, [(2, 5), (8, 5)], color, width)]
    if direction == "plus":
        parts.append(_poly(x, y, [(5, 2), (5, 8)], color, width))
    return parts


# --- colours -------------------------------------------------------------------------
@dataclass(frozen=True)
class Ink:
    """State colours of controls, worked out once per variant."""

    fill: tuple  # (top, bottom) of resting controls
    border: tuple
    hover_fill: tuple
    hover_border: tuple
    press_fill: tuple
    press_border: tuple
    press_text: str
    toggle_fill: tuple
    toggle_border: tuple
    field: str  # line-edit ground
    field_border: tuple
    field_focus: tuple
    hairline: tuple  # frames round views
    soft: tuple  # translucent wash for grooves, inactive tabs
    select: tuple  # selection bar
    select_text: str
    select_mark: tuple | None  # bar down the selection's left side
    select_muted: tuple  # selection in an inactive window, under normal text
    select_muted_line: tuple
    hover_wash: tuple  # translucent hover for view and menu rows
    hover_line: tuple
    accent: str  # glyph colour for hover
    grey: str  # mid tone that reads on both the ground and the selection


def ink(pal: Palette) -> Ink:
    if pal.dark:
        return Ink(
            fill=(_a(mix(pal.button, WHITE, 0.03)), _a(mix(pal.button, BLACK, 0.3))),
            border=(_a(WHITE, 0.32), _a(WHITE, 0.16)),
            hover_fill=(_a(mix(pal.button, WHITE, 0.09)), _a(mix(pal.button, WHITE, 0.02))),
            hover_border=(_a(WHITE, 0.92), _a(WHITE, 0.55)),
            press_fill=(_a(pal.select_hi), _a(pal.select)),
            press_border=(_a(WHITE), _a(pal.select_deep)),
            press_text=pal.select_text,
            toggle_fill=(_a(WHITE, 0.16), _a(WHITE, 0.1)),
            toggle_border=(_a(WHITE, 0.8), _a(WHITE, 0.5)),
            field=pal.view,
            field_border=(_a(WHITE, 0.24), _a(WHITE, 0.13)),
            field_focus=(_a(WHITE, 0.95), _a(WHITE, 0.7)),
            hairline=(_a(WHITE, 0.17), _a(WHITE, 0.1)),
            soft=(_a(WHITE, 0.05), _a(WHITE, 0.03)),
            select=(_a(pal.select_hi), _a(mix(pal.select, pal.select_deep, 0.35))),
            select_text=pal.select_text,
            select_mark=None,
            select_muted=(_a(WHITE, 0.17), _a(WHITE, 0.11)),
            select_muted_line=(_a(WHITE, 0.36), _a(WHITE, 0.2)),
            hover_wash=(_a(WHITE, 0.08), _a(WHITE, 0.05)),
            hover_line=(_a(WHITE, 0.3), _a(WHITE, 0.18)),
            accent=WHITE,
            grey="#8b8c90",
        )
    return Ink(
        fill=(_a(WHITE), _a(mix(WHITE, LOGO_BLUE, 0.07))),
        border=(_a(pal.select, 0.5), _a(pal.select_deep, 0.6)),
        hover_fill=(_a(WHITE), _a(mix(WHITE, pal.hover, 0.16))),
        hover_border=(_a(pal.hover), _a(pal.ornament_deep, 0.9)),
        press_fill=(_a(mix(pal.select, pal.select_hi, 0.4)), _a(pal.select_deep)),
        press_border=(_a(pal.select_deep), _a(pal.select_deep)),
        press_text=pal.select_text,
        toggle_fill=(_a(mix(WHITE, LOGO_BLUE, 0.16)), _a(mix(WHITE, LOGO_BLUE, 0.25))),
        toggle_border=(_a(pal.select, 0.9), _a(pal.select_deep, 0.9)),
        field=pal.view,
        field_border=(_a(pal.select, 0.42), _a(pal.select_deep, 0.45)),
        field_focus=(_a(pal.select), _a(pal.select_deep)),
        hairline=(_a(pal.select, 0.32), _a(pal.select_deep, 0.3)),
        soft=(_a(pal.select, 0.07), _a(pal.select, 0.1)),
        select=(_a(mix(pal.select, pal.select_hi, 0.3)), _a(pal.select)),
        select_text=pal.select_text,
        select_mark=_a(pal.ornament),
        select_muted=(_a(pal.select, 0.2), _a(pal.select, 0.14)),
        select_muted_line=(_a(pal.select, 0.5), _a(pal.select_deep, 0.4)),
        hover_wash=(_a(pal.hover, 0.16), _a(pal.hover, 0.1)),
        hover_line=(_a(pal.hover, 0.65), _a(pal.ornament_deep, 0.5)),
        accent=pal.select,
        grey="#8a9ab3",
    )


# --- elements ----------------------------------------------------------------------------
def _frames(cv: Canvas, pal: Palette, k: Ink, mt: Metrics) -> None:
    btn = dict(c=mt.button, m=16, **_shape(pal, mt.button_r))
    sheen = _a(WHITE, 0.035) if pal.dark else _a(WHITE, 0.9)
    buttons = {
        "normal": FrameStyle(*k.fill, border_top=k.border[0], border_bot=k.border[1], sheen=sheen, **btn),
        "focused": FrameStyle(*k.hover_fill, border_top=k.hover_border[0], border_bot=k.hover_border[1], sheen=sheen, **btn),
        "pressed": FrameStyle(*k.press_fill, border_top=k.press_border[0], border_bot=k.press_border[1], **btn),
        "toggled": FrameStyle(*k.toggle_fill, border_top=k.toggle_border[0], border_bot=k.toggle_border[1], **btn),
    }
    for state, style in buttons.items():
        cv.frame(f"button-{state}", style)

    cv.frame("lineedit-normal", FrameStyle(_a(k.field), _a(k.field), border_top=k.field_border[0],
                                           border_bot=k.field_border[1], **btn))
    cv.frame("lineedit-focused", FrameStyle(_a(k.field), _a(k.field), border_top=k.field_focus[0],
                                            border_bot=k.field_focus[1], **btn))

    small = dict(c=mt.small, m=16, **_shape(pal, mt.small_r))
    cv.frame("common-normal", FrameStyle(_a(pal.view), _a(pal.view), border_top=k.hairline[0],
                                         border_bot=k.hairline[1], **small))
    cv.frame("tabframe-normal", FrameStyle(_a(pal.window, 0), _a(pal.window, 0), border_top=k.hairline[0],
                                           border_bot=k.hairline[1], **small))
    # Keyboard focus outline; Kvantum draws it at most 2px thick and stateless.
    cv.frame("focus", FrameStyle(_a(WHITE, 0), _a(WHITE, 0), c=2, m=16, r=0,
                                 border_top=_a(pal.focus, 0.6), border_bot=_a(pal.focus, 0.6)))

    group_wash = _a(WHITE, 0.025) if pal.dark else _a(pal.select, 0.035)
    cv.frame("group-normal", FrameStyle(group_wash, group_wash, c=mt.group, m=16,
                                        border_top=k.hairline[0], border_bot=k.hairline[1],
                                        accent=_a(pal.ornament, 0.9), **_shape(pal, mt.group_r)))

    # Tabs have no bottom frame, so their sides run straight into the tab
    # widget's border; the active one carries the indicator bar on top.
    tab = dict(c=mt.button, m=16, **_shape(pal, mt.button_r, {"bottomleft", "bottomright"}))
    edge = k.hairline[0]
    hover_tab = (_a(WHITE, 0.09), _a(WHITE, 0.05)) if pal.dark else (_a(pal.hover, 0.16), _a(pal.hover, 0.1))
    cv.frame("tab-normal", FrameStyle(*k.soft, border_top=edge, border_bot=edge, **tab))
    cv.frame("tab-focused", FrameStyle(*hover_tab, border_top=k.hover_line[0], border_bot=k.hover_line[0], **tab))
    active = FrameStyle(_a(pal.window), _a(pal.window), border_top=edge, border_bot=edge,
                        line=("top", _a(pal.indicator), 2), **tab)
    cv.frame("tab-toggled", active)
    cv.frame("tab-pressed", active)

    item = dict(c=mt.item, m=16, **_shape(pal, mt.item_r))
    mark = ("left", k.select_mark, 2) if k.select_mark else None
    selected = FrameStyle(*k.select, line=mark, **item)
    deeper = replace(selected, fill_top=_a(mix(k.select[0][0], k.select[1][0], 0.5)))
    hover = FrameStyle(*k.hover_wash, border_top=k.hover_line[0], border_bot=k.hover_line[1], **item)
    cv.frame("menuitem-focused", hover)
    cv.frame("menuitem-toggled", selected)
    cv.frame("menuitem-pressed", deeper)
    # Item views: Kvantum draws "pressed" for the selection in the view with
    # keyboard focus and "toggled" for a selection elsewhere (Dolphin's Places
    # list while files are browsed), adding "-inactive" in an inactive window.
    # Only the focused selection gets the full bar. Elsewhere it is muted under
    # the normal text colour, which some views use there whatever the style
    # says (Dolphin's Places list among them); the full bar would hide it.
    muted = FrameStyle(*k.select_muted, border_top=k.select_muted_line[0], border_bot=k.select_muted_line[1], **item)
    cv.frame("itemview-focused", hover)
    cv.frame("itemview-pressed", selected)
    cv.frame("itemview-toggled", muted)
    for state in ("toggled", "pressed"):
        cv.frame(f"itemview-{state}-inactive", muted)

    # Menus and tooltips: the shell's glass, with the corner ornaments of the
    # panel popups, and the composited shadow version of the same frame.
    a_top, a_bot = pal.glass_alpha["normal"]
    menu = FrameStyle(_a(pal.glass_top, max(a_top, 0.97)), _a(pal.glass_bot, max(a_bot, 0.98)), c=mt.popup, m=16,
                      border_top=pal.edge_top, border_bot=pal.edge_bot, sheen=pal.sheen,
                      accent=_a(pal.ornament, 0.95), **_shape(pal, mt.popup_r))
    cv.frame("menu-normal", menu)
    cv.shadowed("menu", menu, MENU_SHADOW, pal.shadow, 0.5 * pal.shadow_strength)
    tip = FrameStyle(_a(pal.tooltip, 0.98), _a(mix(pal.tooltip, pal.window, 0.6), 0.98), c=mt.tip, m=16,
                     border_top=pal.edge_top, border_bot=pal.edge_bot, **_shape(pal, mt.tip_r))
    cv.frame("tooltip-normal", tip)
    cv.shadowed("tooltip", tip, TOOLTIP_SHADOW, pal.shadow, 0.45 * pal.shadow_strength)

    # Header sections: a band with the ornament line under it.
    head_line = _a(WHITE, 0.3) if pal.dark else _a(pal.ornament, 0.85)
    head = dict(c=2, m=16, r=0)
    for state, lift in (("normal", 0.0), ("focused", 0.06), ("pressed", 0.11)):
        top = mix(pal.header, WHITE if pal.dark else pal.select, lift)
        cv.frame(f"header-{state}", FrameStyle(_a(top), _a(mix(top, pal.window, 0.4)),
                                               line=("bottom", head_line, 1), **head))

    # Gauges: progress bar (horizontal) and slider groove (vertical).
    gauge = dict(c=2, m=16, **_shape(pal, 2))
    cv.frame("progress-normal", FrameStyle(*k.soft, border_top=k.hairline[0], border_bot=k.hairline[1], **gauge))
    bar = (_a(pal.select_hi), _a(pal.select_deep)) if not pal.dark else (_a(WHITE), _a(pal.select_deep))
    for state in ("normal", "focused"):
        cv.frame(f"progress-pattern-{state}", FrameStyle(*bar, **gauge))
    # Asked for by name when the bar is disabled; there is no fallback to normal.
    cv.frame("progress-pattern-disabled", FrameStyle(_a(pal.text_faint, 0.6), _a(pal.text_faint, 0.45), **gauge))
    cv.frame("slider-normal", FrameStyle(*k.soft, border_top=k.hairline[1], border_bot=k.hairline[1], **gauge))
    cv.frame("slider-toggled", FrameStyle(*bar, **gauge))

    # Scrollbars: a slim bar inset in a faint groove.
    thumb = dict(c=4, m=16, inset=2, **_shape(pal, 2))
    tones = (0.3, 0.58, 0.88) if pal.dark else (0.38, 0.62, 0.9)
    tone = WHITE if pal.dark else pal.select
    for state, alpha in zip(("normal", "focused", "pressed"), tones):
        cv.frame(f"scrollbarslider-{state}", FrameStyle(_a(tone, alpha), _a(tone, alpha), **thumb))
    cv.frame("scrollbargroove-normal", FrameStyle(_a(tone, 0.035), _a(tone, 0.035), c=2, m=16, r=0))

    # Title bar of windows inside windows (MDI).
    for state, (top, bot) in (("focused", (pal.title_top, pal.title_bot)),
                              ("normal", (pal.title_inactive_top, pal.title_inactive_bot))):
        cv.frame(f"titlebar-{state}", FrameStyle(_a(top), _a(bot), c=2, m=16, r=0))


def _checks(cv: Canvas, pal: Palette, k: Ink) -> None:
    s = CHECK
    tick = [(4, 8.2), (6.8, 11), (12, 5.4)]
    dash = [(4.5, 8), (11.5, 8)]
    cut = pal.corner == "cut"
    r = 3 if cut else 4
    looks = {}
    if pal.dark:
        looks["box"] = {
            "normal": (_a(pal.view), _a(WHITE, 0.55)),
            "focused": (_a(mix(pal.view, WHITE, 0.08)), _a(WHITE)),
            "pressed": (_a(WHITE, 0.25), _a(WHITE)),
            "disabled": (_a(pal.view), _a(WHITE, 0.2)),
        }
        looks["on"] = {
            "normal": (_a(pal.select), _a(pal.select), pal.select_text),
            "focused": (_a(WHITE), _a(WHITE), pal.select_text),
            "pressed": (_a(pal.select_deep), _a(WHITE), pal.select_text),
            "disabled": (_a(WHITE, 0.25), _a(WHITE, 0.25), pal.view),
        }
    else:
        looks["box"] = {
            "normal": (_a(WHITE), _a(pal.select, 0.62)),
            "focused": (_a(mix(WHITE, pal.hover, 0.1)), _a(pal.hover)),
            "pressed": (_a(mix(WHITE, LOGO_BLUE, 0.2)), _a(pal.select)),
            "disabled": (_a(WHITE), _a(pal.select, 0.25)),
        }
        looks["on"] = {
            "normal": (_a(pal.select), _a(pal.select_deep), WHITE),
            "focused": (_a(pal.select), _a(pal.hover), WHITE),
            "pressed": (_a(pal.select_deep), _a(pal.select_deep), WHITE),
            "disabled": (_a(pal.select, 0.3), _a(pal.select, 0.3), WHITE),
        }

    def checkbox(gid: str, fill, stroke, mark=None, mark_color=None) -> None:
        def draw(x, y):
            parts = [_box(pal, x + 1.5, y + 1.5, s - 3, s - 3, r, fill, stroke)]
            if mark:
                parts.append(_poly(x, y, mark, _a(mark_color), 2))
            return parts
        cv.glyph(gid, s, s, draw)

    def radio(gid: str, fill, stroke, dot=None) -> None:
        def draw(x, y):
            parts = [_circle(x + s / 2, y + s / 2, s / 2 - 1.5, fill, stroke, 1.5)]
            if dot:
                parts.append(_circle(x + s / 2, y + s / 2, 3, _a(dot)))
            return parts
        cv.glyph(gid, s, s, draw)

    for prefix, box, on in (("", looks["box"], looks["on"]), ("menu-", None, None), ("item-", None, None)):
        if prefix == "menu-":
            # Menu rows turn into the selection bar under the pointer, where the
            # usual marks would vanish; "focused" is what Kvantum draws there.
            box = dict(looks["box"])
            on = dict(looks["on"])
            box["normal"] = (None, _a(k.grey))
            box["focused"] = (None, _a(k.select_text))
            on["normal"] = (_a(k.grey), _a(k.grey), pal.view if pal.dark else WHITE)
            on["focused"] = (_a(k.select_text), _a(k.select_text), k.select[1][0])
        elif prefix == "item-":
            if not pal.dark:
                continue  # Sora's white boxes already read on its blue selection
            box = dict(looks["box"])
            on = dict(looks["on"])
            # Rows may be selected (white) or not (black); grey reads on both.
            box["normal"] = (None, _a(k.grey))
            on["normal"] = (_a(k.grey), _a(k.grey), pal.select_text)
        for state in STATES4:
            fill, stroke = box[state]
            ofill, ostroke, mark = on[state]
            checkbox(f"{prefix}checkbox-{state}", fill, stroke)
            checkbox(f"{prefix}checkbox-checked-{state}", ofill, ostroke, tick, mark)
            checkbox(f"{prefix}checkbox-tristate-{state}", ofill, ostroke, dash, mark)
            if prefix != "item-":  # view items hold check boxes only
                radio(f"{prefix}radio-{state}", fill, stroke)
                radio(f"{prefix}radio-checked-{state}", ofill, ostroke, mark)


def _indicators(cv: Canvas, pal: Palette, k: Ink) -> None:
    dim = _a(pal.text, 0.75)
    faint = _a(pal.text_faint)
    states = {
        # On buttons: pressed buttons take the selection fill, toggled ones keep
        # the resting text colour.
        "arrow": {"normal": dim, "focused": _a(k.accent), "pressed": _a(k.press_text), "toggled": _a(pal.text),
                  "disabled": faint},
        # Inline spin buttons sit on the line edit, never on a filled button.
        "spin": {"normal": dim, "focused": _a(k.accent), "pressed": _a(pal.select if not pal.dark else WHITE),
                 "disabled": faint},
        "tree": {"normal": _a(pal.text_dim), "focused": _a(k.accent), "pressed": _a(k.accent), "disabled": faint},
    }
    for base, colors in states.items():
        directions = ("plus", "minus") if base == "tree" else ("up", "down", "left", "right", "plus", "minus")
        for direction in directions:
            # The tree's plus (collapsed) points right, its minus (expanded) down.
            shape = {"plus": "right", "minus": "down"}[direction] if base == "tree" else direction
            for state, color in colors.items():
                cv.glyph(f"{base}-{direction}-{state}", ARROW, ARROW,
                         lambda x, y, sh=shape, c=color: _sign(sh, x, y, c))
    # Submenu arrows: the highlighted row is the selection bar.
    for direction in ("left", "right"):
        for state, color in (("normal", dim), ("focused", _a(k.select_text)), ("pressed", _a(k.select_text)),
                             ("toggled", _a(k.select_text)), ("disabled", faint)):
            cv.glyph(f"menuitem-{direction}-{state}", ARROW, ARROW,
                     lambda x, y, d=direction, c=color: _sign(d, x, y, c))

    # Default button: a corner notch in the ornament colour.
    cv.glyph("button-default-indicator", 9, 9,
             lambda x, y: [_fill_poly(x, y, [(9, 2), (9, 9), (2, 9)], _a(pal.ornament, 0.95))])

    # Tab close button and tear mark.
    for state, color in (("normal", _a(pal.text_dim)), ("focused", _a(pal.text)), ("pressed", _a(pal.negative)),
                         ("disabled", faint)):
        cv.glyph(f"tab-close-{state}", ARROW, ARROW,
                 lambda x, y, c=color: [_poly(x, y, [(2.5, 2.5), (7.5, 7.5)], c, 1.5),
                                        _poly(x, y, [(7.5, 2.5), (2.5, 7.5)], c, 1.5)])
    cv.glyph("tab-tear", 2, 20, lambda x, y: [_rect(x, y, 2, 20, k.hairline[0])])

    # Separators.
    line = _a(WHITE, 0.18) if pal.dark else _a(pal.ornament, 0.55)
    cv.glyph("menuitem-separator", 40, SEPARATOR_H, lambda x, y: [_rect(x, y + SEPARATOR_H // 2, 40, 1, line)])
    for state in ("normal", "focused"):
        cv.glyph(f"menuitem-tearoff-{state}", 20, 8,
                 lambda x, y, s=state: [_rect(x + n, y + 3.5, 3, 1, _a(pal.text_dim if s == "normal" else pal.text))
                                        for n in range(0, 20, 5)])
    cv.glyph("header-separator", 2, 20, lambda x, y: [_rect(x + 0.5, y + 4, 1, 12, k.hairline[0])])
    cv.glyph("toolbar-separator", 5, 20, lambda x, y: [_rect(x + 2, y + 3, 1, 14, k.hairline[0])])
    cv.glyph("toolbar-handle", 5, 20,
             lambda x, y: [_circle(x + 2.5, y + 4 + 4 * n, 1, k.hairline[0]) for n in range(4)])

    # Grips.
    for state, color in (("normal", _a(pal.text_faint)), ("focused", _a(k.accent))):
        cv.glyph(f"sizegrip-{state}", 13, 13,
                 lambda x, y, c=color: [_circle(x + cx, y + cy, 1.1, c)
                                        for cx, cy in ((11, 5), (8, 8), (11, 8), (5, 11), (8, 11), (11, 11))])
    for state, color in (("normal", _a(pal.text_faint)), ("focused", _a(k.accent)), ("pressed", _a(pal.select))):
        cv.glyph(f"splitter-grip-{state}", SPLITTER_W, 16,
                 lambda x, y, c=color: [_circle(x + SPLITTER_W / 2, y + 4 + 4 * n, 1.1, c) for n in range(3)])

    # Slider ticks and handle.
    cv.glyph("slider-tick-normal", 5, 1, lambda x, y: [_rect(x, y, 5, 1, _a(pal.text_faint))])
    h = HANDLE
    if pal.dark:
        handles = {
            "normal": (_a(pal.select), _a(WHITE, 0.0)),
            "focused": (_a(WHITE), _a(WHITE, 0.0)),
            "pressed": (_a(pal.select_deep), _a(WHITE, 0.0)),
            "disabled": (_a(pal.text_faint), _a(WHITE, 0.0)),
        }
        for state, (fill, _) in handles.items():
            cv.glyph(f"slidercursor-{state}", h, h,
                     lambda x, y, f=fill: [_box(pal, x + 2, y + 2, h - 4, h - 4, 4, f, None),
                                           _box(pal, x + 6, y + 6, h - 12, h - 12, 1.5, _a(pal.view), None)])
    else:
        rings = {"normal": _a(pal.select), "focused": _a(pal.hover), "pressed": _a(pal.select_deep),
                 "disabled": _a(pal.text_faint)}
        for state, ring in rings.items():
            fill = _a(pal.select) if state == "pressed" else _a(WHITE)
            cv.glyph(f"slidercursor-{state}", h, h,
                     lambda x, y, r_=ring, f=fill: [_circle(x + h / 2, y + h / 2, h / 2 - 2, f, r_, 2)])

    # Dial.
    cv.glyph("dial", 64, 64, lambda x, y: [_circle(x + 32, y + 32, 30, k.soft[0], k.hairline[0], 1.5)])
    cv.glyph("dial-notches", 64, 64, lambda x, y: [
        _poly(x, y, [(32 + 30 * math.sin(t), 32 - 30 * math.cos(t)), (32 + 26 * math.sin(t), 32 - 26 * math.cos(t))],
              _a(pal.text_faint), 1) for t in (n * math.pi / 6 for n in range(12))])
    cv.glyph("dial-handle", 10, 10, lambda x, y: [_circle(x + 5, y + 5, 4, _a(pal.indicator))])

    # Buttons of windows inside windows (MDI).
    glyphs = {
        "close": lambda x, y, c: [_poly(x, y, [(3, 3), (9, 9)], c, 1.5), _poly(x, y, [(9, 3), (3, 9)], c, 1.5)],
        "maximize": lambda x, y, c: [_box(pal, x + 2.5, y + 2.5, 7, 7, 1.5, None, c, 1.3)],
        "restore": lambda x, y, c: [_box(pal, x + 2.5, y + 4.5, 5, 5, 1, None, c, 1.3),
                                    _poly(x, y, [(4.5, 2.5), (9.5, 2.5), (9.5, 7.5)], c, 1.3)],
        "minimize": lambda x, y, c: [_poly(x, y, [(3, 8.5), (9, 8.5)], c, 1.5)],
        "shade": lambda x, y, c: [_poly(x, y, [(3, 7.5), (6, 4.5), (9, 7.5)], c, 1.5)],
    }
    for name, draw in glyphs.items():
        for state, color in (("normal", _a(pal.title_text, 0.85)), ("focused", _a(pal.title_text)),
                             ("pressed", _a(pal.ornament)), ("disabled", _a(pal.title_inactive_text))):
            cv.glyph(f"mdi-{name}-{state}", 12, 12, lambda x, y, d=draw, c=color: d(x, y, c))
    cv.glyph("mdi-menu-normal", 12, 12,
             lambda x, y: [_fill_poly(x, y, [(6, 2), (10, 6), (6, 10), (2, 6)], _a(pal.ornament))])


def build_svg(pal: Palette) -> str:
    cv = Canvas()
    k = ink(pal)
    mt = metrics(pal)
    _frames(cv, pal, k, mt)
    _checks(cv, pal, k)
    _indicators(cv, pal, k)
    return cv.svg()


# --- config --------------------------------------------------------------------------------
def _frame_keys(top: int, bottom: int | None = None, left: int | None = None, right: int | None = None) -> dict:
    bottom = top if bottom is None else bottom
    left = top if left is None else left
    right = left if right is None else right
    return {"frame.top": top, "frame.bottom": bottom, "frame.left": left, "frame.right": right}


def _margins(top: int, bottom: int, left: int, right: int) -> dict:
    return {"text.margin.top": top, "text.margin.bottom": bottom, "text.margin.left": left,
            "text.margin.right": right}


def _text(normal: str, focus: str | None = None, press: str | None = None, toggle: str | None = None) -> dict:
    return {"text.normal.color": normal, "text.focus.color": focus or normal,
            "text.press.color": press or normal, "text.toggle.color": toggle or normal}


def config_sections(pal: Palette) -> dict[str, dict[str, object]]:
    k = ink(pal)
    mt = metrics(pal)
    b = mt.button
    text = pal.text
    sections: dict[str, dict[str, object]] = {}
    sections["%General"] = {
        "author": "Kingdom Hearts Plasma theme",
        "comment": f"{pal.title}: Kingdom Hearts {'Organization XIII (dark)' if pal.dark else 'Sora (light)'} controls",
        "x11drag": "menubar_and_primary_toolbar",
        "alt_mnemonic": "true",
        "left_tabs": "true",
        "attach_active_tab": "true",
        "joined_inactive_tabs": "false",
        "bold_active_tab": "false",
        "group_toolbar_buttons": "false",
        "spread_progressbar": "true",
        "progressbar_thickness": 8,
        "composite": "true",
        "translucent_windows": "false",
        "blurring": "false",
        "popup_blurring": "false",
        "menu_shadow_depth": MENU_SHADOW,
        "tooltip_shadow_depth": TOOLTIP_SHADOW,
        "spread_menuitems": "false",
        "menu_separator_height": SEPARATOR_H,
        "scrollable_menu": "true",
        "combo_menu": "true",
        "hide_combo_checkboxes": "true",
        "combo_as_lineedit": "true",
        "combo_focus_rect": "false",
        "inline_spin_indicators": "true",
        "vertical_spin_indicators": "false",
        "spin_button_width": 16,
        "splitter_width": SPLITTER_W,
        "scroll_width": SCROLL_W,
        "scroll_min_extent": 36,
        "scroll_arrows": "false",
        "transient_scrollbar": "false",
        "tree_branch_line": "false",
        "slider_width": SLIDER_W,
        "slider_handle_width": HANDLE,
        "slider_handle_length": HANDLE,
        "check_size": CHECK,
        "groupbox_top_label": "true",
        "animate_states": "true",
        "no_inactiveness": "false",
        "layout_spacing": 6,
        "layout_margin": 9,
        "toolbar_separator_thickness": 5,
        "menubar_mouse_tracking": "true",
        "dark_titlebar": "true" if pal.dark else "false",
        "respect_DE": "true",
    }
    sections["GeneralColors"] = {
        "window.color": pal.window,
        "base.color": pal.view,
        "alt.base.color": pal.view_alt,
        "button.color": pal.button,
        "light.color": mix(pal.button, WHITE, 0.15),
        "mid.light.color": mix(pal.button, WHITE, 0.07),
        "dark.color": mix(pal.button, BLACK, 0.45),
        "mid.color": mix(pal.button, BLACK, 0.2),
        "shadow.color": BLACK,
        "highlight.color": pal.select,
        # The muted bar of an inactive window's selection, as one opaque colour.
        "inactive.highlight.color": mix(pal.view, WHITE, 0.15) if pal.dark else mix(pal.view, pal.select, 0.2),
        "tooltip.base.color": pal.tooltip,
        "text.color": text,
        "window.text.color": text,
        "button.text.color": text,
        "disabled.text.color": pal.text_faint,
        "tooltip.text.color": text,
        "highlight.text.color": pal.select_text,
        "inactive.highlight.text.color": text,
        "link.color": pal.link,
        "link.visited.color": pal.visited,
        "progress.indicator.text.color": pal.select_text,
    }
    sections["Hacks"] = {
        "respect_darkness": "true",
        "transparent_ktitle_label": "true",
        "transparent_dolphin_view": "false",
        # The dark variant's selection is light; tinting its icons would wash them out.
        "no_selection_tint": "true",
        "normal_default_pushbutton": "true",
        "iconless_pushbutton": "false",
        "iconless_menu": "false",
        "kcapacitybar_as_progressbar": "true",
        "tint_on_mouseover": 0,
    }
    button = {
        "frame": "true", "frame.element": "button", "interior": "true", "interior.element": "button",
        "indicator.element": "arrow", "indicator.size": 9,
        **_frame_keys(b), **_margins(2, 2, 7, 7),
        "text.iconspacing": 5, "text.shadow": 0, "text.bold": "false",
        **_text(text, text, k.press_text, text),
    }
    sections["PanelButtonCommand"] = button
    sections["PanelButtonTool"] = {"inherits": "PanelButtonCommand", **_margins(2, 2, 3, 3)}
    sections["ComboBox"] = {"inherits": "PanelButtonCommand"}
    # Drawn as <indicator>-<state>, so the direction is part of the name; combo
    # boxes borrow it too, having no "arrow-normal" of their own.
    sections["DropDownButton"] = {"inherits": "PanelButtonCommand", "indicator.element": "arrow-down"}
    sections["IndicatorArrow"] = {"indicator.element": "arrow", "indicator.size": 9}
    sections["IndicatorSpinBox"] = {"inherits": "PanelButtonCommand", "frame": "false", "interior": "false",
                                    "indicator.element": "spin", "indicator.size": 9}
    sections["ToolboxTab"] = {"inherits": "PanelButtonCommand"}
    sections["Dock"] = {"inherits": "PanelButtonCommand", "frame": "false", "interior": "false"}
    sections["DockTitle"] = {"inherits": "PanelButtonCommand", "frame": "false", "interior": "false",
                             **_text(pal.text_dim, text, text, text), "text.bold": "true"}
    sections["RadioButton"] = {"inherits": "PanelButtonCommand", "frame": "false", "interior.element": "radio",
                               **_text(text, text, text, text)}
    sections["CheckBox"] = {"inherits": "PanelButtonCommand", "frame": "false", "interior.element": "checkbox",
                            **_text(text, text, text, text)}
    sections["Focus"] = {"frame": "true", "frame.element": "focus", "interior": "false", **_frame_keys(1)}
    sections["GenericFrame"] = {"frame": "true", "frame.element": "common", "interior": "false",
                                **_frame_keys(mt.small)}
    sections["LineEdit"] = {"frame": "true", "frame.element": "lineedit", "interior": "true",
                            "interior.element": "lineedit", **_frame_keys(b), **_margins(2, 2, 4, 4)}
    sections["Tab"] = {
        "frame": "true", "frame.element": "tab", "interior": "true", "interior.element": "tab",
        "indicator.element": "tab", "indicator.size": 10,
        **_frame_keys(b, 0, b), **_margins(3, 3, 10, 10), "text.bold": "false",
        **_text(pal.text_dim, text, text, text),
    }
    sections["TabFrame"] = {"frame": "true", "frame.element": "tabframe", "interior": "false",
                            **_frame_keys(mt.small)}
    sections["TabBarFrame"] = {"frame": "false", "interior": "false"}
    sections["TreeExpander"] = {"frame": "false", "interior": "false", "indicator.element": "tree",
                                "indicator.size": 9}
    sections["HeaderSection"] = {
        "frame": "true", "frame.element": "header", "interior": "true", "interior.element": "header",
        "indicator.element": "arrow", "indicator.size": 9,
        **_frame_keys(2), **_margins(2, 2, 4, 4), "text.bold": "false", **_text(text),
    }
    sections["SizeGrip"] = {"frame": "false", "interior": "false", "indicator.element": "sizegrip",
                            "indicator.size": 13}
    sections["Toolbar"] = {"frame": "false", "interior": "false", "indicator.element": "toolbar",
                           "indicator.size": 5, "text.margin": 0, **_text(text)}
    sections["Slider"] = {"frame": "true", "frame.element": "slider", "interior": "true",
                          "interior.element": "slider", **_frame_keys(2)}
    sections["SliderCursor"] = {"frame": "false", "interior": "true", "interior.element": "slidercursor"}
    sections["Progressbar"] = {"frame": "true", "frame.element": "progress", "interior": "true",
                               "interior.element": "progress", **_frame_keys(2), "text.margin": 0,
                               "text.bold": "false", **_text(text)}
    sections["ProgressbarContents"] = {"frame": "true", "frame.element": "progress-pattern", "interior": "true",
                                       "interior.element": "progress-pattern", **_frame_keys(2),
                                       **_text(pal.select_text)}
    sections["ItemView"] = {
        "frame": "true", "frame.element": "itemview", "interior": "true", "interior.element": "itemview",
        **_frame_keys(mt.item), **_margins(1, 1, 3, 3),
        **_text(text, text, k.select_text, text),
        "text.press.inactive.color": text, "text.toggle.inactive.color": text,
    }
    sections["Splitter"] = {"frame": "false", "interior": "false", "indicator.element": "splitter-grip",
                            "indicator.size": 16}
    sections["Scrollbar"] = {"frame": "false", "interior": "false", "indicator.element": "arrow",
                             "indicator.size": 9}
    # The thumb's own grip indicator is left undrawn: the name matches nothing.
    sections["ScrollbarSlider"] = {"frame": "true", "frame.element": "scrollbarslider", "interior": "true",
                                   "interior.element": "scrollbarslider", "indicator.element": "kh-none",
                                   **_frame_keys(4)}
    sections["ScrollbarGroove"] = {"frame": "true", "frame.element": "scrollbargroove", "interior": "true",
                                   "interior.element": "scrollbargroove", "indicator.element": "kh-none",
                                   **_frame_keys(2)}
    sections["MenuItem"] = {
        "frame": "true", "frame.element": "menuitem", "interior": "true", "interior.element": "menuitem",
        "indicator.element": "menuitem", **_frame_keys(mt.item), **_margins(2, 2, 5, 5),
        **_text(text, k.select_text, k.select_text, k.select_text),
    }
    sections["MenuBarItem"] = {
        "frame": "true", "frame.element": "menuitem", "interior": "true", "interior.element": "menuitem",
        **_frame_keys(mt.item), **_margins(2, 2, 6, 6),
        **_text(text, text, k.select_text, k.select_text),
    }
    sections["MenuBar"] = {"frame": "false", "interior": "false", **_text(text)}
    sections["Menu"] = {"frame": "true", "frame.element": "menu", "interior": "true", "interior.element": "menu",
                        **_frame_keys(mt.popup), **_text(text)}
    sections["ToolTip"] = {"frame": "true", "frame.element": "tooltip", "interior": "true",
                           "interior.element": "tooltip", **_frame_keys(mt.tip), "text.margin": 1, **_text(text)}
    sections["GroupBox"] = {"frame": "true", "frame.element": "group", "interior": "true",
                            "interior.element": "group", **_frame_keys(mt.group), "text.margin": 0,
                            "text.bold": "true", **_text(text)}
    sections["TitleBar"] = {"frame": "false", "interior": "true", "interior.element": "titlebar",
                            "indicator.element": "mdi", "indicator.size": 12, "text.bold": "true",
                            **_text(pal.title_inactive_text, pal.title_text, pal.title_text, pal.title_text)}
    sections["StatusBar"] = {"frame": "false", "interior": "false"}
    sections["Window"] = {"interior": "false", **_text(text)}
    return sections


def render_config(sections: dict[str, dict[str, object]]) -> str:
    out = []
    for name, keys in sections.items():
        out.append(f"[{name}]")
        out += [f"{key}={value}" for key, value in keys.items()]
        out.append("")
    return "\n".join(out)


# --- self-check -------------------------------------------------------------------------
# States Kvantum asks for, per section, beyond "normal" (disabled frames and
# interiors it derives itself).
FRAME_STATES = {
    "PanelButtonCommand": ("normal", "focused", "pressed", "toggled"),
    "LineEdit": ("normal", "focused"),
    "Tab": ("normal", "focused", "pressed", "toggled"),
    "ItemView": ("focused", "pressed", "toggled"),
    "MenuItem": ("focused", "pressed", "toggled"),
    "MenuBarItem": ("focused", "pressed", "toggled"),
    "HeaderSection": ("normal", "focused", "pressed"),
    "ScrollbarSlider": ("normal", "focused", "pressed"),
    "Slider": ("normal", "toggled"),
    "ProgressbarContents": ("normal", "focused", "disabled"),
    "TitleBar": ("normal", "focused"),
    "SliderCursor": ("normal", "focused", "pressed", "disabled"),
}


def required_ids(sections: dict[str, dict[str, object]]) -> set[str]:
    """Element ids Kvantum will look up for this config, by its naming rules."""

    def resolved(section: str, key: str):
        seen = set()
        while section and section not in seen:
            seen.add(section)
            keys = sections.get(section, {})
            if key in keys:
                return keys[key]
            section = keys.get("inherits")
        return None

    need: set[str] = set()
    for name in sections:
        if name in ("%General", "GeneralColors", "Hacks"):
            continue
        states = FRAME_STATES.get(name, ("normal",))
        if resolved(name, "frame") == "true":
            element = resolved(name, "frame.element")
            if name == "Focus":
                need |= {f"{element}-{side}" for side in SIDES}
            else:
                need |= {f"{element}-{state}-{side}" for state in states for side in SIDES}
        if resolved(name, "interior") == "true":
            element = resolved(name, "interior.element")
            if name in ("CheckBox", "RadioButton"):
                variants = ["", "checked-"] + (["tristate-"] if name == "CheckBox" else [])
                need |= {f"{element}-{v}{s}" for v in variants for s in ("normal", "focused")}
            else:
                need |= {f"{element}-{state}" for state in states}
    arrows = {"up", "down", "left", "right"}
    need |= {f"arrow-{d}-{s}" for d in arrows for s in STATES4}
    need |= {f"spin-{d}-{s}" for d in arrows | {"plus", "minus"} for s in STATES4}
    need |= {f"tree-{d}-{s}" for d in ("plus", "minus") for s in STATES4}
    need |= {f"menuitem-{d}-{s}" for d in ("left", "right") for s in STATES4}
    need |= {f"tab-close-{s}" for s in STATES4} | {"tab-tear"}
    need |= {"menuitem-separator", "menuitem-tearoff-normal", "menuitem-tearoff-focused"}
    need |= {"header-separator", "toolbar-handle", "toolbar-separator", "button-default-indicator"}
    need |= {"sizegrip-normal", "sizegrip-focused", "slider-tick-normal", "dial", "dial-notches", "dial-handle"}
    need |= {f"splitter-grip-{s}" for s in ("normal", "focused", "pressed")}
    need |= {f"mdi-{n}-{s}" for n in ("close", "maximize", "restore", "minimize", "shade") for s in STATES4}
    need |= {"mdi-menu-normal"}
    for element in ("menu", "tooltip"):
        need |= {f"{element}-shadow-{side}" for side in SIDES}
        need |= {f"{element}-shadow-hint-{d}" for d in ("top", "bottom", "left", "right")}
    return need


def svg_ids(svg_text: str) -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', svg_text))


# --- build ------------------------------------------------------------------------------
def build(out: Path, pal: Palette) -> Path:
    """Write <name>.kvconfig and <name>.svg into out/Kvantum/KingdomHearts."""
    folder = out / "Kvantum" / THEME
    name = theme_name(pal)
    with log.timed("kvantum", "build kvantum style", variant=pal.key, theme=name, target=str(folder)):
        sections = config_sections(pal)
        svg_text = build_svg(pal)
        have = svg_ids(svg_text)
        missing = sorted(required_ids(sections) - have)
        if missing:
            log.error("kvantum", "the SVG lacks elements the config asks for; Kvantum would draw its "
                      "default theme there", variant=pal.key, missing=missing[:40], count=len(missing))
            raise ValueError(f"{len(missing)} Kvantum elements missing, first: {missing[0]}")
        # Each variant writes only its own files: both share the folder.
        write_text(folder / f"{name}.kvconfig", render_config(sections))
        write_text(folder / f"{name}.svg", svg_text)
        log.info("kvantum", "kvantum style written", variant=pal.key, theme=name, elements=len(have),
                 style_key=style_key(pal))
    return folder
