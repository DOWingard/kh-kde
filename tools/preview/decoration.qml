import QtQuick

// Decoration states side by side over the variant's wallpaper.
Item {
    id: scene
    width: 1280
    height: 720

    property url theme
    property url wallpaper
    property color bodyColor
    property color bodyText

    Image {
        anchors.fill: parent
        source: scene.wallpaper
        fillMode: Image.PreserveAspectCrop
    }

    MockWindow {
        x: 40; y: 30
        theme: scene.theme; bodyColor: scene.bodyColor; bodyText: scene.bodyText
        caption: "Dolphin — Destiny Islands"
        note: "active"
        clientWidth: 560; clientHeight: 250
    }
    MockWindow {
        x: 660; y: 30
        theme: scene.theme; bodyColor: scene.bodyColor; bodyText: scene.bodyText
        caption: "Journal"
        active: false
        note: "inactive"
        clientWidth: 520; clientHeight: 170
    }
    MockWindow {
        x: 660; y: 260
        theme: scene.theme; bodyColor: scene.bodyColor; bodyText: scene.bodyText
        caption: "A very long window caption that has to be cut short somewhere before the buttons"
        note: "hover on close, every button, long caption"
        buttonsLeft: [1, 3]
        buttonsRight: [4, 8, 9, 10, 5, 6, 7]
        demoHover: 7
        demoToggled: 8
        clientWidth: 520; clientHeight: 120
    }
    MockWindow {
        x: 40; y: 370
        theme: scene.theme; bodyColor: scene.bodyColor; bodyText: scene.bodyText
        caption: "Konsole"
        note: "hover on maximise, pressed minimise"
        demoHover: 6
        demoPressed: 5
        clientWidth: 300; clientHeight: 110
    }
    MockWindow {
        x: 0; y: 590
        theme: scene.theme; bodyColor: scene.bodyColor; bodyText: scene.bodyText
        caption: "Maximised window"
        note: "maximised"
        maximized: true
        clientWidth: 1280; clientHeight: 100
    }
}
