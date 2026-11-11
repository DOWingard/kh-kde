#!/usr/bin/env python3
"""Render the built theme pieces to PNGs without touching the live desktop.

The Plasma Style is drawn through KSvg (the library Plasma itself uses), so
slice bounds, margins and shadows are checked exactly as the shell would see
them. The window decoration, splash and login screens are loaded as QML against
stand-ins for the objects KWin and SDDM provide. Cursors are read back from the
packed cursor files; widgets are drawn by the real Kvantum engine with the built theme.
The keyblade menu is the built plugin, loaded by id the way the Plasma shell loads it.

    ./tools/preview.py                 # everything, both variants
    ./tools/preview.py --only splash   # plasmastyle | decoration | splash | sddm | cursors | widgets | keyblades

Images land in CONTEXT/tmp/previews/. Requires PyQt6 and a prior ./build.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cursorsheet  # noqa: E402
import tempfile  # noqa: E402
import widgetgallery  # noqa: E402
from khtheme import kvantum, log, picker, wallpapers  # noqa: E402
from khtheme.colorscheme import scheme_id  # noqa: E402
from khtheme.palette import VARIANTS, Palette  # noqa: E402

SCENES = Path(__file__).resolve().parent / "preview"
DIST = ROOT / "dist"
OUT = ROOT / "CONTEXT" / "tmp" / "previews"


def scene_props(scene: str, pal: Palette) -> dict:
    from PyQt6.QtCore import QUrl

    if scene == "plasmastyle":
        return {
            "base": str(DIST / "plasma" / "desktoptheme" / pal.theme_id),
            "dark": pal.dark,
            "textColor": pal.text,
            "wallpaper": QUrl.fromLocalFile(str(wallpapers.default_image(DIST, pal))),
        }
    if scene == "decoration":
        main = DIST / "kwin" / "decorations" / pal.decoration_id / "contents" / "ui" / "main.qml"
        return {
            "theme": QUrl.fromLocalFile(str(main)),
            "wallpaper": QUrl.fromLocalFile(str(wallpapers.default_image(DIST, pal))),
            "bodyColor": pal.window,
            "bodyText": pal.text,
        }
    if scene == "splash":
        splash = DIST / "plasma" / "look-and-feel" / pal.theme_id / "contents" / "splash" / "Splash.qml"
        return {"splash": splash.as_uri()}
    if scene == "sddm":
        return {"main": (DIST / "sddm" / f"KingdomHearts-{pal.key}" / "Main.qml").as_uri(), "variantName": pal.key, "fail": False}
    raise KeyError(scene)


SETTLE_MS = {"plasmastyle": 900, "decoration": 900, "splash": 2600, "sddm": 1600}


def render_cursors(pal: Palette) -> bool:
    return cursorsheet.render(DIST, pal, OUT / f"cursors-{pal.key}.png", nominal=32)


def render_widgets(pal: Palette) -> bool:
    scheme = DIST / "color-schemes" / f"{scheme_id(pal)}.colors"
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "widgetgallery.py"), str(scheme),
             str(OUT / f"widgets-{pal.key}.png"), "--kvantum", str(DIST / "Kvantum" / kvantum.THEME),
             "--style", kvantum.style_key(pal)],
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        log.error("preview", "widget gallery timed out", error=exc, variant=pal.key)
        return False
    return result.returncode == 0


def render_keyblades(pal: Palette) -> bool:
    """The Keyblade Browser menu as the desktop would show it, offering the
    keyblades of the built cursor theme."""
    tool = picker.preview_tool(DIST)
    if not tool.is_file():
        log.error("preview", "keyblade browser not built; run ./build.py --only picker", expected=str(tool))
        return False
    scheme = DIST / "color-schemes" / f"{scheme_id(pal)}.colors"
    target = OUT / f"keyblades-{pal.key}.png"
    with tempfile.TemporaryDirectory(prefix="khpicker-") as config:
        env = dict(os.environ)
        env.update(widgetgallery.styled_environment(Path(config), scheme, kvantum.style_key(pal), DIST / "Kvantum" / kvantum.THEME))
        env["QT_PLUGIN_PATH"] = str(picker.plugin_root(DIST))
        env["KH_CURSOR_DIRS"] = str(DIST / "cursors")
        try:
            result = subprocess.run([str(tool), str(target)], env=env, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            log.error("preview", "keyblade menu timed out", error=exc, variant=pal.key)
            return False
    if result.returncode != 0:
        log.error("preview", "keyblade menu failed", variant=pal.key, stderr=result.stderr[-1500:])
        return False
    try:
        summary = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        log.error("preview", "keyblade menu summary unreadable", error=exc, variant=pal.key, output=result.stdout[-300:])
        return False
    buttons = summary.get("buttons", [])
    unnamed = [b["slug"] for b in buttons if not b.get("tooltip")]
    log.info("preview", "rendered", scene=f"keyblades-{pal.key}", target=str(target), style=summary.get("style"),
             entries=summary.get("entries"), keyblades=len(buttons), caption=summary.get("caption"),
             checked=[b["slug"] for b in buttons if b.get("checked")], without_name=unnamed)
    return bool(buttons) and not unnamed


# Scenes that are not QML: name -> renderer(pal) -> success.
STATIC = {"cursors": render_cursors, "widgets": render_widgets, "keyblades": render_keyblades}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", choices=sorted([*SETTLE_MS, *STATIC]), help="render only these scenes")
    args = parser.parse_args()
    scenes = args.only or [*SETTLE_MS, *STATIC]

    if not DIST.is_dir():
        log.error("preview", "dist/ not found; run ./build.py first", dist=str(DIST))
        return 2
    # Render into memory instead of opening windows on the desktop.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtCore import QTimer, QUrl
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtQuick import QQuickView
    except ImportError as exc:
        log.error("preview", "PyQt6 is required for previews", error=exc)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for scene in scenes:
        if scene in STATIC:
            for pal in VARIANTS:
                if not STATIC[scene](pal):
                    failures.append(f"{scene}-{pal.key}")
    jobs = [(scene, pal) for scene in scenes if scene in SETTLE_MS for pal in VARIANTS]
    app = QGuiApplication(sys.argv[:1])
    views = []  # keep views alive until the event loop ends

    def run_next() -> None:
        if not jobs:
            app.quit()
            return
        scene, pal = jobs.pop(0)
        name = f"{scene}-{pal.key}"
        view = QQuickView()
        views.append(view)
        # Stand-ins for the QML modules that only exist inside KWin.
        view.engine().addImportPath(str(SCENES / "mock"))
        view.setInitialProperties(scene_props(scene, pal))
        view.setSource(QUrl.fromLocalFile(str(SCENES / f"{scene}.qml")))
        if view.status() != QQuickView.Status.Ready:
            failures.append(name)
            log.error("preview", "scene failed to load", scene=name, errors=[e.toString() for e in view.errors()])
            QTimer.singleShot(0, run_next)
            return
        view.show()

        def grab() -> None:
            target = OUT / f"{name}.png"
            image = view.grabWindow()
            if image.isNull() or not image.save(str(target)):
                failures.append(name)
                log.error("preview", "could not save render", scene=name, target=str(target))
            else:
                log.info("preview", "rendered", scene=name, target=str(target), size=f"{image.width()}x{image.height()}")
            view.close()
            run_next()

        QTimer.singleShot(SETTLE_MS[scene], grab)

    QTimer.singleShot(0, run_next)
    app.exec()
    if failures:
        log.error("preview", "some previews failed", failed=failures)
        return 1
    log.info("preview", "previews written", directory=str(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
