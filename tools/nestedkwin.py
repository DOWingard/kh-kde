#!/usr/bin/env python3
"""Run the built window decoration under a real, private KWin and photograph it.

    ./tools/nestedkwin.py                  # both variants
    ./tools/nestedkwin.py --variant Sora

A headless KWin is started on its own D-Bus session with a throw-away
configuration and data directory, so neither the running desktop nor the
installed themes are touched. Two test windows are opened in it and its
(virtual) screen is saved to CONTEXT/tmp/previews/kwin-<variant>.png.

Unlike tools/preview.py, which draws the decoration against stand-ins, this
exercises KWin's own decoration engine, so it catches API mistakes.
Requires kwin_wayland, dbus-run-session, spectacle and PyQt6.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from khtheme import log  # noqa: E402
from khtheme.palette import VARIANTS, Palette  # noqa: E402

DIST = ROOT / "dist"
OUT = ROOT / "CONTEXT" / "tmp" / "previews"
SIZE = (1280, 720)
TOOLS = ["kwin_wayland", "dbus-run-session", "spectacle"]

CLIENT = """import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

app = QApplication(sys.argv)
windows = []
for title in ("Dive to the Heart", "Journal"):
    window = QWidget()
    window.setWindowTitle(title)
    QVBoxLayout(window).addWidget(QLabel(title))
    window.resize(500, 260)
    window.show()
    windows.append(window)
QTimer.singleShot(9000, app.quit)
app.exec()
"""

SESSION = """#!/bin/sh
export QT_QPA_PLATFORM=wayland
"{python}" "{client}" >"{work}/client.log" 2>&1 &
sleep 5
spectacle -b -n -f -o "{work}/shot.png" >"{work}/spectacle.log" 2>&1
sleep 1
"""


def png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    return struct.unpack(">II", head[16:24])


def check(pal: Palette) -> bool:
    package = DIST / "kwin" / "decorations" / pal.decoration_id
    if not package.is_dir():
        log.error("nestedkwin", "decoration is not built; run ./build.py first", path=str(package))
        return False
    with tempfile.TemporaryDirectory(prefix="khkwin-") as tmp_name:
        work = Path(tmp_name)
        (work / "config").mkdir()
        shutil.copytree(package, work / "data" / "kwin" / "decorations" / pal.decoration_id)
        (work / "config" / "kwinrc").write_text(
            f"[org.kde.kdecoration2]\nlibrary=org.kde.kwin.aurorae\ntheme={pal.decoration_id}\n", encoding="utf-8"
        )
        client = work / "client.py"
        client.write_text(CLIENT, encoding="utf-8")
        session = work / "session.sh"
        session.write_text(SESSION.format(python=sys.executable, client=client, work=work), encoding="utf-8")
        session.chmod(0o755)

        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY")}
        env.update(
            XDG_CONFIG_HOME=str(work / "config"),
            XDG_DATA_HOME=str(work / "data"),
            XDG_CACHE_HOME=str(work / "cache"),
            # Lets the screenshot tool of this private session capture its screen.
            KWIN_WAYLAND_NO_PERMISSION_CHECKS="1",
        )
        cmd = [
            "dbus-run-session", "--", "kwin_wayland", "--virtual", "--width", str(SIZE[0]), "--height", str(SIZE[1]),
            "--socket", f"wayland-khcheck-{os.getpid()}", "--no-lockscreen", "--no-global-shortcuts", "--no-kactivities",
            "--exit-with-session", str(session),
        ]
        with log.timed("nestedkwin", "run nested window manager", variant=pal.key):
            try:
                result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired as exc:
                log.error("nestedkwin", "nested window manager did not exit", error=exc, variant=pal.key)
                return False
        notes = [ln for ln in result.stderr.splitlines() if ".qml" in ln or "aurorae" in ln.lower()]
        if notes:
            log.warn("nestedkwin", "the decoration engine reported problems", variant=pal.key, lines=notes[:12])
        shot = work / "shot.png"
        if not shot.is_file():
            log.error("nestedkwin", "no screenshot was produced", variant=pal.key, exit_code=result.returncode,
                      stderr=result.stderr[-800:])
            return False
        try:
            size = png_size(shot)
        except (OSError, ValueError, struct.error) as exc:
            log.error("nestedkwin", "screenshot is unreadable", error=exc, variant=pal.key)
            return False
        if size != SIZE:
            # Anything else would be a picture of some other screen; do not keep it.
            log.error("nestedkwin", "screenshot is not of the nested screen; discarded", variant=pal.key, size=size)
            return False
        OUT.mkdir(parents=True, exist_ok=True)
        target = OUT / f"kwin-{pal.key}.png"
        shutil.copyfile(shot, target)
        log.info("nestedkwin", "decoration rendered by KWin", variant=pal.key, target=str(target), engine_notes=len(notes))
    return not notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", choices=[p.key for p in VARIANTS], help="check a single variant")
    args = parser.parse_args()
    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    if missing:
        log.error("nestedkwin", "required tools are missing", tools=missing)
        return 2
    try:
        import PyQt6.QtWidgets  # noqa: F401
    except ImportError as exc:
        log.error("nestedkwin", "PyQt6 is required for the test windows", error=exc)
        return 2
    failed = [pal.key for pal in VARIANTS if args.variant in (None, pal.key) and not check(pal)]
    if failed:
        log.error("nestedkwin", "check failed", variants=failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
