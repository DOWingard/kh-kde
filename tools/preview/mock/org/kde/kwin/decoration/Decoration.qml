import QtQuick

// Stand-in for KWin's Decoration root item; sized like the real one.
Item {
    property QtObject borders: Borders {}
    property QtObject maximizedBorders: Borders {}
    property QtObject extendedBorders: Borders {}
    property QtObject padding: Borders {}
    property bool alpha: true

    width: decoration.client.width + decoration.borderLeft + decoration.borderRight
           + (decoration.client.maximized ? 0 : (padding.left + padding.right))
    height: decoration.client.height + decoration.borderTop + decoration.borderBottom
            + (decoration.client.maximized ? 0 : (padding.top + padding.bottom))
}
