import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Lpstudio

ApplicationWindow {
    id: win
    width: 1180
    height: 820
    visible: true
    title: "lp-studio — vinyl style authoring"
    color: bg

    // --- palette ---
    readonly property color bg:      "#141414"
    readonly property color panel:   "#1e1e1e"
    readonly property color panel2:  "#262626"
    readonly property color stroke:  "#333333"
    readonly property color fg:      "#e6e6e6"
    readonly property color fgDim:   "#9a9a9a"
    readonly property color accent:  "#6ea8ff"

    // --- top bar: identity + presets + actions ---
    header: Rectangle {
        color: win.panel
        height: 56
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            spacing: 10

            Label { text: "Name"; color: win.fgDim }
            TextField {
                id: nameField
                Layout.preferredWidth: 150
                text: studio.name
                color: win.fg
                placeholderText: "untitled"
                background: Rectangle { color: win.panel2; border.color: win.stroke; radius: 4 }
                onEditingFinished: studio.name = text
                Connections { target: studio; function onNameChanged() { nameField.text = studio.name } }
            }

            Label { text: "Style"; color: win.fgDim }
            ComboBox {
                id: familyBox
                Layout.preferredWidth: 130
                model: studio.families()
                currentIndex: model.indexOf(studio.family)
                onActivated: studio.family = currentText
                Connections {
                    target: studio
                    function onFamilyChanged() { familyBox.currentIndex = familyBox.model.indexOf(studio.family) }
                }
            }

            ComboBox {
                id: presetBox
                Layout.preferredWidth: 180
                model: studio.variantNames()
                displayText: "Seed variant…"
                onActivated: studio.loadVariant(currentText)
            }

            ComboBox {
                id: savedBox
                Layout.preferredWidth: 170
                displayText: "Load saved…"
                model: studio.savedTemplates()
                onActivated: studio.loadTemplate(currentText)
                Connections { target: studio; function onStatusChanged() { savedBox.model = studio.savedTemplates() } }
            }

            Item { Layout.fillWidth: true }

            Switch {
                text: "Advanced"
                visible: studio.family === "nebula" || studio.family === "smoke"
                checked: studio.advanced
                onToggled: studio.advanced = checked
            }
            Switch {
                text: "HQ preview"
                visible: studio.family === "smoke"
                checked: studio.hq
                onToggled: studio.hq = checked
            }
            Switch {
                text: "Spin"
                checked: preview.spinning
                onToggled: preview.spinning = checked
            }
            ToolButton { text: "Randomize"; onClicked: studio.randomize() }
            ToolButton { text: "Reset"; onClicked: studio.reset() }
            ToolButton { text: "Snippet"; onClicked: snippetDialog.open() }
            Button {
                text: "Save"
                highlighted: true
                onClicked: studio.save()
            }
        }
    }

    // --- body: controls | preview ---
    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Controls (scrollable, data-driven from paramSpec)
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 420
            color: win.panel

            ScrollView {
                anchors.fill: parent
                anchors.margins: 14
                contentWidth: availableWidth
                clip: true

                ColumnLayout {
                    width: parent.parent.availableWidth
                    spacing: 18

                    Repeater {
                        // Reading family/advanced makes this binding re-evaluate
                        // (and the panel rebuild) on every style switch.
                        model: { studio.family; studio.advanced; return studio.paramSpec(); }
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: modelData.group
                                color: win.accent
                                font.bold: true
                                font.pixelSize: 13
                            }

                            Repeater {
                                model: modelData.controls
                                delegate: ParamControl {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spec: modelData
                                }
                            }
                        }
                    }
                }
            }
        }

        // Preview
        Rectangle {
            Layout.fillHeight: true
            Layout.fillWidth: true
            color: win.bg

            MandelPreviewItem {
                id: preview
                controller: studio
                anchors.fill: parent
                anchors.margins: 28
            }

            Label {
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.margins: 12
                text: studio.status
                color: win.fgDim
                font.pixelSize: 12
            }
        }
    }

    // --- catalog snippet dialog ---
    Dialog {
        id: snippetDialog
        title: "catalog.py snippet"
        modal: true
        anchors.centerIn: parent
        width: 720
        standardButtons: Dialog.Close

        onAboutToShow: snippetText.text = studio.catalogSnippet()

        ColumnLayout {
            anchors.fill: parent
            spacing: 10

            Label {
                text: "Paste these into lpcore/vinyl/catalog.py to make this a real style."
                color: win.fgDim
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 300
                color: win.panel2
                border.color: win.stroke
                radius: 4
                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 8
                    TextArea {
                        id: snippetText
                        readOnly: true
                        color: win.fg
                        font.family: "monospace"
                        font.pixelSize: 12
                        wrapMode: TextArea.NoWrap
                        background: null
                    }
                }
            }
            Button {
                text: "Copy to clipboard"
                onClicked: studio.copyToClipboard(snippetText.text)
            }
        }
    }
}
