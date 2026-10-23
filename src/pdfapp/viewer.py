from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea


class PdfViewer(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self._label)
        self.setWidgetResizable(True)

    def show_pixmap(self, pixmap: QPixmap) -> None:
        self._label.setPixmap(pixmap)
        self._label.resize(pixmap.size())
