from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QWidget


class PdfViewer(QScrollArea):
    # Coordenadas do clique em PIXELS do pixmap ORIGINAL (sem escala).
    page_clicked = Signal(float, float)
    # Emitido sempre que o zoom muda (valor float, ex: 1.0, 1.25, 2.0).
    zoom_changed = Signal(float)

    MIN_ZOOM = 0.25
    MAX_ZOOM = 4.0
    ZOOM_STEP = 1.25

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pixmap: QPixmap | None = None
        self._zoom: float = 1.0

        self.setStyleSheet(
            "QScrollArea { background-color: #525659; border: none; }"
            "QScrollArea > QWidget > QWidget { background-color: #525659; }"
        )

        self._label = QLabel()
        self._label.setFrameShape(QFrame.Shape.NoFrame)
        self._label.setMargin(0)
        self._label.setContentsMargins(0, 0, 0, 0)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self._label)

    # ------------------------------------------------------------------
    # Exibição e zoom
    # ------------------------------------------------------------------
    def show_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self._apply_zoom()

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom * self.ZOOM_STEP)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom / self.ZOOM_STEP)

    def reset_zoom(self) -> None:
        self._set_zoom(1.0)

    @property
    def zoom(self) -> float:
        return self._zoom

    def _set_zoom(self, value: float) -> None:
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, value))
        if abs(new_zoom - self._zoom) < 0.001:
            return

        # Guarda o centro do viewport em coordenadas do pixmap antes de mudar.
        old_zoom = self._zoom
        vp_center = self.viewport().rect().center()
        h_bar = self.horizontalScrollBar()
        v_bar = self.verticalScrollBar()
        center_x = h_bar.value() + vp_center.x()
        center_y = v_bar.value() + vp_center.y()

        self._zoom = new_zoom
        self._apply_zoom()
        self.zoom_changed.emit(new_zoom)

        # Reposiciona o scroll para manter o centro do viewport no mesmo ponto.
        ratio = new_zoom / old_zoom
        h_bar.setValue(int(center_x * ratio) - vp_center.x())
        v_bar.setValue(int(center_y * ratio) - vp_center.y())

    def _apply_zoom(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        if abs(self._zoom - 1.0) < 0.001:
            scaled = self._pixmap
        else:
            target_w = max(1, int(self._pixmap.width() * self._zoom))
            scaled = self._pixmap.scaledToWidth(
                target_w,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._label.setPixmap(scaled)
        self._label.setFixedSize(scaled.size())

    # ------------------------------------------------------------------
    # Clique
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        pixmap = self._pixmap
        if (
            event.button() == Qt.MouseButton.LeftButton
            and pixmap is not None
            and not pixmap.isNull()
        ):
            origin = self._label.mapToGlobal(QPoint(0, 0))
            global_pos = event.globalPosition()
            # Converte do espaço do label escalado para o pixmap original.
            x = (global_pos.x() - origin.x()) / self._zoom
            y = (global_pos.y() - origin.y()) / self._zoom

            if 0.0 <= x < pixmap.width() and 0.0 <= y < pixmap.height():
                self.page_clicked.emit(x, y)

        super().mousePressEvent(event)