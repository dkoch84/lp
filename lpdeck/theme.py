"""Theming for lp-deck.

We deliberately do NOT set a style or palette — that lets the app inherit the
user's Qt platform theme (qt6ct / KDE Plasma): their colours, accent, fonts,
icons, and light/dark choice. The stylesheet below is written entirely in
``palette(<role>)`` references, so it's a thin minimalist polish that adapts to
whatever palette the system supplies — light or dark, any accent.
"""

# Minimalist, rounded, palette-driven. `palette(highlight)` is the system accent.
STYLESHEET = """
* { outline: 0; }

QLineEdit {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 9px;
    padding: 8px 12px;
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}
QLineEdit:focus { border: 1px solid palette(highlight); }

QListWidget {
    background: transparent;
    border: none;
    padding: 4px;
}
QListWidget::item {
    padding: 9px 12px;
    border-radius: 7px;
    margin: 1px 0;
}
QListWidget::item:hover { background: palette(alternate-base); }
QListWidget::item:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}

QPushButton {
    background: palette(button);
    border: 1px solid palette(mid);
    border-radius: 8px;
    padding: 6px 12px;
}
QPushButton:hover { border: 1px solid palette(highlight); }
QPushButton:pressed { background: palette(midlight); }

/* accent play button */
QPushButton#playButton {
    background: palette(highlight);
    color: palette(highlighted-text);
    border: none;
    border-radius: 18px;
    min-width: 36px; min-height: 36px;
    font-size: 17px;
}

QComboBox {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 8px;
    padding: 5px 10px;
}
QComboBox:hover { border: 1px solid palette(highlight); }
QComboBox QAbstractItemView {
    background: palette(base);
    border: 1px solid palette(mid);
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}

/* now-playing bar sits on the base colour with a hairline separator */
QWidget#nowPlaying {
    background: palette(base);
    border-top: 1px solid palette(mid);
}
QLabel#npTitle { font-size: 15px; font-weight: 600; }
QLabel#npSub   { color: palette(mid); }
"""


def apply(app):
    """Apply lp-deck's minimalist polish on top of the inherited platform theme."""
    app.setApplicationName("lp-deck")
    app.setStyleSheet(STYLESHEET)
