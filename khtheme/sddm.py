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
class Screen:
    picture: str  # file under assets/title
    # Horizontal place of the picture when the screen is wider than it
    # (0 left, 1 right): the side where the painting runs off the edge.
    align_x: float
    # Empty part of the picture the menu is centred in, as fractions of the
    # picture (left, top, right, bottom). An edge on the picture's border
    # carries on to the screen's edge, so extra white beside the picture counts.
    space: tuple[float, float, float, float]
    accent: str  # band behind the chosen row
    orb: tuple[str, str]  # top and bottom colour of the light in the marker
    round_orb: bool


SCREENS = {
    # 358/2 Days: logo top left, painting on the right running off the edge.
    ORG_XIII.key: Screen("days.jpg", 1.0, (0.0, 0.26, 0.43, 1.0), "#d0262c", ("#fff6b8", "#f2b705"), False),
    # Kingdom Hearts II: painting top right, logo bottom left, white all round.
    SORA.key: Screen("kh2.jpg", 0.5, (0.0, 0.0, 0.37, 0.62), "#ec5a24", ("#fff1b0", "#f07800"), True),
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

    readonly property var rows: [nameRow, passRow, loginRow, sessionRow, powerRow]
    property int current: userModel.lastUser ? 1 : 0
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
        property string caption: ""
        property Item input: null
        readonly property bool selected: root.current === index
        default property alias content: slot.data
        signal activated()
        signal cycled(int step)
        function takeFocus() { if (input) input.forceActiveFocus(); else row.forceActiveFocus(); }
        width: Math.round(620 * root.u)
        height: Math.round(60 * root.u)
        activeFocusOnTab: false

        // The square marker; the chosen row's holds a light.
        Rectangle {
            id: marker
            width: row.height; height: row.height
            color: row.selected ? "#151515" : "#c8c8c8"
            Behavior on color { ColorAnimation { duration: 120 } }
            Rectangle {
                anchors.centerIn: parent
                visible: row.selected
                width: parent.width * 0.8; height: width
                radius: root.c.roundOrb ? width / 2 : width * 0.22
                color: root.c.glow
            }
            Rectangle {
                anchors.centerIn: parent
                visible: row.selected
                width: parent.width * 0.52; height: width
                radius: root.c.roundOrb ? width / 2 : width * 0.18
                gradient: Gradient {
                    GradientStop { position: 0.0; color: root.c.orbTop }
                    GradientStop { position: 1.0; color: root.c.orbBottom }
                }
            }
        }
        // The bar: a band that deepens toward its end, and a rule beneath.
        Rectangle {
            id: bar
            x: marker.width + Math.round(6 * root.u)
            width: row.width - x
            height: row.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: row.selected ? root.c.band0 : root.c.grey0 }
                GradientStop { position: 0.5; color: row.selected ? root.c.band0 : root.c.grey0 }
                GradientStop { position: 0.85; color: row.selected ? root.c.band : root.c.grey }
                GradientStop { position: 1.0; color: row.selected ? root.c.bandEnd : root.c.greyEnd }
            }
            Rectangle {
                anchors.bottom: parent.bottom
                x: -marker.width - Math.round(6 * root.u)
                width: row.width
                height: Math.max(2, Math.round((row.selected ? 4 : 3) * root.u))
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: row.selected ? "#151515" : "#c8c8c8" }
                    GradientStop { position: 0.75; color: row.selected ? "#151515" : "#d8d8d8" }
                    GradientStop { position: 1.0; color: row.selected ? "#00151515" : "#00d8d8d8" }
                }
            }
            Text {
                anchors.right: parent.right
                anchors.rightMargin: Math.round(12 * root.u)
                anchors.verticalCenter: parent.verticalCenter
                text: row.caption
                color: row.selected ? "#ffffff" : "#a5a5a5"
                font.family: menuFont.name
                font.pixelSize: Math.round(15 * root.u)
                font.letterSpacing: Math.round(3 * root.u)
            }
        }
        Item {
            id: slot
            x: marker.width + Math.round(24 * root.u)
            width: row.width - x - Math.round(110 * root.u)
            height: row.height
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

    // The menu's lettering: dark and outlined in white on the chosen row,
    // pale grey and engraved on the others.
    component RowText: Text {
        property bool selected: false
        anchors.verticalCenter: parent ? parent.verticalCenter : undefined
        color: selected ? "#141414" : "#c6c6c6"
        style: Text.Outline
        styleColor: selected ? "#ffffff" : "#a2a2a2"
        font.family: menuFont.name
        font.pixelSize: Math.round(40 * root.u)
        font.letterSpacing: Math.round(4 * root.u)
        // Long values (session names) shrink to fit their bar.
        fontSizeMode: Text.HorizontalFit
        minimumPixelSize: Math.round(20 * root.u)
        elide: Text.ElideRight
        width: parent ? parent.width : implicitWidth
    }

    component RowInput: TextInput {
        property bool selected: false
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        clip: true
        color: selected ? "#141414" : "#c6c6c6"
        selectionColor: root.c.accent
        selectedTextColor: "#ffffff"
        font.family: menuFont.name
        font.pixelSize: Math.round(40 * root.u)
        font.letterSpacing: Math.round(4 * root.u)
    }

    Column {
        id: menu
        x: Math.round((root.spaceL + root.spaceR - width) / 2)
        y: Math.round((root.spaceT + root.spaceB - height) / 2)
        width: Math.round(620 * root.u)
        spacing: Math.round(30 * root.u)

        // Where the title screen credits its developer: a greeting, or what went wrong.
        Item {
            width: menu.width
            height: Math.round(92 * root.u)
            Text {
                id: small
                x: Math.round(14 * root.u)
                text: root.failed ? "Login failed" : root.busy ? "Logging in" : root.notice.length > 0 ? root.notice
                      : keyboard.capsLock ? "Caps Lock is on" : "Welcome to"
                color: root.failed ? root.c.accent : "#8e8e8e"
                font.family: menuFont.name
                font.pixelSize: Math.round(22 * root.u)
                font.letterSpacing: Math.round(4 * root.u)
                font.capitalization: Font.AllUppercase
                width: menu.width - x
                elide: Text.ElideRight
            }
            Rectangle {
                anchors.top: small.bottom
                anchors.topMargin: Math.round(6 * root.u)
                width: Math.round(menu.width * 0.5)
                height: Math.max(1, Math.round(2 * root.u))
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "#b4b4b4" }
                    GradientStop { position: 0.7; color: "#b4b4b4" }
                    GradientStop { position: 1.0; color: "#00b4b4b4" }
                }
            }
            Text {
                x: Math.round(28 * root.u)
                anchors.bottom: parent.bottom
                text: sddm.hostName
                color: "#a7a7a7"
                font.family: menuFont.name
                font.pixelSize: Math.round(34 * root.u)
                font.letterSpacing: Math.round(6 * root.u)
                font.capitalization: Font.AllUppercase
                width: menu.width - x
                elide: Text.ElideRight
            }
        }

        Column {
            spacing: Math.round(16 * root.u)

            MenuRow {
                id: nameRow
                index: 0
                caption: "NAME"
                input: nameInput
                onActivated: root.select(1)
                RowText { selected: nameRow.selected; visible: nameInput.text.length === 0; text: "NAME" }
                // Shown in capitals like the rest of the menu; what is typed is kept as typed.
                RowInput { id: nameInput; selected: nameRow.selected; text: userModel.lastUser; font.capitalization: Font.AllUppercase }
            }
            MenuRow {
                id: passRow
                index: 1
                caption: "PASSWORD"
                input: passInput
                onActivated: root.login()
                RowText { selected: passRow.selected; visible: passInput.text.length === 0; text: "PASSWORD" }
                RowInput {
                    id: passInput
                    selected: passRow.selected
                    echoMode: TextInput.Password
                    passwordCharacter: "•"
                    onTextChanged: if (text.length > 0) root.failed = false
                }
            }
            MenuRow {
                id: loginRow
                index: 2
                onActivated: root.login()
                RowText { selected: loginRow.selected; text: "LOG IN" }
            }
            MenuRow {
                id: sessionRow
                index: 3
                caption: "SESSION"
                readonly property var item: sessions.count > 0 ? sessions.itemAt(root.sessionIndex % sessions.count) : null
                onActivated: cycled(1)
                onCycled: (step) => { if (sessions.count > 0) root.sessionIndex = (root.sessionIndex + step + sessions.count) % sessions.count; }
                RowText {
                    selected: sessionRow.selected
                    text: (sessionRow.selected ? "‹ " : "") + (sessionRow.item ? sessionRow.item.sessionName : "Default").toUpperCase()
                          + (sessionRow.selected ? " ›" : "")
                }
            }
            MenuRow {
                id: powerRow
                index: 4
                caption: "POWER"
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


def config(pal: Palette, size: tuple[int, int]) -> dict:
    screen = SCREENS[pal.key]
    grey = "#cfcfcf"
    return {
        "picture": "background.jpg",
        "size": list(size),
        "alignX": screen.align_x,
        "space": list(screen.space),
        "accent": screen.accent,
        "band0": _rgba(screen.accent, 0.0),
        "band": _rgba(screen.accent, 0.8),
        "bandEnd": _rgba(screen.accent, 0.35),
        "grey0": _rgba(grey, 0.0),
        "grey": _rgba(grey, 0.55),
        "greyEnd": _rgba(grey, 0.2),
        "glow": _rgba(screen.orb[1], 0.35),
        "orbTop": screen.orb[0],
        "orbBottom": screen.orb[1],
        "roundOrb": screen.round_orb,
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
Version=2.2
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
    errors = [line for line in result.stderr.splitlines() if "qml" in line.lower() and ("error" in line.lower()
                                                                                       or "warning" in line.lower())]
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
        write_text(root / "Main.qml", main_qml(pal, _picture_size(picture)))
        write_text(root / "metadata.desktop", metadata(pal))
        write_text(root / "theme.conf", theme_conf(pal))
        preview = root / "preview.jpg"
        if not render_preview(root, preview):
            shutil.copyfile(picture, preview)
        log.info("sddm", "login theme staged (install needs root: ./install.py sddm)", variant=pal.key)
    return root
