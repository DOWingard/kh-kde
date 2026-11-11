"""SDDM login themes: one theme directory per variant.

Each variant is its own theme (`KingdomHearts-OrgXIII`, `KingdomHearts-Sora`),
so both appear as choices in System Settings' Login Screen page. The screen is
a title-screen wallpaper (Organization XIII: 358/2 Days; Sora: Kingdom Hearts
II) with the sign-in drawn as the games' title menu: a column of bars, each
with a square marker that lights up on the chosen row. The menu stands in the
empty white part of the picture. Installing needs root, so the build only
stages the themes under dist/sddm.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import log
from .palette import ORG_XIII, SORA, Palette
from .svg import write_text

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
FONT = "KHMenuBold.otf"
# Stand-ins for the objects SDDM gives a theme, used to render the preview.
HARNESS = ROOT / "tools" / "preview" / "sddm.qml"
PREVIEW_SIZE = (1920, 1080)
PREVIEW_SETTLE_MS = 1500

THEME_ID = "KingdomHearts"
# The single theme directory earlier versions built for both variants.
LEGACY_ID = THEME_ID


@dataclass(frozen=True)
class Menu:
    """How one game's title menu is drawn."""

    letter_spacing: float  # em
    text_scale: float  # letter size against the bar's height
    row_gap: float  # gap between bars against the bar's height
    shadow: tuple[str, float]  # chosen row's drop shadow: colour, offset in units
    rule: str  # chosen row's rule: "fade" (thin, greying out) or "solid" (thick, full length)
    band: tuple[str, str]  # chosen row's band: colour where it starts showing, colour at the end
    grey_band: str  # band behind the other rows, at its end
    credit: tuple[str, str, bool]  # greeting colour, computer-name colour, bold greeting
    marker: list[str]  # ImageMagick drawing of the lit marker on a 128 px square


# Kingdom Hearts II Final Mix: spaced-out lettering, an ember-like round light,
# a thin rule that fades to grey, an orange band.
KH2_MENU = Menu(
    letter_spacing=0.3, text_scale=0.64, row_gap=0.42, shadow=("#a9a9a9", 2.5), rule="fade",
    band=("#f6c9a6", "#e2603a"), grey_band="#b9b9b9", credit=("#a5a5a5", "#b3b3b3", False),
    marker=["xc:#140b03",
            "(", "-size", "128x128", "xc:none", "-fill", "#ff8c12", "-draw", "circle 64,64 64,20", "-blur", "0x13", ")",
            "-composite",
            "(", "-size", "128x128", "xc:none", "-fill", "#ffd25a", "-draw", "circle 64,64 64,40", "-blur", "0x9", ")",
            "-composite",
            "(", "-size", "128x128", "xc:none", "-fill", "#fff8dc", "-draw", "circle 64,64 64,52", "-blur", "0x6", ")",
            "-composite"],
)
# 358/2 Days: large, tight lettering, a glowing rounded square, a thick black
# rule across the whole bar, a red band.
DAYS_MENU = Menu(
    letter_spacing=0.06, text_scale=0.8, row_gap=0.22, shadow=("#9c9c9c", 2.0), rule="solid",
    band=("#eeb0b0", "#c9262e"), grey_band="#bdbdbd", credit=("#5c5c5c", "#7d7d7d", True),
    marker=["xc:#1c1402",
            "(", "-size", "128x128", "xc:none", "-fill", "#ff9a10", "-draw", "roundrectangle 18,18 110,110 16,16",
            "-blur", "0x9", ")", "-composite",
            "(", "-size", "128x128", "xc:none", "-fill", "#ffd23c", "-draw", "roundrectangle 26,26 102,102 12,12",
            "-blur", "0x2", ")", "-composite",
            "(", "-size", "128x128", "xc:none", "-fill", "#fff0a0", "-draw", "roundrectangle 34,34 94,94 10,10",
            "-blur", "0x5", ")", "-composite"],
)


@dataclass(frozen=True)
class Screen:
    picture: str  # file under assets/title
    # Horizontal place of the picture when the screen is wider than it
    # (0 left, 1 right): the side where the painting runs off the edge.
    align_x: float
    # Empty part of the picture the menu is centred in, as fractions of the
    # picture (left, top, right, bottom). An edge on the picture's border
    # carries on to the screen's edge, so extra white beside the picture counts.
    space: tuple[float, float, float, float]
    menu: Menu


SCREENS = {
    # 358/2 Days: logo top left, painting on the right running off the edge.
    ORG_XIII.key: Screen("days.jpg", 1.0, (0.0, 0.26, 0.43, 1.0), DAYS_MENU),
    # Kingdom Hearts II: painting top right, logo bottom left, white all round.
    SORA.key: Screen("kh2.jpg", 0.5, (0.0, 0.0, 0.37, 0.62), KH2_MENU),
}


def theme_id(pal: Palette) -> str:
    return f"{THEME_ID}-{pal.key}"


MAIN_QML = r"""import QtQuick

// Login screen laid out like the series' title menus. SDDM provides the
// context objects `sddm`, `userModel`, `sessionModel`, `keyboard` and `config`.
Rectangle {
    id: root
    width: 1920
    height: 1080
    color: "white"

    readonly property var c: (@CONFIG@)

    // The picture is fitted whole; its white surround continues as the page.
    readonly property real fit: Math.min(width / c.size[0], height / c.size[1])
    readonly property real picW: c.size[0] * fit
    readonly property real picH: c.size[1] * fit
    readonly property real picX: (width - picW) * c.alignX
    readonly property real picY: (height - picH) / 2
    // The empty part of the picture the menu is centred in.
    readonly property real spaceL: c.space[0] <= 0 ? 0 : picX + c.space[0] * picW
    readonly property real spaceT: c.space[1] <= 0 ? 0 : picY + c.space[1] * picH
    readonly property real spaceR: c.space[2] >= 1 ? width : picX + c.space[2] * picW
    readonly property real spaceB: c.space[3] >= 1 ? height : picY + c.space[3] * picH
    // Menu scale: 1 on a 1080-line screen, smaller when the empty part is too small.
    readonly property real u: Math.max(0.4, Math.min(height / 1080, (spaceR - spaceL) * 0.88 / 620,
                                                     (spaceB - spaceT) * 0.92 / 560))
    readonly property int barHeight: Math.round(60 * u)
    readonly property int textSize: Math.round(barHeight * c.textScale)

    readonly property var rows: [nameRow, passRow, startRow, sessionRow, powerRow]
    property int current: 0
    property int sessionIndex: sessionModel.lastIndex >= 0 ? sessionModel.lastIndex : 0
    property int powerIndex: 0
    property bool failed: false
    property bool busy: false
    property string notice: ""
    readonly property var powers: {
        var list = [];
        if (sddm.canPowerOff) list.push({ key: "off", label: "Shut Down" });
        if (sddm.canReboot) list.push({ key: "reboot", label: "Restart" });
        if (sddm.canSuspend) list.push({ key: "suspend", label: "Suspend" });
        return list;
    }

    FontLoader { id: menuFont; source: "assets/KHMenuBold.otf" }

    function login() {
        root.failed = false;
        root.notice = "";
        root.busy = true;
        sddm.login(nameInput.text, passInput.text, root.sessionIndex);
    }
    function power() {
        if (root.powers.length === 0) return;
        var key = root.powers[root.powerIndex % root.powers.length].key;
        if (key === "off") sddm.powerOff();
        else if (key === "reboot") sddm.reboot();
        else sddm.suspend();
    }
    function select(n) {
        root.current = Math.max(0, Math.min(root.rows.length - 1, n));
    }
    onCurrentChanged: rows[current].takeFocus()

    Connections {
        target: sddm
        function onLoginFailed() {
            root.busy = false;
            root.failed = true;
            passInput.text = "";
            root.select(1);
            root.rows[1].takeFocus();
        }
        function onLoginSucceeded() { root.busy = false; }
        function onInformationMessage(message) { root.notice = message; }
    }

    Image {
        x: root.picX; y: root.picY; width: root.picW; height: root.picH
        source: "assets/" + root.c.picture
        smooth: true
        mipmap: true
    }

    // Session names, read through delegates: SDDM's model has no get().
    Item {
        visible: false
        Repeater { id: sessions; model: sessionModel; delegate: Item { property string sessionName: model.name } }
    }

    // ---- one menu bar ----
    component MenuRow: FocusScope {
        id: row
        property int index: 0
        property Item input: null
        readonly property bool selected: root.current === index
        default property alias content: slot.data
        signal activated()
        signal cycled(int step)
        function takeFocus() { if (input) input.forceActiveFocus(); else row.forceActiveFocus(); }
        width: Math.round(620 * root.u)
        height: root.barHeight

        // The square marker; the chosen row's holds a light.
        Rectangle {
            id: marker
            width: row.height; height: row.height
            color: "#c4c4c4"
            Image {
                anchors.fill: parent
                visible: row.selected
                source: "assets/marker.png"
                smooth: true
            }
        }
        // The band toward the bar's end.
        Rectangle {
            x: marker.width
            width: row.width - x
            height: row.height - rule.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: row.selected ? root.c.band0 : root.c.grey0 }
                GradientStop { position: 0.52; color: row.selected ? root.c.band0 : root.c.grey0 }
                GradientStop { position: 0.72; color: row.selected ? root.c.bandMid : root.c.greyMid }
                GradientStop { position: 1.0; color: row.selected ? root.c.bandEnd : root.c.greyEnd }
            }
        }
        // The rule under the bar.
        Rectangle {
            id: rule
            anchors.bottom: parent.bottom
            x: marker.width
            width: row.width - x
            height: Math.max(2, Math.round((row.selected && root.c.rule === "solid" ? 5 : 3) * root.u))
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: row.selected ? "#141414" : "#cdcdcd" }
                GradientStop { position: 0.55; color: row.selected ? (root.c.rule === "solid" ? "#141414" : "#5a5a5a") : "#d2d2d2" }
                GradientStop { position: 1.0; color: row.selected ? (root.c.rule === "solid" ? "#141414" : "#c8c8c8") : "#dcdcdc" }
            }
        }
        // A soft second line under a fading rule.
        Rectangle {
            visible: row.selected && root.c.rule === "fade"
            anchors.top: rule.bottom
            x: rule.x
            width: rule.width * 0.8
            height: rule.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#d0d0d0" }
                GradientStop { position: 1.0; color: "#00d0d0d0" }
            }
        }
        // Lettering stays clear of the band, as on the title screens.
        Item {
            id: slot
            x: marker.width + Math.round(20 * root.u)
            width: Math.round((row.width - marker.width) * 0.66) - Math.round(20 * root.u)
            height: row.height - rule.height
        }
        // A click picks a row; a click on the picked row uses it.
        MouseArea {
            anchors.fill: parent
            z: 10
            onClicked: {
                if (row.selected) row.activated(); else root.select(row.index);
                row.takeFocus();
            }
        }
        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Up) root.select(root.current - 1);
            else if (event.key === Qt.Key_Down) root.select(root.current + 1);
            else if (event.key === Qt.Key_Tab) root.select((root.current + 1) % root.rows.length);
            else if (event.key === Qt.Key_Backtab) root.select((root.current + root.rows.length - 1) % root.rows.length);
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) row.activated();
            else if (event.key === Qt.Key_Left) row.cycled(-1);
            else if (event.key === Qt.Key_Right) row.cycled(1);
            else return;
            event.accepted = true;
        }
    }

    // The menu's lettering: black over a grey drop shadow on the chosen row,
    // flat pale grey on the others.
    component RowText: Item {
        id: label
        property bool selected: false
        property string text: ""
        anchors.fill: parent
        Text {
            id: shadow
            visible: label.selected
            x: Math.round(root.c.shadowOffset * root.u)
            y: Math.round(root.c.shadowOffset * root.u)
            width: parent.width; height: parent.height
            verticalAlignment: Text.AlignVCenter
            text: label.text
            color: root.c.shadow
            font: face.font
            fontSizeMode: face.fontSizeMode
            minimumPixelSize: face.minimumPixelSize
            elide: Text.ElideRight
        }
        Text {
            id: face
            width: parent.width; height: parent.height
            verticalAlignment: Text.AlignVCenter
            text: label.text
            color: label.selected ? "#121212" : "#c9c9c9"
            font.family: menuFont.name
            font.pixelSize: root.textSize
            // Spacing does not shrink with the letters, so long values get less of it.
            font.letterSpacing: root.textSize * root.c.letterSpacing * Math.min(1, 9 / Math.max(1, label.text.length))
            // Long values (session names) shrink to fit their bar.
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Math.round(root.textSize * 0.35)
            elide: Text.ElideRight
        }
    }

    // A field typed into: what is typed takes the menu's lettering, and its
    // label shows while it is empty.
    component RowInput: Item {
        id: field
        property bool selected: false
        property string label: ""
        property alias input: editor
        anchors.fill: parent
        RowText { selected: field.selected; visible: editor.text.length === 0; text: field.label }
        Text {
            visible: field.selected && editor.text.length > 0
            x: Math.round(root.c.shadowOffset * root.u)
            y: Math.round(root.c.shadowOffset * root.u)
            width: parent.width; height: parent.height
            verticalAlignment: Text.AlignVCenter
            clip: true
            text: editor.displayText
            color: root.c.shadow
            font: editor.font
        }
        TextInput {
            id: editor
            width: parent.width; height: parent.height
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            color: field.selected ? "#121212" : "#c9c9c9"
            selectionColor: root.c.accent
            selectedTextColor: "#ffffff"
            font.family: menuFont.name
            font.pixelSize: root.textSize
            font.letterSpacing: root.textSize * root.c.letterSpacing
        }
    }

    Column {
        id: menu
        x: Math.round((root.spaceL + root.spaceR - width) / 2)
        y: Math.round((root.spaceT + root.spaceB - height) / 2)
        width: Math.round(620 * root.u)
        spacing: Math.round(26 * root.u)

        // Where the title screen credits its developer: a greeting, or what went wrong.
        Item {
            width: menu.width
            height: Math.round(76 * root.u)
            Text {
                id: small
                x: Math.round(14 * root.u)
                text: root.failed ? "Login failed" : root.busy ? "Logging in" : root.notice.length > 0 ? root.notice
                      : keyboard.capsLock ? "Caps Lock is on" : "Welcome to"
                color: root.failed ? root.c.accent : root.c.greeting
                font.family: menuFont.name
                font.bold: root.c.greetingBold
                font.pixelSize: Math.round(20 * root.u)
                font.letterSpacing: Math.round(20 * root.u) * root.c.letterSpacing * 0.8
                font.capitalization: Font.AllUppercase
                width: menu.width - x
                elide: Text.ElideRight
            }
            Rectangle {
                anchors.top: small.bottom
                anchors.topMargin: Math.round(3 * root.u)
                x: -Math.round(40 * root.u)
                width: Math.round(menu.width * 0.5)
                height: Math.max(1, Math.round(3 * root.u))
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "#00a0a0a0" }
                    GradientStop { position: 0.15; color: "#a0a0a0" }
                    GradientStop { position: 0.7; color: "#c4c4c4" }
                    GradientStop { position: 1.0; color: "#00c4c4c4" }
                }
            }
            Text {
                x: Math.round(32 * root.u)
                anchors.bottom: parent.bottom
                text: sddm.hostName
                color: root.c.hostName
                font.family: menuFont.name
                font.pixelSize: Math.round(30 * root.u)
                font.letterSpacing: Math.round(30 * root.u) * root.c.letterSpacing * 0.8
                font.capitalization: Font.AllUppercase
                width: menu.width - x
                elide: Text.ElideRight
            }
        }

        Column {
            spacing: Math.round(root.barHeight * root.c.rowGap)

            MenuRow {
                id: nameRow
                index: 0
                input: nameField.input
                onActivated: root.select(1)
                RowInput { id: nameField; selected: nameRow.selected; label: "LOGIN" }
            }
            MenuRow {
                id: passRow
                index: 1
                input: passField.input
                onActivated: root.login()
                RowInput { id: passField; selected: passRow.selected; label: "PASSWORD" }
            }
            MenuRow {
                id: startRow
                index: 2
                onActivated: root.login()
                RowText { selected: startRow.selected; text: "START" }
            }
            MenuRow {
                id: sessionRow
                index: 3
                readonly property var item: sessions.count > 0 ? sessions.itemAt(root.sessionIndex % sessions.count) : null
                // Wayland is the usual session, so only other kinds keep their suffix.
                readonly property string name: (item ? item.sessionName : "Default").replace(/\s*\(Wayland\)\s*$/i, "").toUpperCase()
                onActivated: cycled(1)
                onCycled: (step) => { if (sessions.count > 0) root.sessionIndex = (root.sessionIndex + step + sessions.count) % sessions.count; }
                RowText {
                    selected: sessionRow.selected
                    text: (sessionRow.selected ? "‹ " : "") + sessionRow.name + (sessionRow.selected ? " ›" : "")
                }
            }
            MenuRow {
                id: powerRow
                index: 4
                visible: root.powers.length > 0
                onActivated: root.power()
                onCycled: (step) => { root.powerIndex = (root.powerIndex + step + root.powers.length) % root.powers.length; }
                RowText {
                    selected: powerRow.selected
                    text: root.powers.length === 0 ? "" : (powerRow.selected ? "‹ " : "")
                          + root.powers[root.powerIndex % root.powers.length].label.toUpperCase() + (powerRow.selected ? " ›" : "")
                }
            }
        }
    }

    // The typed fields, reached by id from the functions above.
    readonly property alias nameInput: nameField.input
    readonly property alias passInput: passField.input

    Component.onCompleted: rows[current].takeFocus()
}
"""


def _rgba(hex_color: str, alpha: float) -> str:
    """#AARRGGBB, the form QML colour properties accept."""
    return f"#{round(alpha * 255):02x}{hex_color.lstrip('#')}"


def _picture_size(path: Path) -> tuple[int, int]:
    try:
        result = subprocess.run(["magick", "identify", "-format", "%w %h", f"{path}[0]"], check=True,
                                capture_output=True, text=True, timeout=60)
        w, h = (int(v) for v in result.stdout.split())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
        log.error("sddm", "could not read the picture's size", error=exc, picture=str(path))
        raise
    return w, h


def _draw_marker(menu: Menu, target: Path) -> None:
    cmd = ["magick", "-size", "128x128", *menu.marker, str(target)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        log.error("sddm", "drawing the menu marker timed out", error=exc)
        raise
    except subprocess.CalledProcessError as exc:
        log.error("sddm", "drawing the menu marker failed", error=exc, stderr=exc.stderr.decode(errors="replace")[-800:])
        raise


def config(pal: Palette, size: tuple[int, int]) -> dict:
    screen = SCREENS[pal.key]
    menu = screen.menu
    return {
        "picture": "background.jpg",
        "size": list(size),
        "alignX": screen.align_x,
        "space": list(screen.space),
        "letterSpacing": menu.letter_spacing,
        "textScale": menu.text_scale,
        "rowGap": menu.row_gap,
        "shadow": menu.shadow[0],
        "shadowOffset": menu.shadow[1],
        "rule": menu.rule,
        "accent": menu.band[1],
        "band0": _rgba(menu.band[0], 0.0),
        "bandMid": _rgba(menu.band[0], 0.9),
        "bandEnd": menu.band[1],
        "grey0": _rgba(menu.grey_band, 0.0),
        "greyMid": _rgba(menu.grey_band, 0.45),
        "greyEnd": menu.grey_band,
        "greeting": menu.credit[0],
        "hostName": menu.credit[1],
        "greetingBold": menu.credit[2],
    }


def main_qml(pal: Palette, size: tuple[int, int]) -> str:
    return MAIN_QML.replace("@CONFIG@", json.dumps(config(pal, size), indent=8))


def metadata(pal: Palette) -> str:
    tone = "dark" if pal.dark else "light"
    return f"""[SddmGreeterTheme]
Name=Kingdom Hearts – {pal.title}
Description={pal.title} ({tone}) login screen
Author=Kingdom Hearts Plasma theme
License=Fan project; artwork (c) Disney / Square Enix
Type=sddm-theme
Version=2.3
Screenshot=preview.jpg
MainScript=Main.qml
ConfigFile=theme.conf
Theme-Id={theme_id(pal)}
Theme-API=2.0
QtVersion=6
"""


def theme_conf(pal: Palette) -> str:
    return f"""[General]
variant={pal.key}
"""


def render_preview(root: Path, target: Path) -> bool:
    """Draw the login screen as SDDM would show it, for the theme chooser.

    Rendered off screen with PyQt6 against stand-ins for SDDM's objects;
    False when that is not possible here.
    """
    if not HARNESS.is_file():
        log.warn("sddm", "preview harness missing; the chooser shows the picture alone", expected=str(HARNESS))
        return False
    script = (
        "import sys\n"
        "from PyQt6.QtCore import QTimer, QUrl\n"
        "from PyQt6.QtGui import QGuiApplication\n"
        "from PyQt6.QtQuick import QQuickView\n"
        "harness, main, out, w, h, settle = sys.argv[1:]\n"
        "app = QGuiApplication(sys.argv[:1])\n"
        "view = QQuickView()\n"
        "view.setInitialProperties({'main': QUrl.fromLocalFile(main).toString(), 'width': int(w), 'height': int(h)})\n"
        "view.setSource(QUrl.fromLocalFile(harness))\n"
        "if view.status() != QQuickView.Status.Ready:\n"
        "    print([e.toString() for e in view.errors()], file=sys.stderr); sys.exit(3)\n"
        "view.resize(int(w), int(h)); view.show()\n"
        "def grab():\n"
        "    image = view.grabWindow()\n"
        "    sys.exit(0 if not image.isNull() and image.save(out, quality=90) else 4)\n"
        "QTimer.singleShot(int(settle), grab)\n"
        "app.exec()\n"
    )
    # The software renderer needs no GPU, so package builds and CI draw it too.
    # Qt sends warnings to the journal when stderr is not a terminal; they are
    # read here instead.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_FORCE_STDERR_LOGGING="1")
    started = time.monotonic()
    try:
        result = subprocess.run([sys.executable, "-c", script, str(HARNESS), str(root / "Main.qml"), str(target),
                                 str(PREVIEW_SIZE[0]), str(PREVIEW_SIZE[1]), str(PREVIEW_SETTLE_MS)],
                                env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        log.warn("sddm", "preview render timed out; the chooser shows the picture alone", error=exc)
        return False
    if result.returncode != 0 or not target.is_file():
        log.warn("sddm", "preview render failed; the chooser shows the picture alone",
                 exit_code=result.returncode, stderr=result.stderr.strip()[-1200:],
                 hint="PyQt6 (python-pyqt6) draws the real screen")
        return False
    # Qt prefixes every QML diagnostic (errors, binding loops, type errors) with
    # the file and line it concerns.
    errors = [line for line in result.stderr.splitlines()
              if re.search(r"\.qml:\d+", line) or ("qml" in line.lower() and "error" in line.lower())]
    if errors:
        # A warning here (a broken binding, a missing file) is a fault in the screen itself.
        log.warn("sddm", "the login screen reported QML problems while rendering", messages=errors[:10])
        return False
    log.info("sddm", "preview rendered", target=str(target), duration_ms=round((time.monotonic() - started) * 1000))
    return True


def build(out: Path, pal: Palette) -> Path:
    root = out / "sddm" / theme_id(pal)
    legacy = out / "sddm" / LEGACY_ID
    if legacy.is_dir():
        shutil.rmtree(legacy)
        log.info("sddm", "removed the combined login theme of an older layout", path=str(legacy))
    with log.timed("sddm", "build login theme", variant=pal.key, target=str(root)):
        picture = ASSETS / "title" / SCREENS[pal.key].picture
        font = FONTS / FONT
        for needed in (picture, font):
            if not needed.is_file():
                log.error("sddm", "asset is missing", path=str(needed))
                raise FileNotFoundError(needed)
        if root.exists():
            shutil.rmtree(root)
        assets = root / "assets"
        assets.mkdir(parents=True)
        shutil.copyfile(picture, assets / "background.jpg")
        shutil.copyfile(font, assets / FONT)
        _draw_marker(SCREENS[pal.key].menu, assets / "marker.png")
        write_text(root / "Main.qml", main_qml(pal, _picture_size(picture)))
        write_text(root / "metadata.desktop", metadata(pal))
        write_text(root / "theme.conf", theme_conf(pal))
        preview = root / "preview.jpg"
        if not render_preview(root, preview):
            shutil.copyfile(picture, preview)
        log.info("sddm", "login theme staged (install needs root: ./install.py sddm)", variant=pal.key)
    return root
