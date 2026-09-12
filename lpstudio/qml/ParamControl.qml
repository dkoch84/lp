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
    spacing: 2

    readonly property bool isSlider: spec.kind === "slider"
    readonly property bool isToggle: spec.kind === "toggle"
    readonly property bool isChoice: spec.kind === "choice"
    readonly property bool isInteger: spec.integer === true

    function fmt(v) {
        return isInteger ? Math.round(v).toString() : (Math.round(v * 100) / 100).toString()
    }

    RowLayout {
        visible: !root.isToggle
        Layout.fillWidth: true
        Label {
            text: root.spec.label
            color: "#bdbdbd"
            font.pixelSize: 12
            Layout.fillWidth: true
        }
        Label {
            visible: root.isSlider
            text: root.fmt(slider.value)
            color: "#e6e6e6"
            font.pixelSize: 12
            font.family: "monospace"
        }
    }

    // Toggle variant (e.g. additive vs. normal-blend grooves)
    CheckBox {
        id: toggle
        visible: root.isToggle
        text: root.spec.label
        checked: studio.param(root.spec.key) >= 0.5
        onToggled: studio.setParam(root.spec.key, checked ? 1 : 0)
        contentItem: Label {
            text: toggle.text
            color: "#bdbdbd"
            font.pixelSize: 12
            leftPadding: toggle.indicator.width + 6
            verticalAlignment: Text.AlignVCenter
        }
        Connections {
            target: studio
            function onParamsChanged() { toggle.checked = studio.param(root.spec.key) >= 0.5 }
        }
    }

    // Slider variant (colour params)
    Slider {
        id: slider
        visible: root.isSlider
        Layout.fillWidth: true
        from: root.spec.min !== undefined ? root.spec.min : 0
        to: root.spec.max !== undefined ? root.spec.max : 255
        stepSize: root.spec.step !== undefined ? root.spec.step : (root.isInteger ? 1 : 0)
        value: studio.param(root.spec.key)
        onMoved: studio.setParam(root.spec.key, value)
        Connections {
            target: studio
            function onParamsChanged() { slider.value = studio.param(root.spec.key) }
        }
    }

    // Choice variant (enum dropdown — value is the option index)
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

    // Field variant (location params — need precision a slider can't give)
    TextField {
        id: field
        visible: !root.isSlider && !root.isChoice && !root.isToggle
        Layout.fillWidth: true
        color: "#e6e6e6"
        text: root.fmt(studio.param(root.spec.key))
        background: Rectangle { color: "#262626"; border.color: "#333333"; radius: 4 }
        onEditingFinished: {
            var v = parseFloat(text)
            if (!isNaN(v)) studio.setParam(root.spec.key, v)
        }
        Connections {
            target: studio
            function onParamsChanged() { field.text = root.fmt(studio.param(root.spec.key)) }
        }
    }
}
