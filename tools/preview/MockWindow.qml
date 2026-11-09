import QtQuick

// A window frame drawn by a decoration theme's main.qml, with stand-ins for the
// objects KWin provides. `decoration` and `decorationSettings` are found by the
// loaded theme through the enclosing scope, as KWin's context properties are.
Item {
    id: win

    property url theme
    property string caption: "Window"
    property bool active: true
    property bool maximized: false
    property int clientWidth: 420
    property int clientHeight: 200
    property color bodyColor: "#ffffff"
    property color bodyText: "#000000"
    property string note: ""
    property var buttonsLeft: [1]
    property var buttonsRight: [5, 6, 7]
    property int demoHover: -1
    property int demoPressed: -1
    property int demoToggled: -1

    property alias decoration: deco
    property QtObject decorationSettings: QtObject {
        property bool closeOnDoubleClickOnMenu: false
        property int borderSize: 3
        // The preview shows every button, so every action counts as available.
        property bool onAllDesktopsAvailable: true
    }

    width: frame.item ? frame.item.width : 0
    height: frame.item ? frame.item.height : 0

    QtObject {
        id: deco
        property QtObject client: QtObject {
            property string caption: win.caption
            property bool active: win.active
            property bool maximized: win.maximized
            property int width: win.clientWidth
            property int height: win.clientHeight
            property bool shaded: false
            property bool closeable: true
            property bool maximizeable: true
            property bool minimizeable: true
            property bool onAllDesktops: false
            property bool keepAbove: false
            property bool keepBelow: false
            property bool shadeable: true
            property bool providesContextHelp: true
            property bool hasApplicationMenu: false
        }
        readonly property QtObject sides: frame.item ? (win.maximized ? frame.item.maximizedBorders : frame.item.borders) : null
        property int borderLeft: sides ? sides.left : 0
        property int borderRight: sides ? sides.right : 0
        property int borderTop: sides ? sides.top : 0
        property int borderBottom: sides ? sides.bottom : 0
        property bool animationsSupported: false
        property var buttonsLeft: win.buttonsLeft
        property var buttonsRight: win.buttonsRight
        property int demoHover: win.demoHover
        property int demoPressed: win.demoPressed
        property int demoToggled: win.demoToggled

        function installTitleItem(item) {}
        function readConfig(key, fallback) { return fallback; }
        function requestShowWindowMenu() {}
        function requestClose() {}
    }

    Rectangle {
        z: 1  // KWin draws the client over the decoration
        x: (win.maximized || !frame.item ? 0 : frame.item.padding.left) + deco.borderLeft
        y: (win.maximized || !frame.item ? 0 : frame.item.padding.top) + deco.borderTop
        width: win.clientWidth
        height: win.clientHeight
        color: win.bodyColor
        Text {
            anchors { left: parent.left; top: parent.top; margins: 14 }
            text: win.note
            color: win.bodyText
            font.pixelSize: 12
            opacity: 0.7
        }
    }

    Loader {
        id: frame
        source: win.theme
    }
}
