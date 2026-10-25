from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.pdfapp import theme

# Espaço entre a página e as bordas da área de visualização (pixels lógicos).
PAGE_MARGIN_X = 32
PAGE_MARGIN_TOP = 28
PAGE_MARGIN_BOTTOM = 36

SHADOW_LAYERS = 10
SHADOW_OFFSET_Y = 3

SELECTION_PADDING = 2.0

EMPTY_TITLE = "Nenhum PDF aberto"


class _SelectionOverlay(QWidget):
    """Camada transparente sobre a página que desenha o texto selecionado.

    É filha do QLabel da página (por isso é pintada por cima dele) e deixa
    todos os cliques passarem. O retângulo é guardado em pixels do pixmap
    ORIGINAL e multiplicado pelo zoom só na hora de pintar.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._rect: QRectF | None = None
        self._zoom: float = 1.0

    def set_state(self, rect: QRectF | None, zoom: float) -> None:
        self._rect = rect
        self._zoom = zoom
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (nome do Qt)
        if self._rect is None:
            return
        zoom = self._zoom
        rect = QRectF(
            self._rect.x() * zoom,
            self._rect.y() * zoom,
            self._rect.width() * zoom,
            self._rect.height() * zoom,
        ).adjusted(
            -SELECTION_PADDING,
            -SELECTION_PADDING,
            SELECTION_PADDING,
            SELECTION_PADDING,
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fill = QColor(theme.COLOR_ACCENT)
        fill.setAlpha(36)
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(theme.COLOR_ACCENT), 1.5))
        painter.drawRoundedRect(rect, 3, 3)
        painter.end()


class _PageCanvas(QWidget):
    """Fundo cinza que contém a página, desenha a sombra e o estado vazio.

    O QLabel da página continua com o tamanho exato do pixmap (setFixedSize);
    a margem e a sombra ficam no canvas, FORA do label. Por isso a conversão
    clique -> pixel do pixmap continua dependendo só da posição do label.
    """

    def __init__(self, label: QLabel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self._is_empty = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            PAGE_MARGIN_X, PAGE_MARGIN_TOP, PAGE_MARGIN_X, PAGE_MARGIN_BOTTOM
        )
        layout.setSpacing(0)
        layout.addWidget(
            label,
            0,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        )

    def set_empty(self, empty: bool) -> None:
        self._is_empty = empty
        self.update()

    # ------------------------------------------------------------------
    # Pintura
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (nome do Qt)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.COLOR_CANVAS))

        if self._is_empty:
            self._paint_empty_state(painter)
        else:
            self._paint_page_frame(painter, self._label.geometry())

        painter.end()

    def _paint_page_frame(self, painter: QPainter, page: QRect) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        # Sombra suave: camadas translúcidas, da mais externa para a interna.
        for i in range(SHADOW_LAYERS, 0, -1):
            alpha = int(16 * (1.0 - i / (SHADOW_LAYERS + 1)))
            painter.setBrush(QColor(20, 30, 50, alpha))
            rect = QRectF(page).adjusted(-i, -i + SHADOW_OFFSET_Y, i, i + SHADOW_OFFSET_Y)
            painter.drawRoundedRect(rect, 2 + i * 0.6, 2 + i * 0.6)

        # Contorno fino ao redor da página.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#CDD3DB"), 1))
        painter.drawRect(QRectF(page).adjusted(-0.5, -0.5, 0.5, 0.5))

    def _paint_empty_state(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        icon_size = 64
        title_font = self.font()
        title_font.setPointSizeF(self.font().pointSizeF() + 3)
        title_font.setBold(True)
        hint_font = self.font()

        title_h = QFontMetrics(title_font).height()
        hint_h = QFontMetrics(hint_font).height()
        gap_icon = 16
        gap_text = 6
        block_h = icon_size + gap_icon + title_h + gap_text + hint_h

        cx = self.width() // 2
        top = max(0, (self.height() - block_h) // 2)

        icon = theme.make_pixmap(
            "document", theme.COLOR_TEXT_DISABLED, icon_size, self.devicePixelRatioF()
        )
        painter.drawPixmap(QPoint(cx - icon_size // 2, top), icon)

        width = max(self.width(), 200)
        title_rect = QRect(
            cx - width // 2, top + icon_size + gap_icon, width, title_h
        )
        painter.setFont(title_font)
        painter.setPen(QColor(theme.COLOR_TEXT))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, EMPTY_TITLE)

        shortcut = QKeySequence(QKeySequence.StandardKey.Open).toString(
            QKeySequence.SequenceFormat.NativeText
        )
        hint = f"Abra um PDF com {shortcut}" if shortcut else "Abra um PDF"
        hint_rect = QRect(
            cx - width // 2, title_rect.bottom() + gap_text, width, hint_h
        )
        painter.setFont(hint_font)
        painter.setPen(QColor(theme.COLOR_TEXT_MUTED))
        painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, hint)


class PdfViewer(QScrollArea):
    # Coordenadas do clique em PIXELS do pixmap ORIGINAL (sem escala).
    page_clicked = Signal(float, float)
    # Duplo clique, nas mesmas coordenadas de page_clicked.
    page_double_clicked = Signal(float, float)
    # Emitido sempre que o zoom muda (valor float, ex: 1.0, 1.25, 2.0).
    zoom_changed = Signal(float)

    MIN_ZOOM = 0.25
    MAX_ZOOM = 4.0
    ZOOM_STEP = 1.25

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pixmap: QPixmap | None = None
        self._zoom: float = 1.0
        self._selection: QRectF | None = None

        # O label tem SEMPRE o tamanho exato do pixmap exibido (sem padding).
        self._label = QLabel()
        self._label.setFrameShape(QFrame.Shape.NoFrame)
        self._label.setMargin(0)
        self._label.setContentsMargins(0, 0, 0, 0)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._label.hide()

        # Camada de seleção por cima da página (filha do label).
        self._overlay = _SelectionOverlay(self._label)

        # O canvas é quem se adapta à janela (centraliza, desenha a sombra);
        # o label dentro dele não é redimensionado.
        self._canvas = _PageCanvas(self._label)

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setWidget(self._canvas)

    # ------------------------------------------------------------------
    # Exibição, seleção e zoom
    # ------------------------------------------------------------------
    def show_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self._canvas.set_empty(False)
        self._label.show()
        self._apply_zoom()

    def set_selection(
        self, rect: tuple[float, float, float, float] | None
    ) -> None:
        """Destaca um retângulo (x, y, largura, altura) em pixels do pixmap
        original, ou remove o destaque se `rect` for None."""
        self._selection = None if rect is None else QRectF(*rect)
        self._overlay.set_state(self._selection, self._zoom)

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

        # Ponto do pixmap original que está sob o centro do viewport.
        old_zoom = self._zoom
        vp_center = self.viewport().rect().center()
        origin = self._label.mapTo(self.viewport(), QPoint(0, 0))
        anchor_x = (vp_center.x() - origin.x()) / old_zoom
        anchor_y = (vp_center.y() - origin.y()) / old_zoom

        self._zoom = new_zoom
        self._apply_zoom()
        self.zoom_changed.emit(new_zoom)

        # O layout só atualiza as barras de rolagem depois do evento de
        # layout; por isso o reposicionamento é adiado para o próximo ciclo.
        QTimer.singleShot(
            0, lambda: self._restore_anchor(anchor_x, anchor_y)
        )

    def _restore_anchor(self, anchor_x: float, anchor_y: float) -> None:
        """Rola o viewport para que o ponto-âncora volte ao centro."""
        vp_center = self.viewport().rect().center()
        origin = self._label.mapTo(self.viewport(), QPoint(0, 0))
        current = QPointF(
            origin.x() + anchor_x * self._zoom,
            origin.y() + anchor_y * self._zoom,
        )
        h_bar = self.horizontalScrollBar()
        v_bar = self.verticalScrollBar()
        h_bar.setValue(h_bar.value() + int(round(current.x() - vp_center.x())))
        v_bar.setValue(v_bar.value() + int(round(current.y() - vp_center.y())))

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

        self._overlay.setGeometry(0, 0, scaled.width(), scaled.height())
        self._overlay.raise_()
        self._overlay.set_state(self._selection, self._zoom)
        self._canvas.update()

    # ------------------------------------------------------------------
    # Cliques
    # ------------------------------------------------------------------
    def _pixmap_coords(self, event: QMouseEvent) -> tuple[float, float] | None:
        """Posição do evento em pixels do pixmap original, ou None se o
        clique caiu fora da página (ou se não há página carregada)."""
        pixmap = self._pixmap
        if pixmap is None or pixmap.isNull():
            return None

        origin = self._label.mapToGlobal(QPoint(0, 0))
        global_pos = event.globalPosition()
        # Converte do espaço do label escalado para o pixmap original.
        x = (global_pos.x() - origin.x()) / self._zoom
        y = (global_pos.y() - origin.y()) / self._zoom

        if 0.0 <= x < pixmap.width() and 0.0 <= y < pixmap.height():
            return x, y
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            coords = self._pixmap_coords(event)
            if coords is not None:
                self.page_clicked.emit(*coords)

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # Não chama o super: o padrão do Qt repassaria o evento a
        # mousePressEvent e o clique seria emitido duas vezes.
        if event.button() == Qt.MouseButton.LeftButton:
            coords = self._pixmap_coords(event)
            if coords is not None:
                self.page_double_clicked.emit(*coords)
        event.accept()