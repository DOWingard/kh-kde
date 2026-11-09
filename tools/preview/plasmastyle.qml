import QtQuick
import org.kde.ksvg as KSvg

Rectangle {
    id: root
    width: 1100; height: 560
    property string base: ""
    property bool dark: true
    property string textColor: dark ? "#e9ebf2" : "#14213d"
    property url wallpaper
    color: root.dark ? "#0b0b0c" : "#dff0fa"
    Image { anchors.fill: parent; source: root.wallpaper; fillMode: Image.PreserveAspectCrop }

    // ---- dialog with shadow, header and list items ----
    Item {
        x: 40; y: 30; width: 380; height: 330
        KSvg.FrameSvgItem { id: sh; imagePath: root.base + "/translucent/dialogs/background.svgz"; prefix: "shadow"
            x: -18; y: -18; width: parent.width + 36; height: parent.height + 36 }
        KSvg.FrameSvgItem { id: dlg; anchors.fill: parent; imagePath: root.base + "/translucent/dialogs/background.svgz" }
        KSvg.FrameSvgItem { imagePath: root.base + "/widgets/plasmoidheading.svgz"; prefix: "header"; x: 0; y: 0; width: parent.width; height: 46 }
        KSvg.FrameSvgItem { imagePath: root.base + "/widgets/plasmoidheading.svgz"; prefix: "footer"; x: 0; y: parent.height - 44; width: parent.width; height: 44 }
        Text { x: 18; y: 14; text: "Applications"; color: root.textColor; font.pixelSize: 15; font.bold: true }
        Column { x: dlg.margins.left + 6; y: 56; spacing: 4
            Repeater { model: ["normal", "hover", "selected", "selected+hover"]
                Item { width: 356; height: 36
                    KSvg.FrameSvgItem { anchors.fill: parent; imagePath: root.base + "/widgets/viewitem.svgz"; prefix: modelData }
                    Text { anchors.verticalCenter: parent.verticalCenter; x: 12; text: "List item — " + modelData; color: root.textColor; font.pixelSize: 13 }
                }
            }
        }
        Text { x: 18; y: parent.height - 30; text: "margins: " + dlg.margins.left + "/" + dlg.margins.top; color: root.textColor; font.pixelSize: 12 }
    }
    // ---- normal + solid dialog ----
    KSvg.FrameSvgItem { x: 460; y: 30; width: 180; height: 120; imagePath: root.base + "/dialogs/background.svgz"
        Text { anchors.centerIn: parent; text: "normal"; color: root.textColor } }
    KSvg.FrameSvgItem { x: 660; y: 30; width: 180; height: 120; imagePath: root.base + "/solid/dialogs/background.svgz"
        Text { anchors.centerIn: parent; text: "solid"; color: root.textColor } }
    KSvg.FrameSvgItem { x: 860; y: 30; width: 180; height: 120; imagePath: root.base + "/opaque/dialogs/background.svgz"
        Text { anchors.centerIn: parent; text: "opaque"; color: root.textColor } }
    // ---- tooltip ----
    Item { x: 470; y: 190; width: 200; height: 54
        KSvg.FrameSvgItem { imagePath: root.base + "/translucent/widgets/tooltip.svgz"; prefix: "shadow"; x: -12; y: -12; width: parent.width+24; height: parent.height+24 }
        KSvg.FrameSvgItem { anchors.fill: parent; imagePath: root.base + "/translucent/widgets/tooltip.svgz" }
        Text { anchors.centerIn: parent; text: "Tooltip text"; color: root.textColor; font.pixelSize: 13 }
    }
    // ---- desktop widget ----
    Item { x: 720; y: 190; width: 300; height: 150
        KSvg.FrameSvgItem { imagePath: root.base + "/translucent/widgets/background.svgz"; prefix: "shadow"; x: -16; y: -16; width: parent.width+32; height: parent.height+32 }
        KSvg.FrameSvgItem { anchors.fill: parent; imagePath: root.base + "/translucent/widgets/background.svgz" }
        Text { anchors.centerIn: parent; text: "22:41"; color: root.textColor; font.pixelSize: 44; font.family: "Noto Serif Display" }
    }
    // ---- floating panel with tasks ----
    Item { x: 40; y: 400; width: 1020; height: 38
        KSvg.FrameSvgItem { imagePath: root.base + "/translucent/widgets/panel-background.svgz"; prefix: "shadow"; x: -14; y: -14; width: parent.width+28; height: parent.height+28 }
        KSvg.FrameSvgItem { id: pnl; anchors.fill: parent; imagePath: root.base + "/translucent/widgets/panel-background.svgz" }
        Row { x: 50; height: parent.height; spacing: 0
            Repeater { model: ["normal", "hover", "focus", "attention", "minimized", "progress"]
                Item { width: 150; height: 38
                    KSvg.FrameSvgItem { anchors.fill: parent; imagePath: root.base + "/widgets/tasks.svgz"; prefix: modelData }
                    Text { anchors.centerIn: parent; text: modelData; color: root.textColor; font.pixelSize: 13 }
                }
            }
        }
    }
    // ---- docked panel (top border only) + solid ----
    KSvg.FrameSvgItem { x: 0; y: 480; width: 540; height: 38; imagePath: root.base + "/translucent/widgets/panel-background.svgz"; enabledBorders: KSvg.FrameSvg.TopBorder
        Row { x: 20; height: parent.height
            Repeater { model: ["north-focus", "focus", "west-focus", "east-focus"]
                Item { width: 120; height: 38
                    KSvg.FrameSvgItem { anchors.fill: parent; imagePath: root.base + "/widgets/tasks.svgz"; prefix: modelData }
                    Text { anchors.centerIn: parent; text: modelData; color: root.textColor; font.pixelSize: 12 } } } } }
    KSvg.FrameSvgItem { x: 560; y: 480; width: 540; height: 38; imagePath: root.base + "/solid/widgets/panel-background.svgz"; enabledBorders: KSvg.FrameSvg.TopBorder
        Text { anchors.centerIn: parent; text: "solid docked panel"; color: root.textColor } }
}
