"""The keyblades offered as mouse pointers.

The sprites come from Chain of Memories' item art: one sheet of every keyblade
the game hands out, plus the Kingdom Key on its own. All of them are drawn the
same way round (tip at the top left, guard at the bottom right), so each is
cut out of its sheet as it is and placed on one shared canvas with its top-left
corner at the origin. That keeps every keyblade at the same scale and the tip
in the same corner, whichever one is chosen.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import log

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "keyblades"
SHEET = ASSETS / "sheet.png"
SINGLE = ASSETS / "kingdom-key.png"

MAIN = "kingdom-key"


@dataclass(frozen=True)
class Keyblade:
    slug: str
    name: str
    source: Path
    box: tuple[int, int, int, int]  # x, y, width, height of the sprite on its source


# The sheet's own Kingdom Key (at 3,305) is pixel for pixel the single sprite,
# so only the single one is used. Order: the main keyblade, then the sheet's
# left column top to bottom, then its right column.
KEYBLADES = [
    Keyblade(MAIN, "Kingdom Key", SINGLE, (3, 1, 27, 24)),
    Keyblade("oblivion", "Oblivion", SHEET, (2, 0, 28, 26)),
    Keyblade("oathkeeper", "Oathkeeper", SHEET, (2, 31, 28, 25)),
    Keyblade("divine-rose", "Divine Rose", SHEET, (2, 60, 28, 23)),
    Keyblade("lady-luck", "Lady Luck", SHEET, (4, 88, 26, 25)),
    Keyblade("olympia", "Olympia", SHEET, (3, 120, 27, 26)),
    Keyblade("wishing-star", "Wishing Star", SHEET, (3, 153, 27, 23)),
    Keyblade("fairy-harp", "Fairy Harp", SHEET, (4, 183, 26, 24)),
    Keyblade("pumpkinhead", "Pumpkinhead", SHEET, (3, 214, 27, 24)),
    Keyblade("crabclaw", "Crabclaw", SHEET, (3, 243, 27, 26)),
    Keyblade("three-wishes", "Three Wishes", SHEET, (3, 274, 27, 26)),
    Keyblade("soul-eater", "Soul Eater", SHEET, (40, 78, 26, 24)),
    Keyblade("metal-chocobo", "Metal Chocobo", SHEET, (40, 105, 26, 23)),
    Keyblade("one-winged-angel", "One-Winged Angel", SHEET, (40, 133, 26, 20)),
    Keyblade("lionheart", "Lionheart", SHEET, (40, 158, 26, 23)),
    Keyblade("spellbinder", "Spellbinder", SHEET, (39, 186, 27, 26)),
    Keyblade("diamond-dust", "Diamond Dust", SHEET, (39, 217, 27, 23)),
    Keyblade("ultima-weapon", "Ultima Weapon", SHEET, (39, 245, 27, 25)),
]

# The shared canvas: the largest sprite fits exactly.
CANVAS = (max(k.box[2] for k in KEYBLADES), max(k.box[3] for k in KEYBLADES))


def by_slug(slug: str) -> Keyblade:
    for keyblade in KEYBLADES:
        if keyblade.slug == slug:
            return keyblade
    raise KeyError(f"unknown keyblade {slug!r}; choose from {[k.slug for k in KEYBLADES]}")


def factor(nominal: int, scale: float) -> int:
    """Whole-number enlargement for a cursor size, so pixel art stays crisp:
    the multiple that brings the canvas closest to `scale` times the size."""
    return max(1, round(scale * nominal / CANVAS[1]))


def _magick(args: list[str], what: str) -> str:
    try:
        return subprocess.run(["magick", *args], check=True, capture_output=True, text=True, timeout=60).stdout
    except FileNotFoundError as exc:
        log.error("keyblades", "ImageMagick is not installed", error=exc, step=what)
        raise
    except subprocess.TimeoutExpired as exc:
        log.error("keyblades", "ImageMagick timed out", error=exc, step=what)
        raise
    except subprocess.CalledProcessError as exc:
        log.error("keyblades", "ImageMagick failed", error=exc, step=what, stderr=exc.stderr[-1500:])
        raise


def _check_box(keyblade: Keyblade) -> None:
    """The box must hold the whole sprite and nothing else: opaque pixels touch
    all four sides, and the one-pixel ring around it is empty."""
    x, y, w, h = keyblade.box
    size = _magick([str(keyblade.source), "-format", "%w %h", "info:"], f"measure {keyblade.source.name}").split()
    sw, sh = int(size[0]), int(size[1])
    inner = _magick(
        [str(keyblade.source), "-crop", f"{w}x{h}+{x}+{y}", "+repage", "-format", "%@", "info:"], f"check {keyblade.slug}"
    )
    rx, ry = max(0, x - 1), max(0, y - 1)
    rw, rh = min(sw, x + w + 1) - rx, min(sh, y + h + 1) - ry
    ring = _magick(
        [str(keyblade.source), "-crop", f"{rw}x{rh}+{rx}+{ry}", "+repage", "-format", "%@", "info:"], f"check {keyblade.slug}"
    )
    expected_ring = f"{w}x{h}+{x - rx}+{y - ry}"
    if inner != f"{w}x{h}+0+0" or ring != expected_ring:
        log.error("keyblades", "sprite box does not fit its sprite", keyblade=keyblade.slug, box=keyblade.box,
                  opaque_inside=inner, opaque_with_ring=ring, expected_ring=expected_ring)
        raise ValueError(f"{keyblade.slug}: box {keyblade.box} does not match the sprite on {keyblade.source.name}")


def cut(out: Path) -> dict[str, Path]:
    """Cut every sprite onto the shared canvas; returns slug -> PNG."""
    out.mkdir(parents=True, exist_ok=True)
    slugs = [k.slug for k in KEYBLADES]
    if len(set(slugs)) != len(slugs):
        raise ValueError("keyblade slugs must be unique")
    written = {}
    for keyblade in KEYBLADES:
        if not keyblade.source.is_file():
            log.error("keyblades", "sprite source is missing", path=str(keyblade.source))
            raise FileNotFoundError(keyblade.source)
        _check_box(keyblade)
        x, y, w, h = keyblade.box
        target = out / f"{keyblade.slug}.png"
        _magick(
            [str(keyblade.source), "-crop", f"{w}x{h}+{x}+{y}", "+repage", "-background", "none",
             "-gravity", "NorthWest", "-extent", f"{CANVAS[0]}x{CANVAS[1]}", f"PNG32:{target}"],
            f"cut {keyblade.slug}",
        )
        written[keyblade.slug] = target
    log.debug("keyblades", "sprites cut", count=len(written), canvas=CANVAS, out=str(out))
    return written
