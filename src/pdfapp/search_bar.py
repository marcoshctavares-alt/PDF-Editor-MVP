from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)

from src.pdfapp.theme import make_icon

DEBOUNCE_MS = 250
BUTTON_ICON_SIZE = 18
NO_RESULTS_TEXT = "Nenhum resultado"


class _SearchEdit(QLineEdit):
    previous_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.previous_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class SearchBar(QFrame):
    query_changed = Signal(str)
    next_requested = Signal()
    previous_requested = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("searchBar")
        self.hide()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._emit_query)

        self._edit = _SearchEdit()
        self._edit.setPlaceholderText("Buscar no documento")
        self._edit.setClearButtonEnabled(True)
        self._edit.textChanged.connect(self._on_text_changed)
        self._edit.returnPressed.connect(self._on_return)
        self._edit.previous_requested.connect(self.previous_requested)

        self._status = QLabel("")
        self._status.setObjectName("searchStatus")

        self._previous = self._make_button(
            "up", "Resultado anterior (Shift+F3)", self.previous_requested.emit
        )
        self._next = self._make_button(
            "down", "Próximo resultado (F3)", self.next_requested.emit
        )
        self._close = self._make_button("close", "Fechar a busca (Esc)", self.close_bar)
        self._previous.setEnabled(False)
        self._next.setEnabled(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)
        layout.addWidget(self._edit)
        layout.addWidget(self._status)
        layout.addWidget(self._previous)
        layout.addWidget(self._next)
        layout.addStretch(1)
        layout.addWidget(self._close)

    @staticmethod
    def _make_button(icon: str, tooltip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setObjectName("searchButton")
        button.setIcon(make_icon(icon))
        button.setIconSize(QSize(BUTTON_ICON_SIZE, BUTTON_ICON_SIZE))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(slot)
        return button

    def text(self) -> str:
        return self._edit.text()

    def has_focus(self) -> bool:
        return self._edit.hasFocus()

    def open_bar(self) -> None:
        self.show()
        self._edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._edit.selectAll()

    def close_bar(self) -> None:
        self._edit.clear()
        self._timer.stop()
        self.hide()
        self.set_status(None, 0)
        self.closed.emit()

    def set_status(
        self, current: int | None, total: int, truncated: bool = False
    ) -> None:
        if not self._edit.text().strip():
            text = ""
        elif total == 0 or current is None:
            text = NO_RESULTS_TEXT
        else:
            text = f"{current + 1} de {total}{'+' if truncated else ''}"
        self._status.setText(text)
        self._previous.setEnabled(total > 0)
        self._next.setEnabled(total > 0)

    def _on_text_changed(self, _: str) -> None:
        self._timer.start()

    def _on_return(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._emit_query()
        else:
            self.next_requested.emit()

    def _emit_query(self) -> None:
        self.query_changed.emit(self._edit.text())
