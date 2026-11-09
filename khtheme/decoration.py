"""Window decoration: a QML theme for KWin's Aurorae engine.

The shapes follow the games' command menus rather than a plain title bar:

* cut — Organization XIII. The black, white-lined menu of the second game:
  clipped corners, the caption in a slanted header plate.
* heading — Sora. The first game's menu: one rounded and one square corner,
  the caption in a heading plate rounded on opposite corners.

Buttons are the round controller prompts the games show beside commands. The
frame, shadow, caption plate and buttons are rendered from the palette as PNGs
(at 1x and 2x); the window-menu button is the variant's emblem art.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import log
from .palette import MENU_BLUE, Palette, mix
from .svg import fill_template, fmt, write_text

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT = "KHMenuBold.otf"

PAD = 26  # shadow margin round the window
TITLE = 32
TITLE_MAX = 30  # title height of a maximised window
LINE = 2  # frame thickness at the sides and bottom
CAP = 40  # unstretched frame width at each end of the title bar
FOOT = 14  # unstretched frame height at the bottom
MID = 16  # stretched part of the frame image
BUTTON = 22
EMBLEM = 26  # the window-menu emblem; larger than a button so its detail survives
TAB_H = 24
TAB_CAP = 14
GRIP = 6  # invisible resize margin outside the frame (sides and bottom; KWin gives the top none)
TOP_GRIP = 3  # rows along the top edge, inside the frame, that resize; ends where the buttons start

SCALES = (1, 2)


# --- shapes -----------------------------------------------------------------------
def _outline(pal: Palette, x0: float, y0: float, x1: float, y1: float, inset: float = 0.0, top_only: float = 0.0) -> str:
    """Window silhouette, optionally inset (for strokes) or cut off below the
    title bar (`top_only` = title height)."""
    a, b, c, d = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    if top_only:
        d = y0 + top_only
    if pal.corner == "cut":
        cut = 9 - 0.586 * inset
        return f"M{fmt(a + cut)},{fmt(b)} L{fmt(c - cut)},{fmt(b)} L{fmt(c)},{fmt(b + cut)} L{fmt(c)},{fmt(d)} L{fmt(a)},{fmt(d)} L{fmt(a)},{fmt(b + cut)} Z"
    big, small = 14 - inset, max(0.5, 3 - inset)
    return (
        f"M{fmt(a + big)},{fmt(b)} L{fmt(c - small)},{fmt(b)} A{fmt(small)},{fmt(small)} 0 0 1 {fmt(c)},{fmt(b + small)} "
        f"L{fmt(c)},{fmt(d)} L{fmt(a)},{fmt(d)} L{fmt(a)},{fmt(b + big)} A{fmt(big)},{fmt(big)} 0 0 1 {fmt(a + big)},{fmt(b)} Z"
    )


def _style(pal: Palette, active: bool) -> dict:
    """Colours of the frame for one state."""
    if pal.corner == "cut":
        return {
            "top": pal.title_top if active else pal.title_inactive_top,
            "bot": pal.title_bot if active else pal.title_inactive_bot,
            "frame": pal.complementary_alt,
            "edge": (pal.select_hi, 0.62) if active else (pal.ornament_deep, 0.5),
            "edge_w": 1.0,
            "rule": (pal.select_hi, 0.22) if active else (pal.ornament_deep, 0.2),
            "rule_w": 1.0,
            "glow": pal.glow if active else None,
            "shadow": (pal.shadow, 0.8 if active else 0.5),
        }
    navy = MENU_BLUE[0]
    return {
        "top": pal.title_top if active else pal.title_inactive_top,
        "bot": pal.title_bot if active else pal.title_inactive_bot,
        "frame": navy if active else mix(navy, "#ffffff", 0.45),
        "edge": (navy, 1.0) if active else (mix(navy, "#ffffff", 0.45), 1.0),
        "edge_w": 2.0,
        "rule": (pal.ornament, 1.0) if active else (mix(pal.ornament, "#ffffff", 0.55), 1.0),
        "rule_w": 2.0,
        "glow": None,
        "shadow": (pal.shadow, pal.shadow_strength if active else pal.shadow_strength * 0.6),
    }


def frame_svg(pal: Palette, active: bool) -> str:
    st = _style(pal, active)
    width = 2 * PAD + 2 * CAP + MID
    height = PAD + TITLE + MID + FOOT + PAD
    x0, y0, x1, y1 = PAD, PAD, width - PAD, height - PAD
    half = st["edge_w"] / 2
    shadow_color, shadow_alpha = st["shadow"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<filter id="soft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="8"/></filter>',
        '<filter id="halo" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="4.5"/></filter>',
        f'<linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{st["top"]}"/>'
        f'<stop offset="1" stop-color="{st["bot"]}"/></linearGradient>',
        # Shadow and glow are kept outside the window, so nothing tints a
        # translucent client from behind.
        f'<clipPath id="outside"><path clip-rule="evenodd" d="M0,0 H{width} V{height} H0 Z {_outline(pal, x0, y0, x1, y1)}"/></clipPath>',
        "</defs>",
        '<g clip-path="url(#outside)">',
        f'<path d="{_outline(pal, x0, y0, x1, y1)}" transform="translate(0 5)" fill="{shadow_color}" '
        f'fill-opacity="{fmt(shadow_alpha)}" filter="url(#soft)"/>',
    ]
    if st["glow"]:
        color, alpha = st["glow"]
        parts.append(
            f'<path d="{_outline(pal, x0, y0, x1, y1)}" fill="none" stroke="{color}" stroke-width="5" '
            f'stroke-opacity="{fmt(min(1.0, alpha * 2.4))}" filter="url(#halo)"/>'
        )
    parts.append("</g>")
    # Sides and bottom first, then the bar over their upper ends.
    body = y0 + TITLE
    parts += [
        f'<rect x="{x0}" y="{body}" width="{LINE}" height="{y1 - body}" fill="{st["frame"]}"/>',
        f'<rect x="{x1 - LINE}" y="{body}" width="{LINE}" height="{y1 - body}" fill="{st["frame"]}"/>',
        f'<rect x="{x0}" y="{y1 - LINE}" width="{x1 - x0}" height="{LINE}" fill="{st["frame"]}"/>',
        f'<path d="{_outline(pal, x0, y0, x1, y1, top_only=TITLE)}" fill="url(#bar)"/>',
    ]
    rule_color, rule_alpha = st["rule"]
    inset = st["edge_w"]
    parts.append(
        f'<rect x="{fmt(x0 + inset)}" y="{fmt(body - st["rule_w"])}" width="{fmt(x1 - x0 - 2 * inset)}" '
        f'height="{fmt(st["rule_w"])}" fill="{rule_color}" fill-opacity="{fmt(rule_alpha)}"/>'
    )
    edge_color, edge_alpha = st["edge"]
    parts.append(
        f'<path d="{_outline(pal, x0, y0, x1, y1, inset=half)}" fill="none" stroke="{edge_color}" '
        f'stroke-opacity="{fmt(edge_alpha)}" stroke-width="{fmt(st["edge_w"])}" stroke-linejoin="miter"/>'
    )
    parts.append("</svg>")
    return "".join(parts)


def bar_svg(pal: Palette, active: bool) -> str:
    """Title bar of a maximised window: the bar's fill and rule, no frame."""
    st = _style(pal, active)
    rule_color, rule_alpha = st["rule"]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="{TITLE_MAX}" viewBox="0 0 8 {TITLE_MAX}"><defs>'
        f'<linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{st["top"]}"/>'
        f'<stop offset="1" stop-color="{st["bot"]}"/></linearGradient></defs>'
        f'<rect width="8" height="{TITLE_MAX}" fill="url(#bar)"/>'
        f'<rect y="{fmt(TITLE_MAX - st["rule_w"])}" width="8" height="{fmt(st["rule_w"])}" fill="{rule_color}" '
        f'fill-opacity="{fmt(rule_alpha)}"/></svg>'
    )


def tab_svg(pal: Palette, active: bool) -> str:
    """The plate behind the caption."""
    width = 2 * TAB_CAP + 8
    if pal.corner == "cut":
        lean = 7.0
        shape = f"M{fmt(lean + 0.75)},0.75 L{fmt(width - 0.75)},0.75 L{fmt(width - lean - 0.75)},{fmt(TAB_H - 0.75)} L0.75,{fmt(TAB_H - 0.75)} Z"
        fill = pal.complementary
        stroke, alpha = (pal.select_hi, 0.95) if active else (pal.ornament_deep, 0.55)
        defs = ""
        paint = fill
    else:
        r = 10.0
        a, b, c, d = 0.75, 0.75, width - 0.75, TAB_H - 0.75
        shape = (
            f"M{fmt(a + r)},{fmt(b)} L{fmt(c)},{fmt(b)} L{fmt(c)},{fmt(d - r)} A{fmt(r)},{fmt(r)} 0 0 1 {fmt(c - r)},{fmt(d)} "
            f"L{fmt(a)},{fmt(d)} L{fmt(a)},{fmt(b + r)} A{fmt(r)},{fmt(r)} 0 0 1 {fmt(a + r)},{fmt(b)} Z"
        )
        if active:
            top, bot = mix(MENU_BLUE[0], MENU_BLUE[1], 0.18), pal.text
            stroke, alpha = pal.ornament, 1.0
        else:
            top, bot = "#ffffff", pal.title_inactive_top
            stroke, alpha = mix(MENU_BLUE[0], "#ffffff", 0.6), 1.0
        defs = (
            f'<defs><linearGradient id="plate" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
            f'<stop offset="1" stop-color="{bot}"/></linearGradient></defs>'
        )
        paint = "url(#plate)"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{TAB_H}" viewBox="0 0 {width} {TAB_H}">{defs}'
        f'<path d="{shape}" fill="{paint}" stroke="{stroke}" stroke-opacity="{fmt(alpha)}" stroke-width="1.5" '
        'stroke-linejoin="round"/></svg>'
    )


# Glyphs on the 22-unit button grid, drawn as strokes.
GLYPHS = {
    "close": '<path d="M7.6,7.6 L14.4,14.4 M14.4,7.6 L7.6,14.4"/>',
    "maximize": '<rect x="7.4" y="7.4" width="7.2" height="7.2" rx="0.6"/>',
    "restore": '<rect x="6.9" y="9" width="5.8" height="5.8" rx="0.5"/><path d="M9.6,8.6 V6.9 H15.1 V12.4 H13.2"/>',
    "minimize": '<path d="M7.1,8.3 L14.9,8.3 L11,14.7 Z"/>',
    "alldesktops": '<circle cx="11" cy="11" r="2.6"/>',
    "keepabove": '<path d="M7.4,12.7 L11,8.7 L14.6,12.7"/>',
    "keepbelow": '<path d="M7.4,9.3 L11,13.3 L14.6,9.3"/>',
    "shade": '<path d="M7.2,7.9 H14.8 M8.2,14 L11,11.2 L13.8,14"/>',
    "help": '<path d="M8.8,9 Q8.8,6.8 11,6.8 Q13.2,6.8 13.2,8.8 Q13.2,10.2 11,11 V12.2 M11,14.9 V15"/>',
    "appmenu": '<path d="M7.4,8 H14.6 M7.4,11 H14.6 M7.4,14 H14.6"/>',
}
LOOKS = ("normal", "inactive", "on", "hover", "pressed")


def _button_colors(pal: Palette, art: str, look: str) -> tuple[str | None, tuple[str, float], str]:
    """(fill, (ring, alpha), glyph) for one button state."""
    close = art == "close"
    dark = pal.corner == "cut"
    if look == "normal":
        return None, (pal.glyph, 0.88), pal.glyph
    if look == "inactive":
        return None, (pal.glyph_inactive, 0.7), pal.glyph_inactive
    if look == "on":
        return (pal.hover, (pal.hover, 1.0), pal.select_text) if dark else ("#ffffff", ("#ffffff", 1.0), pal.select_deep)
    if close:
        fill = pal.negative if look == "hover" else mix(pal.negative, "#000000", 0.22)
        return fill, (fill, 1.0), "#ffffff"
    if dark:
        fill = pal.select_hi if look == "hover" else pal.select_deep
        return fill, (fill, 1.0), pal.select_text
    fill = pal.ornament if look == "hover" else pal.ornament_deep
    return fill, (pal.ornament_pale if look == "hover" else fill, 1.0), pal.text if look == "hover" else "#ffffff"


def button_svg(pal: Palette, art: str, look: str) -> str:
    fill, (ring, ring_alpha), glyph = _button_colors(pal, art, look)
    disc = f'fill="{fill}"' if fill else 'fill="none"'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{BUTTON}" height="{BUTTON}" viewBox="0 0 {BUTTON} {BUTTON}">'
        f'<circle cx="11" cy="11" r="9.75" {disc} stroke="{ring}" stroke-opacity="{fmt(ring_alpha)}" stroke-width="1.5"/>'
        f'<g fill="none" stroke="{glyph}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{GLYPHS[art]}</g>'
        "</svg>"
    )


# --- QML ---------------------------------------------------------------------------
MAIN_QML = """import QtQuick
import org.kde.kwin.decoration

Decoration {
    id: root

    readonly property int pad: @@PAD@@
    readonly property int titleHeight: @@TITLE@@
    readonly property int maximizedTitleHeight: @@TITLE_MAX@@
    readonly property int line: @@LINE@@
    readonly property int buttonSize: @@BUTTON@@
    readonly property bool active: decoration.client.active
    readonly property bool maxed: decoration.client.maximized
    // Off until the first frame is up, so windows do not fade in their frame.
    property bool animate: false

    alpha: true

    function image(name) {
        return Qt.resolvedUrl("../images/" + name + ".png");
    }

    Component.onCompleted: {
        borders.left = line;
        borders.right = line;
        borders.bottom = line;
        borders.top = titleHeight;
        maximizedBorders.left = 0;
        maximizedBorders.right = 0;
        maximizedBorders.bottom = 0;
        maximizedBorders.top = maximizedTitleHeight;
        padding.left = pad;
        padding.right = pad;
        padding.top = pad;
        padding.bottom = pad;
        extendedBorders.setAllBorders(@@GRIP@@);
        animate = decoration.animationsSupported === true;
    }

    DecorationOptions {
        id: options
        deco: decoration
    }

    FontLoader {
        id: menuFont
        source: Qt.resolvedUrl("../fonts/@@FONT@@")
    }

    // Frame with its shadow. The two states cross-fade; they are never both
    // fully drawn, which would double the shadow.
    BorderImage {
        anchors.fill: parent
        visible: !root.maxed && opacity > 0
        opacity: 1 - frameActive.opacity
        source: root.image("frame-inactive")
        border { left: @@SLICE_X@@; right: @@SLICE_X@@; top: @@SLICE_TOP@@; bottom: @@SLICE_BOTTOM@@ }
    }
    BorderImage {
        id: frameActive
        anchors.fill: parent
        visible: !root.maxed && opacity > 0
        opacity: root.active ? 1 : 0
        source: root.image("frame-active")
        border { left: @@SLICE_X@@; right: @@SLICE_X@@; top: @@SLICE_TOP@@; bottom: @@SLICE_BOTTOM@@ }
        Behavior on opacity {
            enabled: root.animate
            NumberAnimation { duration: 140 }
        }
    }
    Image {
        visible: root.maxed
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: root.maximizedTitleHeight
        source: root.image(root.active ? "bar-active" : "bar-inactive")
        fillMode: Image.Stretch
    }

    Item {
        id: bar
        x: root.maxed ? 0 : root.pad
        y: root.maxed ? 0 : root.pad
        width: root.width - 2 * x
        height: root.maxed ? root.maximizedTitleHeight : root.titleHeight

        ButtonGroup {
            id: leftButtons
            height: @@EMBLEM@@
            spacing: @@SPACING@@
            explicitSpacer: root.buttonSize / 2
            buttons: options.titleButtonsLeft
            menuButton: menuComponent
            appMenuButton: appMenuComponent
            allDesktopsButton: allDesktopsComponent
            helpButton: helpComponent
            minimizeButton: minimizeComponent
            maximizeButton: maximizeComponent
            keepAboveButton: keepAboveComponent
            keepBelowButton: keepBelowComponent
            shadeButton: shadeComponent
            closeButton: closeComponent
            anchors { left: parent.left; leftMargin: @@EDGE@@; verticalCenter: parent.verticalCenter }
        }

        ButtonGroup {
            id: rightButtons
            height: @@EMBLEM@@
            spacing: @@SPACING@@
            explicitSpacer: root.buttonSize / 2
            buttons: options.titleButtonsRight
            menuButton: menuComponent
            appMenuButton: appMenuComponent
            allDesktopsButton: allDesktopsComponent
            helpButton: helpComponent
            minimizeButton: minimizeComponent
            maximizeButton: maximizeComponent
            keepAboveButton: keepAboveComponent
            keepBelowButton: keepBelowComponent
            shadeButton: shadeComponent
            closeButton: closeComponent
            anchors { right: parent.right; rightMargin: @@EDGE@@; verticalCenter: parent.verticalCenter }
        }

        // The caption sits in a plate that grows with the text, like the
        // header of a command menu.
        BorderImage {
            id: plate
            readonly property real room: rightButtons.x - x - @@GAP@@
            anchors { left: leftButtons.right; leftMargin: leftButtons.width > 0 ? @@GAP@@ : 0; verticalCenter: parent.verticalCenter }
            width: Math.min(caption.implicitWidth + 2 * @@TAB_PAD@@, Math.max(0, room))
            height: @@TAB_H@@
            visible: width >= 3 * @@TAB_PAD@@
            source: root.image(root.active ? "tab-active" : "tab-inactive")
            border { left: @@TAB_CAP@@; right: @@TAB_CAP@@; top: 0; bottom: 0 }

            Text {
                id: caption
                anchors { fill: parent; leftMargin: @@TAB_PAD@@; rightMargin: @@TAB_PAD@@; topMargin: @@TEXT_NUDGE@@ }
                text: decoration.client.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
                color: root.active ? "@@TEXT@@" : "@@TEXT_INACTIVE@@"
                font.family: menuFont.status === FontLoader.Ready ? menuFont.name : options.titleFont.family
                font.weight: Font.Bold
                font.pixelSize: 13
                Behavior on color {
                    enabled: root.animate
                    ColorAnimation { duration: 140 }
                }
            }
        }
    }

    // What KWin treats as the title bar: dragging here moves the window and the
    // pointer stays an arrow; the rows of the top border above it resize.
    // KWin takes this item's place in the scene as a position inside the window
    // frame, and the frame starts at the scene's origin once the shadow margin
    // is left out. So unlike the visible bar it must not be offset by the
    // margin, or nearly the whole bar, buttons included, turns into a resize
    // handle. It has no children on purpose: with children KWin would use
    // their bounding box instead of the item.
    Item {
        id: titleArea
        x: root.maxed ? 0 : root.line
        y: root.maxed ? 0 : @@TOP_GRIP@@
        width: (root.maxed ? root.width : root.width - 2 * root.pad) - 2 * x
        height: (root.maxed ? root.maximizedTitleHeight : root.titleHeight) - y
        Component.onCompleted: decoration.installTitleItem(titleArea)
    }

    Component { id: menuComponent; KhMenuButton {} }
    Component { id: appMenuComponent; KhButton { buttonType: DecorationOptions.DecorationButtonApplicationMenu; art: "appmenu" } }
    Component { id: allDesktopsComponent; KhButton { buttonType: DecorationOptions.DecorationButtonOnAllDesktops; art: "alldesktops" } }
    Component { id: helpComponent; KhButton { buttonType: DecorationOptions.DecorationButtonQuickHelp; art: "help" } }
    Component { id: minimizeComponent; KhButton { buttonType: DecorationOptions.DecorationButtonMinimize; art: "minimize" } }
    Component {
        id: maximizeComponent
        KhButton {
            buttonType: DecorationOptions.DecorationButtonMaximizeRestore
            art: decoration.client.maximized ? "restore" : "maximize"
        }
    }
    Component { id: keepAboveComponent; KhButton { buttonType: DecorationOptions.DecorationButtonKeepAbove; art: "keepabove" } }
    Component { id: keepBelowComponent; KhButton { buttonType: DecorationOptions.DecorationButtonKeepBelow; art: "keepbelow" } }
    Component { id: shadeComponent; KhButton { buttonType: DecorationOptions.DecorationButtonShade; art: "shade" } }
    Component { id: closeComponent; KhButton { buttonType: DecorationOptions.DecorationButtonClose; art: "close" } }
}
"""

BUTTON_QML = """import QtQuick
import org.kde.kwin.decoration

// A round prompt button. The resting image shows through a second image that
// fades in on hover and is swapped for the pressed one while held. The item is
// as tall as the emblem so a row of mixed buttons shares one centre line.
DecorationButton {
    id: button

    property string art
    readonly property string rest: button.toggled ? "on" : (decoration.client.active ? "normal" : "inactive")

    width: @@BUTTON@@
    height: @@EMBLEM@@
    opacity: enabled ? 1 : 0.35

    function image(look) {
        return Qt.resolvedUrl("../images/button-" + button.art + "-" + look + ".png");
    }

    Image {
        anchors.centerIn: parent
        width: @@BUTTON@@
        height: @@BUTTON@@
        source: button.image(button.rest)
    }
    Image {
        anchors.centerIn: parent
        width: @@BUTTON@@
        height: @@BUTTON@@
        source: button.image(button.pressed ? "pressed" : "hover")
        opacity: (button.hovered || button.pressed) ? 1 : 0
        Behavior on opacity {
            enabled: decoration.animationsSupported === true
            NumberAnimation { duration: 110 }
        }
    }
}
"""

MENU_QML = """import QtQuick
import org.kde.kwin.decoration

// The window-menu button, shown as the theme's emblem.
Item {
    id: menu

    width: @@EMBLEM@@
    height: @@EMBLEM@@

    Image {
        anchors.fill: parent
        source: Qt.resolvedUrl("../images/emblem.png")
        opacity: decoration.client.active ? (area.containsMouse ? 1 : 0.92) : 0.5
        scale: area.pressed ? 0.9 : (area.containsMouse ? 1.08 : 1)
        Behavior on scale {
            enabled: decoration.animationsSupported === true
            NumberAnimation { duration: 110 }
        }
    }

    // With "close on double click" enabled, a single click has to wait out the
    // double-click interval before it may open the menu.
    Timer {
        id: single
        interval: Qt.styleHints.mouseDoubleClickInterval
        onTriggered: decoration.requestShowWindowMenu()
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: (mouse) => {
            if (mouse.button === Qt.RightButton || !decorationSettings.closeOnDoubleClickOnMenu) {
                decoration.requestShowWindowMenu();
            } else {
                single.restart();
            }
        }
        onDoubleClicked: {
            if (decorationSettings.closeOnDoubleClickOnMenu) {
                single.stop();
                decoration.requestClose();
            }
        }
    }
}
"""


def _values(pal: Palette) -> dict[str, object]:
    return {
        "PAD": PAD,
        "TITLE": TITLE,
        "TITLE_MAX": TITLE_MAX,
        "LINE": LINE,
        "BUTTON": BUTTON,
        "EMBLEM": EMBLEM,
        "GRIP": GRIP,
        "TOP_GRIP": TOP_GRIP,
        "FONT": FONT,
        "SLICE_X": PAD + CAP,
        "SLICE_TOP": PAD + TITLE,
        "SLICE_BOTTOM": PAD + FOOT,
        "SPACING": 6,
        "EDGE": 11,
        "GAP": 8,
        "TAB_H": TAB_H,
        "TAB_CAP": TAB_CAP,
        "TAB_PAD": 16,
        "TEXT_NUDGE": 1,
        "TEXT": pal.title_text,
        "TEXT_INACTIVE": pal.title_inactive_text,
    }


# --- rendering ---------------------------------------------------------------------
def _run(cmd: list[str], what: str) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except FileNotFoundError as exc:
        log.error("decoration", "required tool is not installed", error=exc, tool=cmd[0], step=what)
        raise
    except subprocess.TimeoutExpired as exc:
        log.error("decoration", "image tool timed out", error=exc, tool=cmd[0], step=what)
        raise
    except subprocess.CalledProcessError as exc:
        log.error(
            "decoration", "image tool failed", error=exc, tool=cmd[0], step=what,
            stderr=exc.stderr.decode(errors="replace")[-1500:],
        )
        raise


def _render(svg: str, images: Path, name: str, tmp: Path) -> None:
    """Rasterise an SVG to <name>.png and <name>@2x.png."""
    source = tmp / f"{name}.svg"
    source.write_text(svg, encoding="utf-8")
    for scale in SCALES:
        suffix = "" if scale == 1 else f"@{scale}x"
        _run(["rsvg-convert", "-z", str(scale), "-o", str(images / f"{name}{suffix}.png"), str(source)], name)


def _emblem(pal: Palette, images: Path, tmp: Path) -> None:
    """The window-menu emblem. On the blue bar the blue heart needs a plate to
    stand on; the white sigil reads on black as it is."""
    source = ASSETS / "reference" / pal.launcher_art
    if not source.is_file():
        log.error("decoration", "emblem art is missing", path=str(source), variant=pal.key)
        raise FileNotFoundError(source)
    for scale in SCALES:
        size = EMBLEM * scale
        suffix = "" if scale == 1 else f"@{scale}x"
        target = images / f"emblem{suffix}.png"
        if pal.corner == "cut":
            flat = ["-fill", pal.launcher_flat, "-colorize", "100"] if pal.launcher_flat else []
            _run(
                ["magick", str(source), "-trim", "+repage", *flat, "-filter", "Lanczos", "-resize", f"{size}x{size}",
                 "-background", "none", "-gravity", "center", "-extent", f"{size}x{size}", f"PNG32:{target}"],
                "emblem",
            )
            continue
        plate = tmp / f"plate-{scale}.svg"
        half = EMBLEM / 2
        plate.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{EMBLEM}" height="{EMBLEM}" viewBox="0 0 {EMBLEM} {EMBLEM}">'
            f'<circle cx="{half}" cy="{half}" r="{half - 1}" fill="#ffffff" stroke="{pal.ornament}" stroke-width="1.5"/></svg>',
            encoding="utf-8",
        )
        plate_png = tmp / f"plate-{scale}.png"
        _run(["rsvg-convert", "-z", str(scale), "-o", str(plate_png), str(plate)], "emblem plate")
        inner = round(size * 0.7)
        _run(
            ["magick", str(plate_png), "(", str(source), "-trim", "+repage", "-filter", "Lanczos", "-resize",
             f"{inner}x{inner}", ")", "-gravity", "center", "-geometry", f"+0+{round(scale * 0.5)}", "-composite",
             f"PNG32:{target}"],
            "emblem",
        )


def _metadata(pal: Palette) -> str:
    meta = {
        "KPackageStructure": "KWin/Decoration",
        "KPlugin": {
            "Id": pal.decoration_id,
            "Name": pal.theme_name,
            "Description": f"{pal.title} window frame in the style of the games' command menus",
            "License": "Fan project; emblem artwork © Disney / Square Enix",
        },
    }
    return json.dumps(meta, indent=2, ensure_ascii=False) + "\n"


def build(out: Path, pal: Palette) -> Path:
    root = out / "kwin" / "decorations" / pal.decoration_id
    with log.timed("decoration", "build window decoration", variant=pal.key, target=str(root)):
        if root.exists():
            shutil.rmtree(root)
        images = root / "contents" / "images"
        images.mkdir(parents=True)
        font = ASSETS / "fonts" / FONT
        if not font.is_file():
            log.error("decoration", "caption font is missing", path=str(font))
            raise FileNotFoundError(font)
        (root / "contents" / "fonts").mkdir()
        shutil.copyfile(font, root / "contents" / "fonts" / FONT)

        values = _values(pal)
        write_text(root / "metadata.json", _metadata(pal))
        write_text(root / "contents" / "ui" / "main.qml", fill_template(MAIN_QML, values))
        write_text(root / "contents" / "ui" / "KhButton.qml", fill_template(BUTTON_QML, values))
        write_text(root / "contents" / "ui" / "KhMenuButton.qml", fill_template(MENU_QML, values))

        count = 0
        with tempfile.TemporaryDirectory(prefix="khdeco-") as tmp_name:
            tmp = Path(tmp_name)
            for active in (True, False):
                state = "active" if active else "inactive"
                _render(frame_svg(pal, active), images, f"frame-{state}", tmp)
                _render(bar_svg(pal, active), images, f"bar-{state}", tmp)
                _render(tab_svg(pal, active), images, f"tab-{state}", tmp)
                count += 3
            for art in GLYPHS:
                for look in LOOKS:
                    _render(button_svg(pal, art, look), images, f"button-{art}-{look}", tmp)
                    count += 1
            _emblem(pal, images, tmp)
        log.info("decoration", "window decoration written", variant=pal.key, images=count + 1, scales=list(SCALES))
    return root
