from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QListView,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.pdfapp import theme
from src.pdfapp.thumbnail_queue import ThumbnailQueue

THUMB_WIDTH = 128
THUMB_MAX_HEIGHT = 192
PANEL_WIDTH = 176
PLACEHOLDER_RATIO = 1.414
FALLBACK_CELL_HEIGHT = 220


class ThumbnailPanel(QFrame):
    page_requested = Signal(int)

    def __init__(
        self,
        provider: Callable[[int], QPixmap | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("thumbnailPanel")
        self.setFixedWidth(PANEL_WIDTH)

        self._provider = provider
        self._queue = ThumbnailQueue()
        self._updating = False
        self._current_row: int | None = None
        self._placeholder = self._make_placeholder()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._tick)

        self._list = QListWidget()
        self._list.setObjectName("thumbnailList")
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setFlow(QListView.Flow.TopToBottom)
        self._list.setWrapping(False)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setUniformItemSizes(True)
        self._list.setIconSize(QSize(THUMB_WIDTH, THUMB_MAX_HEIGHT))
        self._list.setSpacing(6)
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._list.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.verticalScrollBar().valueChanged.connect(self._schedule)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)
        layout.addWidget(self._list)

    def set_pages(self, count: int) -> None:
        self._timer.stop()
        self._updating = True
        try:
            self._list.clear()
            icon = QIcon(self._placeholder)
            for row in range(count):
                item = QListWidgetItem(icon, str(row + 1))
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                self._list.addItem(item)
        finally:
            self._updating = False
        self._queue.reset(count)
        self._current_row = None
        self._schedule()

    def set_current(self, index: int) -> None:
        item = self._list.item(index) if 0 <= index < self._list.count() else None
        if item is None:
            return
        changed = index != self._current_row
        self._current_row = index
        self._updating = True
        try:
            self._list.setCurrentRow(index)
        finally:
            self._updating = False
        if changed:
            self._list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self._schedule()

    def invalidate(self, pages: Iterable[int]) -> None:
        self._queue.mark_dirty(pages)
        self._schedule()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._schedule()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._schedule()

    def _on_row_changed(self, row: int) -> None:
        if self._updating or row < 0:
            return
        self.page_requested.emit(row)

    def _schedule(self, *_: object) -> None:
        if self._list.count() and not self._timer.isActive():
            self._timer.start()

    def _geometry(self) -> tuple[int, int]:
        scroll = self._list.verticalScrollBar().value()
        first = self._list.item(0)
        if first is None:
            return (FALLBACK_CELL_HEIGHT, 0)
        first_rect = self._list.visualItemRect(first)
        origin = first_rect.top() + scroll
        second = self._list.item(1)
        if second is not None:
            pitch = self._list.visualItemRect(second).top() - first_rect.top()
        else:
            pitch = first_rect.height() + self._list.spacing()
        if pitch <= 0:
            pitch = FALLBACK_CELL_HEIGHT
        return (pitch, origin)

    def _visible_rows(self) -> tuple[int, int]:
        count = self._list.count()
        if count == 0:
            return (0, 0)
        pitch, origin = self._geometry()
        top = self._list.verticalScrollBar().value() - origin
        bottom = top + self._list.viewport().height()
        first = max(0, min(count - 1, top // pitch))
        last = max(first, min(count - 1, bottom // pitch))
        return (first, last)

    def _tick(self) -> None:
        first, last = self._visible_rows()
        row = self._queue.next_row(first, last)
        if row is None:
            return

        pixmap = self._provider(row)
        item = self._list.item(row)
        if item is not None and pixmap is not None and not pixmap.isNull():
            item.setIcon(QIcon(self._framed(pixmap)))
        self._queue.mark_rendered(row)
        self._schedule()

    @staticmethod
    def _framed(pixmap: QPixmap) -> QPixmap:
        framed = QPixmap(pixmap)
        painter = QPainter(framed)
        painter.setPen(QColor(theme.COLOR_BORDER_STRONG))
        painter.drawRect(0, 0, framed.width() - 1, framed.height() - 1)
        painter.end()
        return framed

    @staticmethod
    def _make_placeholder() -> QPixmap:
        height = round(THUMB_WIDTH * PLACEHOLDER_RATIO)
        pixmap = QPixmap(THUMB_WIDTH, height)
        pixmap.fill(QColor("#FFFFFF"))
        painter = QPainter(pixmap)
        painter.setPen(QColor(theme.COLOR_BORDER_STRONG))
        painter.drawRect(0, 0, THUMB_WIDTH - 1, height - 1)
        painter.end()
        return pixmap
