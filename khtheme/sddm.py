"""SDDM login theme: one theme directory serving both variants.

`theme.conf` selects the variant (`variant=OrgXIII` or `variant=Sora`); the
QML carries both colour sets and picks its background and emblem to match.
Installing it needs root, so the build only stages it under dist/sddm.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import log, wallpapers
from .palette import ORG_XIII, VARIANTS, Palette
from .svg import write_text

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONTS = ASSETS / "fonts"
FONT = "KHMenuBold.otf"

THEME_ID = "KingdomHearts"

MAIN_QML = r"""import QtQuick

// Login screen. SDDM provides the context objects `sddm`, `userModel`,
// `sessionModel`, `keyboard` and `config` (the values from theme.conf).
Rectangle {
    id: root
    width: 1920
    height: 1080

    readonly property var variants: (%(variants)s)
    readonly property string variantKey: variants[config.variant] !== undefined ? config.variant : "%(fallback)s"
    readonly property var t: variants[variantKey]
    readonly property real u: Math.max(0.6, Math.min(width / 1920, height / 1080))
    property int sessionIndex: sessionModel.lastIndex >= 0 ? sessionModel.lastIndex : 0

    color: t.base

    FontLoader { id: menuFont; source: "assets/KHMenuBold.otf" }

    function login() {
        message.text = "";
        sddm.login(userField.text, passField.text, root.sessionIndex);
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            message.text = "Login failed — check the name and password.";
            passField.text = "";
            passField.grab();
            shake.restart();
        }
        function onLoginSucceeded() {
            message.text = "";
        }
    }

    Image {
        anchors.fill: parent
        source: "assets/background-" + root.variantKey + ".jpg"
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        opacity: status == Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 400 } }
    }
    Rectangle { anchors.fill: parent; color: root.t.scrim; opacity: root.t.scrimOpacity }

    // ---- clock ----
    Column {
        id: clock
        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.round(root.height * 0.07)
        spacing: Math.round(4 * root.u)
        property date now: new Date()
        Timer { interval: 1000; running: true; repeat: true; onTriggered: clock.now = new Date() }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.formatTime(clock.now, "hh:mm")
            color: root.t.text
            font.family: menuFont.name
            font.weight: Font.Bold
            font.pixelSize: Math.round(96 * root.u)
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.formatDate(clock.now, "dddd, d MMMM")
            color: root.t.textDim
            font.pixelSize: Math.round(22 * root.u)
            font.letterSpacing: Math.round(2 * root.u)
        }
    }

    // ---- emblem + title card ----
    Image {
        id: emblem
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: clock.bottom
        anchors.topMargin: Math.round(30 * root.u)
        source: "assets/emblem-" + root.variantKey + ".png"
        height: Math.round(root.height * 0.15)
        width: Math.round(height * implicitWidth / Math.max(1, implicitHeight))
        smooth: true
        mipmap: true
    }
    Text {
        id: world
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: emblem.bottom
        anchors.topMargin: Math.round(18 * root.u)
        text: root.t.world
        color: root.t.text
        font.family: menuFont.name
        font.weight: Font.Bold
        font.pixelSize: Math.round(20 * root.u)
        font.letterSpacing: Math.round(6 * root.u)
        font.capitalization: Font.AllUppercase
    }
    Rectangle {
        id: rule
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: world.bottom
        anchors.topMargin: Math.round(12 * root.u)
        width: Math.round(world.width * 0.6)
        height: 1
        color: root.t.ornament
        opacity: 0.85
    }

    // ---- reusable pieces ----
    component Field: Rectangle {
        id: field
        property alias text: input.text
        property alias editor: input
        property string placeholder: ""
        property bool secret: false
        signal accepted()
        width: Math.round(340 * root.u)
        height: Math.round(44 * root.u)
        radius: Math.round(root.t.radius * root.u)
        color: root.t.field
        border.width: input.activeFocus ? 2 : 1
        border.color: input.activeFocus ? root.t.focus : root.t.line
        Behavior on border.color { ColorAnimation { duration: 120 } }
        function grab() { input.forceActiveFocus(); }
        Text {
            anchors.fill: input
            verticalAlignment: Text.AlignVCenter
            visible: input.text.length === 0
            text: field.placeholder
            color: root.t.textDim
            font: input.font
        }
        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: Math.round(14 * root.u)
            anchors.rightMargin: Math.round(14 * root.u)
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            color: root.t.text
            selectionColor: root.t.select
            selectedTextColor: root.t.selectText
            font.pixelSize: Math.round(16 * root.u)
            echoMode: field.secret ? TextInput.Password : TextInput.Normal
            passwordCharacter: "●"
            onAccepted: field.accepted()
        }
    }

    component Action: Rectangle {
        id: action
        property string label: ""
        signal triggered()
        activeFocusOnTab: true
        implicitWidth: caption.implicitWidth + Math.round(28 * root.u)
        height: Math.round(36 * root.u)
        width: implicitWidth
        radius: Math.round(root.t.radius * root.u)
        color: area.pressed ? root.t.select : (area.containsMouse || activeFocus ? root.t.hoverFill : "transparent")
        border.width: 1
        border.color: area.containsMouse || activeFocus ? root.t.focus : "transparent"
        Behavior on color { ColorAnimation { duration: 120 } }
        Keys.onReturnPressed: action.triggered()
        Keys.onSpacePressed: action.triggered()
        Text {
            id: caption
            anchors.centerIn: parent
            text: action.label
            color: area.pressed ? root.t.selectText : root.t.text
            font.pixelSize: Math.round(15 * root.u)
        }
        MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; onClicked: action.triggered() }
    }

    // ---- login card ----
    Rectangle {
        id: card
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: rule.bottom
        anchors.topMargin: Math.round(34 * root.u)
        width: form.width + Math.round(56 * root.u)
        height: form.height + Math.round(48 * root.u)
        radius: Math.round(root.t.radius * 1.5 * root.u)
        color: root.t.glass
        border.width: 1
        border.color: root.t.edge

        SequentialAnimation {
            id: shake
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: 14; duration: 50 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: -14; duration: 80 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: 8; duration: 70 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: 0; duration: 60 }
        }

        Column {
            id: form
            anchors.centerIn: parent
            spacing: Math.round(12 * root.u)

            Field {
                id: userField
                placeholder: "Name"
                text: userModel.lastUser
                onAccepted: passField.grab()
                KeyNavigation.tab: passField.editor
            }
            Row {
                spacing: Math.round(10 * root.u)
                Field {
                    id: passField
                    width: userField.width - enter.width - parent.spacing
                    placeholder: "Password"
                    secret: true
                    onAccepted: root.login()
                    KeyNavigation.tab: enter
                }
                Rectangle {
                    id: enter
                    width: height
                    height: passField.height
                    radius: passField.radius
                    activeFocusOnTab: true
                    color: enterArea.pressed ? root.t.selectDeep : root.t.select
                    border.width: activeFocus ? 2 : 0
                    border.color: root.t.ornament
                    Keys.onReturnPressed: root.login()
                    Keys.onSpacePressed: root.login()
                    // arrow drawn from two rotated bars so no icon font is needed
                    Item {
                        anchors.centerIn: parent
                        width: Math.round(14 * root.u); height: width
                        Rectangle { width: parent.width; height: 2; color: root.t.selectText; anchors.verticalCenter: parent.verticalCenter }
                        Rectangle { width: parent.width * 0.55; height: 2; color: root.t.selectText; rotation: 45; antialiasing: true
                                    x: parent.width * 0.52; y: parent.height / 2 - parent.width * 0.2 - 1 }
                        Rectangle { width: parent.width * 0.55; height: 2; color: root.t.selectText; rotation: -45; antialiasing: true
                                    x: parent.width * 0.52; y: parent.height / 2 + parent.width * 0.2 - 1 }
                    }
                    MouseArea { id: enterArea; anchors.fill: parent; onClicked: root.login() }
                }
            }
            Text {
                id: message
                width: userField.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                visible: text.length > 0 || keyboard.capsLock
                text: ""
                color: root.t.negative
                font.pixelSize: Math.round(14 * root.u)
                Text {
                    anchors.fill: parent
                    horizontalAlignment: Text.AlignHCenter
                    visible: message.text.length === 0 && keyboard.capsLock
                    text: "Caps Lock is on"
                    color: root.t.neutral
                    font: message.font
                }
            }
        }
    }

    // ---- session picker (click to cycle) and power actions ----
    Item {
        visible: false
        Repeater {
            id: sessions
            model: sessionModel
            delegate: Item { property string sessionName: model.name }
        }
    }
    Row {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: Math.round(28 * root.u)
        spacing: Math.round(8 * root.u)
        Action {
            readonly property var current: sessions.count > 0 ? sessions.itemAt(root.sessionIndex) : null
            label: "Session: " + (current ? current.sessionName : "default")
            onTriggered: if (sessions.count > 0) root.sessionIndex = (root.sessionIndex + 1) %% sessions.count
        }
    }
    Row {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Math.round(28 * root.u)
        spacing: Math.round(8 * root.u)
        Action { label: "Suspend"; visible: sddm.canSuspend; onTriggered: sddm.suspend() }
        Action { label: "Restart"; visible: sddm.canReboot; onTriggered: sddm.reboot() }
        Action { label: "Shut Down"; visible: sddm.canPowerOff; onTriggered: sddm.powerOff() }
    }

    Component.onCompleted: {
        if (userField.text.length === 0) {
            userField.grab();
        } else {
            passField.grab();
        }
    }
}
"""


def _rgba(hex_color: str, alpha: float) -> str:
    """#AARRGGBB, the form QML colour properties accept."""
    return f"#{round(alpha * 255):02x}{hex_color.lstrip('#')}"


def _variant_colors(pal: Palette) -> dict:
    return {
        "base": pal.complementary if pal.dark else pal.window,
        "scrim": pal.scrim[0],
        "scrimOpacity": pal.scrim[1],
        "world": pal.world,
        "text": pal.text,
        "textDim": pal.text_dim,
        "ornament": pal.ornament if pal.dark else pal.ornament_deep,
        "glass": _rgba(pal.glass_bot, 0.78),
        "edge": _rgba(pal.edge_top[0], 0.7),
        "field": _rgba(pal.view, 0.9),
        "line": _rgba(pal.text_dim, 0.45),
        "focus": pal.focus,
        "select": pal.select,
        "selectDeep": pal.select_deep,
        "selectText": pal.select_text,
        "hoverFill": _rgba(pal.hover, 0.22),
        "negative": pal.negative,
        "neutral": pal.neutral,
        # Square fields for the clipped style, rounded ones for the heading style.
        "radius": 0 if pal.corner == "cut" else 10,
    }


def main_qml() -> str:
    variants = {pal.key: _variant_colors(pal) for pal in VARIANTS}
    return MAIN_QML % {"variants": json.dumps(variants, indent=8, ensure_ascii=False), "fallback": ORG_XIII.key}


METADATA = f"""[SddmGreeterTheme]
Name=Kingdom Hearts
Description=Organization XIII (dark) and Sora (light) login screen
Author=Kingdom Hearts Plasma theme
License=Fan project; artwork (c) Disney / Square Enix
Type=sddm-theme
Version=2.0
Screenshot=preview.jpg
MainScript=Main.qml
ConfigFile=theme.conf
Theme-Id={THEME_ID}
Theme-API=2.0
QtVersion=6
"""

THEME_CONF = f"""[General]
# OrgXIII (dark) or Sora (light)
variant={ORG_XIII.key}
"""


def _run(cmd: list[str], what: str) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        log.error("sddm", f"{what}: tool is not installed", error=exc, command=cmd[0])
        raise
    except subprocess.TimeoutExpired as exc:
        log.error("sddm", f"{what} timed out", error=exc, command=cmd[0])
        raise
    except subprocess.CalledProcessError as exc:
        log.error("sddm", f"{what} failed", error=exc, command=cmd[0], stderr=exc.stderr[-1500:])
        raise


def build(out: Path, pal: Palette) -> Path:
    root = out / "sddm" / THEME_ID
    with log.timed("sddm", "build login theme", variant=pal.key, target=str(root)):
        wallpaper = wallpapers.default_image(out, pal)
        write_text(root / "Main.qml", main_qml())
        write_text(root / "metadata.desktop", METADATA)
        write_text(root / "theme.conf", THEME_CONF)
        assets = root / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        stale = assets / f"emblem-{pal.key}.svg"
        if stale.exists():
            stale.unlink()
            log.info("sddm", "removed an emblem from an older layout", path=str(stale))
        font = FONTS / FONT
        # The emblem alone: a full logo does not read over a detailed picture.
        mark = ASSETS / "reference" / pal.launcher_art
        for needed in (font, mark):
            if not needed.is_file():
                log.error("sddm", "asset is missing", path=str(needed))
                raise FileNotFoundError(needed)
        shutil.copyfile(font, assets / FONT)
        _run(
            ["magick", str(mark), "-trim", "+repage", "-resize", "600x600>", f"PNG32:{assets / f'emblem-{pal.key}.png'}"],
            "emblem",
        )
        targets = [assets / f"background-{pal.key}.jpg"]
        if pal.key == ORG_XIII.key:
            targets.append(root / "preview.jpg")
        for target in targets:
            shutil.copyfile(wallpaper, target)
        log.info("sddm", "login theme staged (install needs root: ./install.py sddm)", variant=pal.key)
    return root
