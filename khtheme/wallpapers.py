"""Wallpaper packages built from the sourced artwork in assets/wallpapers.

Every picture becomes its own package, so all of them show up in the wallpaper
chooser. One more package, the combined one, carries each variant's default
picture as its light and dark image; Plasma swaps between them with the colour
scheme, so the desktop follows a light/dark switch on its own.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import log
from .palette import ORG_XIII, SORA, Palette
from .svg import write_text

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "wallpapers"
SIZES = [(3840, 2160), (2560, 1440), (1920, 1080)]
COMBINED_ID = "KingdomHearts"
QUALITY = 92


@dataclass(frozen=True)
class Wallpaper:
    slug: str  # file stem under assets/wallpapers
    title: str
    variant: str  # palette key this picture belongs to
    default: bool = False  # the variant's desktop, lock-screen and login picture

    @property
    def package_id(self) -> str:
        return f"{COMBINED_ID}-{self.slug}"


WALLPAPERS = (
    Wallpaper("dive-to-the-heart", "Kingdom Hearts — Dive to the Heart", ORG_XIII.key, default=True),
    Wallpaper("roxas-black-coat", "Kingdom Hearts — Roxas in the Black Coat", ORG_XIII.key),
    Wallpaper("heart-moon", "Kingdom Hearts — The Heart-Shaped Moon", ORG_XIII.key),
    Wallpaper("black-coat", "Kingdom Hearts — Black Coat at Dawn", ORG_XIII.key),
    Wallpaper("roxas-rain", "Kingdom Hearts — Roxas in the Rain", ORG_XIII.key),
    Wallpaper("menu-pattern", "Kingdom Hearts — Menu Pattern", ORG_XIII.key),
    Wallpaper("final-mix-trio", "Kingdom Hearts — Sora, Donald and Goofy", SORA.key, default=True),
    Wallpaper("destiny-islands", "Kingdom Hearts — Destiny Islands", SORA.key),
    Wallpaper("final-world", "Kingdom Hearts — The Final World", SORA.key),
    Wallpaper("sora-islands", "Kingdom Hearts — Sora on the Islands", SORA.key),
)


def default_for(pal: Palette) -> Wallpaper:
    for wallpaper in WALLPAPERS:
        if wallpaper.variant == pal.key and wallpaper.default:
            return wallpaper
    raise LookupError(f"no default wallpaper is declared for variant {pal.key}")


def default_image(out: Path, pal: Palette, size: tuple[int, int] = (1920, 1080)) -> Path:
    """Path of the variant's default picture at `size`, as written by build()."""
    path = out / "wallpapers" / default_for(pal).package_id / "contents" / "images" / f"{size[0]}x{size[1]}.jpg"
    if not path.is_file():
        log.error("wallpapers", "default wallpaper is not built; run the 'wallpapers' component first", path=str(path))
        raise FileNotFoundError(path)
    return path


def _source_size(source: Path) -> tuple[int, int]:
    try:
        result = subprocess.run(
            ["magick", "identify", "-format", "%w %h", str(source)], check=True, capture_output=True, timeout=60
        )
        w, h = (int(v) for v in result.stdout.split())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
        log.error("wallpapers", "could not read picture size", error=exc, source=source.name)
        raise
    return w, h


def _scale(source: Path, target: Path, width: int, height: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "magick", str(source), "-filter", "Lanczos", "-resize", f"{width}x{height}^", "-gravity", "center",
        "-extent", f"{width}x{height}", "-strip", "-quality", str(QUALITY), str(target),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        log.error("wallpapers", "ImageMagick timed out", error=exc, source=source.name, size=f"{width}x{height}")
        raise
    except subprocess.CalledProcessError as exc:
        log.error(
            "wallpapers", "ImageMagick failed", error=exc, source=source.name,
            stderr=exc.stderr.decode(errors="replace")[-1500:],
        )
        raise


def _metadata(root: Path, package_id: str, name: str) -> None:
    meta = {"KPlugin": {"Id": package_id, "Name": name, "License": "Fan project; artwork © Disney / Square Enix"}}
    write_text(root / "metadata.json", json.dumps(meta, indent=2, ensure_ascii=False) + "\n")


def _build_one(out: Path, wallpaper: Wallpaper) -> Path:
    source = ASSETS / f"{wallpaper.slug}.jpg"
    if not source.is_file():
        log.error("wallpapers", "wallpaper artwork is missing", path=str(source))
        raise FileNotFoundError(source)
    root = out / "wallpapers" / wallpaper.package_id
    if root.exists():
        shutil.rmtree(root)
    width, height = _source_size(source)
    # Never enlarge: a size above the artwork's own adds bytes, not detail.
    # The smallest size is always written so every package has a picture.
    sizes = [s for s in SIZES if s[0] <= width and s[1] <= height]
    if not sizes:
        sizes = [SIZES[-1]]
        log.warn("wallpapers", "artwork is smaller than the smallest size and is enlarged to fit; it will look soft",
                 wallpaper=wallpaper.slug, source=f"{width}x{height}", written=f"{sizes[0][0]}x{sizes[0][1]}")
    elif len(sizes) < len(SIZES):
        log.info("wallpapers", "artwork is smaller than the largest size; skipping upscales",
                 wallpaper=wallpaper.slug, source=f"{width}x{height}", written=[f"{w}x{h}" for w, h in sizes])
    for w, h in sizes:
        _scale(source, root / "contents" / "images" / f"{w}x{h}.jpg", w, h)
    shutil.copyfile(root / "contents" / "images" / f"{sizes[-1][0]}x{sizes[-1][1]}.jpg", root / "contents" / "screenshot.jpg")
    _metadata(root, wallpaper.package_id, wallpaper.title)
    return root


def _build_combined(out: Path) -> None:
    root = out / "wallpapers" / COMBINED_ID
    if root.exists():
        shutil.rmtree(root)
    for pal, sub in ((SORA, "images"), (ORG_XIII, "images_dark")):
        source = out / "wallpapers" / default_for(pal).package_id / "contents" / "images"
        if not source.is_dir():
            log.info("wallpapers", "combined package waits for a default picture that is not built yet", variant=pal.key)
            continue
        shutil.copytree(source, root / "contents" / sub)
    light = root / "contents" / "images" / "1920x1080.jpg"
    if light.is_file():
        shutil.copyfile(light, root / "contents" / "screenshot.jpg")
    _metadata(root, COMBINED_ID, "Kingdom Hearts")


def _remove_legacy(out: Path, pal: Palette) -> None:
    """Earlier builds wrote one generated picture per variant under the theme id."""
    legacy = out / "wallpapers" / pal.theme_id
    if legacy.is_dir():
        shutil.rmtree(legacy)
        log.info("wallpapers", "removed a wallpaper package from an older layout", path=str(legacy))


def build(out: Path, pal: Palette) -> Path:
    mine = [w for w in WALLPAPERS if w.variant == pal.key]
    with log.timed("wallpapers", "build wallpapers", variant=pal.key, count=len(mine)):
        _remove_legacy(out, pal)
        for wallpaper in mine:
            _build_one(out, wallpaper)
            log.debug("wallpapers", "package written", wallpaper=wallpaper.slug)
        _build_combined(out)
        log.info("wallpapers", "wallpaper packages written", variant=pal.key, packages=[w.package_id for w in mine])
    return out / "wallpapers" / default_for(pal).package_id
