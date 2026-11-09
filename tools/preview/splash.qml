import QtQuick
Item { id: w; width: 1280; height: 720; property string splash: ""; property int _delay: 2600
    Loader { id: l; anchors.fill: parent; source: w.splash; onLoaded: { item.stage = 1; t.start() } }
    Timer { id: t; interval: 150; repeat: true; onTriggered: { if (l.item.stage < 4) l.item.stage += 1 } } }
