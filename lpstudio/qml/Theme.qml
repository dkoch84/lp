import QtQuick

// lp-studio's colours. The shared tokens use lp-deck's names and values
// (lpdeck/qml/Theme.qml; tests/test_studio_window.py keeps them in step), plus
// the guardrail states. `dark` follows the system unless the user picks one.
QtObject {
    property bool dark: true

    readonly property color bg:           dark ? "#15161b" : "#f5f5f7"
    readonly property color sidebar:      dark ? "#101117" : "#eaeaf0"
    readonly property color surface:      dark ? "#1e2028" : "#ffffff"
    readonly property color surfaceHover: dark ? "#2a2d37" : "#e6e6ee"
    readonly property color text:         dark ? "#ECEDEF" : "#1b1c20"
    readonly property color textDim:      dark ? "#9296A1" : "#6a6e78"
    readonly property color accent:       dark ? "#E0A24C" : "#b9741b"
    readonly property color accentText:   dark ? "#1a1206" : "#ffffff"
    readonly property color line:         dark ? "#2a2c35" : "#d9d9e1"

    // guardrails: fine, worth a look, will render flat
    readonly property color ok:           dark ? "#6fbf8a" : "#2e8a52"
    readonly property color warn:         dark ? "#e3b341" : "#9a6b00"
    readonly property color bad:          dark ? "#ef6f62" : "#c23a2c"

    readonly property int radius: 10
    readonly property int pad: 18
    readonly property string mono: "monospace"

    function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }
    function level(name) { return name === "bad" ? bad : (name === "warn" ? warn : ok) }
}
