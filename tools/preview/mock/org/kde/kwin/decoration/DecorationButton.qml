import QtQuick

// Stand-in for KWin's DecorationButton. The mock window can pin one button
// type into its hover or pressed state so those looks appear in a still image.
Item {
    id: button
    property int buttonType: 0
    property bool hovered: decoration.demoHover === buttonType
    property bool pressed: decoration.demoPressed === buttonType
    property bool toggled: decoration.demoToggled === buttonType
}
