import QtQuick

// Stand-in for KWin's Borders type.
QtObject {
    property int left: 0
    property int right: 0
    property int top: 0
    property int bottom: 0

    function setAllBorders(value) { left = value; right = value; top = value; bottom = value; }
    function setBorders(value) { left = value; right = value; bottom = value; }
    function setSideBorders(value) { left = value; right = value; }
    function setTitle(value) { top = value; }
}
