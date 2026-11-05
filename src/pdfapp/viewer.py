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
from src.pdfcore.image_items import CORNERS, corner_point, resize_keep_aspect

PAGE_MARGIN_X = 32
PAGE_MARGIN_TOP = 28
PAGE_MARGIN_BOTTOM = 36

SHADOW_LAYERS = 10
SHADOW_OFFSET_Y = 3

SELECTION_PADDING = 2.0
HANDLE_SIZE = 8.0
HANDLE_HIT = 8.0
MIN_RESIZE_SIDE = 8.0

CORNER_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
}

EMPTY_TITLE = "Nenhum PDF aberto"


def clamp_move(
    rect: tuple[float, float, float, float],
    page: tuple[float, float],
    dx: float,
    dy: float,
) -> tuple[float, float]:
    x, y, width, height = rect
    max_x = max(0.0, page[0] - width)
    max_y = max(0.0, page[1] - height)
    return (
        min(max(x + dx, 0.0), max_x) - x,
        min(max(y + dy, 0.0), max_y) - y,
    )


class _SelectionOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._rect: QRectF | None = None
        self._drag: QRectF | None = None
        self._move: tuple[float, float] | None = None
        self._resize: QRectF | None = None
        self._handles: bool = False
        self._highlights: list[QRectF] = []
        self._highlight_current: int | None = None
        self._zoom: float = 1.0

    def set_state(self, rect: QRectF | None, zoom: float) -> None:
        self._rect = rect
        self._zoom = zoom
        self.update()

    def set_drag(self, rect: QRectF | None) -> None:
        self._drag = rect
        self.update()

    def set_move(self, offset: tuple[float, float] | None) -> None:
        self._move = offset
        self.update()

    def set_highlights(self, rects: list[QRectF], current: int | None) -> None:
        self._highlights = rects
        self._highlight_current = current
        self.update()

    def set_resize(self, rect: QRectF | None) -> None:
        self._resize = rect
        self.update()

    def set_handles(self, enabled: bool) -> None:
        self._handles = enabled
        self.update()

    def _scaled(self, rect: QRectF) -> QRectF:
        zoom = self._zoom
        return QRectF(
            rect.x() * zoom,
            rect.y() * zoom,
            rect.width() * zoom,
            rect.height() * zoom,
        )

    def paintEvent(self, event) -> None:
        if self._rect is None and self._drag is None and not self._highlights:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for index, highlight in enumerate(self._highlights):
            is_current = index == self._highlight_current
            fill = QColor(
                theme.COLOR_SEARCH_CURRENT if is_current else theme.COLOR_SEARCH
            )
            fill.setAlpha(150 if is_current else 105)
            painter.setBrush(fill)
            if is_current:
                painter.setPen(QPen(QColor(theme.COLOR_SEARCH_CURRENT), 1.5))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(self._scaled(highlight))

        if self._rect is not None:
            rect = self._scaled(self._rect).adjusted(
                -SELECTION_PADDING,
                -SELECTION_PADDING,
                SELECTION_PADDING,
                SELECTION_PADDING,
            )
            fill = QColor(theme.COLOR_ACCENT)
            fill.setAlpha(
                14 if self._move is not None or self._resize is not None else 36
            )
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(theme.COLOR_ACCENT), 1.5))
            painter.drawRoundedRect(rect, 3, 3)

            if self._move is not None:
                ghost = self._scaled(
                    self._rect.translated(self._move[0], self._move[1])
                ).adjusted(
                    -SELECTION_PADDING,
                    -SELECTION_PADDING,
                    SELECTION_PADDING,
                    SELECTION_PADDING,
                )
                ghost_fill = QColor(theme.COLOR_ACCENT)
                ghost_fill.setAlpha(64)
                ghost_pen = QPen(QColor(theme.COLOR_ACCENT), 1.5)
                ghost_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setBrush(ghost_fill)
                painter.setPen(ghost_pen)
                painter.drawRoundedRect(ghost, 3, 3)

            if self._resize is not None:
                preview = self._scaled(self._resize).adjusted(
                    -SELECTION_PADDING,
                    -SELECTION_PADDING,
                    SELECTION_PADDING,
                    SELECTION_PADDING,
                )
                preview_fill = QColor(theme.COLOR_ACCENT)
                preview_fill.setAlpha(64)
                preview_pen = QPen(QColor(theme.COLOR_ACCENT), 1.5)
                preview_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setBrush(preview_fill)
                painter.setPen(preview_pen)
                painter.drawRoundedRect(preview, 3, 3)

            if self._handles and self._move is None and self._resize is None:
                painter.setBrush(QColor(theme.COLOR_SURFACE))
                painter.setPen(QPen(QColor(theme.COLOR_ACCENT), 1.5))
                scaled = self._scaled(self._rect)
                half = HANDLE_SIZE / 2
                for corner in CORNERS:
                    cx, cy = corner_point(
                        (scaled.left(), scaled.top(), scaled.right(), scaled.bottom()),
                        corner,
                    )
                    painter.drawRect(QRectF(cx - half, cy - half, HANDLE_SIZE, HANDLE_SIZE))

        if self._drag is not None:
            fill = QColor(theme.COLOR_ACCENT)
            fill.setAlpha(24)
            pen = QPen(QColor(theme.COLOR_ACCENT), 1.5)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setBrush(fill)
            painter.setPen(pen)
            painter.drawRect(self._scaled(self._drag))

        painter.end()


class _PageCanvas(QWidget):
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

    def paintEvent(self, event) -> None:
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

        for i in range(SHADOW_LAYERS, 0, -1):
            alpha = int(16 * (1.0 - i / (SHADOW_LAYERS + 1)))
            painter.setBrush(QColor(20, 30, 50, alpha))
            rect = QRectF(page).adjusted(-i, -i + SHADOW_OFFSET_Y, i, i + SHADOW_OFFSET_Y)
            painter.drawRoundedRect(rect, 2 + i * 0.6, 2 + i * 0.6)

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
    page_clicked = Signal(float, float)
    page_double_clicked = Signal(float, float)
    rect_drawn = Signal(float, float, float, float)
    selection_moved = Signal(float, float)
    selection_resized = Signal(float, float, float, float)
    zoom_changed = Signal(float)

    MIN_ZOOM = 0.25
    MAX_ZOOM = 4.0
    ZOOM_STEP = 1.25
    DRAG_THRESHOLD = 5.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pixmap: QPixmap | None = None
        self._zoom: float = 1.0
        self._selection: QRectF | None = None
        self._rect_mode: bool = False
        self._drag_start: tuple[float, float] | None = None
        self._movable: bool = False
        self._move_press: tuple[float, float] | None = None
        self._move_press_global: tuple[float, float] | None = None
        self._moving: bool = False
        self._move_offset: tuple[float, float] = (0.0, 0.0)
        self._resizable: bool = False
        self._resize_corner: str | None = None
        self._resize_press_global: tuple[float, float] | None = None
        self._resizing: bool = False
        self._resize_rect: tuple[float, float, float, float] | None = None

        self._label = QLabel()
        self._label.setFrameShape(QFrame.Shape.NoFrame)
        self._label.setMargin(0)
        self._label.setContentsMargins(0, 0, 0, 0)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._label.hide()

        self._overlay = _SelectionOverlay(self._label)

        self._canvas = _PageCanvas(self._label)

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setWidget(self._canvas)
        self.viewport().setMouseTracking(True)

    def show_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self._canvas.set_empty(False)
        self._label.show()
        self._apply_zoom()

    def set_selection(
        self,
        rect: tuple[float, float, float, float] | None,
        movable: bool = False,
        resizable: bool = False,
    ) -> None:
        self._cancel_move()
        self._cancel_resize()
        self._selection = None if rect is None else QRectF(*rect)
        self._movable = movable and rect is not None
        self._resizable = resizable and rect is not None
        self._overlay.set_handles(self._resizable)
        self._overlay.set_state(self._selection, self._zoom)

    def _cancel_resize(self) -> None:
        was_active = self._resize_corner is not None
        self._resize_corner = None
        self._resize_press_global = None
        self._resizing = False
        self._resize_rect = None
        self._overlay.set_resize(None)
        if was_active:
            self.viewport().unsetCursor()

    def set_search_highlights(
        self,
        rects: list[tuple[float, float, float, float]],
        current: int | None = None,
    ) -> None:
        self._overlay.set_highlights(
            [QRectF(x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in rects],
            current,
        )

    def scroll_to_rect(self, rect: tuple[float, float, float, float]) -> None:
        QTimer.singleShot(0, lambda: self._scroll_now(rect))

    def _scroll_now(self, rect: tuple[float, float, float, float]) -> None:
        x0, y0, x1, y1 = rect
        origin = self._label.mapTo(self._canvas, QPoint(0, 0))
        center_x = origin.x() + (x0 + x1) / 2 * self._zoom
        center_y = origin.y() + (y0 + y1) / 2 * self._zoom
        viewport = self.viewport()
        self.ensureVisible(
            int(round(center_x)),
            int(round(center_y)),
            viewport.width() // 3,
            viewport.height() // 3,
        )

    def _cancel_move(self) -> None:
        self._move_press = None
        self._move_press_global = None
        self._moving = False
        self._move_offset = (0.0, 0.0)
        self._overlay.set_move(None)
        self.viewport().unsetCursor()

    def set_rect_mode(self, enabled: bool) -> None:
        self._rect_mode = enabled
        if not enabled:
            self._cancel_drag()

    def _cancel_drag(self) -> None:
        self._drag_start = None
        self._overlay.set_drag(None)

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

        old_zoom = self._zoom
        vp_center = self.viewport().rect().center()
        origin = self._label.mapTo(self.viewport(), QPoint(0, 0))
        anchor_x = (vp_center.x() - origin.x()) / old_zoom
        anchor_y = (vp_center.y() - origin.y()) / old_zoom

        self._zoom = new_zoom
        self._apply_zoom()
        self.zoom_changed.emit(new_zoom)

        QTimer.singleShot(
            0, lambda: self._restore_anchor(anchor_x, anchor_y)
        )

    def _restore_anchor(self, anchor_x: float, anchor_y: float) -> None:
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

    def _pixmap_coords(self, event: QMouseEvent) -> tuple[float, float] | None:
        pixmap = self._pixmap
        if pixmap is None or pixmap.isNull():
            return None

        origin = self._label.mapToGlobal(QPoint(0, 0))
        global_pos = event.globalPosition()
        x = (global_pos.x() - origin.x()) / self._zoom
        y = (global_pos.y() - origin.y()) / self._zoom

        if 0.0 <= x < pixmap.width() and 0.0 <= y < pixmap.height():
            return x, y
        return None

    def _clamped_coords(self, event: QMouseEvent) -> tuple[float, float] | None:
        pixmap = self._pixmap
        if pixmap is None or pixmap.isNull():
            return None

        origin = self._label.mapToGlobal(QPoint(0, 0))
        global_pos = event.globalPosition()
        x = (global_pos.x() - origin.x()) / self._zoom
        y = (global_pos.y() - origin.y()) / self._zoom
        return (
            max(0.0, min(float(pixmap.width()), x)),
            max(0.0, min(float(pixmap.height()), y)),
        )

    @staticmethod
    def _ordered_rect(
        a: tuple[float, float], b: tuple[float, float]
    ) -> tuple[float, float, float, float]:
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

    def _raw_coords(self, event: QMouseEvent) -> tuple[float, float] | None:
        if self._pixmap is None or self._pixmap.isNull():
            return None
        origin = self._label.mapToGlobal(QPoint(0, 0))
        global_pos = event.globalPosition()
        return (
            (global_pos.x() - origin.x()) / self._zoom,
            (global_pos.y() - origin.y()) / self._zoom,
        )

    def _selection_hit(self, coords: tuple[float, float]) -> bool:
        selection = self._selection
        if selection is None or not self._movable:
            return False
        pad = SELECTION_PADDING / self._zoom
        return selection.adjusted(-pad, -pad, pad, pad).contains(
            QPointF(coords[0], coords[1])
        )

    def _handle_at(self, coords: tuple[float, float]) -> str | None:
        selection = self._selection
        if selection is None or not self._resizable:
            return None
        rect = (selection.left(), selection.top(), selection.right(), selection.bottom())
        for corner in CORNERS:
            cx, cy = corner_point(rect, corner)
            if (
                abs(coords[0] - cx) * self._zoom <= HANDLE_HIT
                and abs(coords[1] - cy) * self._zoom <= HANDLE_HIT
            ):
                return corner
        return None

    def _update_resize(self, event: QMouseEvent) -> None:
        corner = self._resize_corner
        press_global = self._resize_press_global
        selection = self._selection
        pixmap = self._pixmap
        if corner is None or press_global is None or selection is None or pixmap is None:
            return

        global_pos = event.globalPosition()
        screen_distance = max(
            abs(global_pos.x() - press_global[0]),
            abs(global_pos.y() - press_global[1]),
        )
        if not self._resizing and screen_distance < self.DRAG_THRESHOLD:
            return

        current = self._raw_coords(event)
        if current is None:
            return

        self._resizing = True
        self._resize_rect = resize_keep_aspect(
            (selection.left(), selection.top(), selection.right(), selection.bottom()),
            corner,
            current,
            MIN_RESIZE_SIDE,
            (float(pixmap.width()), float(pixmap.height())),
        )
        x0, y0, x1, y1 = self._resize_rect
        self._overlay.set_resize(QRectF(x0, y0, x1 - x0, y1 - y0))

    def _update_hover_cursor(self, event: QMouseEvent) -> None:
        coords = self._raw_coords(event)
        if coords is not None:
            corner = self._handle_at(coords)
            if corner is not None:
                self.viewport().setCursor(CORNER_CURSORS[corner])
                return
        if self._movable:
            if coords is not None and self._selection_hit(coords):
                self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
                return
        self.viewport().unsetCursor()

    def _update_move(self, event: QMouseEvent) -> None:
        press = self._move_press
        press_global = self._move_press_global
        selection = self._selection
        pixmap = self._pixmap
        if press is None or press_global is None or selection is None or pixmap is None:
            return

        global_pos = event.globalPosition()
        screen_distance = max(
            abs(global_pos.x() - press_global[0]),
            abs(global_pos.y() - press_global[1]),
        )
        if not self._moving and screen_distance < self.DRAG_THRESHOLD:
            return

        current = self._raw_coords(event)
        if current is None:
            return

        self._moving = True
        self._move_offset = clamp_move(
            (selection.x(), selection.y(), selection.width(), selection.height()),
            (float(pixmap.width()), float(pixmap.height())),
            current[0] - press[0],
            current[1] - press[1],
        )
        self._overlay.set_move(self._move_offset)
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._rect_mode:
            if event.button() == Qt.MouseButton.LeftButton:
                start = self._pixmap_coords(event)
                if start is not None:
                    self._drag_start = start
                    self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            raw = self._raw_coords(event)
            corner = None if raw is None else self._handle_at(raw)
            if corner is not None:
                global_pos = event.globalPosition()
                self._resize_corner = corner
                self._resize_press_global = (global_pos.x(), global_pos.y())
                self._resizing = False
                self._resize_rect = None
                self.viewport().setCursor(CORNER_CURSORS[corner])
                self.setFocus(Qt.FocusReason.MouseFocusReason)
                event.accept()
                return

            coords = self._pixmap_coords(event)
            if coords is not None:
                self.page_clicked.emit(*coords)
                if self._selection_hit(coords):
                    global_pos = event.globalPosition()
                    self._move_press = coords
                    self._move_press_global = (global_pos.x(), global_pos.y())
                    self._moving = False
                    self._move_offset = (0.0, 0.0)
                    event.accept()
                    return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None:
            current = self._clamped_coords(event)
            if current is not None:
                x0, y0, x1, y1 = self._ordered_rect(self._drag_start, current)
                self._overlay.set_drag(QRectF(x0, y0, x1 - x0, y1 - y0))
            event.accept()
            return

        if self._resize_corner is not None:
            self._update_resize(event)
            event.accept()
            return

        if self._move_press is not None:
            self._update_move(event)
            event.accept()
            return

        self._update_hover_cursor(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self._resize_corner is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            resizing = self._resizing
            rect = self._resize_rect
            self._cancel_resize()
            event.accept()
            if resizing and rect is not None:
                self.selection_resized.emit(*rect)
            return

        if (
            self._move_press is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            moving = self._moving
            dx, dy = self._move_offset
            self._cancel_move()
            event.accept()
            if moving and (dx != 0.0 or dy != 0.0):
                self.selection_moved.emit(dx, dy)
            return

        start = self._drag_start
        if start is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        end = self._clamped_coords(event) or start
        self._cancel_drag()
        event.accept()

        moved = max(abs(end[0] - start[0]), abs(end[1] - start[1])) * self._zoom
        if moved < self.DRAG_THRESHOLD:
            end = start
        self.rect_drawn.emit(*self._ordered_rect(start, end))

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._rect_mode:
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            coords = self._pixmap_coords(event)
            if coords is not None:
                self.page_double_clicked.emit(*coords)
        event.accept()
