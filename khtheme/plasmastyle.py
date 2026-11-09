"""Plasma Style (desktop theme): panel, popups, tooltips, task buttons, list items.

Frames follow the variant's shape language (see `Palette.corner`): clipped
corners with bright corner strokes, or headings rounded on two opposite corners.

Only the surfaces that carry the theme's identity are drawn here. Everything
else (buttons, sliders, checkboxes, ...) falls back to Breeze's SVGs, which are
colour-scheme driven and pick up the palette from the bundled `colors` file.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from . import VERSION, log
from .colorscheme import render_colors
from .palette import BLACK, WHITE, Palette
from .wallpapers import default_for
from .svg import (
    FrameStyle,
    document,
    frame_pieces,
    margin_hints,
    shadow_pieces,
    write_svgz,
    write_text,
)

GAP = 8  # spacing between element groups on the SVG canvas


def _shape(pal: Palette, r: float) -> dict:
    """Corner treatment of the variant's shape language for a frame of size r:
    clipped corners all round, or a heading with two opposite corners rounded."""
    if pal.corner == "cut":
        return {"r": r, "cut": True}
    return {"r": r, "square": {"topright", "bottomleft"}}


def _glass(pal: Palette, variant: str, **overrides) -> FrameStyle:
    """Shell glass in one of three opacities: `normal` (compositing without
    blur), `translucent` (blur behind, so the fill can be thinner) and `solid`
    (used when a maximised window makes the panel/popup opaque)."""
    a_top, a_bot = pal.glass_alpha[variant]
    base = FrameStyle(
        fill_top=(pal.glass_top, a_top),
        fill_bot=(pal.glass_bot, a_bot),
        border_top=pal.edge_top,
        border_bot=pal.edge_bot,
        sheen=pal.sheen,
        accent=(pal.ornament, 0.95),
        c=16,
        **_shape(pal, 10),
    )
    return replace(base, **overrides)


def _frame_doc(
    pal: Palette,
    style: FrameStyle,
    margins: tuple[float, float, float, float],
    shadow: tuple[int, float] | None,
    mask: bool = True,
    thick_margins: tuple[float, float, float, float] | None = None,
) -> str:
    """One self-contained frame SVG: slices, optional shadow + blur mask, hints."""
    defs: list[str] = []
    body: list[str] = []
    x = 0.0
    height = float(style.size)

    d, b = frame_pieces("", x, 0, style, "f")
    defs += d
    body += b
    x += style.size + GAP

    if shadow:
        spread, alpha = shadow
        d, b, k = shadow_pieces(
            "shadow", x, 0, spread, int(style.r), pal.shadow, alpha * pal.shadow_strength, "sh"
        )
        defs += d
        body += b
        hx = x + 2 * k + style.m + GAP
        hint = 'fill="#ff00ff" opacity="0.002"'
        body += [
            f'<rect id="shadow-hint-top-margin" x="{hx}" y="0" width="4" height="{spread}" {hint}/>',
            f'<rect id="shadow-hint-bottom-margin" x="{hx + 6}" y="0" width="4" height="{spread}" {hint}/>',
            f'<rect id="shadow-hint-left-margin" x="{hx + 12}" y="0" width="{spread}" height="4" {hint}/>',
            f'<rect id="shadow-hint-right-margin" x="{hx + 12}" y="6" width="{spread}" height="4" {hint}/>',
        ]
        height = max(height, 2 * k + style.m)
        x = hx + 12 + spread + GAP

    if mask:
        # The blur/contrast region must match the visible shape, otherwise the
        # blurred backdrop leaks past the rounded corners.
        solid = replace(
            style,
            fill_top=(BLACK, 1),
            fill_bot=(BLACK, 1),
            border_top=None,
            border_bot=None,
            sheen=None,
            accent=None,
            line=None,
        )
        d, b = frame_pieces("mask", x, 0, solid, "m")
        defs += d
        body += b
        x += style.size + GAP

    body += margin_hints("", x, 0, *margins)
    if thick_margins:
        body += margin_hints("thick", x + 30, 0, *thick_margins)
        body.append(
            f'<rect id="thick-center" x="{x + 30}" y="60" width="16" height="16" fill="#000000" opacity="0.002"/>'
        )
    body.append(f'<rect id="hint-stretch-borders" x="{x}" y="60" width="4" height="4" fill="#00ff00" opacity="0.002"/>')
    x += 60

    return document(x, max(height, 80), defs, body)


def _states_doc(states: dict[str, FrameStyle], hints: dict[str, tuple[float, float, float, float]]) -> str:
    """Several prefixed frames (one per widget state) in a single SVG."""
    defs: list[str] = []
    body: list[str] = []
    x = 0.0
    y = 0.0
    row_h = 0.0
    width = 0.0
    for n, (prefix, style) in enumerate(states.items()):
        d, b = frame_pieces(prefix, x, y, style, f"t{n}")
        defs += d
        body += b
        row_h = max(row_h, style.size)
        x += style.size + GAP
        width = max(width, x)
        if (n + 1) % 6 == 0:
            x = 0.0
            y += row_h + GAP
            row_h = 0.0
    y += row_h + GAP
    for n, (prefix, m) in enumerate(hints.items()):
        body += margin_hints(prefix, n * 40, y, *m)
    body.append(
        f'<rect id="hint-stretch-borders" x="{len(hints) * 40}" y="{y}" width="4" height="4" fill="#00ff00" opacity="0.002"/>'
    )
    return document(max(width, len(hints) * 40 + 8), y + 56, defs, body)


def _task_states(pal: Palette) -> dict[str, FrameStyle]:
    """Task-manager buttons, shaped like rows of the variant's command menu.
    Labels are drawn in the normal text colour in every state, so fills stay
    translucent enough to keep them legible. The active window carries a solid
    bar: on the screen-edge side for clipped rows, down the left side for
    heading rows (the thick left border of the first game's menu)."""
    cut = pal.corner == "cut"
    row = dict(c=9, inset=3, m=24, r=5, cut=True) if cut else dict(c=11, inset=3, m=24, r=8, square={"topleft", "bottomleft"})
    tint = WHITE if pal.dark else pal.select_deep
    k = pal.tint
    base = {
        "normal": FrameStyle((tint, 0.05), (tint, 0.03), border_top=(tint, 0.22 if cut else 0.16), border_bot=(tint, 0.12), **row),
        "hover": FrameStyle((pal.hover, 0.24), (pal.hover, 0.12), border_top=(pal.hover, 0.7), border_bot=(pal.hover, 0.4), **row),
        "focus": FrameStyle(
            (pal.select_hi, 0.62 * k),
            (pal.select if pal.dark else pal.select_hi, 0.5 * k),
            border_top=(pal.focus, 0.9),
            border_bot=(pal.select_hi, 0.7),
            **row,
        ),
        "attention": FrameStyle((pal.neutral, 0.7 * k), (pal.neutral, 0.4 * k), border_top=(pal.neutral, 0.95), border_bot=(pal.neutral, 0.7), **row),
        "minimized": FrameStyle((tint, 0.025), (tint, 0.015), border_top=(pal.text_dim, 0.2), border_bot=(pal.text_dim, 0.1), **row),
        "progress": FrameStyle((pal.positive, 0.55 * k), (pal.positive, 0.3 * k), border_top=(pal.positive, 0.85), border_bot=(pal.positive, 0.55), **row),
    }
    # Panel location -> edge of the button that touches the screen edge.
    outer_edge = {"": "bottom", "north": "top", "west": "left", "east": "right"}
    states: dict[str, FrameStyle] = {}
    for location, edge in outer_edge.items():
        for name, style in base.items():
            if name == "focus":
                bar = (edge, (pal.indicator, 1.0), 2) if cut else ("left", (pal.indicator, 1.0), 3)
                style = replace(style, line=bar)
            states[f"{location}-{name}" if location else name] = style
    return states


def _viewitem_states(pal: Palette) -> dict[str, FrameStyle]:
    item = dict(c=6, m=24, r=4, cut=True) if pal.corner == "cut" else dict(c=8, m=24, r=7, square={"topleft", "bottomleft"})
    k = min(1.0, pal.tint * 1.4)
    return {
        "normal": FrameStyle((WHITE, 0.0), (WHITE, 0.0), **item),
        "hover": FrameStyle((pal.hover, 0.2), (pal.hover, 0.12), border_top=(pal.hover, 0.5), border_bot=(pal.hover, 0.3), **item),
        "selected": FrameStyle(
            (pal.select_hi, 0.5 * k), (pal.select, 0.42 * k), border_top=(pal.select_hi, 0.9), border_bot=(pal.select, 0.75), **item
        ),
        "selected+hover": FrameStyle(
            (pal.select_hi, 0.68 * k), (pal.select, 0.58 * k), border_top=(pal.focus, 1.0), border_bot=(pal.select_hi, 0.85), **item
        ),
    }


def _heading_doc(pal: Palette) -> str:
    """Header/footer bands inside popups. Kept as a faint overlay so the popup's
    own border and corner ornaments stay visible through them."""
    common = dict(c=16, r=10, m=32, cut=pal.corner == "cut")
    if pal.dark:
        head = ((WHITE, 0.06), (WHITE, 0.015))
        foot = ((BLACK, 0.2), (BLACK, 0.32))
    else:
        head = ((pal.select, 0.09), (pal.select, 0.03))
        foot = ((pal.select_deep, 0.04), (pal.select_deep, 0.08))
    # Bands follow the popup's own corners where they touch them.
    popup_square = _shape(pal, 10).get("square", set())
    header = FrameStyle(
        *head,
        square={"bottomleft", "bottomright"} | (popup_square & {"topleft", "topright"}),
        line=("bottom", (pal.ornament, 0.4 if pal.dark else 0.75), 1),
        **common,
    )
    footer = FrameStyle(
        *foot, square={"topleft", "topright"} | (popup_square & {"bottomleft", "bottomright"}), line=("top", pal.edge_bot, 1), **common
    )
    return _states_doc({"header": header, "footer": footer}, {"": (6, 6, 6, 6)})


def _metadata(pal: Palette) -> str:
    return json.dumps(
        {
            "KPlugin": {
                "Authors": [{"Name": "Kingdom Hearts Plasma theme"}],
                "Category": "Plasma Theme",
                "Description": f"{pal.title} panels and popups shaped like the games' command menus",
                "EnabledByDefault": True,
                "Id": pal.theme_id,
                "License": "CC-BY-SA-4.0",
                "Name": pal.theme_name,
                "Version": VERSION,
            },
            "X-Plasma-API": "5.0",
            "X-Plasma-API-Minimum-Version": "6.0",
        },
        indent=4,
        ensure_ascii=False,
    )


def _plasmarc(pal: Palette) -> str:
    contrast, intensity, saturation = pal.contrast
    return f"""[Wallpaper]
defaultWallpaperTheme={default_for(pal).package_id}
defaultFileSuffix=.jpg
defaultWidth=1920
defaultHeight=1080

[BlurBehindEffect]
enabled=true

[ContrastEffect]
enabled=true
contrast={contrast}
intensity={intensity}
saturation={saturation}

[AdaptiveTransparency]
enabled=true
"""


def build(out: Path, pal: Palette) -> Path:
    """Write the variant's Plasma Style into out/plasma/desktoptheme/<id>."""
    root = out / "plasma" / "desktoptheme" / pal.theme_id
    with log.timed("plasmastyle", "build plasma style", variant=pal.key, target=str(root)):
        files: dict[str, str] = {}

        for variant, sub in (("normal", ""), ("translucent", "translucent/"), ("solid", "solid/")):
            files[f"{sub}dialogs/background"] = _frame_doc(pal, _glass(pal, variant), (6, 6, 6, 6), shadow=(18, 0.62))
            files[f"{sub}widgets/background"] = _frame_doc(pal, _glass(pal, variant), (8, 8, 8, 8), shadow=(16, 0.55))
            files[f"{sub}widgets/tooltip"] = _frame_doc(
                pal, _glass(pal, variant, c=8, accent=None, **_shape(pal, 6)), (5, 5, 6, 6), shadow=(12, 0.55)
            )
            files[f"{sub}widgets/panel-background"] = _frame_doc(
                pal,
                _glass(pal, variant, c=14, **_shape(pal, 12)),
                (4, 4, 4, 4),
                shadow=(14, 0.5),
                thick_margins=(8, 8, 8, 8),
            )

        # Without compositing there is no alpha: square, fully opaque surfaces.
        flat = dict(r=0, accent=None, cut=False, square=set())
        files["opaque/dialogs/background"] = _frame_doc(
            pal, _glass(pal, "solid", **flat), (6, 6, 6, 6), shadow=None, mask=False
        )
        files["opaque/widgets/tooltip"] = _frame_doc(
            pal, _glass(pal, "solid", c=8, **flat), (5, 5, 6, 6), shadow=None, mask=False
        )
        files["opaque/widgets/panel-background"] = _frame_doc(
            pal, _glass(pal, "solid", c=14, **flat), (4, 4, 4, 4), shadow=None, mask=False, thick_margins=(8, 8, 8, 8)
        )

        files["widgets/tasks"] = _states_doc(_task_states(pal), {"normal": (5, 5, 7, 7)})
        files["widgets/viewitem"] = _states_doc(_viewitem_states(pal), {})
        files["widgets/plasmoidheading"] = _heading_doc(pal)

        for rel, text in files.items():
            write_svgz(root / f"{rel}.svgz", text)
            log.debug("plasmastyle", "wrote element", variant=pal.key, file=rel, bytes=len(text))

        write_text(root / "metadata.json", _metadata(pal) + "\n")
        write_text(root / "plasmarc", _plasmarc(pal))
        write_text(root / "colors", render_colors(pal))
        log.info("plasmastyle", "plasma style written", variant=pal.key, svg_files=len(files), target=str(root))
    return root
