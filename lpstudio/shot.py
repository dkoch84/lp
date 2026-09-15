"""Headless screenshot of lp-studio's real window, the twin of ``lp.shot`` and
``lpdeck.shot``: check a layout change without a display.

    python -m lpstudio.shot out.png --family smoke
    python -m lpstudio.shot out.png --shipped cobalt-marble --theme light
    python -m lpstudio.shot out.png --template smoke/purple-marble --unlink
    python -m lpstudio.shot out.png --family smoke --ship
    python -m lpstudio.shot out.png --family smoke --variations
    python -m lpstudio.shot out.png --shipped teal-marble --compare purple-marble

It waits for the preview's first render (``--wait`` seconds at most), then for
thumbnails to load, and prints any QML warnings it saw.
"""
import argparse
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from PySide6.QtCore import Q_ARG, QEventLoop, QMetaObject, QObject, QTimer, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lpstudio.__main__ import build_engine
from lpstudio.preview_item import MandelPreviewItem
from lpstudio.studio import StudioController


def _pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _wait_for_render(item, seconds):
    loop = QEventLoop()
    item.rendered.connect(loop.quit)
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Headless lp-studio screenshot")
    ap.add_argument("out", help="PNG path to write")
    ap.add_argument("--family", help="style family to show")
    ap.add_argument("--template", help="saved template to load, e.g. smoke/purple-marble")
    ap.add_argument("--shipped", help="shipped style to load, e.g. cobalt-marble")
    ap.add_argument("--advanced", action="store_true")
    ap.add_argument("--unlink", action="store_true", help="unlink the smoke colour ramp")
    ap.add_argument("--theme", choices=("dark", "light"))
    ap.add_argument("--ship", action="store_true", help="open the Ship dialog")
    ap.add_argument("--variations", action="store_true", help="open colour variations")
    ap.add_argument("--compare", help="compare against this catalog style")
    ap.add_argument("--filter", help="type this into the control filter")
    ap.add_argument("--w", type=int, default=1320)
    ap.add_argument("--h", type=int, default=880)
    ap.add_argument("--wait", type=float, default=30.0, help="seconds to wait for the preview")
    args = ap.parse_args(argv)

    warnings = []
    qInstallMessageHandler(lambda _mode, _ctx, msg: warnings.append(msg))

    QQuickStyle.setStyle("Basic")
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    controller = StudioController()
    if args.family:
        controller.setFamily(args.family)
    if args.template:
        controller.loadTemplate(args.template)
    if args.shipped:
        controller.loadShipped(args.shipped)
    if args.advanced:
        controller.setAdvanced(True)
    if args.unlink:
        controller.setRampLinked(False)

    settings = os.path.join(tempfile.mkdtemp(prefix="lpstudio-shot-"), "studio.ini")
    engine = build_engine(controller, settings_file=settings)
    win = engine.rootObjects()[0]
    win.resize(args.w, args.h)
    if args.theme:
        win.setProperty("themeMode", args.theme)
    if args.filter:
        search = win.findChild(QObject, "searchField")
        if search is not None:
            search.setProperty("text", args.filter)
    app.processEvents()

    preview = win.findChild(MandelPreviewItem)
    if preview is not None:
        _wait_for_render(preview, args.wait)
    if args.compare:
        QMetaObject.invokeMethod(win, "showCompare", Q_ARG("QVariant", args.compare))
    if args.ship:
        QMetaObject.invokeMethod(win, "openShip")
    if args.variations:
        QMetaObject.invokeMethod(win, "openVariations")
    _pump(4000 if args.variations else 1200)

    win.grabWindow().save(args.out)
    for item in win.findChildren(MandelPreviewItem):
        item.shutdown()
    shown = [w for w in warnings if "pygame" not in w]
    for w in shown:
        print("qml:", w, file=sys.stderr)
    print(f"wrote {args.out}" + (f" ({len(shown)} warnings)" if shown else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
