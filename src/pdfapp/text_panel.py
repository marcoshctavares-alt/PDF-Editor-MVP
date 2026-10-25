from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.pdfapp.theme import COLOR_BORDER_STRONG, make_icon
from src.pdfcore.text_items import (
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_FONT_SIZE,
    FONT_FAMILIES,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
)

PANEL_WIDTH = 260

HINT_NO_SELECTION = (
    "Define a aparência dos próximos textos inseridos. "
    "Clique em um texto da página para editá-lo."
)
HINT_SELECTION = "As alterações valem para o texto selecionado."


def _rgb_to_hex(color: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, round(c * 255))) for c in color)
    return f"#{r:02X}{g:02X}{b:02X}"


class TextPropertiesPanel(QFrame):
    """Painel lateral com fonte, estilo, tamanho e cor do texto.

    Não conhece o documento: apenas emite sinais. Quem usa o painel decide se
    a mudança vale para um texto selecionado ou para os próximos textos.
    """

    # (campo, valor): "family" str, "bold"/"italic" bool, "size" float,
    # "color" tupla (r, g, b) com valores de 0 a 1.
    property_changed = Signal(str, object)
    edit_requested = Signal()
    delete_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("propertiesPanel")
        self.setFixedWidth(PANEL_WIDTH)

        self._color: tuple[float, float, float] = DEFAULT_COLOR

        title = QLabel("Texto")
        title.setObjectName("panelTitle")

        self._hint = QLabel(HINT_NO_SELECTION)
        self._hint.setObjectName("panelHint")
        self._hint.setWordWrap(True)

        self._family = QComboBox()
        self._family.addItems(FONT_FAMILIES)
        self._family.setCurrentText(DEFAULT_FAMILY)
        self._family.currentTextChanged.connect(
            lambda text: self.property_changed.emit("family", text)
        )

        self._bold = self._make_style_button("N", "Negrito", bold=True)
        self._bold.toggled.connect(
            lambda checked: self.property_changed.emit("bold", checked)
        )
        self._italic = self._make_style_button("I", "Itálico", italic=True)
        self._italic.toggled.connect(
            lambda checked: self.property_changed.emit("italic", checked)
        )

        style_row = QHBoxLayout()
        style_row.setContentsMargins(0, 0, 0, 0)
        style_row.setSpacing(6)
        style_row.addWidget(self._bold)
        style_row.addWidget(self._italic)
        style_row.addStretch(1)

        self._size = QDoubleSpinBox()
        self._size.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
        self._size.setDecimals(1)
        self._size.setSingleStep(1.0)
        self._size.setSuffix(" pt")
        self._size.setValue(DEFAULT_FONT_SIZE)
        # Digitar "24" não deve disparar uma mudança para "2" no meio do
        # caminho: com isso, o valor só é emitido no Enter ou ao sair do campo
        # (as setas continuam emitindo na hora).
        self._size.setKeyboardTracking(False)
        self._size.valueChanged.connect(
            lambda value: self.property_changed.emit("size", float(value))
        )

        self._color_button = QPushButton()
        self._color_button.setObjectName("colorButton")
        self._color_button.setToolTip("Escolher cor")
        self._color_button.clicked.connect(self._choose_color)
        self._apply_color_style()

        self._edit_button = QPushButton("Editar texto")
        self._edit_button.setIcon(make_icon("edit"))
        self._edit_button.clicked.connect(self.edit_requested)

        self._delete_button = QPushButton("Apagar")
        self._delete_button.setObjectName("dangerButton")
        self._delete_button.setIcon(make_icon("trash"))
        self._delete_button.clicked.connect(self.delete_requested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self._hint)
        layout.addSpacing(8)
        layout.addWidget(self._field_label("Fonte"))
        layout.addWidget(self._family)
        layout.addSpacing(4)
        layout.addWidget(self._field_label("Estilo"))
        layout.addLayout(style_row)
        layout.addSpacing(4)
        layout.addWidget(self._field_label("Tamanho"))
        layout.addWidget(self._size)
        layout.addSpacing(4)
        layout.addWidget(self._field_label("Cor"))
        layout.addWidget(self._color_button)
        layout.addSpacing(12)
        layout.addWidget(self._edit_button)
        layout.addWidget(self._delete_button)
        layout.addStretch(1)

        self.set_has_selection(False)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def set_values(
        self,
        family: str,
        bold: bool,
        italic: bool,
        size: float,
        color: tuple[float, float, float],
    ) -> None:
        """Mostra valores no painel SEM emitir property_changed."""
        for widget in (self._family, self._bold, self._italic, self._size):
            widget.blockSignals(True)
        try:
            self._family.setCurrentText(family)
            self._bold.setChecked(bool(bold))
            self._italic.setChecked(bool(italic))
            self._size.setValue(float(size))
        finally:
            for widget in (self._family, self._bold, self._italic, self._size):
                widget.blockSignals(False)

        self._color = tuple(color)  # type: ignore[assignment]
        self._apply_color_style()

    def set_has_selection(self, has_selection: bool) -> None:
        self._hint.setText(HINT_SELECTION if has_selection else HINT_NO_SELECTION)
        self._edit_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    @staticmethod
    def _make_style_button(
        text: str, tooltip: str, bold: bool = False, italic: bool = False
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("styleToggle")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCheckable(True)
        font = button.font()
        font.setBold(bold)
        font.setItalic(italic)
        button.setFont(font)
        return button

    def _apply_color_style(self) -> None:
        self._color_button.setStyleSheet(
            "QPushButton#colorButton {"
            f" background: {_rgb_to_hex(self._color)};"
            f" border: 1px solid {COLOR_BORDER_STRONG};"
            " border-radius: 6px;"
            " min-width: 40px;"
            " min-height: 26px;"
            " padding: 0px;"
            "}"
        )

    def _choose_color(self) -> None:
        initial = QColor.fromRgbF(*self._color)
        chosen = QColorDialog.getColor(initial, self, "Cor do texto")
        if not chosen.isValid():
            return
        color = (chosen.redF(), chosen.greenF(), chosen.blueF())
        self._color = color
        self._apply_color_style()
        self.property_changed.emit("color", color)