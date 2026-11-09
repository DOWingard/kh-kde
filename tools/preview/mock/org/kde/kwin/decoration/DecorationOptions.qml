import QtQuick

// Stand-in for KWin's DecorationOptions; button layout comes from the mock window.
QtObject {
    enum DecorationButton {
        DecorationButtonNone,
        DecorationButtonMenu,
        DecorationButtonApplicationMenu,
        DecorationButtonOnAllDesktops,
        DecorationButtonQuickHelp,
        DecorationButtonMinimize,
        DecorationButtonMaximizeRestore,
        DecorationButtonClose,
        DecorationButtonKeepAbove,
        DecorationButtonKeepBelow,
        DecorationButtonShade,
        DecorationButtonResize,
        DecorationButtonExplicitSpacer
    }

    property var deco
    property font titleFont
    property var titleButtonsLeft: decoration.buttonsLeft
    property var titleButtonsRight: decoration.buttonsRight
    property int mousePressAndHoldInterval: 500
}
