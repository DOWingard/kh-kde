"""KDE colour scheme (.colors) generated from a palette.

The same text doubles as the Plasma Style's `colors` file so shell widgets and
applications share one palette.
"""

from __future__ import annotations

from pathlib import Path

from . import log
from .palette import Palette, mix, rgb_csv
from .svg import write_text


def scheme_id(pal: Palette) -> str:
    return f"KingdomHearts{pal.key}"


def _set(pal: Palette, bg: str, alt: str, **over) -> dict[str, str]:
    values = {
        "BackgroundAlternate": alt,
        "BackgroundNormal": bg,
        "DecorationFocus": pal.focus,
        "DecorationHover": pal.hover,
        "ForegroundActive": pal.select_hi if pal.dark else pal.select,
        "ForegroundInactive": pal.text_dim,
        "ForegroundLink": pal.link,
        "ForegroundNegative": pal.negative,
        "ForegroundNeutral": pal.neutral,
        "ForegroundNormal": pal.text,
        "ForegroundPositive": pal.positive,
        "ForegroundVisited": pal.visited,
    }
    values.update(over)
    return values


def color_sets(pal: Palette) -> dict[str, dict[str, str]]:
    on_dark = dict(
        ForegroundNormal=pal.complementary_text,
        ForegroundInactive=mix(pal.complementary_text, pal.complementary, 0.4),
        ForegroundActive=pal.select_hi,
        ForegroundLink=mix(pal.select_hi, "#ffffff", 0.35),
        ForegroundVisited=mix(pal.visited, "#ffffff", 0.35),
    )
    return {
        "Colors:Button": _set(pal, pal.button, pal.button_alt),
        "Colors:Complementary": _set(pal, pal.complementary, pal.complementary_alt, **on_dark),
        "Colors:Header": _set(pal, pal.header, pal.window),
        "Colors:Header][Inactive": _set(pal, pal.header_inactive, pal.window, ForegroundNormal=pal.text_dim),
        "Colors:Selection": _set(
            pal,
            pal.select,
            pal.select_deep,
            ForegroundNormal=pal.select_text,
            ForegroundInactive=mix(pal.select_text, pal.select, 0.3),
            ForegroundActive=pal.ornament_pale,
            ForegroundLink=pal.ornament_pale,
            ForegroundVisited=mix(pal.select_text, pal.visited, 0.4),
            DecorationFocus=pal.ornament,
            DecorationHover=pal.ornament_pale,
        ),
        "Colors:Tooltip": _set(pal, pal.tooltip, pal.window),
        "Colors:View": _set(pal, pal.view, pal.view_alt),
        "Colors:Window": _set(pal, pal.window, pal.window_alt),
    }


def render_colors(pal: Palette) -> str:
    lines = [
        "[ColorEffects:Disabled]",
        "Color=" + rgb_csv(pal.window),
        "ColorAmount=0.3",
        "ColorEffect=0",
        "ContrastAmount=0.55",
        "ContrastEffect=1",
        "IntensityAmount=-0.1" if pal.dark else "IntensityAmount=0.1",
        "IntensityEffect=2",
        "",
        "[ColorEffects:Inactive]",
        "ChangeSelectionColor=true",
        "Color=" + rgb_csv(pal.button),
        "ColorAmount=0.2",
        "ColorEffect=2",
        "ContrastAmount=0.1",
        "ContrastEffect=2",
        "Enable=false",
        "IntensityAmount=0",
        "IntensityEffect=0",
        "",
    ]
    for section, values in color_sets(pal).items():
        lines.append(f"[{section}]")
        lines += [f"{key}={rgb_csv(value)}" for key, value in values.items()]
        lines.append("")
    lines += [
        "[General]",
        f"ColorScheme={scheme_id(pal)}",
        f"Name={pal.theme_name}",
        "accentActiveTitlebar=false",
        "accentInactiveTitlebar=false",
        "shadeSortColumn=true",
        "",
        "[KDE]",
        "contrast=4",
        "",
        "[WM]",
        "activeBackground=" + rgb_csv(mix(pal.title_top, pal.title_bot, 0.5)),
        "activeBlend=" + rgb_csv(pal.title_text),
        "activeForeground=" + rgb_csv(pal.title_text),
        "inactiveBackground=" + rgb_csv(mix(pal.title_inactive_top, pal.title_inactive_bot, 0.5)),
        "inactiveBlend=" + rgb_csv(pal.title_inactive_text),
        "inactiveForeground=" + rgb_csv(pal.title_inactive_text),
        "",
    ]
    return "\n".join(lines)


def build(out: Path, pal: Palette) -> Path:
    target = out / "color-schemes" / f"{scheme_id(pal)}.colors"
    with log.timed("colorscheme", "build colour scheme", variant=pal.key, target=str(target)):
        write_text(target, render_colors(pal))
    return target
