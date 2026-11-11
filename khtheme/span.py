"""One picture spread across every screen.

The screens' logical rectangles (as the desktop arranges them, rotation and
scale included) are enclosed in one bounding box. The picture is fitted to
that box like a single wallpaper filling it (scaled to cover, centred), and
each screen gets the part of the picture that lies behind it. Parts of the box
no screen covers, such as the step between a landscape and a portrait screen,
are simply not shown.

Slices keep the picture's own pixels (they are never resized here), so the
desktop scales each one to its screen once.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import log

QUALITY = 92


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float


def bounds(screens: list[Rect]) -> Rect:
    left = min(s.x for s in screens)
    top = min(s.y for s in screens)
    right = max(s.x + s.width for s in screens)
    bottom = max(s.y + s.height for s in screens)
    return Rect(left, top, right - left, bottom - top)


def crops(picture: tuple[int, int], screens: list[Rect]) -> list[tuple[int, int, int, int]]:
    """Pixel rectangle (x, y, w, h) of the picture behind each screen.

    With s the cover scale (picture pixels to logical units) and (ox, oy) the
    offset of the centred visible part, a screen at (x, y, w, h) inside the
    box shows picture pixels (ox + x/s, oy + y/s, w/s, h/s).
    """
    box = bounds(screens)
    pw, ph = picture
    scale = max(box.width / pw, box.height / ph)
    ox = (pw - box.width / scale) / 2
    oy = (ph - box.height / scale) / 2
    out = []
    for screen in screens:
        x = round(ox + (screen.x - box.x) / scale)
        y = round(oy + (screen.y - box.y) / scale)
        w = max(1, min(round(screen.width / scale), pw - x))
        h = max(1, min(round(screen.height / scale), ph - y))
        out.append((max(0, x), max(0, y), w, h))
    return out


def size(picture: Path) -> tuple[int, int]:
    try:
        result = subprocess.run(["magick", "identify", "-format", "%w %h", f"{picture}[0]"], check=True,
                                capture_output=True, text=True, timeout=60)
        w, h = (int(v) for v in result.stdout.split())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
        log.error("span", "could not read the picture's size", error=exc, picture=str(picture))
        raise
    return w, h


def cut(picture: Path, crop: tuple[int, int, int, int], target: Path) -> None:
    x, y, w, h = crop
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    cmd = ["magick", f"{picture}[0]", "-crop", f"{w}x{h}+{x}+{y}", "+repage", "-strip", "-quality", str(QUALITY),
           str(target)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        log.error("span", "ImageMagick timed out", error=exc, picture=str(picture), crop=crop)
        raise
    except subprocess.CalledProcessError as exc:
        log.error("span", "ImageMagick failed", error=exc, picture=str(picture), crop=crop,
                  stderr=exc.stderr.decode(errors="replace")[-1500:])
        raise
    log.debug("span", "slice written", target=str(target), crop=crop,
              duration_ms=round((time.monotonic() - started) * 1000, 1))
