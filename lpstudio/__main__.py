"""Entry point: ``python -m lpstudio`` — the vinyl-style authoring tool.

Boots a QQmlApplicationEngine, registers the MandelPreviewItem, exposes the
StudioController as the ``studio`` context property, and loads Studio.qml.
"""
import os
import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuickControls2 import QQuickStyle

from .preview_item import MandelPreviewItem
from .studio import StudioController

QML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml")


def main():
    QQuickStyle.setStyle("Basic")        # neutral base; lp-studio styles its own
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setOrganizationName("lp-studio")
    app.setApplicationName("lp-studio")
    qmlRegisterType(MandelPreviewItem, "Lpstudio", 1, 0, "MandelPreviewItem")

    controller = StudioController()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("studio", controller)
    engine.load(os.path.join(QML_DIR, "Studio.qml"))
    if not engine.rootObjects():
        raise RuntimeError("failed to load Studio.qml")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
