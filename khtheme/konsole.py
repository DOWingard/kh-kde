"""Konsole colour scheme generated from the palette's terminal colours."""

from __future__ import annotations

from pathlib import Path

from . import log
from .palette import Palette, mix, rgb_csv
from .svg import write_text


def render(pal: Palette) -> str:
    if len(pal.term_normal) != 8 or len(pal.term_bright) != 8:
        raise ValueError(f"palette {pal.key} must define 8 normal and 8 bright terminal colours")
    lines = [
        "[Background]",
        f"Color={rgb_csv(pal.term_bg)}",
        "",
        "[BackgroundFaint]",
        f"Color={rgb_csv(pal.term_bg)}",
        "",
        "[BackgroundIntense]",
        f"Color={rgb_csv(pal.term_bg)}",
        "",
    ]
    for n in range(8):
        lines += [f"[Color{n}]", f"Color={rgb_csv(pal.term_normal[n])}", ""]
        lines += [f"[Color{n}Faint]", f"Color={rgb_csv(mix(pal.term_normal[n], pal.term_bg, 0.35))}", ""]
        lines += [f"[Color{n}Intense]", f"Color={rgb_csv(pal.term_bright[n])}", ""]
    lines += [
        "[Foreground]",
        f"Color={rgb_csv(pal.term_fg)}",
        "",
        "[ForegroundFaint]",
        f"Color={rgb_csv(mix(pal.term_fg, pal.term_bg, 0.35))}",
        "",
        "[ForegroundIntense]",
        f"Color={rgb_csv(pal.text)}",
        "",
        "[General]",
        "Anchor=0.5,0.5",
        "Blur=true",
        "ColorRandomization=false",
        f"Description={pal.theme_name}",
        "FillStyle=Tile",
        "Opacity=0.94",
        "Wallpaper=",
        "WallpaperFlipType=NoFlip",
        "WallpaperOpacity=1",
        "",
    ]
    return "\n".join(lines)


def build(out: Path, pal: Palette) -> Path:
    target = out / "konsole" / f"{pal.theme_id}.colorscheme"
    with log.timed("konsole", "build terminal colour scheme", variant=pal.key, target=str(target)):
        write_text(target, render(pal))
    return target
