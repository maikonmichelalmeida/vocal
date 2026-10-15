"""Entry point: python -m vocal_app. Run outside Spyder's existing Qt loop."""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Vocal Trainer Desktop")
    parser.add_argument("--smoke-test", action="store_true", help="Open the window and exit after 1.5 s")
    parser.add_argument("--screenshot", help="Save a screenshot of the application's own window")
    args = parser.parse_args()
    os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from vocal_app.ui.main_window import MainWindow

    if QApplication.instance() is not None:
        raise RuntimeError("Execute em um processo separado: .venv\\Scripts\\python.exe -m vocal_app")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Vocal Trainer")
    app.setOrganizationName("Vocal")
    window = MainWindow()
    window.show()
    if args.screenshot:
        QTimer.singleShot(900, lambda: window.grab().save(args.screenshot))
    if args.smoke_test:
        QTimer.singleShot(1500, window.close)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
