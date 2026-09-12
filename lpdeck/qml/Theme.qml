import QtQuick

// Theme tokens with a dark + light palette. `dark` is bound to the persisted
// setting (controller.darkMode). Bindings re-evaluate when it flips, so the
// whole UI recolours live. Accent stays vinyl-amber in both modes (a touch
// deeper in light mode for legible amber-on-white text).
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

    readonly property int radius: 10
    readonly property int pad: 18
}
