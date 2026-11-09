#!/usr/bin/env python3
"""Generate every theme asset for both variants into dist/.

Usage:
    ./build.py                 # build everything
    ./build.py --only plasmastyle decoration
    ./build.py --variant OrgXIII
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys
from pathlib import Path

from khtheme import log
from khtheme.palette import VARIANTS

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# Build order matters only where one component embeds another's output
# (the global theme previews use the wallpapers).
COMPONENTS = [
    "colorscheme",
    "plasmastyle",
    "decoration",
    "wallpapers",
    "icons",
    "cursors",
    "konsole",
    "fonts",
    "sounds",
    "lookandfeel",
    "sddm",
]

REQUIRED_TOOLS = {
    "decoration": ["rsvg-convert", "magick"],
    "wallpapers": ["magick"],
    "icons": ["magick"],
    "cursors": ["rsvg-convert", "magick"],
    "sounds": ["ffmpeg"],
    "lookandfeel": ["magick"],
    "sddm": ["magick"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", choices=COMPONENTS, help="build only these components")
    parser.add_argument("--variant", choices=[p.key for p in VARIANTS], help="build a single variant")
    parser.add_argument("--clean", action="store_true", help="remove dist/ first")
    args = parser.parse_args()

    selected = args.only or COMPONENTS
    variants = [p for p in VARIANTS if args.variant in (None, p.key)]

    missing = sorted({t for c in selected for t in REQUIRED_TOOLS.get(c, []) if shutil.which(t) is None})
    if missing:
        log.error("build", "required external tools are missing", tools=missing)
        return 2

    if args.clean and DIST.exists():
        shutil.rmtree(DIST)
        log.info("build", "removed previous output", path=str(DIST))

    log.info("build", "build started", components=selected, variants=[p.key for p in variants], out=str(DIST))
    failures = []
    for name in selected:
        try:
            module = importlib.import_module(f"khtheme.{name}")
        except ModuleNotFoundError as exc:
            log.error("build", "component module missing", error=exc, component=name)
            failures.append(name)
            continue
        for pal in variants:
            try:
                module.build(DIST, pal)
            except Exception as exc:  # keep going so one broken component doesn't hide others
                log.error("build", "component failed", error=exc, component=name, variant=pal.key)
                failures.append(f"{name}:{pal.key}")

    if failures:
        log.error("build", "build finished with failures", failed=failures)
        return 1
    log.info("build", "build finished", out=str(DIST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
