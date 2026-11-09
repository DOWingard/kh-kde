"""Contact sheet of a built cursor theme, read back from the Xcursor files.

Each cursor is shown on the variant's own surface colour and on the opposite
one, enlarged without smoothing, with its hotspot marked. Reading the packed
files (instead of the intermediate images) checks the writer as well.
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
from pathlib import Path

from khtheme import log
from khtheme.cursors import RASTER_CURSORS, _vector_cursors
from khtheme.palette import Palette

XCURSOR_IMAGE = 0xFFFD0002
ZOOM = 3
CELL = 150  # unscaled cell edge; fits the largest image at the sheet's nominal size
MARK = "#ff00ff"


def read_xcursor(path: Path) -> list[tuple[int, int, int, int, int, int, bytes]]:
    """Parse an Xcursor file into (nominal, w, h, xhot, yhot, delay, BGRA) tuples."""
    data = path.read_bytes()
    if data[:4] != b"Xcur":
        raise ValueError(f"{path.name}: not an Xcursor file")
    _, _, count = struct.unpack_from("<III", data, 4)
    images = []
    for n in range(count):
        kind, nominal, offset = struct.unpack_from("<III", data, 16 + 12 * n)
        if kind != XCURSOR_IMAGE:
            continue
        _, _, _, _, w, h, xhot, yhot, delay = struct.unpack_from("<IIIIIIIII", data, offset)
        pixels = data[offset + 36 : offset + 36 + w * h * 4]
        if len(pixels) != w * h * 4:
            raise ValueError(f"{path.name}: image {n} is truncated")
        if not (xhot < w and yhot < h):
            raise ValueError(f"{path.name}: hotspot {xhot},{yhot} lies outside the {w}x{h} image")
        images.append((nominal, w, h, xhot, yhot, delay, pixels))
    return images


def render(dist: Path, pal: Palette, target: Path, nominal: int = 48) -> bool:
    cursors = dist / "icons" / pal.cursor_id / "cursors"
    if not cursors.is_dir():
        log.error("cursorsheet", "cursor theme is not built", path=str(cursors))
        return False
    names = RASTER_CURSORS + sorted(_vector_cursors())
    other = "#f1f8fc" if pal.dark else "#0b0b0c"
    cells: list[str] = []
    with tempfile.TemporaryDirectory(prefix="khsheet-") as tmp_name:
        tmp = Path(tmp_name)
        for name in names:
            try:
                images = [im for im in read_xcursor(cursors / name) if im[0] == nominal]
            except (OSError, ValueError, struct.error) as exc:
                log.error("cursorsheet", "cursor file is unreadable", error=exc, cursor=name)
                return False
            if not images:
                log.error("cursorsheet", "cursor has no image at the sheet size", cursor=name, nominal=nominal)
                return False
            # Animated cursors: four frames spread over the loop.
            picks = images if len(images) == 1 else [images[i * len(images) // 4] for i in range(4)]
            for n, (_, w, h, xhot, yhot, _, pixels) in enumerate(picks):
                raw = tmp / f"{name}-{n}.bgra"
                raw.write_bytes(pixels)
                for side, bg in (("own", pal.window), ("other", other)):
                    cell = tmp / f"{name}-{n}-{side}.png"
                    subprocess.run(
                        [
                            "magick", "-size", f"{CELL}x{CELL}", f"xc:{bg}",
                            "(", "-size", f"{w}x{h}", "-depth", "8", f"bgra:{raw}", "-alpha", "disassociate", ")",
                            "-geometry", "+8+8", "-composite",
                            "-fill", MARK, "-draw", f"point {8 + xhot},{8 + yhot}",
                            "-filter", "point", "-resize", f"{ZOOM * 100}%", str(cell),
                        ],
                        check=True, capture_output=True, timeout=60,
                    )
                    cells.append(str(cell))
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["magick", "montage", *cells, "-tile", "8x", "-geometry", "+2+2", "-background", "#808080", str(target)],
                check=True, capture_output=True, timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log.error("cursorsheet", "could not assemble the sheet", error=exc, target=str(target))
            return False
    log.info("cursorsheet", "sheet written", variant=pal.key, target=str(target), cursors=len(names), nominal=nominal)
    return True
