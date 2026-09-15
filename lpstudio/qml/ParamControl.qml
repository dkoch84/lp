import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// One editable parameter: a labelled slider (with live value) or a free-entry
// text field, two-way bound to the controller via studio.param/setParam.
// `spec` is one entry from a paramSpec group: {key, label, kind, min, max,
// step, integer}.
ColumnLayout {
    id: root
    required property var spec
    property QtObject theme
    spacing: 2

    readonly property bool isSlider: spec.kind === "slider"
    readonly property bool isToggle: spec.kind === "toggle"
    readonly property bool isChoice: spec.kind === "choice"
    readonly property bool isInteger: spec.integer === true

    function fmt(v) {
        return isInteger ? Math.round(v).toString() : parseFloat(v.toFixed(3)).toString()
    }

    // One arrow-key nudge: the slider's step (1 for integers), x10 with Shift.
    function nudge(event) {
        var step = spec.step !== undefined ? spec.step : (isInteger ? 1 : 0.01)
        return (event.modifiers & Qt.ShiftModifier) ? step * 10 : step
    }

    RowLayout {
        visible: !root.isToggle
        Layout.fillWidth: true
        Label {
            text: root.spec.label
            color: root.theme.textDim
            font.pixelSize: 12
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        // The slider's value, typed exactly: Enter (or clicking away) applies it,
        // Up/Down nudge by one step, Shift for ten.
        TextField {
            id: valueBox
            objectName: "valueBox"
            visible: root.isSlider
            Layout.preferredWidth: 70
            horizontalAlignment: Text.AlignRight
            color: root.theme.text
            font.pixelSize: 12
            font.family: root.theme.mono
            selectByMouse: true
            topPadding: 2
            bottomPadding: 2
            leftPadding: 4
            rightPadding: 4
            background: Rectangle {
                color: valueBox.activeFocus ? root.theme.surface : "transparent"
                border.color: valueBox.activeFocus ? root.theme.accent : root.theme.line
                radius: 4
            }

            function commit(v) {
                if (!isNaN(v)) {
                    v = Math.min(slider.to, Math.max(slider.from, v))
                    studio.setParam(root.spec.key, root.isInteger ? Math.round(v) : v)
                }
                text = root.fmt(studio.param(root.spec.key))
            }

            Component.onCompleted: text = root.fmt(studio.param(root.spec.key))
            onEditingFinished: commit(parseFloat(text))
            Keys.onUpPressed: function(event) { commit(studio.param(root.spec.key) + root.nudge(event)) }
            Keys.onDownPressed: function(event) { commit(studio.param(root.spec.key) - root.nudge(event)) }
        }
    }

    CheckBox {
        id: toggle
        visible: root.isToggle
        text: root.spec.label
        checked: studio.param(root.spec.key) >= 0.5
        onToggled: studio.setParam(root.spec.key, checked ? 1 : 0)
        Connections {
            target: studio
            function onParamsChanged() { toggle.checked = studio.param(root.spec.key) >= 0.5 }
        }
    }

    Slider {
        id: slider
        visible: root.isSlider
        Layout.fillWidth: true
        from: root.spec.min !== undefined ? root.spec.min : 0
        to: root.spec.max !== undefined ? root.spec.max : 255
        stepSize: root.spec.step !== undefined ? root.spec.step : (root.isInteger ? 1 : 0)
        value: studio.param(root.spec.key)
        onMoved: studio.setParam(root.spec.key, value)
        onValueChanged: if (!valueBox.activeFocus) valueBox.text = root.fmt(value)
        Connections {
            target: studio
            function onParamsChanged() { slider.value = studio.param(root.spec.key) }
        }
    }

    // Choice: an enum dropdown whose value is the option index
    ComboBox {
        id: choice
        visible: root.isChoice
        Layout.fillWidth: true
        model: root.spec.options
        currentIndex: studio.param(root.spec.key)
        onActivated: studio.setParam(root.spec.key, currentIndex)
        Connections {
            target: studio
            function onParamsChanged() { choice.currentIndex = studio.param(root.spec.key) }
        }
    }

    // Field: location params that need more precision than a slider gives
    TextField {
        id: field
        visible: !root.isSlider && !root.isChoice && !root.isToggle
        Layout.fillWidth: true
        font.family: root.theme.mono
        text: root.fmt(studio.param(root.spec.key))
        selectByMouse: true
        onEditingFinished: {
            var v = parseFloat(text)
            if (!isNaN(v)) studio.setParam(root.spec.key, v)
            text = root.fmt(studio.param(root.spec.key))
        }
        Connections {
            target: studio
            function onParamsChanged() { if (!field.activeFocus) field.text = root.fmt(studio.param(root.spec.key)) }
        }
    }
}
