"""The menu and title fonts, staged for installation as user fonts.

The decoration, splash and login screens load their own copies, so they do not
depend on this; installing the fonts makes them selectable for the rest of the
desktop (window titles of other themes, terminal, documents).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import log
from .palette import Palette

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FAMILY_DIR = "KingdomHearts"
_built = False


def build(out: Path, pal: Palette) -> Path:
    global _built
    root = out / "fonts" / FAMILY_DIR
    if _built:
        log.debug("fonts", "fonts already staged in this run", variant=pal.key)
        return root
    with log.timed("fonts", "stage fonts", target=str(root)):
        fonts = sorted(ASSETS.glob("*.otf"))
        if not fonts:
            log.error("fonts", "no fonts found", path=str(ASSETS))
            raise FileNotFoundError(ASSETS)
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        for font in fonts:
            shutil.copyfile(font, root / font.name)
        log.info("fonts", "fonts staged", files=[f.name for f in fonts])
    _built = True
    return root
