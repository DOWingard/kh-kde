"""Mouse cursor themes built from the sourced art.

The pointer is the variant's keyblade, links use the menu glove, and the busy
cursors play the variant's walking sprite. Shapes with no counterpart in the
source material (text beam, resize arrows, hands) are drawn as vectors in the
glove's style: white fill, dark outline.

Images are composed with ImageMagick and written in the Xcursor binary format
directly, so no xcursorgen is needed. Shapes that are not produced here are
inherited from Breeze's cursor theme.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import log
from .palette import Palette
from .svg import fmt, write_text

ASSETS = Path(__file__).resolve().parent.parent / "assets"
GLOVE = ASSETS / "cursor" / "menu-glove.png"

GRID = 32  # design grid of the vector shapes
SIZES = [24, 32, 48, 64]
OUTLINE = 1.5  # outline thickness on the design grid

# Image height relative to the nominal cursor size. A keyblade is a thin
# diagonal, so it has to be drawn larger than an arrow to carry the same weight.
KEY_SCALE = 2.0
GLOVE_SCALE = 1.45
SPRITE_SCALE = 2.0
SIDE_SPRITE_SCALE = 1.3  # the sprite riding beside the pointer on "progress"
VECTOR_SCALE = 1.25
BADGE_SCALE = 0.7

XCURSOR_IMAGE = 0xFFFD0002


# --- shape helpers -----------------------------------------------------------
def _rr(x: float, y: float, w: float, h: float, r: float) -> str:
    return f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" rx="{fmt(r)}"/>'


def _poly(points: list[tuple[float, float]]) -> str:
    return '<path d="M' + " L".join(f"{fmt(x)},{fmt(y)}" for x, y in points) + ' Z"/>'


def _outlined(pal: Palette, shapes: str, fill: str | None = None, transform: str = "") -> str:
    """Draw overlapping shapes as one silhouette: a wide stroke of the outline
    colour underneath, the fills on top."""
    t = f' transform="{transform}"' if transform else ""
    return (
        f'<g{t}><g fill="{pal.cursor_line}" stroke="{pal.cursor_line}" stroke-width="{fmt(2 * OUTLINE)}" '
        f'stroke-linejoin="round" stroke-linecap="round">{shapes}</g>'
        f'<g fill="{fill or pal.cursor_fill}">{shapes}</g></g>'
    )


def _hand_shapes(pointing: bool, closed: bool = False) -> str:
    if pointing:
        return (
            _rr(11.6, 2.6, 4.6, 15, 2.3)  # index finger
            + _rr(16, 10.6, 4.2, 9, 2.1)
            + _rr(19.9, 11.6, 4, 9, 2)
            + _rr(23.5, 13.2, 3.6, 8, 1.8)
            + _rr(11.6, 14, 15.5, 13.2, 4.5)  # palm
            + '<path d="M12.5,17 L8.4,14.6 Q6.2,13.6 5.6,15.6 Q5.2,17 6.8,18.4 L12.5,24 Z"/>'  # thumb
        )
    top = 10.4 if closed else 5
    length = 8 if closed else 13
    return (
        _rr(9.4, top + 1.6, 3.8, length, 1.9)
        + _rr(13.4, top, 3.8, length + 1, 1.9)
        + _rr(17.4, top + 0.4, 3.8, length + 1, 1.9)
        + _rr(21.4, top + 2.4, 3.6, length - 0.6, 1.8)
        + _rr(9.4, 14, 15.6, 13.4, 5)
        + ('<path d="M10,19.4 L7.4,17.4 Q5.6,16.6 5.2,18.4 Q5,19.6 6.2,20.8 L10,24.6 Z"/>' if closed
           else '<path d="M10,19 L6.6,15.4 Q5,14 4.2,15.6 Q3.6,17 5,18.6 L10,25 Z"/>')
    )


def _hand(pal: Palette, pointing: bool, closed: bool = False) -> str:
    # a cuff in the accent colour finishes the glove
    cuff = (
        f'<rect x="12.4" y="27.2" width="13.9" height="2.6" rx="1.2" fill="{pal.cursor_accent}" '
        f'stroke="{pal.cursor_line}" stroke-width="{fmt(OUTLINE * 0.8)}"/>'
        if pointing
        else f'<rect x="10.4" y="27.2" width="13.6" height="2.6" rx="1.2" fill="{pal.cursor_accent}" '
        f'stroke="{pal.cursor_line}" stroke-width="{fmt(OUTLINE * 0.8)}"/>'
    )
    return cuff + _outlined(pal, _hand_shapes(pointing, closed))


DOUBLE_ARROW = _poly(
    [(3, 16), (9.5, 9.5), (9.5, 14.2), (22.5, 14.2), (22.5, 9.5), (29, 16), (22.5, 22.5), (22.5, 17.8), (9.5, 17.8), (9.5, 22.5)]
)
FOUR_ARROW = _poly(
    [
        (16, 3), (20.5, 8.5), (17.4, 8.5), (17.4, 14.6), (23.5, 14.6), (23.5, 11.5), (29, 16), (23.5, 20.5),
        (23.5, 17.4), (17.4, 17.4), (17.4, 23.5), (20.5, 23.5), (16, 29), (11.5, 23.5), (14.6, 23.5),
        (14.6, 17.4), (8.5, 17.4), (8.5, 20.5), (3, 16), (8.5, 11.5), (8.5, 14.6), (14.6, 14.6), (14.6, 8.5), (11.5, 8.5),
    ]
)


# name -> (hotspot on the grid, drawer(pal) -> svg body)
def _vector_cursors() -> dict:
    return {
        "grab": ((16, 15), lambda pal: _hand(pal, False)),
        "grabbing": ((16, 15), lambda pal: _hand(pal, False, closed=True)),
        "text": (
            (16, 16),
            lambda pal: _outlined(pal, _rr(15.1, 5, 1.8, 22, 0.6) + _rr(11.6, 4, 8.8, 2.2, 1.1) + _rr(11.6, 25.8, 8.8, 2.2, 1.1)),
        ),
        "crosshair": (
            (16, 16),
            lambda pal: _outlined(
                pal, _rr(15.2, 3, 1.6, 10, 0.6) + _rr(15.2, 19, 1.6, 10, 0.6) + _rr(3, 15.2, 10, 1.6, 0.6) + _rr(19, 15.2, 10, 1.6, 0.6)
            )
            + f'<circle cx="16" cy="16" r="1.3" fill="{pal.cursor_accent}" stroke="{pal.cursor_line}" stroke-width="0.8"/>',
        ),
        "move": ((16, 16), lambda pal: _outlined(pal, FOUR_ARROW)),
        "ew-resize": ((16, 16), lambda pal: _outlined(pal, DOUBLE_ARROW)),
        "ns-resize": ((16, 16), lambda pal: _outlined(pal, DOUBLE_ARROW, transform="rotate(90 16 16)")),
        "nwse-resize": ((16, 16), lambda pal: _outlined(pal, DOUBLE_ARROW, transform="rotate(45 16 16)")),
        "nesw-resize": ((16, 16), lambda pal: _outlined(pal, DOUBLE_ARROW, transform="rotate(-45 16 16)")),
        "not-allowed": (
            (16, 16),
            lambda pal: (
                f'<g fill="none" stroke="{pal.cursor_line}" stroke-width="5.6" stroke-linecap="round">'
                '<circle cx="16" cy="16" r="10.5"/><path d="M8.6,8.6 L23.4,23.4"/></g>'
                f'<g fill="none" stroke="{pal.negative}" stroke-width="3" stroke-linecap="round">'
                '<circle cx="16" cy="16" r="10.5"/><path d="M8.6,8.6 L23.4,23.4"/></g>'
            ),
        ),
    }


# Marks for the badges that ride beside the pointer, on a 16-unit grid.
def _badges(pal: Palette) -> dict[str, tuple[str, str]]:
    return {
        "help": (pal.info, '<path d="M5.8,6.2 Q5.8,4 8,4 Q10.2,4 10.2,6 Q10.2,7.4 8,8.2 L8,9"/><path d="M8,11.6 L8,11.7"/>'),
        "copy": (pal.positive, '<path d="M8,4.6 L8,11.4 M4.6,8 L11.4,8"/>'),
        "alias": (pal.cursor_accent, '<path d="M5.2,10.8 L10.6,5.4 M6.6,5.2 L10.8,5.2 L10.8,9.4"/>'),
    }


RASTER_CURSORS = ["default", "pointer", "wait", "progress", "help", "copy", "alias"]

ALIASES = {
    "default": ["left_ptr", "arrow", "top_left_arrow"],
    "pointer": ["hand1", "hand2", "pointing_hand", "e29285e634086352946a0e7090d73106", "9d800788f1b08800ae810202380a0822"],
    "grab": ["openhand", "hand", "5aca4d189052212118709018842178c0"],
    "grabbing": ["closedhand", "dnd-move", "dnd-none", "208530c400c041818281048008011002"],
    "text": ["xterm", "ibeam"],
    "crosshair": ["cross", "tcross", "cross_reverse"],
    "move": ["fleur", "all-scroll", "size_all", "4498f0e0c1937ffe01fd06f973665830", "9081237383d90e509aa00f00170e968f"],
    "ew-resize": [
        "sb_h_double_arrow", "h_double_arrow", "size_hor", "e-resize", "w-resize", "left_side", "right_side",
        "col-resize", "split_h", "028006030e0e7ebffc7f7070c0600140", "14fef782d02440884392942c11205230",
    ],
    "ns-resize": [
        "sb_v_double_arrow", "v_double_arrow", "size_ver", "n-resize", "s-resize", "top_side", "bottom_side",
        "row-resize", "split_v", "00008160000006810000408080010102", "2870a09082c103050810ffdffffe0204",
    ],
    "nwse-resize": ["size_fdiag", "nw-resize", "se-resize", "top_left_corner", "bottom_right_corner", "c7088f0f3e6c8088236ef8e1e3e70000"],
    "nesw-resize": ["size_bdiag", "ne-resize", "sw-resize", "top_right_corner", "bottom_left_corner", "fcf1c3c7cd4491d801f1e1c78f100000"],
    "not-allowed": ["forbidden", "crossed_circle", "no-drop", "circle", "dnd-no-drop", "03b6e0fcb3499374a867c041f52298f0"],
    "wait": ["watch"],
    "progress": [
        "left_ptr_watch", "half-busy", "00000000000000020006000e7e9ffc3f", "08e8e1c95fe2fc01f976f1e063a24ccd",
        "3ecb610c1bf2410f44200f48c40d3599",
    ],
    "help": ["question_arrow", "whats_this", "left_ptr_help", "5c6cd98b3f3ebcb1f9c7f1c204630408", "d9ce0ab605698f320427677b458ad60b"],
    "copy": ["dnd-copy", "1081e37283d90000800003c07f3ef6bf", "6407b0e94181790501fd1e167b474872", "b66166c04f8c3109214a4fbd64a50fc8"],
    "alias": ["link", "dnd-link", "3085a0e285430894940527032f8b26df", "640fb0e74195791501fd1ed57b41487f", "a2a266d0498c3104214a47bd64ab0fc8"],
}

_SHADOW = (
    '<filter id="sh" x="-30%" y="-30%" width="160%" height="170%" color-interpolation-filters="sRGB">'
    '<feGaussianBlur in="SourceAlpha" stdDeviation="0.85"/><feOffset dx="0.5" dy="1.1"/>'
    '<feComponentTransfer><feFuncA type="linear" slope="0.42"/></feComponentTransfer>'
    '<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
)


def vector_svg(pal: Palette, name: str) -> str:
    _, draw = _vector_cursors()[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{GRID}" height="{GRID}" viewBox="0 0 {GRID} {GRID}">'
        f'<defs>{_SHADOW}</defs><g filter="url(#sh)">{draw(pal)}</g></svg>'
    )


def badge_svg(pal: Palette, name: str) -> str:
    color, mark = _badges(pal)[name]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
        f'<circle cx="8" cy="8" r="6.6" fill="{color}" stroke="{pal.cursor_line}" stroke-width="1.3"/>'
        f'<g fill="none" stroke="{pal.cursor_line if color == pal.cursor_accent else "#ffffff"}" stroke-width="1.9" '
        f'stroke-linecap="round" stroke-linejoin="round">{mark}</g></svg>'
    )


# --- raster pipeline ------------------------------------------------------------
@dataclass(frozen=True)
class _Art:
    path: Path
    w: int
    h: int


# One Xcursor image: nominal size, width, height, xhot, yhot, delay ms, BGRA pixels.
Image = tuple[int, int, int, int, int, int, bytes]


def _run(cmd: list[str], what: str) -> bytes:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, timeout=120).stdout
    except FileNotFoundError as exc:
        log.error("cursors", "required tool is not installed", error=exc, tool=cmd[0], step=what)
        raise
    except subprocess.TimeoutExpired as exc:
        log.error("cursors", "image tool timed out", error=exc, tool=cmd[0], step=what)
        raise
    except subprocess.CalledProcessError as exc:
        log.error(
            "cursors", "image tool failed", error=exc, tool=cmd[0], step=what,
            stderr=exc.stderr.decode(errors="replace")[-1500:],
        )
        raise


def _make(args: list[str], out: Path, what: str) -> _Art:
    """Run an ImageMagick pipeline, write the result as PNG and return its size."""
    dims = _run(["magick", *args, "-format", "%w %h", "-write", "info:-", f"PNG32:{out}"], what)
    try:
        w, h = (int(v) for v in dims.split())
    except ValueError as exc:
        log.error("cursors", "could not read image size", error=exc, step=what, output=dims[:80].decode(errors="replace"))
        raise
    return _Art(out, w, h)


def _stylise(source: list[str], height: int, nominal: int, rim: str, out: Path, what: str, trim: bool = True) -> _Art:
    """Scale sourced art to `height` and set it on a soft drop shadow, with an
    optional outline so it stays readable on any surface."""
    k = nominal / 24
    pad = math.ceil(4 * k)
    drop = max(1, round(1.2 * k))
    args = [*source]
    if trim:
        args += ["-trim", "+repage"]
    args += ["-filter", "Lanczos", "-resize", f"x{height}", "-bordercolor", "none", "-border", str(pad)]
    args += [
        "(", "-clone", "0", "-alpha", "extract", "-blur", f"0x{fmt(0.9 * k)}", "-roll", f"+{max(1, drop // 2)}+{drop}",
        "-evaluate", "multiply", "0.45", "-background", "black", "-alpha", "shape", ")",
    ]
    if rim:
        # Blur-and-threshold grows the silhouette with antialiased edges, which
        # a morphological dilate cannot do at these sizes.
        args += [
            "(", "-clone", "0", "-alpha", "extract", "-blur", f"0x{fmt(0.85 * k)}", "-level", "0,22%",
            "-background", rim, "-alpha", "shape", ")",
        ]
    args += ["(", "-clone", "0", ")", "-delete", "0", "-background", "none", "-flatten"]
    return _make(args, out, what)


def _alpha(art: _Art) -> bytes:
    return _run(["magick", str(art.path), "-alpha", "extract", "-depth", "8", "gray:-"], "read alpha")


def _tip_top_left(art: _Art) -> tuple[int, int]:
    """The solid pixel nearest the top-left corner: the end of the blade."""
    alpha = _alpha(art)
    best = (art.w + art.h, 0, 0)
    for y in range(art.h):
        row = alpha[y * art.w : (y + 1) * art.w]
        for x in range(min(art.w, best[0] - y)):
            if row[x] > 128:
                best = (x + y, x, y)
                break
    return best[1], best[2]


def _tip_top(art: _Art) -> tuple[int, int]:
    """Middle of the topmost solid row: the fingertip of the upright glove."""
    alpha = _alpha(art)
    for y in range(art.h):
        xs = [x for x, a in enumerate(alpha[y * art.w : (y + 1) * art.w]) if a > 128]
        if xs:
            return (xs[0] + xs[-1]) // 2, y + 1
    log.warn("cursors", "art has no solid pixels; hotspot falls back to the corner", art=art.path.name)
    return 0, 0


def _compose(width: int, height: int, layers: list[tuple[_Art, int, int]], what: str) -> bytes:
    """Stack layers on a transparent canvas and return premultiplied BGRA."""
    args = ["-size", f"{width}x{height}", "xc:none"]
    for art, x, y in layers:
        args += [str(art.path), "-geometry", f"+{x}+{y}", "-composite"]
    pixels = _run(["magick", *args, "-depth", "8", "-alpha", "associate", "bgra:-"], what)
    if len(pixels) != width * height * 4:
        raise ValueError(f"{what}: expected {width * height * 4} bytes of pixels, got {len(pixels)}")
    return pixels


def _rsvg(svg: str, px: int, out: Path, what: str) -> _Art:
    source = out.with_suffix(".svg")
    source.write_text(svg, encoding="utf-8")
    _run(["rsvg-convert", "-w", str(px), "-h", str(px), "-o", str(out), str(source)], what)
    return _Art(out, px, px)


def _sprite_frames(gif: Path, tmp: Path) -> tuple[list[Path], int]:
    """Unpack an animated GIF into full frames; returns them with the frame delay in ms."""
    if not gif.is_file():
        log.error("cursors", "loading sprite is missing", path=str(gif))
        raise FileNotFoundError(gif)
    target = tmp / "sprite"
    target.mkdir()
    _run(["magick", str(gif), "-coalesce", f"PNG32:{target / 'f-%03d.png'}"], "unpack sprite")
    frames = sorted(target.glob("f-*.png"))
    ticks = _run(["magick", "identify", "-format", "%T\n", str(gif)], "read sprite timing").split()
    delay = int(ticks[0]) * 10 if ticks else 0
    if delay <= 0:
        delay = 40
        log.warn("cursors", "sprite has no frame delay; using a default", gif=gif.name, delay_ms=delay)
    return frames, delay


def _size_set(pal: Palette, nominal: int, tmp: Path, frames: list[Path], delay: int) -> dict[str, list[Image]]:
    """Every cursor at one nominal size."""
    work = tmp / str(nominal)
    work.mkdir()
    out: dict[str, list[Image]] = {}

    def single(art: _Art, hot: tuple[int, int]) -> list[Image]:
        return [(nominal, art.w, art.h, hot[0], hot[1], 0, _compose(art.w, art.h, [(art, 0, 0)], "pack"))]

    key = _stylise(
        [str(ASSETS / "reference" / pal.pointer_art)], round(nominal * KEY_SCALE), nominal,
        pal.pointer_rim, work / "key.png", "pointer art",
    )
    key_hot = _tip_top_left(key)
    out["default"] = single(key, key_hot)

    # The glove points right in the source; mirrored and turned it becomes a
    # right hand pointing up, the conventional link cursor.
    glove = _stylise(
        [str(GLOVE), "-flop", "-rotate", "90"], round(nominal * GLOVE_SCALE), nominal, "", work / "glove.png", "glove art"
    )
    out["pointer"] = single(glove, _tip_top(glove))

    # A keyblade runs corner to corner, so companions go in the empty corner
    # above the guard (badges) or just past it (the sprite) instead of on top.
    def beside(art: _Art, fx: float, fy: float) -> tuple[int, int, list[tuple[_Art, int, int]]]:
        x, y = round(key.w * fx), round(key.h * fy)
        return max(key.w, x + art.w), max(key.h, y + art.h), [(key, 0, 0), (art, x, y)]

    for name in _badges(pal):
        badge = _rsvg(badge_svg(pal, name), round(nominal * BADGE_SCALE), work / f"badge-{name}.png", "badge")
        w, h, layers = beside(badge, 0.6, 0.04)
        out[name] = [(nominal, w, h, key_hot[0], key_hot[1], 0, _compose(w, h, layers, name))]

    px = round(nominal * VECTOR_SCALE)
    for name, ((hx, hy), _) in _vector_cursors().items():
        art = _rsvg(vector_svg(pal, name), px, work / f"{name}.png", name)
        out[name] = single(art, (round(hx * px / GRID), round(hy * px / GRID)))

    wait: list[Image] = []
    progress: list[Image] = []
    for n, frame in enumerate(frames):
        big = _stylise(
            [str(frame)], round(nominal * SPRITE_SCALE), nominal, pal.sprite_rim, work / f"wait-{n:03d}.png", "sprite", trim=False
        )
        wait.append((nominal, big.w, big.h, big.w // 2, big.h // 2, delay, _compose(big.w, big.h, [(big, 0, 0)], "wait")))
        small = _stylise(
            [str(frame)], round(nominal * SIDE_SPRITE_SCALE), nominal, pal.sprite_rim, work / f"side-{n:03d}.png", "sprite",
            trim=False,
        )
        w, h, layers = beside(small, 0.86, 0.1)
        progress.append((nominal, w, h, key_hot[0], key_hot[1], delay, _compose(w, h, layers, "progress")))
    out["wait"] = wait
    out["progress"] = progress
    log.debug("cursors", "size rendered", variant=pal.key, nominal=nominal, cursors=len(out), frames=len(frames))
    return out


def xcursor_bytes(images: list[Image]) -> bytes:
    """Pack images into one Xcursor file. Frames of an animation share a nominal size."""
    header = b"Xcur" + struct.pack("<III", 16, 0x10000, len(images))
    toc = b""
    chunks = b""
    offset = 16 + 12 * len(images)
    for nominal, width, height, xhot, yhot, delay, pixels in images:
        toc += struct.pack("<III", XCURSOR_IMAGE, nominal, offset)
        chunk = struct.pack("<IIIIIIIII", 36, XCURSOR_IMAGE, nominal, 1, width, height, xhot, yhot, delay) + pixels
        chunks += chunk
        offset += len(chunk)
    return header + toc + chunks


def _index(pal: Palette) -> str:
    return f"""[Icon Theme]
Name={pal.theme_name}
Comment={pal.title} cursors
Inherits=breeze_cursors
"""


def build(out: Path, pal: Palette) -> Path:
    # Cursor themes get a tree of their own: they are installed to a different
    # place than icon themes, although both are "icon themes" on disk.
    root = out / "cursors" / pal.cursor_id
    target = root / "cursors"
    with log.timed("cursors", "build cursor theme", variant=pal.key, target=str(target)):
        legacy = out / "icons" / pal.cursor_id
        if legacy.is_dir():
            shutil.rmtree(legacy)
            log.info("cursors", "removed a cursor theme from an older layout", path=str(legacy))
        names = set(RASTER_CURSORS) | set(_vector_cursors())
        missing = set(ALIASES) - names
        if missing:
            raise KeyError(f"aliases defined for cursors that are not produced: {sorted(missing)}")
        for needed in (ASSETS / "reference" / pal.pointer_art, GLOVE):
            if not needed.is_file():
                log.error("cursors", "cursor art is missing", path=str(needed), variant=pal.key)
                raise FileNotFoundError(needed)
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="khcursor-") as tmp_name:
            tmp = Path(tmp_name)
            frames, delay = _sprite_frames(ASSETS / "loading" / pal.loading_art, tmp)
            # The work is all in subprocesses, so threads scale across cores.
            with ThreadPoolExecutor(max_workers=min(len(SIZES), os.cpu_count() or 1)) as pool:
                per_size = list(pool.map(lambda n: _size_set(pal, n, tmp, frames, delay), SIZES))
        for name in sorted(names):
            images = [image for size_set in per_size for image in size_set[name]]
            (target / name).write_bytes(xcursor_bytes(images))
            for alias in ALIASES.get(name, []):
                link = target / alias
                if link.is_symlink() or link.exists():
                    link.unlink()
                os.symlink(name, link)
            log.debug("cursors", "cursor written", variant=pal.key, cursor=name, images=len(images))
        write_text(root / "index.theme", _index(pal))
        log.info(
            "cursors", "cursor theme written", variant=pal.key, cursors=len(names), sizes=SIZES,
            sprite_frames=len(frames), frame_ms=delay,
        )
    return target
