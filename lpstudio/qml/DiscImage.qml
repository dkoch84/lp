import QtQuick

// A style image cut to a disc, the way it sits on a record. File images go
// through the "disc" provider (lpstudio/images.py), which scales and masks them
// off the UI thread; image:// sources (colour variations) arrive already masked.
Item {
    id: root
    property QtObject theme
    property string source: ""
    property real size: 60
    property bool selected: false

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    Image {
        anchors.fill: parent
        source: root.source.startsWith("file://") ? "image://disc/" + root.source.slice(7) : root.source
        sourceSize.width: Math.min(720, Math.round(root.size * 2))
        sourceSize.height: Math.min(720, Math.round(root.size * 2))
        asynchronous: true
        smooth: true
    }
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.color: root.selected ? root.theme.accent : root.theme.line
        border.width: root.selected ? 2 : 1
    }
}
