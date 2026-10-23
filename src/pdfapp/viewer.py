from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QWidget


class PdfViewer(QScrollArea):
    # Coordenadas do clique em PIXELS do pixmap (origem no canto superior esquerdo).
    page_clicked = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pixmap: QPixmap | None = None

        self._label = QLabel()
        self._label.setFrameShape(QFrame.Shape.NoFrame)
        self._label.setMargin(0)
        self._label.setContentsMargins(0, 0, 0, 0)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        # O QLabel precisa ter exatamente o tamanho do pixmap (sem padding),
        # pois a conversão clique -> coordenada do PDF depende disso.
        self.setWidgetResizable(False)
        self.setWidget(self._label)

    def show_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self._label.setPixmap(pixmap)
        self._label.setFixedSize(pixmap.size())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pixmap = self._pixmap
        if (
            event.button() == Qt.MouseButton.LeftButton
            and pixmap is not None
            and not pixmap.isNull()
        ):
            # Mapeia a posição global do clique para o sistema de coordenadas
            # do QLabel, independentemente da rolagem e do offset do viewport.
            origin = self._label.mapToGlobal(QPoint(0, 0))
            global_pos = event.globalPosition()
            x = global_pos.x() - origin.x()
            y = global_pos.y() - origin.y()

            if 0.0 <= x < pixmap.width() and 0.0 <= y < pixmap.height():
                self.page_clicked.emit(x, y)

        super().mousePressEvent(event)