import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import Lpdeck

ApplicationWindow {
    id: win
    visible: true
    width: 1320
    height: 860
    title: "lp-deck"

    Theme { id: theme; dark: controller ? controller.darkMode : true }
    color: theme.bg

    property string section: "artists"
    property bool queueOpen: false
    property string query: ""
    property bool expanded: false        // Now-Playing taken over the whole app
    property bool vinylConfig: false     // vinyl chooser taken over the main area
    property bool showLyrics: false      // expanded view: lyrics instead of art+vinyl
    // live vinyl-chooser selection (was the popup's; now window-level)
    property string vScope: "album"
    property string vStyle: "black"
    property string vLabel: "label-white"
    property var vEffects: []
    property string vGrooves: "auto"
    function loadVinyl() {
        var v = controller.currentVinyl()
        vStyle = v.style; vLabel = v.label; vEffects = v.effects || []
        vGrooves = v.grooves || "auto"
    }
    // Swatches that show album art (the picture disc, the album-art label)
    // carry the playing album's id so they draw its real cover; the rest
    // leave it out and stay cached once for every album.
    function vinylSwatch(style, label) {
        var art = style === "picture" || label === "art"
        return "image://vinyl/" + style + "~" + label
               + (art && controller ? "~" + controller.npAlbumId : "")
    }
    function toggleEffect(id, on) {
        var e = vEffects.filter(function(x) { return x !== id })
        if (on) e.push(id)
        vEffects = e
        controller.setVinylEffects(vScope, e)
    }
    function applyVinyl() { controller.setVinyl(vScope, vStyle, vLabel, 100) }
    function openVinylConfig() { loadVinyl(); vinylConfig = true }
    // true while any modal popup is open — used to disable the shell beneath it
    // (a modal Popup does NOT block TapHandlers on items behind it, so taps that
    // hit popup content were *also* reaching the song rows → playing a track).
    property bool popupOpen: settingsPopup.opened
                             || rowActions.opened || metadataPopup.opened
                             || addToPlaylist.opened || newPlaylistPopup.opened
                             || playlistActions.opened || renamePopup.opened
                             || smartActions.opened || smartEditor.opened
    // alias to the context `controller`. VinylItem has its own `controller`
    // property, so binding it to the bare name `controller` self-references
    // (null); bind to `win.appController` instead.
    property var appController: controller

    // ---- keyboard shortcuts (off while typing in a text field) ----
    readonly property bool typing: activeFocusItem !== null
                                   && activeFocusItem.hasOwnProperty("cursorPosition")
    readonly property bool keysFree: !typing && !popupOpen
    // Closing the window quits, unless lp-deck is set to keep playing in the tray.
    onClosing: (close) => {
        if (controller && controller.closeToTray) {
            close.accepted = false
            win.hide()
        } else {
            Qt.quit()
        }
    }
    Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }
    Shortcut { sequence: "Space"; enabled: win.keysFree; onActivated: controller.playPause() }
    Shortcut { sequence: "Ctrl+Right"; enabled: win.keysFree; onActivated: controller.next() }
    Shortcut { sequence: "Ctrl+Left"; enabled: win.keysFree; onActivated: controller.previous() }
    Shortcut { sequence: "Shift+Right"; enabled: win.keysFree; onActivated: controller.seekBy(10) }
    Shortcut { sequence: "Shift+Left"; enabled: win.keysFree; onActivated: controller.seekBy(-10) }
    Shortcut { sequence: "Ctrl+Up"; enabled: win.keysFree
               onActivated: controller.setVolume(controller.volume + 5) }
    Shortcut { sequence: "Ctrl+Down"; enabled: win.keysFree
               onActivated: controller.setVolume(controller.volume - 5) }
    Shortcut { sequence: "Ctrl+M"; enabled: !win.popupOpen; onActivated: controller.toggleMute() }
    Shortcut { sequence: "Ctrl+S"; enabled: !win.popupOpen
               onActivated: controller.setShuffle(!controller.shuffle) }
    Shortcut { sequence: "Ctrl+R"; enabled: !win.popupOpen; onActivated: controller.cycleRepeat() }
    Shortcut { sequence: "Ctrl+."; enabled: !win.popupOpen
               onActivated: controller.toggleStopAfterCurrent() }
    Shortcut { sequence: "Ctrl+F"; enabled: !win.popupOpen
               onActivated: { search.forceActiveFocus(); search.selectAll() } }

    // bring the window forward when the desktop's media controls ask
    Connections {
        target: controller
        function onRaiseRequested() { win.show(); win.raise(); win.requestActivate() }
        function onNoticeChanged() { if (controller.notice !== "") noticeTimer.restart() }
    }

    // ---- notice toast (a skipped track, …) ----
    Rectangle {
        id: noticeToast
        parent: Overlay.overlay
        z: 1000
        readonly property bool shown: controller && controller.notice !== ""
        opacity: shown ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 180 } }
        width: Math.min(noticeText.implicitWidth + 36, win.width - 40)
        height: noticeText.implicitHeight + 20
        x: Math.round((parent.width - width) / 2)
        y: parent.height - height - 110
        radius: 10
        color: theme.surface
        border.color: theme.line
        Label {
            id: noticeText
            anchors.centerIn: parent
            width: Math.min(implicitWidth, win.width - 76)
            text: controller ? controller.notice : ""
            color: theme.text; font.pixelSize: 13
            wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
        }
        TapHandler { onTapped: controller.clearNotice() }
        Timer { id: noticeTimer; interval: 5000; onTriggered: controller.clearNotice() }
    }

    function fmtTime(s) {
        s = Math.max(0, Math.round(s))
        return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2)
    }
    // what an icon-only button does, for screen readers and tooltips
    function glyphName(g) {
        return ({ "‹": "Back", "✕": "Close", "⏭": "Next", "⏮": "Previous", "▶": "Play",
                  "⏸": "Pause", "🔀": "Shuffle", "🔁": "Repeat", "🔂": "Repeat one",
                  "♥": "Remove from favourites", "♡": "Add to favourites",
                  "🔇": "Unmute", "🔊": "Mute", "◉": "Vinyl", "☰": "Queue",
                  "♫": "Lyrics", "⚙": "Settings", "⛶": "Full view", "⋯": "More" })[g] || g
    }
    function gotoArtists() { section = "artists"; stack.replace(null, artistsPage) }
    function gotoAlbums() { section = "albums"; stack.replace(null, albumsPage, { "artistId": -1 }) }
    function openSmartPlaylist(id, name) {
        stack.push(songsPage, { "smartId": id, "headerTitle": name })
    }
    function gotoPlaylists() { section = "playlists"; stack.replace(null, playlistsPage) }
    function openArtist(id, name) {
        stack.push(albumsPage, { "artistId": id, "artistName": name })
    }
    function openAlbum(id, name, year, cover) {
        stack.push(songsPage, { "albumId": id, "headerTitle": name,
                                "albumYear": year, "coverUrl": cover })
    }
    function openPlaylist(id, name) {
        stack.push(songsPage, { "playlistId": id, "headerTitle": name })
    }
    function openSmart(kind, title) {
        section = kind
        stack.replace(null, songsPage, { "smartKind": kind, "headerTitle": title })
    }
    function openGenres() {
        section = "genres"; stack.replace(null, genresPage)
    }
    function openGenre(name) {
        stack.push(songsPage, { "genreName": name, "headerTitle": name })
    }
    // Typing shows the search page at once, but the query (and the database
    // search it drives) waits until typing pauses, instead of running per key.
    property string pendingQuery: ""
    Timer {
        id: searchDebounce
        interval: 200
        onTriggered: win.query = win.pendingQuery
    }
    function onSearch(t) {
        win.pendingQuery = t
        if (t.length === 0) { searchDebounce.stop(); win.query = "" }
        else searchDebounce.restart()
        if (t.length > 0 && section !== "search") {
            section = "search"; stack.replace(null, searchPage)
        } else if (t.length === 0 && section === "search") {
            gotoArtists()
        }
    }
    // open the per-track action sheet (edit metadata / Picard / add to playlist)
    function trackActions(path, title, plId, pos) {
        rowActions.trackPath = path; rowActions.trackTitle = title
        rowActions.playlistId = (plId === undefined ? -1 : plId)
        rowActions.position = (pos === undefined ? -1 : pos)
        rowActions.isFav = controller.isFavorite(path)
        rowActions.open()
    }
    // add-to-playlist for any target (one/many songs, a whole album, an artist)
    function addSongsToPlaylist(paths) {
        addToPlaylist.target = { kind: "tracks", paths: paths }; addToPlaylist.openSheet()
    }
    function addAlbumToPlaylist(albumPath) {
        addToPlaylist.target = { kind: "album", ref: albumPath }; addToPlaylist.openSheet()
    }
    function addArtistToPlaylist(artistId) {
        addToPlaylist.target = { kind: "artist", ref: artistId }; addToPlaylist.openSheet()
    }

    // ============================ shell ============================
    // Elisa-style: a full-width Now-Playing header pinned at the very top, the
    // library (sidebar | content | queue) fills everything below it.
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        // block taps leaking behind modal popups or the expanded overlay
        enabled: !win.popupOpen && !win.expanded

        NowPlayingHeader { Layout.fillWidth: true }

        // ---- body: main area (library OR vinyl config) + queue ----
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // main area fills everything except the Now-Playing header (above)
            // and the queue (right). The vinyl config takes over this whole area.
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                // library (sidebar + search + stacked views)
                RowLayout {
                    anchors.fill: parent
                    spacing: 0
                    visible: !win.vinylConfig

                    Rectangle {
                        Layout.fillHeight: true
                        Layout.preferredWidth: 210
                        color: theme.sidebar
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 4
                            Label {
                                text: "lp-deck"
                                color: theme.accent
                                font.pixelSize: 20; font.weight: Font.Bold
                                Layout.bottomMargin: 16; Layout.leftMargin: 6
                            }
                            NavItem { label: "Artists"; active: win.section === "artists"
                                      onClicked: win.gotoArtists() }
                            NavItem { label: "Albums"; active: win.section === "albums"
                                      onClicked: win.gotoAlbums() }
                            NavItem { label: "Tracks"; active: win.section === "all"
                                      onClicked: win.openSmart("all", "All tracks") }
                            NavItem { label: "Genres"; active: win.section === "genres"
                                      onClicked: win.openGenres() }
                            NavItem { label: "Playlists"; active: win.section === "playlists"
                                      onClicked: win.gotoPlaylists() }
                            Rectangle { Layout.fillWidth: true; Layout.topMargin: 8
                                        Layout.bottomMargin: 8; implicitHeight: 1
                                        color: theme.line }
                            Label { text: "LIBRARY"; color: theme.textDim
                                    font.pixelSize: 10; font.weight: Font.Bold
                                    Layout.leftMargin: 12; Layout.bottomMargin: 2 }
                            NavItem { label: "♥  Favourites"; active: win.section === "favorites"
                                      onClicked: win.openSmart("favorites", "Favourites") }
                            NavItem { label: "Recently played"; active: win.section === "recent"
                                      onClicked: win.openSmart("recent", "Recently played") }
                            NavItem { label: "Most played"; active: win.section === "most"
                                      onClicked: win.openSmart("most", "Most played") }
                            NavItem { label: "Recently added"; active: win.section === "added"
                                      onClicked: win.openSmart("added", "Recently added") }
                            Item { Layout.fillHeight: true }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 0
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 60
                            color: theme.bg
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: theme.pad
                                anchors.rightMargin: theme.pad
                                SearchField {
                                    id: search
                                    Layout.preferredWidth: 320
                                    placeholderText: "Search artists, albums, songs…"
                                    onTextChanged: win.onSearch(text)
                                }
                                Item { Layout.fillWidth: true }
                                IconButton { glyph: "⚙"; onClicked: settingsPopup.open() }
                            }
                        }
                        StackView {
                            id: stack
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            initialItem: artistsPage
                            clip: true
                        }
                    }
                }

                // full-screen vinyl config (uses the whole main area)
                VinylConfig { anchors.fill: parent; visible: win.vinylConfig }
            }

            QueuePanel { }
        }
    }

    // Esc collapses the expanded view / closes the vinyl config
    Shortcut {
        sequence: "Esc"
        enabled: win.expanded || win.vinylConfig
        onActivated: {
            if (win.vinylConfig) win.vinylConfig = false
            else win.expanded = false
        }
    }

    // ============= expanded Now-Playing (full-app takeover) =============
    // lp-kiosk layout: album art on the left, the spinning vinyl on the right.
    Item {
        anchors.fill: parent
        visible: win.expanded
        enabled: win.expanded && !win.popupOpen
        z: 10
        // opaque backdrop (album-art-tinted gradient) that swallows stray taps so
        // nothing leaks to the library beneath. It does NOT close on click (that
        // was catching the transport buttons) — use ✕ or Esc.
        Rectangle {
            id: expBg
            anchors.fill: parent
            property color accentColor: (controller && controller.npAccent)
                ? controller.npAccent : theme.accent
            gradient: Gradient {
                GradientStop { position: 0.0
                    color: Qt.tint(theme.bg, Qt.rgba(expBg.accentColor.r,
                        expBg.accentColor.g, expBg.accentColor.b, 0.22)) }
                GradientStop { position: 1.0; color: theme.bg }
            }
            MouseArea { anchors.fill: parent }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 44
            spacing: 22

            RowLayout {
                visible: !win.showLyrics
                Layout.fillWidth: true; Layout.fillHeight: true
                spacing: 56
                // album art (left)
                Item {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    Rectangle {
                        anchors.centerIn: parent
                        width: Math.min(parent.width, parent.height)
                        height: width
                        radius: 14; color: theme.surface; clip: true
                        Image {
                            anchors.fill: parent
                            source: controller ? controller.npCoverUrl : ""
                            sourceSize.width: 1000; sourceSize.height: 1000
                            fillMode: Image.PreserveAspectCrop
                        }
                        layer.enabled: true
                    }
                }
                // spinning vinyl (right)
                Item {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    VinylItem {
                        anchors.centerIn: parent
                        width: Math.min(parent.width, parent.height)
                        height: width
                        controller: win.appController
                    }
                }
            }

            // lyrics panel (toggled by the "Lyrics" button)
            Item {
                visible: win.showLyrics
                Layout.fillWidth: true; Layout.fillHeight: true
                Label {
                    anchors.centerIn: parent
                    visible: !(controller && controller.hasLyrics)
                    text: "No lyrics found.\nDrop a synced .lrc (or .txt) next to the track."
                    color: theme.textDim; font.pixelSize: 16
                    horizontalAlignment: Text.AlignHCenter
                }
                ListView {
                    id: lyricsView
                    visible: controller && controller.hasLyrics
                    anchors.fill: parent
                    anchors.leftMargin: 40; anchors.rightMargin: 40
                    clip: true
                    model: controller ? controller.lyricsLines : []
                    boundsBehavior: Flickable.StopAtBounds
                    // auto-scroll the active synced line to the middle
                    property int active: controller ? controller.lyricIndex : -1
                    onActiveChanged: if (active >= 0) positionViewAtIndex(active, ListView.Center)
                    delegate: Item {
                        required property var modelData
                        required property int index
                        width: lyricsView.width
                        implicitHeight: lyr.implicitHeight + 16
                        Label {
                            id: lyr
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            text: modelData.text.length > 0 ? modelData.text : "♪"
                            color: (controller && controller.lyricsSynced
                                    && index === lyricsView.active)
                                   ? theme.accent : theme.textDim
                            font.pixelSize: (controller && controller.lyricsSynced
                                    && index === lyricsView.active) ? 24 : 18
                            font.weight: (controller && controller.lyricsSynced
                                    && index === lyricsView.active)
                                   ? Font.Bold : Font.Normal
                            Behavior on font.pixelSize { NumberAnimation { duration: 150 } }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.alignment: Qt.AlignHCenter; spacing: 4
                Label {
                    text: controller ? controller.npTitle : ""
                    color: theme.text; font.pixelSize: 30; font.weight: Font.Bold
                    horizontalAlignment: Text.AlignHCenter
                }
                Label {
                    text: controller ? controller.npSub : ""
                    color: theme.textDim; font.pixelSize: 16
                    horizontalAlignment: Text.AlignHCenter
                }
            }

            // seek strip (queue-wide)
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 80; Layout.rightMargin: 80
                spacing: 12
                Label { text: controller ? controller.timeElapsed : "0:00"
                        color: theme.textDim; font.pixelSize: 13 }
                Rectangle {
                    id: seekBarExp
                    Layout.fillWidth: true; Layout.preferredHeight: 6
                    Layout.alignment: Qt.AlignVCenter
                    radius: 3; color: theme.line
                    Rectangle {
                        height: parent.height; radius: 3
                        width: parent.width * (controller ? controller.npPosition : 0)
                        color: theme.accent
                    }
                    Repeater {
                        model: controller ? controller.trackMarkers : []
                        delegate: Rectangle {
                            required property var modelData
                            width: 2; height: 10
                            y: (seekBarExp.height - height) / 2
                            x: seekBarExp.width * modelData - width / 2
                            color: theme.bg
                        }
                    }
                    TapHandler { onTapped: function (ev) {
                        controller.seek(ev.position.x / seekBarExp.width) } }
                    DragHandler { target: null
                        onCentroidChanged: if (active)
                            controller.seek(centroid.position.x / seekBarExp.width) }
                }
                Label { text: controller ? controller.timeTotal : "0:00"
                        color: theme.textDim; font.pixelSize: 13 }
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter; spacing: 18
                IconButton { flat: true; size: 40; glyph: "🔀"
                             color: (controller && controller.shuffle)
                                    ? theme.surfaceHover : "transparent"
                             onClicked: controller.setShuffle(!controller.shuffle) }
                IconButton { flat: true; size: 46; glyph: "⏮"
                             onClicked: controller.previous() }
                IconButton { flat: true; size: 54
                             glyph: (controller && controller.npIsPlaying) ? "⏸" : "▶"
                             onClicked: controller.playPause() }
                IconButton { flat: true; size: 46; glyph: "⏭"
                             onClicked: controller.next() }
                IconButton { flat: true; size: 40
                             glyph: (controller && controller.repeatMode === "one")
                                    ? "🔂" : "🔁"
                             color: (controller && controller.repeatMode !== "off")
                                    ? theme.surfaceHover : "transparent"
                             onClicked: controller.cycleRepeat() }
                IconButton { flat: true; size: 40
                             glyph: (controller && controller.npIsFavorite) ? "♥" : "♡"
                             onClicked: controller.toggleFavoriteCurrent() }
                Item { Layout.preferredWidth: 10 }
                // volume
                IconButton { flat: true; size: 40
                             glyph: (controller && (controller.muted
                                     || controller.volume === 0)) ? "🔇" : "🔊"
                             onClicked: controller.toggleMute() }
                Rectangle {
                    id: volBarExp
                    Layout.preferredWidth: 110; Layout.preferredHeight: 6
                    Layout.alignment: Qt.AlignVCenter
                    radius: 3; color: theme.line
                    Rectangle { height: parent.height; radius: 3
                        width: parent.width * (controller ? controller.volume / 100 : 1)
                        color: theme.textDim }
                    TapHandler { onTapped: function (ev) {
                        controller.setVolume(Math.round(ev.position.x / volBarExp.width * 100)) } }
                    DragHandler { target: null
                        onCentroidChanged: if (active)
                            controller.setVolume(Math.round(centroid.position.x / volBarExp.width * 100)) }
                }
                Item { Layout.preferredWidth: 10 }
                // lyrics + vinyl toggles
                IconButton { flat: true; size: 40; glyph: "♫"
                             color: win.showLyrics ? theme.surfaceHover : "transparent"
                             onClicked: win.showLyrics = !win.showLyrics }
                IconButton { flat: true; size: 40; glyph: "◉"
                             onClicked: { win.expanded = false; win.openVinylConfig() } }
            }
        }

        // collapse back to the compact header (also: Esc)
        IconButton {
            anchors.top: parent.top; anchors.right: parent.right
            anchors.margins: 18
            size: 46; glyph: "✕"
            onClicked: win.expanded = false
        }
    }

    // ====================== reusable components ======================
    component NavItem: Rectangle {
        property string label
        property bool active: false
        signal clicked()
        Layout.fillWidth: true
        implicitHeight: 38
        radius: 8
        color: active ? theme.surface : (hh.hovered ? theme.surfaceHover : "transparent")
        border.width: activeFocus ? 2 : 0; border.color: theme.accent
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: label
        Accessible.onPressAction: clicked()
        Keys.onReturnPressed: clicked()
        Keys.onEnterPressed: clicked()
        Label {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left; anchors.leftMargin: 12
            text: parent.label
            color: parent.active ? theme.accent : theme.text
            font.pixelSize: 14; font.weight: parent.active ? Font.DemiBold : Font.Normal
        }
        HoverHandler { id: hh }
        TapHandler { onTapped: parent.clicked() }
    }

    component SearchField: TextField {
        placeholderText: "Search songs, albums, artists…"
        Accessible.name: "Search"
        color: theme.text
        placeholderTextColor: theme.textDim
        selectionColor: theme.accent
        leftPadding: 14; rightPadding: 14; topPadding: 9; bottomPadding: 9
        background: Rectangle {
            radius: 9
            color: theme.surface
            border.width: parent.activeFocus ? 1 : 0
            border.color: theme.accent
        }
    }

    // a square art card that scales up subtly on hover
    component ArtCard: Item {
        property url source
        property int edge: 150
        property string accessibleName
        property bool highlighted: false     // the keyboard's current item in a grid
        signal activated()
        signal rightClicked()
        Accessible.role: Accessible.Button
        Accessible.name: accessibleName
        Accessible.onPressAction: activated()
        implicitWidth: edge; implicitHeight: edge
        Rectangle {
            id: cardRect
            anchors.fill: parent
            radius: theme.radius
            color: theme.surface
            clip: true
            scale: ch.hovered ? 1.035 : 1.0
            Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutQuad } }
            Image {
                anchors.fill: parent
                source: parent.parent.source
                sourceSize.width: 300; sourceSize.height: 300
                asynchronous: true
                fillMode: Image.PreserveAspectCrop
            }
            Rectangle {            // hover accent ring
                anchors.fill: parent
                radius: theme.radius
                color: "transparent"
                border.width: (ch.hovered || parent.parent.highlighted) ? 2 : 0
                border.color: theme.accent
            }
            layer.enabled: true
        }
        HoverHandler { id: ch }
        TapHandler { onTapped: activated() }
        TapHandler { acceptedButtons: Qt.RightButton; onTapped: rightClicked() }
    }

    // page title row with optional back button
    component PageHeader: RowLayout {
        property string title
        property bool showBack: false
        signal back()
        Layout.fillWidth: true
        Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
        Layout.topMargin: 14; Layout.bottomMargin: 10
        spacing: 12
        IconButton {
            visible: parent.showBack
            glyph: "‹"
            onClicked: parent.back()
        }
        Label {
            text: parent.title
            color: theme.text
            font.pixelSize: 24; font.weight: Font.Bold
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
    }

    component IconButton: Rectangle {
        property string glyph
        property bool accent: false
        property bool flat: false        // Elisa-style: transparent, icon-only
        property int size: 38
        property string tip: ""          // what it does; defaults to a name for the glyph
        signal clicked()
        implicitWidth: size; implicitHeight: size
        activeFocusOnTab: true
        border.width: activeFocus ? 2 : 0; border.color: theme.accent
        Accessible.role: Accessible.Button
        Accessible.name: tip !== "" ? tip : win.glyphName(glyph)
        Accessible.onPressAction: clicked()
        Keys.onReturnPressed: clicked()
        Keys.onEnterPressed: clicked()
        ToolTip.visible: ib.hovered
        ToolTip.delay: 700
        ToolTip.text: tip !== "" ? tip : win.glyphName(glyph)
        radius: width / 2
        color: flat ? (ib.hovered ? theme.surfaceHover : "transparent")
                    : (accent ? theme.accent
                              : (ib.hovered ? theme.surfaceHover : theme.surface))
        Label {
            anchors.centerIn: parent
            text: parent.glyph
            color: (parent.accent && !parent.flat) ? theme.accentText
                   : (ib.hovered ? theme.text : theme.textDim)
            font.pixelSize: Math.round(parent.size * (parent.accent && !parent.flat ? 0.46 : 0.5))
        }
        HoverHandler { id: ib }
        TapHandler { onTapped: parent.clicked() }
    }

    // a row of pill options; the one matching `current` is highlighted
    component Segmented: Row {
        property var options: []
        property var current
        signal picked(var value)
        spacing: 8
        Repeater {
            model: parent.options
            delegate: Rectangle {
                required property var modelData
                implicitHeight: 34
                implicitWidth: segLbl.implicitWidth + 28
                radius: 17
                color: modelData.value === current ? theme.accent
                       : (segH.hovered ? theme.line : theme.surfaceHover)
                Label {
                    id: segLbl; anchors.centerIn: parent; text: modelData.label
                    color: modelData.value === current ? theme.accentText : theme.text
                    font.pixelSize: 13
                }
                activeFocusOnTab: true
                border.width: activeFocus ? 2 : 0; border.color: theme.text
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checkable: true
                Accessible.checked: modelData.value === current
                Accessible.onPressAction: picked(modelData.value)
                Keys.onReturnPressed: picked(modelData.value)
                Keys.onEnterPressed: picked(modelData.value)
                HoverHandler { id: segH }
                TapHandler { onTapped: picked(modelData.value) }
            }
        }
    }

    // a dark-themed horizontal slider (settings: crossfade / preamp)
    component ThemeSlider: Slider {
        id: sld
        from: 0; to: 100
        implicitHeight: 24
        background: Rectangle {
            x: sld.leftPadding
            y: sld.topPadding + sld.availableHeight / 2 - height / 2
            width: sld.availableWidth; height: 6; radius: 3; color: theme.line
            Rectangle { width: sld.visualPosition * parent.width
                        height: parent.height; radius: 3; color: theme.accent }
        }
        handle: Rectangle {
            x: sld.leftPadding + sld.visualPosition * (sld.availableWidth - width)
            y: sld.topPadding + sld.availableHeight / 2 - height / 2
            width: 16; height: 16; radius: 8
            color: sld.pressed ? Qt.lighter(theme.accent, 1.1) : theme.text
            border.color: theme.accent; border.width: 1
        }
    }

    // a full-width clickable row for action sheets
    component SheetRow: Rectangle {
        property string label
        signal clicked()
        Layout.fillWidth: true
        implicitHeight: 44
        radius: 8
        color: srh.hovered ? theme.surfaceHover : "transparent"
        border.width: activeFocus ? 2 : 0; border.color: theme.accent
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: label
        Accessible.onPressAction: clicked()
        Keys.onReturnPressed: clicked()
        Keys.onEnterPressed: clicked()
        Label {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left; anchors.leftMargin: 12
            text: parent.label; color: theme.text; font.pixelSize: 14
        }
        HoverHandler { id: srh }
        TapHandler { onTapped: parent.clicked() }
    }

    // a dark-themed text input
    component Field: TextField {
        color: theme.text
        placeholderTextColor: theme.textDim
        selectionColor: theme.accent
        leftPadding: 12; rightPadding: 12; topPadding: 8; bottomPadding: 8
        background: Rectangle {
            radius: 8; color: theme.surfaceHover
            border.width: parent.activeFocus ? 1 : 0; border.color: theme.accent
        }
    }

    // popup background that swallows taps in empty areas — a modal Popup does
    // not reliably block the TapHandlers on items behind it, so without this a
    // tap that misses a control leaks through to the page underneath.
    component PopupBg: Rectangle {
        color: theme.surface; radius: 14
        border.width: 1; border.color: theme.line
        MouseArea { anchors.fill: parent }
    }

    // a vinyl swatch (rendered disc preview) for the override chooser
    component Swatch: Column {
        property url source
        property string caption
        property bool selected: false
        property int diameter: 72
        signal clicked()
        spacing: 5
        activeFocusOnTab: true
        Accessible.role: Accessible.RadioButton
        Accessible.name: caption
        Accessible.checkable: true
        Accessible.checked: selected
        Accessible.onPressAction: clicked()
        Keys.onReturnPressed: clicked()
        Keys.onEnterPressed: clicked()
        Rectangle {
            width: diameter; height: diameter; radius: diameter / 2
            anchors.horizontalCenter: parent.horizontalCenter
            color: "transparent"
            border.width: (selected || parent.activeFocus) ? 3 : 0; border.color: theme.accent
            Image {
                anchors.fill: parent; anchors.margins: 3
                source: parent.parent.source
                sourceSize.width: diameter * 2; sourceSize.height: diameter * 2
                asynchronous: true
            }
        }
        Label {
            width: diameter + 14; text: caption; horizontalAlignment: Text.AlignHCenter
            color: selected ? theme.accent : theme.textDim
            font.pixelSize: diameter > 90 ? 12 : 10; elide: Text.ElideRight
        }
        HoverHandler { }
        TapHandler { onTapped: clicked() }
    }

    // mouse-wheel scroll booster — the default Flickable wheel step is tiny.
    // Notched mouse wheels (angleDelta in ±120 steps) get a big content jump;
    // touchpad pixel-scrolls (angleDelta 0) fall through to native smooth flicking.
    component WheelScroller: WheelHandler {
        property var view          // a Flickable (GridView/ListView/ScrollView flickable)
        property real lines: 0.6   // multiplier per wheel notch
        onWheel: function (ev) {
            if (!view || view.contentHeight === undefined) return
            if (ev.angleDelta.y === 0) return         // touchpad → leave it to Flickable
            var maxY = Math.max(0, view.contentHeight - view.height)
            view.contentY = Math.max(0, Math.min(maxY,
                view.contentY - ev.angleDelta.y * lines))
            ev.accepted = true
        }
    }

    // a small pill button used in popups
    component Pill: Rectangle {
        property string label
        property bool selected: false
        signal clicked()
        implicitHeight: 30
        implicitWidth: pillLbl.implicitWidth + 22
        radius: 15
        color: selected ? theme.accent : (pillH.hovered ? theme.line : theme.surfaceHover)
        border.width: activeFocus ? 2 : 0; border.color: theme.text
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: label
        Accessible.checkable: selected
        Accessible.checked: selected
        Accessible.onPressAction: clicked()
        Keys.onReturnPressed: clicked()
        Keys.onEnterPressed: clicked()
        Label { id: pillLbl; anchors.centerIn: parent; text: parent.label
                color: parent.selected ? theme.accentText : theme.text; font.pixelSize: 12 }
        HoverHandler { id: pillH }
        TapHandler { onTapped: parent.clicked() }
    }

    // an on/off row for settings
    component SettingToggle: Rectangle {
        id: tg
        property string label
        property string detail: ""
        property bool checked: false
        signal toggled(bool on)
        Layout.fillWidth: true
        implicitHeight: tgCol.implicitHeight + 14
        radius: 8
        color: tgH.hovered ? theme.surfaceHover : "transparent"
        border.width: activeFocus ? 2 : 0; border.color: theme.accent
        opacity: enabled ? 1 : 0.5
        activeFocusOnTab: true
        Accessible.role: Accessible.CheckBox
        Accessible.name: label
        Accessible.description: detail
        Accessible.checkable: true
        Accessible.checked: checked
        Accessible.onToggleAction: toggled(!checked)
        Accessible.onPressAction: toggled(!checked)
        Keys.onReturnPressed: toggled(!checked)
        Keys.onEnterPressed: toggled(!checked)
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
            spacing: 10
            ColumnLayout {
                id: tgCol
                Layout.fillWidth: true; spacing: 1
                Label { text: tg.label; color: theme.text; font.pixelSize: 13
                        wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Label { visible: tg.detail !== ""; text: tg.detail; color: theme.textDim
                        font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
            Rectangle {
                implicitWidth: 38; implicitHeight: 22; radius: 11
                color: tg.checked ? theme.accent : theme.line
                Rectangle {
                    width: 16; height: 16; radius: 8; y: 3
                    x: tg.checked ? parent.width - width - 3 : 3
                    color: tg.checked ? theme.accentText : theme.textDim
                    Behavior on x { NumberAnimation { duration: 120 } }
                }
            }
        }
        HoverHandler { id: tgH }
        TapHandler { onTapped: tg.toggled(!tg.checked) }
    }

    // a dark-themed drop-down
    component ThemeCombo: ComboBox {
        id: cbx
        implicitHeight: 34
        font.pixelSize: 13
        background: Rectangle {
            radius: 8
            color: cbx.hovered ? theme.line : theme.surfaceHover
            border.width: cbx.activeFocus ? 1 : 0; border.color: theme.accent
        }
        contentItem: Label {
            leftPadding: 10; rightPadding: 22
            text: cbx.displayText; color: theme.text; font: cbx.font
            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        }
        indicator: Label {
            x: cbx.width - width - 10; anchors.verticalCenter: parent.verticalCenter
            text: "▾"; color: theme.textDim
        }
        delegate: ItemDelegate {
            required property var modelData
            required property int index
            width: cbx.width
            highlighted: cbx.highlightedIndex === index
            contentItem: Label { text: modelData[cbx.textRole]; color: theme.text
                                 font: cbx.font; elide: Text.ElideRight }
            background: Rectangle { color: highlighted ? theme.surfaceHover : theme.surface }
        }
        popup: Popup {
            y: cbx.height + 2; width: cbx.width; padding: 4
            implicitHeight: Math.min(contentItem.implicitHeight + 8, 320)
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: cbx.popup.visible ? cbx.delegateModel : null
                currentIndex: cbx.highlightedIndex
                ScrollBar.vertical: ScrollBar { }
            }
            background: Rectangle { color: theme.surface; radius: 8
                                    border.width: 1; border.color: theme.line }
        }
    }

    // ============================ pages ============================

    // ---- Artists grid ----
    Component {
        id: artistsPage
        ColumnLayout {
            spacing: 0
            PageHeader { title: "Artists" }
            GridView {
                id: grid
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true
                // grid auto-fits the window: item size is the setting, column
                // count is derived from the available width.
                property int tile: controller.gridTile
                property int gap: 22
                property int avail: width - 2 * theme.pad
                property int cols: Math.max(1, Math.floor(avail / (tile + gap)))
                cellWidth: cols > 0 ? avail / cols : tile + gap
                cellHeight: tile + 54
                leftMargin: theme.pad; rightMargin: theme.pad; bottomMargin: theme.pad
                model: artistsModel
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { }
                WheelScroller { view: grid }
                // keyboard: Tab into the grid, arrows move, Return opens
                activeFocusOnTab: true
                currentIndex: -1
                onActiveFocusChanged: if (activeFocus && currentIndex < 0 && count > 0) currentIndex = 0
                Keys.onReturnPressed: if (currentItem) win.openArtist(currentItem.artistId, currentItem.name)
                Keys.onEnterPressed: if (currentItem) win.openArtist(currentItem.artistId, currentItem.name)
                delegate: Item {
                    width: grid.cellWidth; height: grid.cellHeight
                    required property string name
                    required property int artistId
                    required property int index
                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 10
                        ArtCard {
                            Layout.alignment: Qt.AlignHCenter
                            edge: grid.tile
                            source: "image://tiles/artist/" + artistId
                            accessibleName: name
                            highlighted: grid.activeFocus && grid.currentIndex === index
                            onActivated: win.openArtist(artistId, name)
                            onRightClicked: win.addArtistToPlaylist(artistId)
                        }
                        Label {
                            Layout.preferredWidth: grid.tile + 10
                            Layout.alignment: Qt.AlignHCenter
                            text: name
                            color: theme.text
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight; maximumLineCount: 2
                            wrapMode: Text.WordWrap
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }
    }

    // ---- Albums grid (one artist) ----
    Component {
        id: albumsPage
        ColumnLayout {
            id: albPg
            property int artistId: -1          // -1: every album in the library
            property string artistName
            // comma-expr makes the binding depend on albumSort → re-queries on change
            property var albumsData: (controller.albumSort,
                                      artistId >= 0 ? controller.artistAlbums(artistId)
                                                    : controller.allAlbums())
            spacing: 0
            PageHeader {
                title: albPg.artistId >= 0 ? artistName : "Albums"
                showBack: stack.depth > 1; onBack: stack.pop()
            }
            GridView {
                id: agrid
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true
                property int tile: controller.gridTile
                property int gap: 22
                property int avail: width - 2 * theme.pad
                property int cols: Math.max(1, Math.floor(avail / (tile + gap)))
                cellWidth: cols > 0 ? avail / cols : tile + gap
                cellHeight: tile + 66
                leftMargin: theme.pad; rightMargin: theme.pad; bottomMargin: theme.pad
                model: albumsData
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { }
                WheelScroller { view: agrid }
                activeFocusOnTab: true
                currentIndex: -1
                onActiveFocusChanged: if (activeFocus && currentIndex < 0 && count > 0) currentIndex = 0
                function openCurrent() {
                    if (!currentItem) return
                    var m = currentItem.modelData
                    win.openAlbum(m.id, m.name, m.year, m.coverUrl)
                }
                Keys.onReturnPressed: openCurrent()
                Keys.onEnterPressed: openCurrent()
                delegate: Item {
                    width: agrid.cellWidth; height: agrid.cellHeight
                    required property var modelData
                    required property int index
                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 10
                        ArtCard {
                            Layout.alignment: Qt.AlignHCenter
                            edge: agrid.tile
                            source: modelData.coverUrl
                            accessibleName: modelData.name
                            highlighted: agrid.activeFocus && agrid.currentIndex === index
                            onActivated: win.openAlbum(modelData.id, modelData.name,
                                                       modelData.year, modelData.coverUrl)
                            onRightClicked: win.addAlbumToPlaylist(modelData.path)
                        }
                        ColumnLayout {
                            Layout.preferredWidth: agrid.tile + 10
                            spacing: 1
                            Label {
                                Layout.fillWidth: true
                                text: modelData.name; color: theme.text
                                elide: Text.ElideRight; font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Label {
                                text: albPg.artistId >= 0 ? (modelData.year || "")
                                      : [modelData.artist, modelData.year].filter(Boolean).join("  ·  ")
                                Layout.fillWidth: true; elide: Text.ElideRight
                                color: theme.textDim; font.pixelSize: 11
                            }
                        }
                    }
                }
            }
        }
    }

    // ---- Song table (album or playlist) ----
    Component {
        id: songsPage
        ColumnLayout {
            id: songPg
            property int albumId: -1
            property int playlistId: -1
            property string smartKind: ""      // favorites | recent | most | added
            property string genreName: ""
            property int smartId: -1           // a smart playlist you defined
            property string headerTitle
            property string albumYear
            property url coverUrl
            property bool isAlbum: albumId >= 0
            property bool isSmart: smartKind.length > 0 || genreName.length > 0 || smartId >= 0
            function querySongs() {
                if (isAlbum) return controller.albumSongs(albumId)
                if (smartId >= 0) return controller.smartPlaylistSongs(smartId)
                if (genreName.length > 0) return controller.genreSongs(genreName)
                if (smartKind.length > 0) return controller.smartList(smartKind)
                return controller.playlistSongs(playlistId)
            }
            property var songs: querySongs()
            function play(i) {
                if (isAlbum) controller.playAlbum(albumId, i)
                else if (isSmart)
                    controller.playPaths(songs.map(function(s){ return s.path }), i)
                else controller.playPlaylist(playlistId, i)
            }
            property var selectedPaths: []
            function reload() { songs = querySongs() }
            function toggleSel(p) {
                var a = selectedPaths.slice(); var i = a.indexOf(p)
                if (i >= 0) a.splice(i, 1); else a.push(p)
                selectedPaths = a
            }
            function isSel(p) { return selectedPaths.indexOf(p) >= 0 }
            Connections {
                target: controller
                function onSongsChanged() { songPg.reload() }
            }
            spacing: 0

            // header
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                Layout.topMargin: 16; Layout.bottomMargin: 12
                spacing: 16
                IconButton { glyph: "‹"; visible: stack.depth > 1
                             onClicked: stack.pop() }
                Rectangle {
                    visible: isAlbum
                    width: 104; height: 104; radius: theme.radius
                    color: theme.surface; clip: true
                    Image {
                        anchors.fill: parent; source: coverUrl
                        sourceSize.width: 208; sourceSize.height: 208
                        fillMode: Image.PreserveAspectCrop; asynchronous: true
                    }
                    layer.enabled: true
                }
                ColumnLayout {
                    spacing: 4
                    Label { text: headerTitle; color: theme.text
                            font.pixelSize: 26; font.weight: Font.Bold }
                    Label { text: (isAlbum && albumYear ? albumYear + "  ·  " : "")
                                  + songs.length + " songs"
                            color: theme.textDim; font.pixelSize: 13 }
                    Item { height: 6 }
                    RowLayout {
                        spacing: 10
                        Rectangle {
                            implicitWidth: 116; implicitHeight: 38; radius: 19
                            color: pb.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent
                            Label { anchors.centerIn: parent; text: "▶   Play"
                                    color: theme.accentText; font.pixelSize: 14
                                    font.weight: Font.DemiBold }
                            HoverHandler { id: pb }
                            TapHandler { onTapped: songPg.play(0) }
                        }
                        Rectangle {
                            implicitWidth: 116; implicitHeight: 38; radius: 19
                            color: qbtn.hovered ? theme.surfaceHover : theme.surface
                            border.width: 1; border.color: theme.line
                            Label { anchors.centerIn: parent; text: "＋  Queue"
                                    color: theme.text; font.pixelSize: 13 }
                            HoverHandler { id: qbtn }
                            TapHandler {
                                onTapped: {
                                    if (songPg.isAlbum)
                                        controller.queueAlbum(songPg.albumId, false)
                                    else
                                        controller.queueTracks(
                                            songPg.songs.map(function(s){ return s.path }), false)
                                }
                            }
                        }
                        Rectangle {
                            implicitWidth: 150; implicitHeight: 38; radius: 19
                            color: apb.hovered ? theme.surfaceHover : theme.surface
                            border.width: 1; border.color: theme.line
                            Label { anchors.centerIn: parent; text: "＋  Add to playlist"
                                    color: theme.text; font.pixelSize: 13 }
                            HoverHandler { id: apb }
                            TapHandler {
                                onTapped: win.addSongsToPlaylist(
                                    songPg.songs.map(function(s){ return s.path }))
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
            }

            // selection action bar
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                implicitHeight: songPg.selectedPaths.length > 0 ? 44 : 0
                visible: songPg.selectedPaths.length > 0
                radius: 8; color: theme.surface
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 10
                    spacing: 12
                    Label { text: songPg.selectedPaths.length + " selected"
                            color: theme.text; font.pixelSize: 13 }
                    Item { Layout.fillWidth: true }
                    Rectangle {
                        implicitWidth: 150; implicitHeight: 32; radius: 16
                        color: selAdd.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent
                        Label { anchors.centerIn: parent; text: "Add to playlist"
                                color: theme.accentText; font.pixelSize: 12
                                font.weight: Font.DemiBold }
                        HoverHandler { id: selAdd }
                        TapHandler { onTapped: win.addSongsToPlaylist(songPg.selectedPaths) }
                    }
                    IconButton { glyph: "✕"; flat: true; size: 30
                                 onClicked: songPg.selectedPaths = [] }
                }
            }

            // table column header
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: theme.pad + 8; Layout.rightMargin: theme.pad + 8
                Layout.topMargin: 6
                spacing: 12
                Label { text: "#"; color: theme.textDim; font.pixelSize: 11
                        Layout.preferredWidth: 28; horizontalAlignment: Text.AlignRight }
                Label { text: "TITLE"; color: theme.textDim; font.pixelSize: 11
                        Layout.fillWidth: true }
                Label { text: "DURATION"; color: theme.textDim; font.pixelSize: 11 }
            }
            Rectangle { Layout.fillWidth: true; Layout.leftMargin: theme.pad
                        Layout.rightMargin: theme.pad; Layout.topMargin: 6
                        implicitHeight: 1; color: theme.line }

            ListView {
                id: songList
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true
                topMargin: 4; bottomMargin: theme.pad
                model: songs
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { }
                WheelScroller { view: songList }
                property int rowH: 46
                // keyboard: Tab into the list, arrows move, Return plays, Menu for actions
                activeFocusOnTab: true
                currentIndex: -1
                onActiveFocusChanged: if (activeFocus && currentIndex < 0 && count > 0) currentIndex = 0
                Keys.onReturnPressed: if (currentIndex >= 0) songPg.play(songs[currentIndex].index)
                Keys.onEnterPressed: if (currentIndex >= 0) songPg.play(songs[currentIndex].index)
                Keys.onMenuPressed: {
                    if (currentIndex < 0) return
                    var s = songs[currentIndex]
                    win.trackActions(s.path, s.title, songPg.isAlbum ? -1 : songPg.playlistId, s.index)
                }
                delegate: Item {
                    id: rowItem
                    required property var modelData
                    width: songList.width
                    height: songList.rowH
                    z: drag.active ? 2 : 1
                    Accessible.role: Accessible.ListItem
                    Accessible.name: modelData.title + ", " + modelData.artist
                                     + (modelData.available === false ? ", missing" : "")
                    Rectangle {
                        id: rowRect
                        width: songList.width - 2 * theme.pad
                        x: theme.pad
                        height: songList.rowH - 2
                        radius: 7
                        // a playlist entry whose file is gone stays, dimmed
                        opacity: rowItem.modelData.available === false ? 0.45 : 1.0
                        // dragging detaches the row vertically; otherwise it sits flush
                        y: drag.active ? (rowItem.height - height) / 2 + drag.translation.y : (rowItem.height - height) / 2
                        color: songPg.isSel(rowItem.modelData.path)
                               ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.18)
                               : (drag.active ? theme.surfaceHover
                                              : ((rh.hovered || (songList.activeFocus && rowItem.ListView.isCurrentItem))
                                                 ? theme.surfaceHover : "transparent"))
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8; anchors.rightMargin: 8
                            spacing: 12
                            // selection checkbox / drag handle / track number
                            Item {
                                Layout.preferredWidth: 28; Layout.preferredHeight: 28
                                Label {
                                    anchors.centerIn: parent
                                    visible: !rh.hovered && !songPg.isSel(rowItem.modelData.path)
                                    text: rowItem.modelData.trackNo > 0 ? rowItem.modelData.trackNo
                                                                        : (rowItem.modelData.index + 1)
                                    color: theme.textDim; font.pixelSize: 13
                                }
                                Rectangle {       // select checkbox
                                    anchors.centerIn: parent
                                    width: 18; height: 18; radius: 9
                                    visible: rh.hovered || songPg.isSel(rowItem.modelData.path)
                                    color: songPg.isSel(rowItem.modelData.path) ? theme.accent : "transparent"
                                    border.width: 1
                                    border.color: songPg.isSel(rowItem.modelData.path) ? theme.accent : theme.textDim
                                    Label { anchors.centerIn: parent; text: "✓"
                                            visible: songPg.isSel(rowItem.modelData.path)
                                            color: theme.accentText; font.pixelSize: 11 }
                                    TapHandler { onTapped: songPg.toggleSel(rowItem.modelData.path) }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 0
                                Label {
                                    // only the TITLE TEXT plays — sized to its
                                    // content so the click area is just the words,
                                    // not the empty rest of the row.
                                    id: titleLabel
                                    text: rowItem.modelData.title
                                    color: titleHover.hovered ? theme.accent : theme.text
                                    font.pixelSize: 14; elide: Text.ElideRight
                                    Layout.fillWidth: false
                                    Layout.maximumWidth: parent.width
                                    HoverHandler {
                                        id: titleHover
                                        cursorShape: Qt.PointingHandCursor
                                    }
                                    TapHandler {
                                        onTapped: songPg.play(rowItem.modelData.index)
                                    }
                                }
                                Label { text: rowItem.modelData.artist; color: theme.textDim
                                        font.pixelSize: 11; elide: Text.ElideRight
                                        Layout.fillWidth: true }
                            }
                            Label { text: win.fmtTime(rowItem.modelData.duration)
                                    color: theme.textDim; font.pixelSize: 13 }
                            // drag handle (playlists only)
                            Label {
                                visible: !songPg.isAlbum && rh.hovered
                                text: "≡"; color: theme.textDim; font.pixelSize: 18
                                Layout.preferredWidth: 18
                                DragHandler {
                                    id: drag
                                    target: null
                                    xAxis.enabled: false
                                    yAxis.enabled: true
                                    onActiveChanged: {
                                        if (!active) {
                                            var delta = Math.round(translation.y / songList.rowH)
                                            var to = rowItem.modelData.index + delta
                                            controller.movePlaylistTrack(songPg.playlistId,
                                                rowItem.modelData.index, to)
                                        }
                                    }
                                }
                            }
                        }
                        HoverHandler { id: rh }
                        // right-click anywhere on the row opens the action sheet;
                        // left-click only plays via the title (above)
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: win.trackActions(rowItem.modelData.path,
                                                       rowItem.modelData.title,
                                                       songPg.isAlbum ? -1 : songPg.playlistId,
                                                       rowItem.modelData.index)
                        }
                    }
                }
            }
        }
    }

    // ---- Playlists ----
    Component {
        id: playlistsPage
        ColumnLayout {
            id: plPage
            property var lists: controller.playlists()
            property var smartLists: controller.smartPlaylists()
            function reload() { lists = controller.playlists(); smartLists = controller.smartPlaylists() }
            Connections { target: controller
                          function onPlaylistsChanged() { plPage.reload() } }
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                Layout.topMargin: 14; Layout.bottomMargin: 10
                Label { text: "Playlists"; color: theme.text
                        font.pixelSize: 24; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                Pill { label: "Import…"; implicitHeight: 36; onClicked: importDialog.open() }
                Pill { label: "＋  Smart playlist"; implicitHeight: 36
                       onClicked: smartEditor.openFor(-1) }
                Rectangle {
                    implicitWidth: 150; implicitHeight: 36; radius: 18
                    color: npb.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent
                    Accessible.role: Accessible.Button
                    Accessible.name: "New playlist"
                    Accessible.onPressAction: newPlaylistPopup.open()
                    Label { anchors.centerIn: parent; text: "＋  New playlist"
                            color: theme.accentText; font.pixelSize: 13
                            font.weight: Font.DemiBold }
                    HoverHandler { id: npb }
                    TapHandler { onTapped: newPlaylistPopup.open() }
                }
            }
            Label {
                visible: plPage.smartLists.length > 0
                text: "SMART PLAYLISTS"; color: theme.textDim
                font.pixelSize: 11; font.weight: Font.Bold
                Layout.leftMargin: theme.pad + 12; Layout.topMargin: 4
            }
            Repeater {
                model: plPage.smartLists
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                    implicitHeight: 46; radius: 7
                    color: (sph.hovered || activeFocus) ? theme.surfaceHover : "transparent"
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: "Smart playlist " + modelData.name
                    Accessible.onPressAction: win.openSmartPlaylist(modelData.id, modelData.name)
                    Keys.onReturnPressed: win.openSmartPlaylist(modelData.id, modelData.name)
                    Keys.onMenuPressed: smartActions.openFor(modelData.id, modelData.name)
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                        spacing: 12
                        Label { text: "✦"; color: theme.accent; font.pixelSize: 15
                                Layout.preferredWidth: 20 }
                        Label { text: modelData.name; color: theme.text; font.pixelSize: 15
                                Layout.fillWidth: true; elide: Text.ElideRight }
                        Label { text: "right-click to edit"; color: theme.textDim
                                font.pixelSize: 11; visible: sph.hovered }
                    }
                    HoverHandler { id: sph }
                    TapHandler { onTapped: win.openSmartPlaylist(modelData.id, modelData.name) }
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: smartActions.openFor(modelData.id, modelData.name)
                    }
                }
            }
            Label {
                visible: plPage.smartLists.length > 0 && plPage.lists.length > 0
                text: "PLAYLISTS"; color: theme.textDim
                font.pixelSize: 11; font.weight: Font.Bold
                Layout.leftMargin: theme.pad + 12; Layout.topMargin: 10
            }
            Label {
                visible: lists.length === 0 && plPage.smartLists.length === 0
                Layout.fillWidth: true; Layout.topMargin: 40
                text: "No playlists yet. Create one, then add songs from the ⋯ menu."
                color: theme.textDim; font.pixelSize: 15
                horizontalAlignment: Text.AlignHCenter
            }
            // takes the spare height when there's no playlist list to fill it
            Item { Layout.fillHeight: true; visible: !plList.visible }
            ListView {
                id: plList
                visible: lists.length > 0
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true
                topMargin: 6; bottomMargin: theme.pad
                model: lists
                ScrollBar.vertical: ScrollBar { }
                WheelScroller { view: plList }
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width - 2 * theme.pad; x: theme.pad
                    height: 48; radius: 7
                    color: ph.hovered ? theme.surfaceHover : "transparent"
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                        spacing: 12
                        Label { text: "♪"; color: theme.accent; font.pixelSize: 16
                                Layout.preferredWidth: 20 }
                        Label { text: modelData.name; color: theme.text
                                font.pixelSize: 15; Layout.fillWidth: true }
                        Label { text: modelData.count + " songs"; color: theme.textDim
                                font.pixelSize: 12 }
                    }
                    HoverHandler { id: ph }
                    TapHandler { onTapped: win.openPlaylist(modelData.id, modelData.name) }
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: {
                            playlistActions.plId = modelData.id
                            playlistActions.plName = modelData.name
                            playlistActions.open()
                        }
                    }
                }
            }
        }
    }

    // ---- Genres ----
    Component {
        id: genresPage
        ColumnLayout {
            id: gnPage
            property var items: controller.genreList()
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                Layout.topMargin: 14; Layout.bottomMargin: 10
                Label { text: "Genres"; color: theme.text
                        font.pixelSize: 24; font.weight: Font.Bold }
            }
            Label {
                visible: gnPage.items.length === 0
                Layout.fillWidth: true; Layout.topMargin: 40
                text: "No genres tagged yet."
                color: theme.textDim; font.pixelSize: 15
                horizontalAlignment: Text.AlignHCenter
            }
            ListView {
                id: gnList
                visible: gnPage.items.length > 0
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true; topMargin: 6; bottomMargin: theme.pad
                model: gnPage.items
                ScrollBar.vertical: ScrollBar { }
                WheelScroller { view: gnList }
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width - 2 * theme.pad; x: theme.pad
                    height: 46; radius: 7
                    color: gh.hovered ? theme.surfaceHover : "transparent"
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                        Label { text: "♫"; color: theme.accent; font.pixelSize: 15
                                Layout.preferredWidth: 20 }
                        Label { text: modelData.name; color: theme.text
                                font.pixelSize: 15; Layout.fillWidth: true }
                    }
                    HoverHandler { id: gh }
                    TapHandler { onTapped: win.openGenre(modelData.name) }
                }
            }
        }
    }

    // ---- Search results (artists / albums / songs) ----
    Component {
        id: searchPage
        ScrollView {
            id: sv
            clip: true
            contentWidth: availableWidth
            property var results: controller.search(win.query)
            WheelScroller { view: sv.contentItem }
            ColumnLayout {
                width: sv.availableWidth
                spacing: 6

                // Artists
                Label {
                    visible: sv.results.artists.length > 0
                    text: "ARTISTS"; color: theme.textDim; font.pixelSize: 12
                    Layout.leftMargin: theme.pad; Layout.topMargin: 14
                }
                Flow {
                    visible: sv.results.artists.length > 0
                    Layout.fillWidth: true
                    Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                    spacing: 18
                    Repeater {
                        model: sv.results.artists
                        delegate: Column {
                            required property var modelData
                            width: 120; spacing: 6
                            ArtCard {
                                width: 110; height: 110; edge: 110
                                source: "image://tiles/artist/" + modelData.id
                                onActivated: win.openArtist(modelData.id, modelData.name)
                            }
                            Label { width: 110; text: modelData.name; color: theme.text
                                    horizontalAlignment: Text.AlignHCenter
                                    elide: Text.ElideRight; font.pixelSize: 12 }
                        }
                    }
                }

                // Albums
                Label {
                    visible: sv.results.albums.length > 0
                    text: "ALBUMS"; color: theme.textDim; font.pixelSize: 12
                    Layout.leftMargin: theme.pad; Layout.topMargin: 14
                }
                Flow {
                    visible: sv.results.albums.length > 0
                    Layout.fillWidth: true
                    Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                    spacing: 18
                    Repeater {
                        model: sv.results.albums
                        delegate: Column {
                            required property var modelData
                            width: 124; spacing: 6
                            ArtCard {
                                width: 114; height: 114; edge: 114
                                source: modelData.coverUrl
                                onActivated: win.openAlbum(modelData.id, modelData.name,
                                                           modelData.year, modelData.coverUrl)
                            }
                            Label { width: 114; text: modelData.name; color: theme.text
                                    elide: Text.ElideRight; font.pixelSize: 12 }
                            Label { width: 114; text: modelData.artist; color: theme.textDim
                                    elide: Text.ElideRight; font.pixelSize: 10 }
                        }
                    }
                }

                // Songs
                Label {
                    visible: sv.results.songs.length > 0
                    text: "SONGS"; color: theme.textDim; font.pixelSize: 12
                    Layout.leftMargin: theme.pad; Layout.topMargin: 14
                }
                Repeater {
                    model: sv.results.songs
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                        implicitHeight: 42; radius: 7
                        color: sh.hovered ? theme.surfaceHover : "transparent"
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 12
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 0
                                Label { text: modelData.title; color: theme.text
                                        font.pixelSize: 14; elide: Text.ElideRight
                                        Layout.fillWidth: true }
                                Label { text: modelData.artist + "  ·  " + modelData.album
                                        color: theme.textDim; font.pixelSize: 11
                                        elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                            Label { text: win.fmtTime(modelData.duration)
                                    color: theme.textDim; font.pixelSize: 12 }
                        }
                        HoverHandler { id: sh }
                        TapHandler {
                            onTapped: controller.playAlbum(modelData.albumId, modelData.index)
                        }
                    }
                }
                Label {
                    visible: win.query.length > 0 && sv.results.artists.length === 0
                             && sv.results.albums.length === 0 && sv.results.songs.length === 0
                    Layout.fillWidth: true; Layout.topMargin: 40
                    horizontalAlignment: Text.AlignHCenter
                    text: "Nothing matches \u201c" + win.query + "\u201d."
                    color: theme.text; font.pixelSize: 15
                }
                Label {
                    Layout.fillWidth: true; Layout.topMargin: 18
                    Layout.leftMargin: theme.pad; Layout.rightMargin: theme.pad
                    horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                    text: "Narrow a search with artist:, album:, title:, genre: or year:, "
                          + "for example  artist:pallbearer year:2010-2019  or  album:\"forgotten days\""
                    color: theme.textDim; font.pixelSize: 12
                }
                Item { Layout.preferredHeight: 16 }
            }
        }
    }

    // ---- now playing bar ----
    // Compact Now-Playing header — Elisa-style: album art + info + a flat
    // transport toolbar + a seek/progress line. The spinning vinyl lives in the
    // expanded (full-app) view, reachable via the ⛶ button.
    // Big Now-Playing header, sized like Elisa's: large album art + track text
    // on a dark gradient band, with a flat transport + seek strip beneath it.
    component NowPlayingHeader: Rectangle {
        id: nph
        property bool playing: controller && controller.npTitle.length > 0
        // top of the gradient is tinted by the album art (Elisa-style), blended
        // ~38% into the base so it reads as a wash, not a colour block.
        property color accentColor: (controller && controller.npAccent)
            ? controller.npAccent : theme.accent
        property color tint: playing
            ? Qt.tint(theme.sidebar, Qt.rgba(accentColor.r, accentColor.g,
                                             accentColor.b, 0.38))
            : Qt.darker(theme.sidebar, 1.3)
        implicitHeight: 236
        gradient: Gradient {
            GradientStop { position: 0.0; color: nph.tint }
            GradientStop { position: 1.0; color: theme.sidebar }
        }
        Behavior on tint { ColorAnimation { duration: 400 } }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width
                    height: 1; color: theme.line }

        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 30; anchors.rightMargin: 24
            anchors.topMargin: 22; anchors.bottomMargin: 14
            spacing: 14

            // ---- art + text ----
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                spacing: 26
                Rectangle {
                    Layout.preferredWidth: 150; Layout.preferredHeight: 150
                    Layout.alignment: Qt.AlignVCenter
                    radius: 8; color: theme.surface; clip: true
                    Image {
                        anchors.fill: parent
                        source: controller ? controller.npCoverUrl : ""
                        sourceSize.width: 300; sourceSize.height: 300
                        fillMode: Image.PreserveAspectCrop
                        visible: controller && controller.npCoverUrl !== ""
                    }
                    layer.enabled: true
                }
                ColumnLayout {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.fillWidth: true
                    spacing: 6
                    Label {
                        text: (controller && controller.npTitle) || "Nothing playing"
                        color: nph.playing ? theme.text : theme.textDim
                        font.pixelSize: 28; font.weight: Font.Bold
                        elide: Text.ElideRight; Layout.fillWidth: true
                    }
                    Label {
                        visible: controller && controller.npSub.length > 0
                        text: controller ? controller.npSub : ""
                        color: theme.textDim; font.pixelSize: 16
                        elide: Text.ElideRight; Layout.fillWidth: true
                    }
                }
                ColumnLayout {
                    Layout.alignment: Qt.AlignTop; spacing: 4
                    RowLayout {
                        spacing: 2
                        IconButton { flat: true; size: 36; glyph: "◉"
                                     color: win.vinylConfig ? theme.surfaceHover : "transparent"
                                     visible: controller && controller.npAlbumId >= 0
                                     onClicked: win.openVinylConfig() }
                        IconButton { flat: true; size: 36; glyph: "☰"
                                     color: win.queueOpen ? theme.surfaceHover : "transparent"
                                     onClicked: win.queueOpen = !win.queueOpen }
                        IconButton { flat: true; size: 36; glyph: "⛶"
                                     visible: controller && controller.npAlbumId >= 0
                                     onClicked: win.expanded = true }
                    }
                }
            }

            // ---- transport + seek strip ----
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                // shuffle
                IconButton { flat: true; size: 32; glyph: "🔀"
                             color: (controller && controller.shuffle)
                                    ? theme.surfaceHover : "transparent"
                             onClicked: controller.setShuffle(!controller.shuffle) }
                IconButton { flat: true; size: 36; glyph: "⏮"
                             onClicked: controller.previous() }
                IconButton { flat: true; size: 40
                             glyph: (controller && controller.npIsPlaying) ? "⏸" : "▶"
                             onClicked: controller.playPause() }
                IconButton { flat: true; size: 36; glyph: "⏭"
                             onClicked: controller.next() }
                // repeat (off → all → one)
                IconButton { flat: true; size: 32
                             glyph: (controller && controller.repeatMode === "one")
                                    ? "🔂" : "🔁"
                             color: (controller && controller.repeatMode !== "off")
                                    ? theme.surfaceHover : "transparent"
                             onClicked: controller.cycleRepeat() }
                // favourite the now-playing track
                IconButton { flat: true; size: 32
                             visible: controller && controller.npAlbumId >= 0
                             glyph: (controller && controller.npIsFavorite) ? "♥" : "♡"
                             onClicked: controller.toggleFavoriteCurrent() }
                Label { text: controller ? controller.timeElapsed : "0:00"
                        color: theme.textDim; font.pixelSize: 12
                        Layout.leftMargin: 6 }
                Rectangle {
                    id: seekBar
                    Layout.fillWidth: true; Layout.preferredHeight: 6
                    Layout.alignment: Qt.AlignVCenter
                    radius: 3; color: theme.line
                    Rectangle {
                        height: parent.height; radius: 3
                        width: parent.width * (controller ? controller.npPosition : 0)
                        color: theme.accent
                    }
                    // per-track tick marks
                    Repeater {
                        model: controller ? controller.trackMarkers : []
                        delegate: Rectangle {
                            required property var modelData
                            width: 2; height: 10; radius: 0
                            y: (seekBar.height - height) / 2
                            x: seekBar.width * modelData - width / 2
                            color: theme.bg
                        }
                    }
                    // click / drag to seek across the whole queue
                    TapHandler {
                        onTapped: function (ev) {
                            controller.seek(ev.position.x / seekBar.width)
                        }
                    }
                    DragHandler {
                        target: null
                        onCentroidChanged: if (active)
                            controller.seek(centroid.position.x / seekBar.width)
                    }
                }
                Label { text: controller ? controller.timeTotal : "0:00"
                        color: theme.textDim; font.pixelSize: 12 }
                // volume: mute toggle + thin slider
                IconButton { flat: true; size: 32
                             glyph: (controller && (controller.muted
                                     || controller.volume === 0)) ? "🔇" : "🔊"
                             Layout.leftMargin: 6
                             onClicked: controller.toggleMute() }
                Rectangle {
                    id: volBar
                    Layout.preferredWidth: 90; Layout.preferredHeight: 6
                    Layout.alignment: Qt.AlignVCenter
                    radius: 3; color: theme.line
                    Rectangle {
                        height: parent.height; radius: 3
                        width: parent.width * (controller ? controller.volume / 100 : 1)
                        color: theme.textDim
                    }
                    TapHandler {
                        onTapped: function (ev) {
                            controller.setVolume(Math.round(ev.position.x / volBar.width * 100))
                        }
                    }
                    DragHandler {
                        target: null
                        onCentroidChanged: if (active)
                            controller.setVolume(Math.round(centroid.position.x / volBar.width * 100))
                    }
                }
            }
        }
    }

    // ---- collapsible queue panel ----
    component QueuePanel: Rectangle {
        Layout.fillHeight: true
        Layout.preferredWidth: win.queueOpen ? 332 : 0
        Behavior on Layout.preferredWidth {
            NumberAnimation { duration: 160; easing.type: Easing.OutQuad }
        }
        clip: true
        color: theme.sidebar
        Rectangle { width: 1; height: parent.height; color: theme.line }  // left hairline

        // fixed-width inner content, anchored right → slides in as the panel widens
        ColumnLayout {
            width: 332
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                Label { text: "Queue"; color: theme.text
                        font.pixelSize: 16; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                Pill { label: "Stop after this"; visible: controller.queueCount > 0
                       selected: controller.stopAfterCurrent
                       onClicked: controller.toggleStopAfterCurrent() }
                Pill { label: "Save…"; onClicked: exportDialog.openFor("queue", -1, "Queue") }
                Pill { label: "Clear"; visible: controller.queueCount > 0
                       onClicked: controller.clearQueue() }
            }

            Label {
                visible: controller.queueCount === 0
                Layout.fillWidth: true; Layout.topMargin: 24
                text: "Queue is empty.\nPick an album to play."
                color: theme.textDim; font.pixelSize: 13
                horizontalAlignment: Text.AlignHCenter
            }

            ListView {
                id: queueList
                visible: controller.queueCount > 0
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true
                model: queueModel
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { }
                WheelScroller { view: queueList }
                currentIndex: -1
                property int dropIndex: -1           // where a dragged row would land
                delegate: Rectangle {
                    required property string title
                    required property string artist
                    required property real duration
                    required property bool isCurrent
                    required property int index
                    width: ListView.view.width - 20; x: 10
                    height: 50; radius: 7
                    color: qh.hovered ? theme.surfaceHover : "transparent"
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10; anchors.rightMargin: 10
                        spacing: 10
                        // row number, or a handle to drag the row to a new place
                        Label {
                            text: dragArea.containsMouse || dragArea.pressed ? "⠿"
                                  : (isCurrent ? "▶" : (index + 1))
                            color: isCurrent ? theme.accent : theme.textDim
                            font.pixelSize: isCurrent ? 12 : 13
                            Layout.preferredWidth: 20
                            horizontalAlignment: Text.AlignHCenter
                            MouseArea {
                                id: dragArea
                                anchors.fill: parent; anchors.margins: -8
                                hoverEnabled: true
                                preventStealing: true
                                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                function target(mouse) {
                                    var p = mapToItem(queueList.contentItem, mouse.x, mouse.y)
                                    var to = queueList.indexAt(20, p.y)
                                    return to >= 0 ? to : (p.y < 0 ? 0 : queueList.count - 1)
                                }
                                onPositionChanged: (mouse) => {
                                    if (pressed) queueList.dropIndex = target(mouse)
                                }
                                onReleased: (mouse) => {
                                    var to = target(mouse)
                                    queueList.dropIndex = -1
                                    if (to !== index) controller.moveInQueue(index, to)
                                }
                                onCanceled: queueList.dropIndex = -1
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 0
                            Label {
                                text: title
                                color: isCurrent ? theme.accent : theme.text
                                font.pixelSize: 13
                                font.weight: isCurrent ? Font.DemiBold : Font.Normal
                                elide: Text.ElideRight; Layout.fillWidth: true
                            }
                            Label {
                                text: artist; color: theme.textDim
                                font.pixelSize: 11; elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                        Label { text: win.fmtTime(duration); color: theme.textDim
                                font.pixelSize: 12; visible: !qh.hovered }
                        IconButton { glyph: "✕"; visible: qh.hovered
                                     onClicked: controller.removeFromQueue(index) }
                    }
                    HoverHandler { id: qh }
                    TapHandler { onTapped: controller.jumpTo(index) }
                    Rectangle {                          // drop marker while dragging
                        visible: queueList.dropIndex === index
                        anchors.left: parent.left; anchors.right: parent.right
                        anchors.top: parent.top
                        height: 2; color: theme.accent
                    }
                }
            }

            // footer: N/M remaining, time remaining / total
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.line
                        visible: controller.queueCount > 0 }
            ColumnLayout {
                visible: controller.queueCount > 0
                Layout.fillWidth: true; Layout.margins: 14
                spacing: 2
                Label {
                    text: controller.tracksRemaining + "/" + controller.queueCount
                          + " tracks remaining"
                    color: theme.text; font.pixelSize: 12
                }
                Label {
                    text: controller.timeRemaining + " remaining  ·  "
                          + controller.timeTotal + " total"
                    color: theme.textDim; font.pixelSize: 11
                }
            }
        }
    }

    // ---- settings popup (sort + grid size) ----
    Popup {
        id: settingsPopup
        objectName: "settingsPopup"
        modal: true; dim: true
        width: 400; padding: 22
        height: Math.min(setCol.implicitHeight + 2 * padding, win.height - 60)
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        background: PopupBg { }
        contentItem: Flickable {
            contentHeight: setCol.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { }
            ColumnLayout {
            id: setCol
            width: parent.width
            spacing: 14
            RowLayout {
                Layout.fillWidth: true
                Label { text: "Settings"; color: theme.text
                        font.pixelSize: 18; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                IconButton { glyph: "✕"; onClicked: settingsPopup.close() }
            }

            // ---- Music library ----
            Label { text: "Music library"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 6 }
            Label {
                text: controller.musicFolder || "No folder chosen"
                color: theme.text; font.pixelSize: 13
                elide: Text.ElideMiddle; Layout.fillWidth: true
            }
            RowLayout {
                spacing: 8
                Pill { label: "Choose folder…"; onClicked: libraryFolderDialog.open() }
                Pill { label: "Rescan"; visible: !controller.scanning
                       onClicked: controller.rescanLibrary() }
            }
            Label {
                visible: text !== ""
                text: controller.scanStatus
                color: theme.textDim; font.pixelSize: 11
                elide: Text.ElideRight; Layout.fillWidth: true
            }
            FolderDialog {
                id: libraryFolderDialog
                title: "Choose your music folder"
                currentFolder: controller.musicFolder ? "file://" + controller.musicFolder : ""
                onAccepted: controller.setMusicFolder(selectedFolder)
            }

            Label { text: "Theme"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 6 }
            Segmented {
                options: [{ label: "Dark", value: true }, { label: "Light", value: false }]
                current: controller.darkMode
                onPicked: (value) => controller.setDarkMode(value)
            }
            Label { text: "Sort artists"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 6 }
            Segmented {
                options: [{ label: "Name A–Z", value: "name_asc" },
                          { label: "Name Z–A", value: "name_desc" }]
                current: controller.artistSort
                onPicked: (value) => controller.setArtistSort(value)
            }
            Label { text: "Sort albums"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 6 }
            Segmented {
                options: [{ label: "Year", value: "year" },
                          { label: "Name", value: "name" }]
                current: controller.albumSort
                onPicked: (value) => controller.setAlbumSort(value)
            }
            Label { text: "Grid size"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 6 }
            Segmented {
                options: [{ label: "Small", value: 120 },
                          { label: "Medium", value: 152 },
                          { label: "Large", value: 188 }]
                current: controller.gridTile
                onPicked: (value) => controller.setGridTile(value)
            }

            Rectangle { Layout.fillWidth: true; Layout.topMargin: 8
                        Layout.bottomMargin: 2; implicitHeight: 1; color: theme.line }

            // ---- Equalizer ----
            RowLayout {
                Layout.fillWidth: true
                Label { text: "Equalizer"; color: theme.textDim; font.pixelSize: 12 }
                Item { Layout.fillWidth: true }
                Segmented {
                    options: [{ label: "On", value: true }, { label: "Off", value: false }]
                    current: controller.eqEnabled
                    onPicked: (value) => controller.setEqEnabled(value)
                }
            }
            Flow {
                Layout.fillWidth: true; spacing: 6
                visible: controller.eqEnabled
                Repeater {
                    model: controller.eqPresets
                    delegate: Rectangle {
                        required property var modelData
                        implicitHeight: 30
                        implicitWidth: epLbl.implicitWidth + 22
                        radius: 15
                        color: modelData === controller.eqPreset ? theme.accent
                               : (ep.hovered ? theme.line : theme.surfaceHover)
                        Label { id: epLbl; anchors.centerIn: parent; text: modelData
                                color: modelData === controller.eqPreset
                                       ? theme.accentText : theme.text
                                font.pixelSize: 12 }
                        HoverHandler { id: ep }
                        TapHandler { onTapped: controller.setEqPreset(modelData) }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true; visible: controller.eqEnabled
                Label { text: "Preamp"; color: theme.textDim; font.pixelSize: 11
                        Layout.preferredWidth: 60 }
                ThemeSlider {
                    Layout.fillWidth: true
                    from: -20; to: 20; value: controller.eqPreamp
                    onMoved: controller.setEqPreamp(value)
                }
                Label { text: Math.round(controller.eqPreamp) + " dB"
                        color: theme.text; font.pixelSize: 11
                        Layout.preferredWidth: 44 }
            }

            // ---- Crossfade ----
            Label { text: "Crossfade"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 6 }
            RowLayout {
                Layout.fillWidth: true
                ThemeSlider {
                    Layout.fillWidth: true
                    from: 0; to: 12; stepSize: 1; value: controller.crossfade
                    onMoved: controller.setCrossfade(value)
                }
                Label { text: controller.crossfade === 0 ? "Off"
                              : controller.crossfade + "s"
                        color: theme.text; font.pixelSize: 11
                        Layout.preferredWidth: 36 }
            }

            SettingToggle { label: "Fade out when pausing"; checked: controller.fadeOnPause
                            onToggled: (on) => controller.setFadeOnPause(on) }

            // ---- Audio output ----
            Label { text: "Audio output"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 6 }
            Flow {
                id: deviceFlow
                Layout.fillWidth: true
                spacing: 8
                property var devices: settingsPopup.opened ? controller.outputDevices() : []
                Repeater {
                    model: deviceFlow.devices
                    delegate: Pill {
                        required property var modelData
                        label: modelData.name
                        selected: modelData.id === controller.outputDevice
                        onClicked: controller.setOutputDevice(modelData.id)
                    }
                }
            }

            // ---- ReplayGain ----
            Label { text: "Volume normalisation (ReplayGain)"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 6 }
            Segmented {
                options: [{ label: "Off", value: "none" },
                          { label: "Track", value: "track" },
                          { label: "Album", value: "album" }]
                current: controller.replayGainMode
                onPicked: (value) => controller.setReplayGainMode(value)
            }
            Label { visible: controller.replayGainMode !== "none"
                    text: "Applies after restart."
                    color: theme.textDim; font.pixelSize: 10 }

            // ---- Desktop ----
            Label { text: "Desktop"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 10 }
            SettingToggle { label: "Show in the system tray"; visible: controller.trayAvailable
                            checked: controller.showTray
                            onToggled: (on) => controller.setShowTray(on) }
            SettingToggle { label: "Keep playing in the tray when the window is closed"
                            visible: controller.trayAvailable; enabled: controller.showTray
                            checked: controller.closeToTray
                            onToggled: (on) => controller.setCloseToTray(on) }
            SettingToggle { label: "Notify when the track changes"
                            detail: "Only while lp-deck isn't the window in front."
                            checked: controller.notifyTrackChange
                            onToggled: (on) => controller.setNotifyTrackChange(on) }
            SettingToggle { label: "Keep the computer awake while playing"
                            checked: controller.keepAwake
                            onToggled: (on) => controller.setKeepAwake(on) }

            // ---- Keyboard shortcuts ----
            Label { text: "Keyboard shortcuts"; color: theme.textDim
                    font.pixelSize: 12; Layout.topMargin: 10 }
            Repeater {
                model: [["Space", "Play or pause"],
                        ["Ctrl+→  Ctrl+←", "Next or previous track"],
                        ["Shift+→  Shift+←", "Forward or back 10 seconds"],
                        ["Ctrl+↑  Ctrl+↓", "Volume up or down"],
                        ["Ctrl+M", "Mute"],
                        ["Ctrl+S", "Shuffle"],
                        ["Ctrl+R", "Repeat"],
                        ["Ctrl+.", "Stop after this track"],
                        ["Ctrl+F", "Search"],
                        ["Esc", "Back"],
                        ["Ctrl+Q", "Quit"]]
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 12
                    Label { text: modelData[0]; color: theme.text; font.pixelSize: 12
                            font.family: "monospace"; Layout.preferredWidth: 150 }
                    Label { text: modelData[1]; color: theme.textDim; font.pixelSize: 12
                            Layout.fillWidth: true }
                }
            }
            }
        }
    }

    // ---- per-track action sheet ----
    Popup {
        id: rowActions
        objectName: "rowActions"
        property string trackPath
        property string trackTitle
        property int playlistId: -1
        property int position: -1
        property bool isFav: false
        modal: true; dim: true
        width: 360; padding: 18
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        background: PopupBg { }
        contentItem: ColumnLayout {
            spacing: 6
            Label { text: rowActions.trackTitle; color: theme.text
                    font.pixelSize: 15; font.weight: Font.Bold
                    elide: Text.ElideRight; Layout.fillWidth: true
                    Layout.bottomMargin: 6 }
            SheetRow { label: "Play next"
                       onClicked: { rowActions.close()
                                    controller.queueTracks([rowActions.trackPath], true) } }
            SheetRow { label: "Add to queue"
                       onClicked: { rowActions.close()
                                    controller.queueTracks([rowActions.trackPath], false) } }
            SheetRow { label: rowActions.isFav ? "Remove from favourites"
                                               : "Add to favourites"
                       onClicked: { rowActions.close()
                                    controller.toggleFavorite(rowActions.trackPath) } }
            SheetRow { label: "Add to playlist…"
                       onClicked: { rowActions.close()
                                    win.addSongsToPlaylist([rowActions.trackPath]) } }
            SheetRow { visible: rowActions.playlistId >= 0
                       label: "Remove from this playlist"
                       onClicked: { rowActions.close()
                                    controller.removeFromPlaylist(rowActions.playlistId,
                                                                  rowActions.position) } }
            SheetRow { label: "Edit metadata…"
                       onClicked: { rowActions.close()
                                    metadataPopup.openFor(rowActions.trackPath) } }
            SheetRow { label: "Open in MusicBrainz Picard"
                       onClicked: { rowActions.close()
                                    controller.openInPicard(rowActions.trackPath) } }
        }
    }

    // ---- playlist action sheet (rename / delete) ----
    Popup {
        id: playlistActions
        objectName: "playlistActions"
        property int plId: -1
        property string plName
        modal: true; dim: true
        width: 340; padding: 18
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        background: PopupBg { }
        contentItem: ColumnLayout {
            spacing: 6
            Label { text: playlistActions.plName; color: theme.text
                    font.pixelSize: 15; font.weight: Font.Bold
                    elide: Text.ElideRight; Layout.fillWidth: true
                    Layout.bottomMargin: 6 }
            SheetRow { label: "Play"
                       onClicked: { playlistActions.close()
                                    controller.playPlaylist(playlistActions.plId, 0) } }
            SheetRow { label: "Rename…"
                       onClicked: { playlistActions.close()
                                    renamePopup.openFor(playlistActions.plId,
                                                        playlistActions.plName) } }
            SheetRow { label: "Export to a file…"
                       onClicked: { playlistActions.close()
                                    exportDialog.openFor("playlist", playlistActions.plId,
                                                         playlistActions.plName) } }
            SheetRow { label: "Delete playlist"
                       onClicked: { playlistActions.close()
                                    controller.deletePlaylist(playlistActions.plId) } }
        }
    }

    // ---- playlist files ----
    FileDialog {
        id: importDialog
        title: "Import a playlist"
        fileMode: FileDialog.OpenFile
        currentFolder: controller.exportFolder
        nameFilters: ["Playlists (*.m3u *.m3u8 *.pls *.xspf)", "All files (*)"]
        onAccepted: {
            if (controller.importPlaylist(selectedFile) >= 0 && win.section !== "playlists")
                win.gotoPlaylists()
        }
    }
    FileDialog {
        id: exportDialog
        property string kind: "playlist"     // playlist | smart | queue
        property int itemId: -1
        function openFor(k, id, name) {
            kind = k; itemId = id
            var safe = (name || "Playlist").replace(/[\/\\:*?"<>|]/g, "_")
            selectedFile = controller.exportFolder + "/" + encodeURIComponent(safe) + ".m3u8"
            open()
        }
        title: "Export to a playlist file"
        fileMode: FileDialog.SaveFile
        currentFolder: controller.exportFolder
        defaultSuffix: "m3u8"
        nameFilters: ["M3U playlist (*.m3u8 *.m3u)", "XSPF playlist (*.xspf)",
                      "PLS playlist (*.pls)"]
        onAccepted: {
            if (kind === "smart") controller.exportSmartPlaylist(itemId, selectedFile)
            else if (kind === "queue") controller.exportQueue(selectedFile)
            else controller.exportPlaylist(itemId, selectedFile)
        }
    }

    // ---- smart playlist actions ----
    Popup {
        id: smartActions
        objectName: "smartActions"
        property int smartId: -1
        property string smartName
        function openFor(id, name) { smartId = id; smartName = name; open() }
        modal: true; dim: true
        width: 340; padding: 18
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        background: PopupBg { }
        contentItem: ColumnLayout {
            spacing: 6
            Label { text: smartActions.smartName; color: theme.text
                    font.pixelSize: 15; font.weight: Font.Bold
                    elide: Text.ElideRight; Layout.fillWidth: true
                    Layout.bottomMargin: 6 }
            SheetRow { label: "Play"
                       onClicked: {
                           smartActions.close()
                           var songs = controller.smartPlaylistSongs(smartActions.smartId)
                           controller.playPaths(songs.map(function(s){ return s.path }), 0)
                       } }
            SheetRow { label: "Edit rules…"
                       onClicked: { smartActions.close(); smartEditor.openFor(smartActions.smartId) } }
            SheetRow { label: "Export to a file…"
                       onClicked: { smartActions.close()
                                    exportDialog.openFor("smart", smartActions.smartId,
                                                         smartActions.smartName) } }
            SheetRow { label: "Delete smart playlist"
                       onClicked: { smartActions.close()
                                    controller.deleteSmartPlaylist(smartActions.smartId) } }
        }
    }

    // ---- smart playlist editor ----
    Popup {
        id: smartEditor
        objectName: "smartEditor"
        property int smartId: -1
        property string match: "all"
        property var rules: []
        property string sort: "artist"
        property string limitText: ""
        // Typed values are written into `rules` in place (reassigning the array
        // would rebuild the rows and drop focus mid-word); `revision` tells the
        // song count to recount.
        property int revision: 0
        readonly property var definition: (revision, { "match": match, "rules": rules,
                                                       "sort": sort,
                                                       "limit": parseInt(limitText) || 0 })
        readonly property int matches: opened ? controller.smartPreviewCount(definition) : 0
        function openFor(id) {
            var d = controller.smartPlaylistDefinition(id)
            smartId = id
            smartNameField.text = d.name || ""
            match = d.match || "all"
            rules = (d.rules && d.rules.length) ? d.rules : [newRule("genre")]
            sort = d.sort || "artist"
            limitText = d.limit ? String(d.limit) : ""
            open()
        }
        function fieldType(f) {
            var fs = controller.smartFields
            for (var i = 0; i < fs.length; i++) if (fs[i].field === f) return fs[i].type
            return "text"
        }
        function newRule(f) {
            var t = fieldType(f)
            return { "field": f, "op": controller.smartOps[t][0].op,
                     "value": t === "number" ? 0 : (t === "date" ? 30 : "") }
        }
        function setRule(i, key, value) {
            var r = rules.slice()
            if (key === "field") r[i] = newRule(value)
            else { r[i] = Object.assign({}, r[i]); r[i][key] = value }
            rules = r
        }
        function removeRule(i) { var r = rules.slice(); r.splice(i, 1); rules = r }
        function indexOfKey(list, key, value) {
            for (var i = 0; i < list.length; i++) if (list[i][key] === value) return i
            return 0
        }
        function save() {
            var name = smartNameField.text
            var id = controller.saveSmartPlaylist(smartId, name, definition)
            var isNew = smartId < 0
            close()
            if (isNew) win.openSmartPlaylist(id, name.trim() || "Smart playlist")
        }
        modal: true; dim: true
        width: Math.min(660, win.width - 40); padding: 20
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        background: PopupBg { }
        contentItem: ColumnLayout {
            spacing: 12
            Label { text: smartEditor.smartId >= 0 ? "Edit smart playlist" : "New smart playlist"
                    color: theme.text; font.pixelSize: 18; font.weight: Font.Bold }
            Field { id: smartNameField; Layout.fillWidth: true; placeholderText: "Name"
                    Accessible.name: "Smart playlist name" }
            RowLayout {
                spacing: 10
                Label { text: "Songs matching"; color: theme.textDim; font.pixelSize: 13 }
                Segmented {
                    options: [{ label: "all rules", value: "all" }, { label: "any rule", value: "any" }]
                    current: smartEditor.match
                    onPicked: (value) => smartEditor.match = value
                }
            }
            Repeater {
                model: smartEditor.rules
                delegate: RowLayout {
                    id: ruleRow
                    required property var modelData
                    required property int index
                    readonly property string type: smartEditor.fieldType(modelData.field)
                    readonly property bool wantsValue: type !== "bool" && modelData.op !== "never"
                    Layout.fillWidth: true
                    spacing: 8
                    ThemeCombo {
                        Layout.preferredWidth: 160
                        model: controller.smartFields; textRole: "label"
                        currentIndex: smartEditor.indexOfKey(controller.smartFields, "field",
                                                             ruleRow.modelData.field)
                        Accessible.name: "Field"
                        onActivated: (i) => smartEditor.setRule(ruleRow.index, "field",
                                                                controller.smartFields[i].field)
                    }
                    ThemeCombo {
                        Layout.preferredWidth: 180
                        model: controller.smartOps[ruleRow.type]; textRole: "label"
                        currentIndex: smartEditor.indexOfKey(controller.smartOps[ruleRow.type], "op",
                                                             ruleRow.modelData.op)
                        Accessible.name: "Condition"
                        onActivated: (i) => smartEditor.setRule(ruleRow.index, "op",
                                                                controller.smartOps[ruleRow.type][i].op)
                    }
                    Field {
                        Layout.fillWidth: true
                        visible: ruleRow.wantsValue
                        text: ruleRow.modelData.value === undefined || ruleRow.modelData.value === null
                              ? "" : String(ruleRow.modelData.value)
                        inputMethodHints: ruleRow.type === "text" ? Qt.ImhNone : Qt.ImhDigitsOnly
                        Accessible.name: "Value"
                        onTextEdited: {
                            smartEditor.rules[ruleRow.index].value =
                                ruleRow.type === "text" ? text : Number(text)
                            smartEditor.revision++
                        }
                    }
                    Item { Layout.fillWidth: true; visible: !ruleRow.wantsValue }
                    IconButton { glyph: "✕"; flat: true; size: 30; tip: "Remove this rule"
                                 onClicked: smartEditor.removeRule(ruleRow.index) }
                }
            }
            Pill { label: "＋  Add rule"
                   onClicked: smartEditor.rules = smartEditor.rules.concat([smartEditor.newRule("artist")]) }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Label { text: "Order"; color: theme.textDim; font.pixelSize: 13 }
                ThemeCombo {
                    Layout.preferredWidth: 180
                    model: controller.smartSorts; textRole: "label"
                    currentIndex: smartEditor.indexOfKey(controller.smartSorts, "value", smartEditor.sort)
                    Accessible.name: "Order"
                    onActivated: (i) => smartEditor.sort = controller.smartSorts[i].value
                }
                Label { text: "Limit"; color: theme.textDim; font.pixelSize: 13
                        Layout.leftMargin: 8 }
                Field {
                    Layout.preferredWidth: 80
                    placeholderText: "none"
                    text: smartEditor.limitText
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 1; top: 10000 }
                    Accessible.name: "Limit"
                    onTextEdited: smartEditor.limitText = text
                }
                Item { Layout.fillWidth: true }
                Label { text: smartEditor.matches === 1 ? "1 song" : smartEditor.matches + " songs"
                        color: theme.textDim; font.pixelSize: 13 }
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                SheetRow { label: "Cancel"; Layout.fillWidth: false; Layout.preferredWidth: 90
                           onClicked: smartEditor.close() }
                Rectangle {
                    implicitWidth: 90; implicitHeight: 38; radius: 19
                    color: smartSave.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent
                    activeFocusOnTab: true
                    border.width: activeFocus ? 2 : 0; border.color: theme.text
                    Accessible.role: Accessible.Button
                    Accessible.name: "Save"
                    Accessible.onPressAction: smartEditor.save()
                    Keys.onReturnPressed: smartEditor.save()
                    Label { anchors.centerIn: parent; text: "Save"
                            color: theme.accentText; font.weight: Font.DemiBold }
                    HoverHandler { id: smartSave }
                    TapHandler { onTapped: smartEditor.save() }
                }
            }
        }
    }

    // ---- rename playlist ----
    Popup {
        id: renamePopup
        objectName: "renamePopup"
        property int plId: -1
        function openFor(id, name) { plId = id; renameField.text = name; open() }
        modal: true; dim: true
        width: 380; padding: 20
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        background: PopupBg { }
        contentItem: ColumnLayout {
            spacing: 12
            Label { text: "Rename playlist"; color: theme.text
                    font.pixelSize: 16; font.weight: Font.Bold }
            Field { id: renameField; Layout.fillWidth: true
                    onAccepted: { controller.renamePlaylist(renamePopup.plId, text)
                                  renamePopup.close() } }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                IconButton { glyph: "✕"; onClicked: renamePopup.close() }
                Rectangle {
                    implicitWidth: 90; implicitHeight: 36; radius: 18
                    color: rn2.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent
                    Label { anchors.centerIn: parent; text: "Save"
                            color: theme.accentText; font.pixelSize: 13
                            font.weight: Font.DemiBold }
                    HoverHandler { id: rn2 }
                    TapHandler {
                        onTapped: { controller.renamePlaylist(renamePopup.plId,
                                                              renameField.text)
                                    renamePopup.close() }
                    }
                }
            }
        }
    }

    // ---- edit metadata form ----
    Popup {
        id: metadataPopup
        objectName: "metadataPopup"
        property string path
        function openFor(p) {
            path = p
            var m = controller.trackMetadata(p)
            fTitle.text = m.title; fArtist.text = m.artist
            fAlbum.text = m.album; fTrack.text = m.track
            open()
        }
        modal: true; dim: true
        width: 460; padding: 22
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        background: PopupBg { }
        contentItem: ColumnLayout {
            spacing: 10
            Label { text: "Edit metadata"; color: theme.text
                    font.pixelSize: 18; font.weight: Font.Bold }
            Label { text: "Title"; color: theme.textDim; font.pixelSize: 11 }
            Field { id: fTitle; Layout.fillWidth: true }
            Label { text: "Artist"; color: theme.textDim; font.pixelSize: 11 }
            Field { id: fArtist; Layout.fillWidth: true }
            Label { text: "Album"; color: theme.textDim; font.pixelSize: 11 }
            Field { id: fAlbum; Layout.fillWidth: true }
            Label { text: "Track #"; color: theme.textDim; font.pixelSize: 11 }
            Field { id: fTrack; Layout.preferredWidth: 90 }
            RowLayout {
                Layout.fillWidth: true; Layout.topMargin: 8
                Item { Layout.fillWidth: true }
                SheetRow { label: "Cancel"; Layout.preferredWidth: 90
                           onClicked: metadataPopup.close() }
                Rectangle {
                    implicitWidth: 90; implicitHeight: 38; radius: 19
                    color: sv2.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent
                    Label { anchors.centerIn: parent; text: "Save"
                            color: theme.accentText; font.weight: Font.DemiBold }
                    HoverHandler { id: sv2 }
                    TapHandler {
                        onTapped: {
                            controller.saveMetadata(metadataPopup.path, fTitle.text,
                                fArtist.text, fAlbum.text, fTrack.text)
                            metadataPopup.close()
                        }
                    }
                }
            }
        }
    }

    // ---- add to playlist (target = one/many songs, an album, or an artist) ----
    Popup {
        id: addToPlaylist
        objectName: "addToPlaylist"
        property var target: ({ kind: "tracks", paths: [] })
        property var lists: []
        function openSheet() { lists = controller.playlists(); open() }
        function commit(pid) {
            if (target.kind === "tracks") controller.addTracksToPlaylist(pid, target.paths)
            else if (target.kind === "album") controller.addAlbumToPlaylist(pid, target.ref)
            else if (target.kind === "artist") controller.addArtistToPlaylist(pid, target.ref)
            close()
        }
        modal: true; dim: true
        width: 380; padding: 20
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        background: PopupBg { }
        contentItem: ColumnLayout {
            spacing: 8
            Label {
                text: addToPlaylist.target.kind === "tracks"
                      ? ("Add " + (addToPlaylist.target.paths
                         ? addToPlaylist.target.paths.length : 0) + " song(s) to playlist")
                      : ("Add " + addToPlaylist.target.kind + " to playlist")
                color: theme.text; font.pixelSize: 18; font.weight: Font.Bold
            }
            Repeater {
                model: addToPlaylist.lists
                delegate: SheetRow {
                    required property var modelData
                    label: modelData.name + "   (" + modelData.count + ")"
                    onClicked: addToPlaylist.commit(modelData.id)
                }
            }
            Label { visible: addToPlaylist.lists.length === 0
                    text: "No playlists yet — create one below."
                    color: theme.textDim; font.pixelSize: 12 }
            RowLayout {
                Layout.fillWidth: true; Layout.topMargin: 6; spacing: 8
                Field { id: newName; Layout.fillWidth: true
                        placeholderText: "New playlist name" }
                Rectangle {
                    implicitWidth: 80; implicitHeight: 38; radius: 19
                    color: ap2.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent
                    Label { anchors.centerIn: parent; text: "Create"
                            color: theme.accentText; font.pixelSize: 12
                            font.weight: Font.DemiBold }
                    HoverHandler { id: ap2 }
                    TapHandler {
                        onTapped: {
                            if (newName.text.length > 0) {
                                var pid = controller.createPlaylist(newName.text)
                                newName.text = ""
                                addToPlaylist.commit(pid)
                            }
                        }
                    }
                }
            }
        }
    }

    // ---- new (empty) playlist ----
    Popup {
        id: newPlaylistPopup
        objectName: "newPlaylistPopup"
        modal: true; dim: true
        width: 380; padding: 20
        x: Math.round((win.width - width) / 2)
        y: Math.round((win.height - height) / 2)
        onOpened: plName.text = ""
        background: PopupBg { }
        contentItem: ColumnLayout {
            spacing: 10
            Label { text: "New playlist"; color: theme.text
                    font.pixelSize: 18; font.weight: Font.Bold }
            Field { id: plName; Layout.fillWidth: true
                    placeholderText: "Playlist name" }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                SheetRow { label: "Cancel"; Layout.preferredWidth: 90
                           onClicked: newPlaylistPopup.close() }
                Rectangle {
                    implicitWidth: 90; implicitHeight: 38; radius: 19
                    color: np2.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent
                    Label { anchors.centerIn: parent; text: "Create"
                            color: theme.accentText; font.weight: Font.DemiBold }
                    HoverHandler { id: np2 }
                    TapHandler {
                        onTapped: {
                            if (plName.text.length > 0)
                                controller.createPlaylist(plName.text)
                            newPlaylistPopup.close()
                        }
                    }
                }
            }
        }
    }

    // ---- full-screen vinyl config (req #7) — takes over the main area ----
    component VinylConfig: Rectangle {
        color: theme.bg
        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 28; anchors.rightMargin: 16
            anchors.topMargin: 16; anchors.bottomMargin: 8
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                IconButton { glyph: "‹"; onClicked: win.vinylConfig = false }
                Label { text: "Vinyl look"; color: theme.text
                        font.pixelSize: 24; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                Label { text: "Apply to"; color: theme.textDim; font.pixelSize: 13 }
                Segmented {
                    options: (controller && controller.npPlaylistId >= 0)
                        ? [{ label: "This album", value: "album" },
                           { label: "This artist", value: "artist" },
                           { label: "This playlist", value: "playlist" },
                           { label: "Everything", value: "global" }]
                        : [{ label: "This album", value: "album" },
                           { label: "This artist", value: "artist" },
                           { label: "Everything", value: "global" }]
                    current: win.vScope
                    onPicked: (value) => { win.vScope = value; win.applyVinyl() }
                }
            }

            ScrollView {
                id: vinylScroll
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                WheelScroller { view: vinylScroll.contentItem }
                ColumnLayout {
                    width: parent.width
                    spacing: 18

                    Repeater {
                        model: controller.vinylCatalog
                        delegate: ColumnLayout {
                            required property var modelData
                            property var section: modelData
                            Layout.fillWidth: true
                            spacing: 12
                            Label {
                                text: section.title.toUpperCase()
                                color: theme.textDim; font.pixelSize: 12
                                font.weight: Font.DemiBold; font.letterSpacing: 1
                                Layout.topMargin: 6
                            }
                            Flow {
                                Layout.fillWidth: true; spacing: 18
                                Repeater {
                                    model: section.items
                                    delegate: Swatch {
                                        required property var modelData
                                        diameter: 120
                                        source: win.vinylSwatch(modelData.value, win.vLabel)
                                        caption: modelData.label
                                        selected: win.vStyle === modelData.value
                                        onClicked: { win.vStyle = modelData.value
                                                     win.applyVinyl() }
                                    }
                                }
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; implicitHeight: 1
                                color: theme.line; Layout.topMargin: 8 }
                    Label {
                        text: "LABEL COLOUR"; color: theme.textDim; font.pixelSize: 12
                        font.weight: Font.DemiBold; font.letterSpacing: 1
                        Layout.topMargin: 6
                    }
                    Flow {
                        Layout.fillWidth: true; spacing: 18
                        Repeater {
                            model: controller.vinylLabels
                            delegate: Swatch {
                                required property var modelData
                                diameter: 120
                                source: win.vinylSwatch(win.vStyle, modelData.value)
                                caption: modelData.label
                                selected: win.vLabel === modelData.value
                                onClicked: { win.vLabel = modelData.value; win.applyVinyl() }
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1
                                color: theme.line; Layout.topMargin: 8 }
                    Label {
                        text: "EFFECTS"; color: theme.textDim; font.pixelSize: 12
                        font.weight: Font.DemiBold; font.letterSpacing: 1
                        Layout.topMargin: 6
                    }
                    RowLayout {
                        spacing: 12
                        Label { text: "Grooves"; color: theme.textDim; font.pixelSize: 13 }
                        Segmented {
                            options: controller.vinylGrooves
                            current: win.vGrooves
                            onPicked: (value) => { win.vGrooves = value
                                        controller.setVinylGrooves(win.vScope, value) }
                        }
                    }
                    RowLayout {
                        spacing: 12
                        Label { text: "Finish"; color: theme.textDim; font.pixelSize: 13 }
                        Row {
                            spacing: 8
                            Repeater {
                                model: controller.vinylEffects
                                delegate: Pill {
                                    required property var modelData
                                    label: modelData.label
                                    selected: win.vEffects.indexOf(modelData.value) >= 0
                                    onClicked: win.toggleEffect(modelData.value, !selected)
                                }
                            }
                        }
                    }
                    Item { Layout.preferredHeight: 12 }
                }
            }
        }
    }
}
