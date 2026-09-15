import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A collapsible group of controls from paramSpec. A group of exactly one RGB
// triple is drawn as a ColorControl. While the panel is filtered, only matching
// controls show and every group with a match is open.
ColumnLayout {
    id: root
    property QtObject theme
    required property var group              // {group, controls}
    property string filter: ""
    property bool expanded: true
    property bool hidden: false              // e.g. a layer past the layer count
    property var lockedPrefixes: []
    signal toggleRequested(bool open)

    objectName: "group_" + group.group
    spacing: 8

    readonly property string colourPrefix: rgbPrefix(group.controls)
    readonly property bool open: expanded || filter.length > 0
    readonly property int matchCount: {
        var n = 0
        for (var i = 0; i < group.controls.length; i++) if (matches(group.controls[i])) n++
        return n
    }
    visible: matchCount > 0 && !hidden

    function rgbPrefix(cs) {
        if (cs.length !== 3 || !cs[0].key.endsWith("_r")) return ""
        var p = cs[0].key.slice(0, -2)
        return (cs[1].key === p + "_g" && cs[2].key === p + "_b") ? p : ""
    }
    function matches(c) {
        if (!filter) return true
        var f = filter.toLowerCase()
        if (group.group.toLowerCase().indexOf(f) >= 0) return true
        return !colourPrefix && c.label.toLowerCase().indexOf(f) >= 0
    }
    function flash() { flashTimer.restart() }

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 32
        radius: 6
        color: flashTimer.running ? root.theme.alpha(root.theme.accent, 0.28)
                                  : (headerMouse.containsMouse ? root.theme.surfaceHover : "transparent")
        Behavior on color { ColorAnimation { duration: 220 } }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            spacing: 8
            Label {
                text: root.open ? "▾" : "▸"
                color: root.theme.textDim
                font.pixelSize: 12
            }
            Label {
                text: root.group.group
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Rectangle {
                id: headerSwatch
                visible: root.colourPrefix !== "" && !root.open
                implicitWidth: 16
                implicitHeight: 16
                radius: 4
                color: root.colourPrefix ? studio.colorOf(root.colourPrefix) : "transparent"
                border.color: root.theme.line
                Connections {
                    target: studio
                    function onParamsChanged() {
                        if (root.colourPrefix) headerSwatch.color = studio.colorOf(root.colourPrefix)
                    }
                }
            }
            Label {
                visible: !root.colourPrefix
                text: root.group.controls.length
                color: root.theme.textDim
                font.pixelSize: 11
            }
        }
        MouseArea {
            id: headerMouse
            objectName: "groupHeader"
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.toggleRequested(!root.expanded)
        }
    }

    ColumnLayout {
        visible: root.open
        Layout.fillWidth: true
        Layout.leftMargin: 8
        Layout.rightMargin: 4
        Layout.bottomMargin: 6
        spacing: 10

        ColorControl {
            visible: root.colourPrefix !== ""
            Layout.fillWidth: true
            theme: root.theme
            prefix: root.colourPrefix || "smk_light"
            controls: root.colourPrefix ? root.group.controls : []
            locked: root.lockedPrefixes.indexOf(root.colourPrefix) >= 0
        }

        Repeater {
            model: root.colourPrefix ? [] : root.group.controls
            delegate: ParamControl {
                required property var modelData
                visible: root.matches(modelData)
                Layout.fillWidth: true
                spec: modelData
                theme: root.theme
            }
        }
    }

    Timer { id: flashTimer; interval: 900 }
}
