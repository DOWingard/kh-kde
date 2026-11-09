#!/usr/bin/env python3
"""Refresh the README's screenshots in docs/screenshots/ from the renders.

    ./tools/preview.py && ./tools/nestedplasma.py && ./tools/screenshots.py

Takes the renders the two tools wrote to CONTEXT/tmp/previews/. Pictures
that are mostly artwork (desktop, login screen) are stored as JPEG, the
rest as PNG. Nothing is written unless every render is present, so the
gallery never mixes pictures of two different builds with a gap.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from khtheme import log  # noqa: E402
from khtheme.palette import VARIANTS  # noqa: E402

PREVIEWS = ROOT / "CONTEXT" / "tmp" / "previews"
OUT = ROOT / "docs" / "screenshots"
# render name prefix -> stored format
SHOTS = {"desktop": "jpg", "sddm": "jpg", "splash": "png", "widgets": "png"}
JPEG_QUALITY = "88"


def main() -> int:
    wanted = [(PREVIEWS / f"{name}-{pal.key}.png", OUT / f"{name}-{pal.key}.{fmt}")
              for name, fmt in SHOTS.items() for pal in VARIANTS]
    missing = [str(source) for source, _ in wanted if not source.is_file()]
    if missing:
        log.error("screenshots", "renders missing; run tools/preview.py and tools/nestedplasma.py first",
                  missing=missing)
        return 2
    if shutil.which("magick") is None:
        log.error("screenshots", "ImageMagick (magick) is required to write JPEG")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    for source, target in wanted:
        if target.suffix == ".png":
            shutil.copyfile(source, target)
        else:
            cmd = ["magick", str(source), "-strip", "-quality", JPEG_QUALITY, str(target)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                log.error("screenshots", "conversion failed", source=str(source), stderr=result.stderr.strip()[-600:])
                return 1
        log.info("screenshots", "written", target=str(target.relative_to(ROOT)),
                 size_kb=round(target.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
