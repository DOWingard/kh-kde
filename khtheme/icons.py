"""Icon theme: the variant's emblem art as the application-launcher icon.

Everything else is inherited from Breeze, whose folder and symbolic icons are
recoloured from the active colour scheme and so already match the palette.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import log
from .palette import Palette
from .svg import write_text

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Icon names the launcher (and distributions' menus) look up.
LAUNCHER_NAMES = [
    "start-here",
    "start-here-symbolic",
    "start-here-kde",
    "start-here-kde-symbolic",
    "start-here-kde-plasma",
    "start-here-kde-plasma-symbolic",
]

SIZES = [16, 22, 24, 32, 48, 64, 96, 128, 256]
MARGIN = 0.04  # clear space round the emblem, as a fraction of the icon edge


def emblem_png(pal: Palette, size: int, target: Path) -> None:
    """The variant's launcher emblem, centred on a transparent square."""
    source = ASSETS / "reference" / pal.launcher_art
    if not source.is_file():
        log.error("icons", "launcher art is missing", path=str(source), variant=pal.key)
        raise FileNotFoundError(source)
    inner = max(1, round(size * (1 - 2 * MARGIN)))
    cmd = ["magick", str(source), "-trim", "+repage"]
    if pal.launcher_flat:
        cmd += ["-fill", pal.launcher_flat, "-colorize", "100"]
    cmd += ["-filter", "Lanczos", "-resize", f"{inner}x{inner}"]
    if size <= 32:
        # Thin strokes go soft when reduced this far; restore their edge.
        cmd += ["-unsharp", "0x0.6+0.7+0.02"]
    cmd += ["-background", "none", "-gravity", "center", "-extent", f"{size}x{size}", f"PNG32:{target}"]
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except FileNotFoundError as exc:
        log.error("icons", "ImageMagick is not installed", error=exc)
        raise
    except subprocess.TimeoutExpired as exc:
        log.error("icons", "ImageMagick timed out", error=exc, source=source.name, size=size)
        raise
    except subprocess.CalledProcessError as exc:
        log.error(
            "icons", "ImageMagick failed", error=exc, source=source.name, size=size,
            stderr=exc.stderr.decode(errors="replace")[-1500:],
        )
        raise


def _index(pal: Palette) -> str:
    dirs = ",".join(f"places/{size}" for size in SIZES)
    sections = []
    for n, size in enumerate(SIZES):
        if size == SIZES[-1]:
            sections.append(
                f"[places/{size}]\nSize={size}\nMinSize={SIZES[n - 1] + 1}\nMaxSize=1024\nContext=Places\nType=Scalable\n"
            )
        else:
            sections.append(f"[places/{size}]\nSize={size}\nContext=Places\nType=Fixed\n")
    return (
        f"[Icon Theme]\nName={pal.theme_name}\nComment={pal.title} emblem launcher on top of Breeze\n"
        f"Inherits={pal.base_icons},hicolor\nExample=start-here-kde\nFollowsColorScheme=true\nDirectories={dirs}\n\n"
        + "\n".join(sections)
    )


def build(out: Path, pal: Palette) -> Path:
    root = out / "icons" / pal.theme_id
    with log.timed("icons", "build icon theme", variant=pal.key, target=str(root)):
        write_text(root / "index.theme", _index(pal))
        # Earlier builds shipped the emblem as SVG; a stale one would win the lookup.
        stale = root / "places" / "scalable"
        if stale.is_dir():
            for path in stale.iterdir():
                path.unlink()
            stale.rmdir()
            log.info("icons", "removed icons from an older layout", path=str(stale))
        for size in SIZES:
            first = root / "places" / str(size) / f"{LAUNCHER_NAMES[0]}.png"
            emblem_png(pal, size, first)
            data = first.read_bytes()
            for name in LAUNCHER_NAMES[1:]:
                (first.parent / f"{name}.png").write_bytes(data)
        log.info(
            "icons", "icon theme written", variant=pal.key, icons=len(LAUNCHER_NAMES), sizes=SIZES,
            source=pal.launcher_art, inherits=pal.base_icons,
        )
    return root
