import QtCore
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Lpstudio

ApplicationWindow {
    id: win
    width: 1320
    height: 880
    minimumWidth: 980
    minimumHeight: 640
    visible: true
    title: "lp-studio: " + (studio.name || "untitled") + (studio.dirty ? " (unsaved)" : "")
    color: theme.bg
    font.pixelSize: 13

    // "system", "dark" or "light"; remembered between runs
    property string themeMode: prefs.themeMode
    property int layerCount: studio.param("smk_layers")
    property var compareModel: studio.compareStyles()
    property var collapsedMap: parseMap(prefs.collapsed)
    readonly property QtObject tokens: theme
    readonly property bool shippable: ["smoke", "clouds", "nebula"].indexOf(studio.family) >= 0
    readonly property var lockedPrefixes: studio.family === "smoke" && studio.rampLinked
                                          ? ["smk_mid", "smk_ink", "smk_acc_ink"] : []
    // the control group each guardrail is about
    readonly property var issueGroup: ({ light: "Body (light)", mid: "Body (deep)", ink: "Smoke ink",
                                         accent_ink: "Accent ink", contrast: "Smoke" })

    Settings {
        id: prefs
        location: settingsLocation
        category: "studio"
        property string themeMode: "system"
        property int panelWidth: 420
        property string collapsed: "{}"
    }

    Theme {
        id: theme
        dark: win.themeMode === "dark"
              || (win.themeMode === "system" && Qt.styleHints.colorScheme !== Qt.ColorScheme.Light)
    }

    palette {
        window: theme.bg
        windowText: theme.text
        base: theme.surface
        alternateBase: theme.sidebar
        text: theme.text
        button: theme.surface
        buttonText: theme.text
        highlight: theme.accent
        highlightedText: theme.accentText
        placeholderText: theme.textDim
        mid: theme.line
        midlight: theme.surfaceHover
        light: theme.surfaceHover
        // Basic draws highlighted buttons and switched-on switches in `dark`, with `brightText`
        dark: theme.accent
        brightText: theme.accentText
        shadow: "#000000"
        toolTipBase: theme.surface
        toolTipText: theme.text
    }

    function parseMap(text) {
        try { return JSON.parse(text) || {} } catch (e) { return {} }
    }
    function groupExpanded(name) {
        return (name in collapsedMap) ? !collapsedMap[name] : !name.startsWith("Layer ")
    }
    function setExpanded(name, open) {
        var m = parseMap(prefs.collapsed)
        m[name] = !open
        prefs.collapsed = JSON.stringify(m)
    }
    function beyondLayerCount(name) {
        var m = /^Layer (\d+)$/.exec(name)
        return m !== null && parseInt(m[1]) > win.layerCount
    }
    function cycleTheme() {
        var order = ["system", "dark", "light"]
        prefs.themeMode = order[(order.indexOf(win.themeMode) + 1) % order.length]
        win.themeMode = Qt.binding(function() { return prefs.themeMode })
    }
    function requestSave() {
        if (studio.saveNeedsConfirm()) confirmSave.open()
        else studio.save()
    }
    function openShip() { shipDialog.open() }
    function openVariations() { variations.show() }
    function showCompare(name) {
        for (var i = 0; i < compareModel.length; i++)
            if (compareModel[i].name === name) { compare.pick(compareModel[i]); return }
    }
    function focusGroup(name) {
        search.text = ""
        setExpanded(name, true)
        for (var i = 0; i < groupRepeater.count; i++) {
            var item = groupRepeater.itemAt(i)
            if (item && item.group.group === name) {
                Qt.callLater(function(it) {
                    var flick = scroller.contentItem
                    var y = it.mapToItem(groupsColumn, 0, 0).y
                    flick.contentY = Math.max(0, Math.min(y - 12, groupsColumn.height - flick.height))
                    it.flash()
                }, item)
                return
            }
        }
    }

    Connections {
        target: studio
        function onParamsChanged() { win.layerCount = studio.param("smk_layers") }
        function onFamilyChanged() { win.compareModel = studio.compareStyles(); compare.clear() }
    }

    Shortcut { sequences: [StandardKey.Undo]; onActivated: studio.undo() }
    Shortcut { sequences: [StandardKey.Redo, "Ctrl+Y"]; onActivated: studio.redo() }
    Shortcut { sequences: [StandardKey.Save]; onActivated: win.requestSave() }
    Shortcut { sequence: "Ctrl+R"; onActivated: studio.randomize() }
    Shortcut { sequences: [StandardKey.Find]; onActivated: search.forceActiveFocus() }

    // --- toolbar ------------------------------------------------------------------

    header: ToolBar {
        implicitHeight: 56
        background: Rectangle {
            color: theme.sidebar
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.line }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: 8

            Label {
                text: "lp-studio"
                color: theme.accent
                font.pixelSize: 15
                font.weight: Font.Bold
            }
            Rectangle { implicitWidth: 1; implicitHeight: 24; color: theme.line }

            TextField {
                id: nameField
                objectName: "nameField"
                Layout.preferredWidth: 180
                text: studio.name
                placeholderText: "style name"
                selectByMouse: true
                onEditingFinished: { studio.name = text; focus = false }
                Connections {
                    target: studio
                    function onNameChanged() { nameField.text = studio.name }
                }
            }
            Rectangle {
                objectName: "dirtyDot"
                visible: studio.dirty
                implicitWidth: 8
                implicitHeight: 8
                radius: 4
                color: theme.accent
                ToolTip.visible: dirtyMouse.containsMouse
                ToolTip.text: "Unsaved changes"
                MouseArea { id: dirtyMouse; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true }
            }

            ComboBox {
                id: familyBox
                objectName: "familyBox"
                Layout.preferredWidth: 130
                model: studio.families()
                currentIndex: model.indexOf(studio.family)
                onActivated: studio.family = currentText
                Connections {
                    target: studio
                    function onFamilyChanged() { familyBox.currentIndex = familyBox.model.indexOf(studio.family) }
                }
            }

            Button {
                id: openButton
                text: "Open"
                flat: true
                onClicked: openMenu.popup(openButton, 0, openButton.height)

                Menu {
                    id: openMenu
                    property var saved: []
                    property var shipped: []
                    onAboutToShow: { saved = studio.savedTemplates(); shipped = studio.shippedStyles() }

                    Menu {
                        id: savedMenu
                        title: "Saved templates"
                        Instantiator {
                            model: openMenu.saved
                            delegate: MenuItem {
                                required property var modelData
                                text: modelData
                                onTriggered: studio.loadTemplate(modelData)
                            }
                            onObjectAdded: (index, object) => savedMenu.insertItem(index, object)
                            onObjectRemoved: (index, object) => savedMenu.removeItem(object)
                        }
                    }
                    Menu {
                        id: shippedMenu
                        title: "Shipped styles"
                        Instantiator {
                            model: openMenu.shipped
                            delegate: MenuItem {
                                required property var modelData
                                text: modelData
                                onTriggered: studio.loadShipped(modelData)
                            }
                            onObjectAdded: (index, object) => shippedMenu.insertItem(index, object)
                            onObjectRemoved: (index, object) => shippedMenu.removeItem(object)
                        }
                    }
                    Menu {
                        id: presetMenu
                        title: "Mandelbrot presets"
                        Instantiator {
                            model: studio.variantNames()
                            delegate: MenuItem {
                                required property var modelData
                                text: modelData
                                onTriggered: studio.loadVariant(modelData)
                            }
                            onObjectAdded: (index, object) => presetMenu.insertItem(index, object)
                            onObjectRemoved: (index, object) => presetMenu.removeItem(object)
                        }
                    }
                }
            }

            ToolSeparator {}

            ToolButton {
                objectName: "undoButton"
                text: "Undo"
                enabled: studio.canUndo
                onClicked: studio.undo()
                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: "Ctrl+Z"
            }
            ToolButton {
                text: "Redo"
                enabled: studio.canRedo
                onClicked: studio.redo()
                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: "Ctrl+Shift+Z"
            }
            ToolButton {
                text: "Randomize"
                onClicked: studio.randomize()
                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: studio.family === "smoke" ? "New composition, same colours (Ctrl+R)" : "Ctrl+R"
            }
            ToolButton {
                text: "Reset"
                onClicked: studio.reset()
                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: "Put this family's controls back to their defaults"
            }

            Item { Layout.fillWidth: true }

            ToolButton {
                objectName: "themeButton"
                text: "Theme: " + win.themeMode.charAt(0).toUpperCase() + win.themeMode.slice(1)
                onClicked: win.cycleTheme()
            }
            ToolButton {
                text: "Export"
                onClicked: snippetDialog.open()
            }
            Button {
                text: "Save"
                onClicked: win.requestSave()
                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: "Save as a template in lpstudio/templates (Ctrl+S)"
            }
            Button {
                objectName: "shipButton"
                text: studio.shipping ? "Rendering..." : "Ship"
                highlighted: true
                enabled: win.shippable && !studio.shipping
                onClicked: win.openShip()
            }
        }
    }

    // --- body: controls | stage --------------------------------------------------

    SplitView {
        id: split
        anchors.fill: parent
        orientation: Qt.Horizontal

        handle: Rectangle {
            implicitWidth: 5
            color: SplitHandle.pressed ? theme.accent : (SplitHandle.hovered ? theme.line : theme.sidebar)
        }

        Rectangle {
            id: panel
            SplitView.preferredWidth: prefs.panelWidth
            SplitView.minimumWidth: 340
            SplitView.maximumWidth: 680
            color: theme.sidebar
            onWidthChanged: if (split.resizing) prefs.panelWidth = Math.round(width)

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.margins: 14
                    spacing: 10

                    TextField {
                        id: search
                        objectName: "searchField"
                        Layout.fillWidth: true
                        placeholderText: "Filter controls (Ctrl+F)"
                        selectByMouse: true
                        Keys.onEscapePressed: text = ""
                    }
                    RowLayout {
                        visible: studio.family === "nebula" || studio.family === "smoke"
                        Layout.fillWidth: true
                        Switch {
                            objectName: "advancedSwitch"
                            text: "Advanced"
                            checked: studio.advanced
                            onToggled: studio.advanced = checked
                        }
                        Label {
                            text: studio.family === "smoke" ? "per-layer trims" : "per-channel amplitude and modulators"
                            color: theme.textDim
                            font.pixelSize: 11
                            Layout.fillWidth: true
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line }

                ScrollView {
                    id: scroller
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: availableWidth
                    clip: true

                    ColumnLayout {
                        id: groupsColumn
                        width: scroller.availableWidth
                        spacing: 4

                        Item { implicitHeight: 8 }

                        RampPanel {
                            visible: studio.family === "smoke" && search.text === ""
                            theme: win.tokens
                            Layout.fillWidth: true
                            Layout.leftMargin: 14
                            Layout.rightMargin: 14
                            Layout.bottomMargin: 8
                        }

                        Repeater {
                            id: groupRepeater
                            // Reading family/advanced rebuilds the panel on a style switch.
                            model: { studio.family; studio.advanced; return studio.paramSpec(); }
                            delegate: ControlGroup {
                                required property var modelData
                                theme: win.tokens
                                group: modelData
                                filter: search.text
                                expanded: win.groupExpanded(modelData.group)
                                hidden: win.beyondLayerCount(modelData.group)
                                lockedPrefixes: win.lockedPrefixes
                                Layout.fillWidth: true
                                Layout.leftMargin: 14
                                Layout.rightMargin: 14
                                onToggleRequested: (open) => win.setExpanded(modelData.group, open)
                            }
                        }

                        Label {
                            visible: search.text !== "" && groupsColumn.visibleGroups === 0
                            text: "No control matches “" + search.text + "”."
                            color: theme.textDim
                            Layout.leftMargin: 22
                            Layout.topMargin: 12
                        }

                        Item { implicitHeight: 24 }

                        readonly property int visibleGroups: {
                            search.text; studio.family; studio.advanced
                            var n = 0
                            for (var i = 0; i < groupRepeater.count; i++) {
                                var it = groupRepeater.itemAt(i)
                                if (it && it.matchCount > 0 && !it.hidden) n++
                            }
                            return n
                        }
                    }
                }
            }
        }

        Rectangle {
            id: stage
            SplitView.fillWidth: true
            color: theme.bg

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 16
                    Layout.rightMargin: 16
                    Layout.topMargin: 10
                    Layout.bottomMargin: 6
                    spacing: 12

                    BusyIndicator {
                        running: preview.busy || studio.shipping
                        visible: running
                        implicitWidth: 22
                        implicitHeight: 22
                    }
                    Label {
                        objectName: "statusLabel"
                        text: studio.status || "Ready"
                        color: theme.textDim
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Button {
                        objectName: "variationsButton"
                        visible: studio.family === "smoke"
                        text: "Colour variations"
                        flat: true
                        onClicked: win.openVariations()
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
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 24

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            MandelPreviewItem {
                                id: preview
                                controller: studio
                                anchors.fill: parent
                            }
                        }

                        Item {
                            id: compare
                            property string name: ""
                            property string url: ""
                            property bool shipped: false
                            function pick(entry) { name = entry.name; url = entry.url; shipped = entry.shipped }
                            function clear() { name = ""; url = "" }
                            visible: name !== ""
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            DiscImage {
                                theme: win.tokens
                                anchors.centerIn: parent
                                anchors.verticalCenterOffset: -20
                                size: Math.max(40, Math.min(parent.width, parent.height - 80))
                                source: compare.url
                            }
                            ColumnLayout {
                                anchors.bottom: parent.bottom
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: 2
                                Label {
                                    text: compare.name
                                    font.weight: Font.DemiBold
                                    Layout.alignment: Qt.AlignHCenter
                                }
                                RowLayout {
                                    Layout.alignment: Qt.AlignHCenter
                                    Label { text: "shipped image, no label or grooves"; color: theme.textDim; font.pixelSize: 11 }
                                    Button {
                                        text: "Open"
                                        visible: compare.shipped
                                        flat: true
                                        onClicked: { studio.loadShipped(compare.name); compare.clear() }
                                    }
                                    Button { text: "Close"; flat: true; onClicked: compare.clear() }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: 16
                        width: Math.min(400, parent.width * 0.42)
                        spacing: 8

                        Repeater {
                            model: studio.guardrails
                            delegate: Rectangle {
                                required property var modelData
                                objectName: "guardrailChip"
                                Layout.fillWidth: true
                                implicitHeight: chipText.implicitHeight + 18
                                radius: 8
                                color: theme.alpha(theme.surface, 0.95)
                                border.color: theme.alpha(theme.level(modelData.level), 0.6)

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    anchors.margins: 6
                                    width: 3
                                    radius: 2
                                    color: theme.level(modelData.level)
                                }
                                Label {
                                    id: chipText
                                    anchors.fill: parent
                                    anchors.leftMargin: 18
                                    anchors.rightMargin: 12
                                    anchors.topMargin: 9
                                    anchors.bottomMargin: 9
                                    text: modelData.message
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 12
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: win.focusGroup(win.issueGroup[modelData.keys[0]])
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    objectName: "compareStrip"
                    visible: win.compareModel.length > 0
                    Layout.fillWidth: true
                    implicitHeight: 124
                    color: theme.sidebar
                    Rectangle { width: parent.width; height: 1; color: theme.line }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        anchors.topMargin: 10
                        anchors.bottomMargin: 6
                        spacing: 6

                        Label {
                            text: "Compare with the catalog: " + win.compareModel.length + " " + studio.family + " styles"
                            color: theme.textDim
                            font.pixelSize: 11
                        }
                        ListView {
                            id: strip
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            orientation: ListView.Horizontal
                            spacing: 12
                            clip: true
                            model: win.compareModel
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

                            delegate: Item {
                                required property var modelData
                                width: 72
                                height: strip.height

                                DiscImage {
                                    id: thumb
                                    theme: win.tokens
                                    size: 56
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    source: modelData.url
                                    selected: compare.name === modelData.name
                                }
                                Label {
                                    anchors.top: thumb.bottom
                                    anchors.topMargin: 4
                                    width: parent.width
                                    horizontalAlignment: Text.AlignHCenter
                                    text: modelData.name.replace(/-marble$/, "")
                                    elide: Text.ElideRight
                                    color: compare.name === modelData.name ? theme.text : theme.textDim
                                    font.pixelSize: 10
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: compare.name === modelData.name ? compare.clear() : compare.pick(modelData)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // --- colour variations ---------------------------------------------------------

    Popup {
        id: variations
        objectName: "variationsPopup"
        property var items: []
        function show() { items = studio.hueVariations(8); open() }

        modal: true
        anchors.centerIn: Overlay.overlay
        padding: 22
        background: Rectangle { color: theme.surface; radius: theme.radius; border.color: theme.line }

        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: "Colour variations"
                font.pixelSize: 17
                font.weight: Font.DemiBold
            }
            Label {
                text: "This composition turned round the colour wheel at the same brightness, each with a linked ramp. Pick one to use it; Ctrl+Z brings yours back."
                color: theme.textDim
                wrapMode: Text.WordWrap
                Layout.preferredWidth: 4 * 112 + 3 * 18
            }
            GridLayout {
                columns: 4
                columnSpacing: 18
                rowSpacing: 14
                Repeater {
                    model: variations.items
                    delegate: ColumnLayout {
                        required property var modelData
                        spacing: 6
                        DiscImage {
                            theme: win.tokens
                            size: 112
                            source: modelData.source
                            Layout.alignment: Qt.AlignHCenter
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: { studio.applyVariation(modelData.index); variations.close() }
                            }
                        }
                        Label {
                            text: modelData.hue + "°  " + modelData.color
                            color: theme.textDim
                            font.family: theme.mono
                            font.pixelSize: 11
                            Layout.alignment: Qt.AlignHCenter
                        }
                    }
                }
            }
        }
    }

    // --- ship ------------------------------------------------------------------------

    Dialog {
        id: shipDialog
        objectName: "shipDialog"
        property var check: ({})
        title: "Ship this style"
        modal: true
        anchors.centerIn: parent
        width: 540
        padding: 20
        onAboutToShow: { shipName.text = studio.name; check = studio.shipCheck(shipName.text) }
        onAccepted: studio.ship(shipName.text)
        background: Rectangle { color: theme.surface; radius: theme.radius; border.color: theme.line }

        function verdict(c) {
            if (c.supported === false) return "Only smoke, clouds and nebula styles ship as a style file. Use Export for this one."
            if (c.valid === false) return "Use lowercase words joined by hyphens, like cobalt-marble."
            if (c.builtin) return "That name belongs to a built-in style."
            if (c.exists) return "Replaces the shipped style with this name and keeps its place in the list."
            return "A new style, added at the end of its list."
        }

        contentItem: ColumnLayout {
            spacing: 10
            Label {
                text: "Writes lpcore/vinyl/styles/nebula/<name>.json and renders its full-size image. Nothing is committed or copied to the kiosk."
                color: theme.textDim
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            TextField {
                id: shipName
                objectName: "shipName"
                Layout.fillWidth: true
                placeholderText: "cobalt-marble"
                selectByMouse: true
                onTextChanged: shipDialog.check = studio.shipCheck(text)
            }
            Label {
                objectName: "shipVerdict"
                text: shipDialog.verdict(shipDialog.check)
                color: shipDialog.check.ok ? (shipDialog.check.exists ? theme.warn : theme.ok) : theme.bad
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Repeater {
                model: shipDialog.check.issues || []
                delegate: Label {
                    required property var modelData
                    text: "• " + modelData.message
                    color: theme.level(modelData.level)
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        footer: DialogButtonBox {
            background: Rectangle { color: "transparent" }
            Button {
                text: "Cancel"
                flat: true
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole
            }
            Button {
                id: shipConfirm
                objectName: "shipConfirm"
                text: "Ship"
                enabled: shipDialog.check.ok === true && !studio.shipping
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
                contentItem: Label {
                    text: shipConfirm.text
                    color: shipConfirm.enabled ? theme.accentText : theme.textDim
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 100
                    implicitHeight: 36
                    radius: 6
                    color: !shipConfirm.enabled ? theme.surfaceHover
                           : (shipConfirm.down ? Qt.darker(theme.accent, 1.15) : theme.accent)
                }
            }
        }
    }

    Dialog {
        id: confirmSave
        title: "Replace the saved template?"
        modal: true
        anchors.centerIn: parent
        width: 440
        standardButtons: Dialog.Cancel | Dialog.Ok
        background: Rectangle { color: theme.surface; radius: theme.radius; border.color: theme.line }
        onAccepted: studio.save()
        contentItem: Label {
            text: "A template named " + studio.family + "/" + (studio.name || "untitled")
                  + " is already saved, and it isn't the one you opened. Replace it?"
            wrapMode: Text.WordWrap
        }
    }

    // --- export ----------------------------------------------------------------------

    Dialog {
        id: snippetDialog
        title: "Export"
        modal: true
        anchors.centerIn: parent
        width: 760
        standardButtons: Dialog.Close
        background: Rectangle { color: theme.surface; radius: theme.radius; border.color: theme.line }
        onAboutToShow: snippetText.text = studio.catalogSnippet()

        contentItem: ColumnLayout {
            spacing: 10
            Label {
                text: win.shippable ? "The style file Ship writes for this style."
                                    : "Paste these into lpcore/vinyl/catalog.py to make this a real style."
                color: theme.textDim
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: 380
                TextArea {
                    id: snippetText
                    readOnly: true
                    selectByMouse: true
                    font.family: theme.mono
                    font.pixelSize: 12
                    wrapMode: TextArea.NoWrap
                }
            }
            Button {
                text: "Copy to clipboard"
                onClicked: studio.copyToClipboard(snippetText.text)
            }
        }
    }
}
