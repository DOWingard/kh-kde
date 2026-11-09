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

It also checks where the frame would resize: each test window reports the
title-bar rectangle KWin holds for it, and every point of the top bar outside
the thin strip along the window edge has to count as title bar. A title bar
that KWin places wrongly makes the whole bar, buttons included, show the
resize cursor.

Last, it checks which title-bar buttons are drawn. The session asks for the
help and "on all desktops" buttons, which can do nothing for a Wayland window
on a single desktop, so neither may appear; after a second desktop is added,
"on all desktops" has to come back.
Requires kwin_wayland, dbus-run-session, spectacle and PyQt6.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from khtheme import decoration, log  # noqa: E402
from khtheme.palette import VARIANTS, Palette  # noqa: E402

DIST = ROOT / "dist"
OUT = ROOT / "CONTEXT" / "tmp" / "previews"
SIZE = (1280, 720)
TOOLS = ["kwin_wayland", "dbus-run-session", "spectacle", "qdbus6"]

CLIENT = """import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

app = QApplication(sys.argv)
windows = []
# The maximised window goes first so the two floating ones stay visible above it.
for title, maximised in (("World Map", True), ("Dive to the Heart", False), ("Journal", False)):
    window = QWidget()
    window.setWindowTitle(title)
    QVBoxLayout(window).addWidget(QLabel(title))
    window.resize(500, 260)
    if maximised:
        window.showMaximized()
    else:
        window.show()
    windows.append(window)
QTimer.singleShot(12000, app.quit)
app.exec()
"""
WINDOWS = 3

# Appended to the copy of the decoration under test (never to the built one):
# reports the geometry KWin ended up with once the window has settled, and the
# buttons drawn, once before and once after the session adds a second desktop.
PROBE_TAG = "KHPROBE "
PROBE = """
    function khProbeButtons(types) {
        const names = {};
        names[DecorationOptions.DecorationButtonMenu] = "menu";
        names[DecorationOptions.DecorationButtonApplicationMenu] = "appmenu";
        names[DecorationOptions.DecorationButtonOnAllDesktops] = "alldesktops";
        names[DecorationOptions.DecorationButtonQuickHelp] = "help";
        names[DecorationOptions.DecorationButtonMinimize] = "minimize";
        names[DecorationOptions.DecorationButtonMaximizeRestore] = "maximize";
        names[DecorationOptions.DecorationButtonKeepAbove] = "keepabove";
        names[DecorationOptions.DecorationButtonKeepBelow] = "keepbelow";
        names[DecorationOptions.DecorationButtonShade] = "shade";
        names[DecorationOptions.DecorationButtonClose] = "close";
        names[DecorationOptions.DecorationButtonExplicitSpacer] = "spacer";
        return types.map(t => names[t] || ("type" + t));
    }
    property int khProbeRound: 0
    Timer {
        interval: %d
        running: true
        repeat: true
        onTriggered: {
            root.khProbeRound += 1;
            if (root.khProbeRound >= 2) {
                stop();
            }
            console.warn("%s" + JSON.stringify({
                "round": root.khProbeRound,
                "caption": decoration.client.caption,
                "maximized": decoration.client.maximized,
                "clientWidth": decoration.client.width,
                "titleBar": [decoration.titleBar.x, decoration.titleBar.y, decoration.titleBar.width, decoration.titleBar.height],
                "borders": [decoration.borderLeft, decoration.borderTop, decoration.borderRight, decoration.borderBottom],
                "grips": [decoration.resizeOnlyBorderLeft, decoration.resizeOnlyBorderTop,
                          decoration.resizeOnlyBorderRight, decoration.resizeOnlyBorderBottom],
                "left": root.khProbeButtons(leftButtons.shown()),
                "right": root.khProbeButtons(rightButtons.shown())
            }));
        }
    }
"""
# Rounds of the probe are this far apart; the session adds the second desktop
# between them.
PROBE_INTERVAL_MS = 4000
PROBE = PROBE % (PROBE_INTERVAL_MS, PROBE_TAG)

# Buttons the session asks for: KDE's default layout, which includes the two
# that only sometimes have a function.
LAYOUT = ("MS", "HIAX")
ALWAYS = {"left": ["menu"], "right": ["minimize", "maximize", "close"]}

SESSION = """#!/bin/sh
export QT_QPA_PLATFORM=wayland
"{python}" "{client}" >"{work}/client.log" 2>&1 &
sleep 5
spectacle -b -n -f -o "{work}/shot.png" >"{work}/spectacle.log" 2>&1
sleep 1
qdbus6 org.kde.KWin /VirtualDesktopManager org.kde.KWin.VirtualDesktopManager.createDesktop 1 "Second" \\
    >"{work}/desktop.log" 2>&1
sleep 6
"""


def png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    return struct.unpack(">II", head[16:24])


def add_probe(main_qml: Path) -> None:
    text = main_qml.read_text(encoding="utf-8").rstrip()
    if not text.endswith("}"):
        raise ValueError(f"{main_qml.name} does not end with the root item's closing brace")
    main_qml.write_text(text[:-1] + PROBE + "}\n", encoding="utf-8")


def read_probes(stderr: str) -> list[dict]:
    probes = []
    for line in stderr.splitlines():
        if PROBE_TAG not in line:
            continue
        try:
            probes.append(json.loads(line.split(PROBE_TAG, 1)[1]))
        except json.JSONDecodeError as exc:
            log.warn("nestedkwin", "unreadable probe line; ignored", error=exc, line=line[:300])
    return probes


def resizing_share(probe: dict) -> tuple[float, list[tuple[int, int]]]:
    """Share of the top bar that would resize, and the offending points.

    Follows KDecoration's rule for the section under the pointer: a point of the
    top border is title bar when the title-bar rectangle contains it, or when it
    lies beside the side borders and not above the rectangle's top; anything
    else there resizes. Points in the edge strip the decoration reserves on
    purpose are not offences.
    """
    left, top, right, _bottom = (int(v) for v in probe["borders"])
    width = int(probe["clientWidth"]) + left + right
    tx, ty, tw, th = (int(round(v)) for v in probe["titleBar"])
    grip = 0 if probe["maximized"] else decoration.TOP_GRIP
    side = 0 if probe["maximized"] else decoration.LINE
    resizing = 0
    offences: list[tuple[int, int]] = []
    for y in range(top):
        for x in range(width):
            in_title = tx <= x < tx + tw and ty <= y < ty + th
            is_title = in_title or (left <= x < width - right and y >= ty)
            if is_title:
                continue
            resizing += 1
            if y >= grip and side <= x < width - side:
                offences.append((x, y))
    return resizing / max(1, top * width), offences


def check_sections(pal: Palette, probes: list[dict]) -> bool:
    probes = [p for p in probes if p.get("round") == 1]
    if len(probes) != WINDOWS:
        log.error("nestedkwin", "not every test window reported its title bar", variant=pal.key,
                  expected=WINDOWS, reported=len(probes))
        return False
    ok = True
    for probe in probes:
        share, offences = resizing_share(probe)
        fields = dict(variant=pal.key, window=probe["caption"], maximized=probe["maximized"],
                      title_bar=probe["titleBar"], borders=probe["borders"], resize_margins=probe["grips"],
                      top_bar_resizing_percent=round(100 * share, 1))
        if offences:
            ok = False
            log.error("nestedkwin", "the top bar resizes away from the window edge", **fields,
                      points=len(offences), first=offences[0], last=offences[-1])
        else:
            log.info("nestedkwin", "the top bar resizes only along the window edge", **fields)
    return ok


def check_buttons(pal: Palette, probes: list[dict]) -> bool:
    """Round 1 runs on one desktop, round 2 after a second one was added."""
    ok = True
    for round_no, want_desktops in ((1, False), (2, True)):
        batch = [p for p in probes if p.get("round") == round_no]
        if len(batch) != WINDOWS:
            log.error("nestedkwin", "not every test window reported its buttons", variant=pal.key,
                      round=round_no, expected=WINDOWS, reported=len(batch))
            ok = False
            continue
        for probe in batch:
            drawn = {"left": probe["left"], "right": probe["right"]}
            problems = []
            if "help" in drawn["left"] + drawn["right"]:
                problems.append("help is drawn though no Wayland window can offer it")
            has_desktops = "alldesktops" in drawn["left"] + drawn["right"]
            if has_desktops != want_desktops:
                problems.append("'on all desktops' is " + ("missing with two desktops" if want_desktops
                                                            else "drawn with only one desktop"))
            for side, names in ALWAYS.items():
                if [n for n in drawn[side] if n in names] != names:
                    problems.append(f"{side} side lacks {names}")
            fields = dict(variant=pal.key, round=round_no, window=probe["caption"], left=drawn["left"],
                          right=drawn["right"])
            if problems:
                ok = False
                log.error("nestedkwin", "wrong title-bar buttons", problems=problems, **fields)
            else:
                log.info("nestedkwin", "title-bar buttons match what the window can do", **fields)
    return ok


def check(pal: Palette) -> bool:
    package = DIST / "kwin" / "decorations" / pal.decoration_id
    if not package.is_dir():
        log.error("nestedkwin", "decoration is not built; run ./build.py first", path=str(package))
        return False
    with tempfile.TemporaryDirectory(prefix="khkwin-") as tmp_name:
        work = Path(tmp_name)
        (work / "config").mkdir()
        under_test = work / "data" / "kwin" / "decorations" / pal.decoration_id
        shutil.copytree(package, under_test)
        try:
            add_probe(under_test / "contents" / "ui" / "main.qml")
        except (OSError, ValueError) as exc:
            log.error("nestedkwin", "could not add the geometry probe", error=exc, variant=pal.key)
            return False
        (work / "config" / "kwinrc").write_text(
            f"[org.kde.kdecoration2]\nlibrary=org.kde.kwin.aurorae\ntheme={pal.decoration_id}\n"
            f"ButtonsOnLeft={LAYOUT[0]}\nButtonsOnRight={LAYOUT[1]}\n\n[Desktops]\nNumber=1\nRows=1\n",
            encoding="utf-8",
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
            # Without a terminal Qt would send KWin's messages to the system
            # journal, and QML errors in the decoration would go unseen here.
            QT_FORCE_STDERR_LOGGING="1",
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
        notes = [ln for ln in result.stderr.splitlines()
                 if PROBE_TAG not in ln and (".qml" in ln or "aurorae" in ln.lower())]
        probes = read_probes(result.stderr)
        sections_ok = check_sections(pal, probes)
        buttons_ok = check_buttons(pal, probes)
        desktop_log = work / "desktop.log"
        if desktop_log.is_file() and desktop_log.read_text(encoding="utf-8", errors="replace").strip():
            log.debug("nestedkwin", "desktop request output", variant=pal.key,
                      output=desktop_log.read_text(encoding="utf-8", errors="replace")[-400:])
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
    return not notes and sections_ok and buttons_ok


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
