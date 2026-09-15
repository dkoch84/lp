import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts

// One RGB colour: click the swatch to pick it, or type a hex value. The three
// channel sliders are one click away for exact numbers. A colour that follows
// the linked ramp is shown as locked; editing it anyway unlinks the ramp.
ColumnLayout {
    id: root
    property QtObject theme
    required property string prefix          // smk_light -> smk_light_r/g/b
    required property var controls           // the three channel specs
    property bool locked: false
    property string color: studio.colorOf(prefix)
    spacing: 8

    function luma(hex) {
        var c = Qt.color(hex)
        return Math.round(255 * (0.299 * c.r + 0.587 * c.g + 0.114 * c.b))
    }

    Connections {
        target: studio
        function onParamsChanged() {
            root.color = studio.colorOf(root.prefix)
            if (!hexField.activeFocus) hexField.text = root.color
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        Rectangle {
            objectName: "swatch_" + root.prefix
            implicitWidth: 52
            implicitHeight: 32
            radius: 6
            color: root.color
            border.color: root.theme.line
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: picker.open()
            }
        }

        TextField {
            id: hexField
            objectName: "hex_" + root.prefix
            Layout.preferredWidth: 96
            text: root.color
            font.family: root.theme.mono
            font.pixelSize: 12
            selectByMouse: true
            // Enter commits and lets go of the keyboard, so Ctrl+Z undoes the
            // colour rather than the typing.
            onEditingFinished: {
                studio.setColor(root.prefix, text)
                text = studio.colorOf(root.prefix)
                focus = false
            }
        }

        Label {
            text: "brightness " + root.luma(root.color)
            color: root.theme.textDim
            font.pixelSize: 11
            Layout.fillWidth: true
        }

        ToolButton {
            id: channels
            objectName: "channels_" + root.prefix
            text: checked ? "Hide RGB" : "RGB"
            checkable: true
            font.pixelSize: 11
        }
    }

    Label {
        visible: root.locked
        text: "Follows the light colour while the ramp is linked."
        color: root.theme.textDim
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    ColumnLayout {
        visible: channels.checked
        Layout.fillWidth: true
        spacing: 8
        Repeater {
            model: root.controls
            delegate: ParamControl {
                required property var modelData
                Layout.fillWidth: true
                spec: modelData
                theme: root.theme
            }
        }
    }

    ColorDialog {
        id: picker
        title: "Choose a colour"
        selectedColor: root.color
        onAccepted: studio.setColor(root.prefix, selectedColor.toString())
    }
}
