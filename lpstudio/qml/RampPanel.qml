import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The smoke colour ramp at a glance: each colour's brightness against the step
// it should sit at (tick), whether the darker colours follow the light one, and
// how much brightness spread the last render actually has.
Rectangle {
    id: root
    property QtObject theme
    readonly property var stats: studio.contrast

    objectName: "rampPanel"
    color: theme.surface
    radius: theme.radius
    border.color: theme.line
    implicitHeight: body.implicitHeight + 28

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: "Colour ramp"
                font.pixelSize: 14
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            Switch {
                id: link
                objectName: "rampLink"
                text: "Link to light colour"
                checked: studio.rampLinked
                onToggled: studio.rampLinked = checked
                Connections {
                    target: studio
                    function onRampLinkedChanged() { link.checked = studio.rampLinked }
                }
            }
        }

        Label {
            text: studio.rampLinked
                  ? "Pick the light colour; the deep body, smoke ink and accent ink follow it at teal-marble's brightness steps."
                  : "Unlinked: every colour is set by hand. Keep each bar near its tick or the smoke has nothing to darken."
            color: root.theme.textDim
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Repeater {
            model: studio.rampSwatches
            delegate: RowLayout {
                required property var modelData
                readonly property bool isLight: modelData.key === "light"
                readonly property bool off: !isLight && Math.abs(modelData.luma - modelData.target) > Math.max(12, modelData.target * 0.35)
                Layout.fillWidth: true
                spacing: 8

                Rectangle {
                    implicitWidth: 14
                    implicitHeight: 14
                    radius: 7
                    color: modelData.color
                    border.color: root.theme.line
                }
                Label {
                    text: modelData.label
                    color: root.theme.textDim
                    font.pixelSize: 11
                    Layout.preferredWidth: 84
                }
                Item {
                    Layout.fillWidth: true
                    implicitHeight: 12
                    Rectangle {
                        anchors.fill: parent
                        radius: 6
                        color: root.theme.bg
                    }
                    Rectangle {
                        width: Math.max(6, parent.width * modelData.luma / 255)
                        height: parent.height
                        radius: 6
                        color: modelData.color
                        border.color: root.theme.line
                    }
                    Rectangle {
                        visible: !isLight
                        x: parent.width * modelData.target / 255 - 1
                        y: -3
                        width: 2
                        height: parent.height + 6
                        color: root.theme.text
                    }
                }
                Label {
                    text: isLight ? modelData.luma : modelData.luma + " / " + modelData.target
                    color: off ? root.theme.bad : root.theme.text
                    font.family: root.theme.mono
                    font.pixelSize: 11
                    horizontalAlignment: Text.AlignRight
                    Layout.preferredWidth: 64
                }
            }
        }

        RowLayout {
            visible: root.stats.iqr !== undefined
            Layout.fillWidth: true
            spacing: 8
            Label {
                text: "Spread"
                color: root.theme.textDim
                font.pixelSize: 11
                Layout.preferredWidth: 106
            }
            Label {
                objectName: "spreadLabel"
                text: root.stats.iqr === undefined ? ""
                      : Math.round(root.stats.iqr) + " levels across the middle half of the disc (teal-marble: 25)"
                color: root.stats.iqr !== undefined && root.stats.iqr < 12 ? root.theme.warn : root.theme.text
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
