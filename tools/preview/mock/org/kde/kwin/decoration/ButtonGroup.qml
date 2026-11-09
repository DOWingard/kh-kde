import QtQuick

// Stand-in for KWin's ButtonGroup: one loader per configured button.
Item {
    id: group
    property var buttons: []
    property int explicitSpacer: 0
    property alias spacing: row.spacing
    property Component closeButton
    property Component helpButton
    property Component keepAboveButton
    property Component keepBelowButton
    property Component maximizeButton
    property Component menuButton
    property Component appMenuButton
    property Component minimizeButton
    property Component allDesktopsButton
    property Component shadeButton

    function componentFor(type) {
        switch (type) {
        case DecorationOptions.DecorationButtonMenu: return menuButton;
        case DecorationOptions.DecorationButtonApplicationMenu: return appMenuButton;
        case DecorationOptions.DecorationButtonOnAllDesktops: return allDesktopsButton;
        case DecorationOptions.DecorationButtonQuickHelp: return helpButton;
        case DecorationOptions.DecorationButtonMinimize: return minimizeButton;
        case DecorationOptions.DecorationButtonMaximizeRestore: return maximizeButton;
        case DecorationOptions.DecorationButtonClose: return closeButton;
        case DecorationOptions.DecorationButtonKeepAbove: return keepAboveButton;
        case DecorationOptions.DecorationButtonKeepBelow: return keepBelowButton;
        case DecorationOptions.DecorationButtonShade: return shadeButton;
        default: return null;
        }
    }

    width: row.width

    Row {
        id: row
        Repeater {
            model: group.buttons
            Loader { sourceComponent: group.componentFor(modelData) }
        }
    }
}
