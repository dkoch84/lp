"""Entry point: ``python -m lpstudio``, the vinyl-style authoring tool.

Boots a QQmlApplicationEngine with the StudioController as the ``studio``
context property, the live preview item, the disc and colour-variation image
providers, and Studio.qml. ``build_engine`` is shared with the tests and
``lpstudio.shot``.
"""
import os
import sys

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from PySide6.QtQuickControls2 import QQuickStyle

from .images import DiscImages, VariationImages
from .preview_item import MandelPreviewItem
from .studio import StudioController

QML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml")


def settings_path():
    """Where the window remembers its theme, panel width and open groups."""
    base = QStandardPaths.writableLocation(QStandardPaths.GenericConfigLocation)
    return os.path.join(base, "lp-studio", "studio.ini")


def build_engine(controller, settings_file=None):
    """Load Studio.qml around ``controller``. Keep the returned engine alive."""
    qmlRegisterType(MandelPreviewItem, "Lpstudio", 1, 0, "MandelPreviewItem")
    engine = QQmlApplicationEngine()
    engine._providers = (DiscImages(), VariationImages(controller))
    engine.addImageProvider("disc", engine._providers[0])
    engine.addImageProvider("variations", engine._providers[1])
    context = engine.rootContext()
    context.setContextProperty("studio", controller)
    context.setContextProperty("settingsLocation",
                               QUrl.fromLocalFile(settings_file or settings_path()))
    engine.load(os.path.join(QML_DIR, "Studio.qml"))
    if not engine.rootObjects():
        raise RuntimeError("failed to load Studio.qml")
    return engine


def main():
    QQuickStyle.setStyle("Basic")        # neutral base; lp-studio styles its own
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setOrganizationName("lp-studio")
    app.setApplicationName("lp-studio")
    controller = StudioController()
    engine = build_engine(controller)    # noqa: F841 (the engine must outlive app.exec)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
