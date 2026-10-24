import sys

from PySide6.QtWidgets import QApplication

from src.pdfapp.main_window import MainWindow
from src.pdfapp.theme import apply_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Editor MVP")
    app.setOrganizationName("marcoshctavares-alt")
    apply_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()