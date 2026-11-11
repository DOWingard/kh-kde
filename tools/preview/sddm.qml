import QtQuick
Item { id: w; width: 1280; height: 720
    property string main: ""; property string variantName: "OrgXIII"; property bool fail: false; property int _delay: 1500
    QtObject { id: sddm; property bool canPowerOff: true; property bool canReboot: true; property bool canSuspend: true; property string hostName: "castle"
        signal loginFailed(); signal loginSucceeded(); signal informationMessage(string message)
        function login(u, p, i) { console.log("LOGIN", u, p.length, i); loginFailed() }
        function powerOff() {} function reboot() {} function suspend() {} }
    QtObject { id: userModel; property string lastUser: "roxas"; property int lastIndex: 0 }
    ListModel { id: sessionModel; property int lastIndex: 1
        ListElement { name: "Plasma (X11)"; file: "plasmax11" } ListElement { name: "Plasma (Wayland)"; file: "plasma" } }
    QtObject { id: keyboard; property bool capsLock: w.fail; property bool numLock: false }
    QtObject { id: config; property string variant: w.variantName }
    Loader { id: l; anchors.fill: parent; source: w.main; onStatusChanged: if (status == Loader.Error) console.log("LOAD ERROR")
        onLoaded: if (w.fail) t.start() }
    Timer { id: t; interval: 300; onTriggered: l.item.login() }
}
