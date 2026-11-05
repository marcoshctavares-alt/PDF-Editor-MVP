from string import Template

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QApplication

COLOR_ACCENT = "#2563EB"
COLOR_ACCENT_HOVER = "#1D4FD8"
COLOR_ACCENT_SOFT = "#E3EDFF"
COLOR_TEXT = "#2B303B"
COLOR_TEXT_MUTED = "#6B7482"
COLOR_TEXT_DISABLED = "#AEB5C0"
COLOR_BORDER = "#E1E4E8"
COLOR_BORDER_STRONG = "#D0D5DB"
COLOR_SURFACE = "#FFFFFF"
COLOR_WINDOW = "#F4F5F7"
COLOR_CANVAS = "#E9ECF0"
COLOR_HOVER = "#EEF1F5"
COLOR_PRESSED = "#E1E6ED"
COLOR_SEARCH = "#FFD54A"
COLOR_SEARCH_CURRENT = "#FF9F1A"

_ICONS: dict[str, list[tuple]] = {
    "open": [
        (
            "poly",
            [
                (3, 6.5), (3, 18), (4.5, 19.5), (19.5, 19.5), (21, 18),
                (21, 10), (19.5, 8.5), (11.5, 8.5), (9.5, 5.5), (4.5, 5.5),
            ],
            True,
        ),
    ],
    "save": [
        (
            "poly",
            [
                (5, 4), (16, 4), (20, 8), (20, 19), (19, 20),
                (5, 20), (4, 19), (4, 5),
            ],
            True,
        ),
        ("poly", [(8, 4), (8, 9), (15, 9), (15, 4)], False),
        ("poly", [(7, 20), (7, 14), (17, 14), (17, 20)], False),
    ],
    "prev": [("poly", [(14.5, 5), (7.5, 12), (14.5, 19)], False)],
    "next": [("poly", [(9.5, 5), (16.5, 12), (9.5, 19)], False)],
    "text": [
        ("poly", [(5, 6.5), (19, 6.5)], False),
        ("poly", [(12, 6.5), (12, 18.5)], False),
        ("poly", [(9, 18.5), (15, 18.5)], False),
    ],
    "zoom_in": [
        ("circle", 10.5, 10.5, 6.5),
        ("poly", [(15.5, 15.5), (20, 20)], False),
        ("poly", [(8, 10.5), (13, 10.5)], False),
        ("poly", [(10.5, 8), (10.5, 13)], False),
    ],
    "zoom_out": [
        ("circle", 10.5, 10.5, 6.5),
        ("poly", [(15.5, 15.5), (20, 20)], False),
        ("poly", [(8, 10.5), (13, 10.5)], False),
    ],
    "undo": [
        ("poly", [(9, 6), (5, 10), (9, 14)], False),
        (
            "poly",
            [(5, 10), (14, 10), (18, 11.5), (19.5, 15), (18, 18.5), (14, 20), (9, 20)],
            False,
        ),
    ],
    "redo": [
        ("poly", [(15, 6), (19, 10), (15, 14)], False),
        (
            "poly",
            [(19, 10), (10, 10), (6, 11.5), (4.5, 15), (6, 18.5), (10, 20), (15, 20)],
            False,
        ),
    ],
    "trash": [
        ("poly", [(4, 7), (20, 7)], False),
        ("poly", [(9, 7), (9, 4.5), (15, 4.5), (15, 7)], False),
        ("poly", [(6, 7), (7, 20), (17, 20), (18, 7)], False),
        ("poly", [(10, 11), (10, 16)], False),
        ("poly", [(14, 11), (14, 16)], False),
    ],
    "edit": [
        ("poly", [(4, 20), (4, 15.5), (15.5, 4), (20, 8.5), (8.5, 20)], True),
        ("poly", [(13, 6.5), (17.5, 11)], False),
    ],
    "image": [
        ("poly", [(4, 5), (20, 5), (20, 19), (4, 19)], True),
        ("circle", 9, 10, 1.6),
        ("poly", [(4, 17), (9, 12.5), (13, 16.5), (15.5, 14), (20, 18)], False),
    ],
    "search": [
        ("circle", 10.5, 10.5, 6.5),
        ("poly", [(15.5, 15.5), (20, 20)], False),
    ],
    "up": [("poly", [(5, 14.5), (12, 7.5), (19, 14.5)], False)],
    "down": [("poly", [(5, 9.5), (12, 16.5), (19, 9.5)], False)],
    "close": [
        ("poly", [(6, 6), (18, 18)], False),
        ("poly", [(18, 6), (6, 18)], False),
    ],
    "highlight": [
        ("poly", [(15, 4), (20, 9), (11, 18), (6, 18), (6, 13)], True),
        ("poly", [(4, 21), (20, 21)], False),
    ],
    "underline": [
        ("poly", [(7, 4), (7, 11), (9, 14.5), (15, 14.5), (17, 11), (17, 4)], False),
        ("poly", [(5, 20), (19, 20)], False),
    ],
    "strikeout": [
        ("poly", [(16.5, 6.5), (9, 6.5), (7, 8.5), (9, 10.5), (15, 13.5), (17, 15.5), (15, 17.5), (7.5, 17.5)], False),
        ("poly", [(4, 12), (20, 12)], False),
    ],
    "copy": [
        ("poly", [(9, 9), (19, 9), (19, 20), (9, 20)], True),
        ("poly", [(15, 9), (15, 4), (5, 4), (5, 15), (9, 15)], False),
    ],
    "rotate_right": [
        (
            "poly",
            [
                (15.2, 6.9), (12.0, 6.0), (8.8, 6.9), (6.4, 9.2), (5.5, 12.5),
                (6.4, 15.8), (8.7, 18.1), (12.0, 19.0), (15.2, 18.1), (17.6, 15.8),
            ],
            False,
        ),
        ("poly", [(16.4, 4.8), (17.2, 8.0), (14.0, 9.0)], False),
    ],
    "rotate_left": [
        (
            "poly",
            [
                (8.8, 6.9), (12.0, 6.0), (15.2, 6.9), (17.6, 9.2), (18.5, 12.5),
                (17.6, 15.8), (15.3, 18.1), (12.0, 19.0), (8.8, 18.1), (6.4, 15.8),
            ],
            False,
        ),
        ("poly", [(7.6, 4.8), (6.8, 8.0), (10.0, 9.0)], False),
    ],
    "delete_page": [
        (
            "poly",
            [(6, 3.5), (14, 3.5), (18, 7.5), (18, 20.5), (6, 20.5)],
            True,
        ),
        ("poly", [(14, 3.5), (14, 7.5), (18, 7.5)], False),
        ("poly", [(9, 14), (15, 14)], False),
    ],
    "sidebar": [
        ("poly", [(4, 5), (20, 5), (20, 19), (4, 19)], True),
        ("poly", [(9.5, 5), (9.5, 19)], False),
    ],
    "document": [
        ("poly", [(6, 3), (14, 3), (19, 8), (19, 21), (6, 21)], True),
        ("poly", [(14, 3), (14, 8), (19, 8)], False),
        ("poly", [(9, 13), (16, 13)], False),
        ("poly", [(9, 17), (14, 17)], False),
    ],
}

_GRID = 24.0
_STROKE = 1.8
_ICON_PX = 64

_icon_cache: dict[str, QIcon] = {}


def make_pixmap(
    name: str, color: str, size: int = 24, dpr: float = 1.0
) -> QPixmap:
    physical = max(1, int(round(size * dpr)))
    pixmap = QPixmap(physical, physical)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / _GRID, size / _GRID)

    pen = QPen(
        QColor(color),
        _STROKE,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    for shape in _ICONS[name]:
        kind = shape[0]
        if kind == "circle":
            _, cx, cy, radius = shape
            painter.drawEllipse(QPointF(cx, cy), radius, radius)
        else:
            _, points, closed = shape
            polygon = QPolygonF([QPointF(x, y) for x, y in points])
            if closed:
                painter.drawPolygon(polygon)
            else:
                painter.drawPolyline(polygon)

    painter.end()
    return pixmap


def make_icon(name: str) -> QIcon:
    cached = _icon_cache.get(name)
    if cached is not None:
        return cached

    normal = make_pixmap(name, COLOR_TEXT, _ICON_PX)
    accent = make_pixmap(name, COLOR_ACCENT, _ICON_PX)
    disabled = make_pixmap(name, COLOR_TEXT_DISABLED, _ICON_PX)

    icon = QIcon()
    icon.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(normal, QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(accent, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(accent, QIcon.Mode.Active, QIcon.State.On)
    icon.addPixmap(disabled, QIcon.Mode.Disabled, QIcon.State.Off)
    icon.addPixmap(disabled, QIcon.Mode.Disabled, QIcon.State.On)

    _icon_cache[name] = icon
    return icon


_QSS = Template(
    """
QMainWindow {
    background: $window;
}

QToolBar#mainToolbar {
    background: $surface;
    border: none;
    border-bottom: 1px solid $border;
    padding: 6px 10px;
    spacing: 2px;
}
QToolBar#mainToolbar::separator {
    background: $border;
    width: 1px;
    margin: 6px 8px;
}
QToolBar#mainToolbar QToolButton {
    background: transparent;
    color: $text;
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
}
QToolBar#mainToolbar QToolButton:hover {
    background: $hover;
}
QToolBar#mainToolbar QToolButton:pressed {
    background: $pressed;
}
QToolBar#mainToolbar QToolButton:checked {
    background: $accent_soft;
    color: $accent;
}
QToolBar#mainToolbar QToolButton:disabled {
    background: transparent;
    color: $text_disabled;
}

QStatusBar {
    background: $surface;
    color: $text_muted;
    border-top: 1px solid $border;
}
QStatusBar::item {
    border: none;
}
QLabel#statusPill {
    background: $hover;
    color: $text;
    border-radius: 10px;
    padding: 2px 10px;
    margin: 3px 4px;
}

QScrollBar:vertical {
    background: transparent;
    width: 14px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #C3C9D2;
    border-radius: 5px;
    min-height: 36px;
}
QScrollBar::handle:vertical:hover {
    background: #A5ADB9;
}
QScrollBar:horizontal {
    background: transparent;
    height: 14px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #C3C9D2;
    border-radius: 5px;
    min-width: 36px;
}
QScrollBar::handle:horizontal:hover {
    background: #A5ADB9;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0px;
    height: 0px;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}

QToolTip {
    background: $text;
    color: #FFFFFF;
    border: none;
    padding: 4px 8px;
}

QDialog, QMessageBox {
    background: $surface;
}
QPushButton {
    background: $surface;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 6px 18px;
    min-width: 64px;
}
QPushButton:hover {
    background: $window;
}
QPushButton:pressed {
    background: $pressed;
}
QPushButton:default {
    background: $accent;
    color: #FFFFFF;
    border-color: $accent;
}
QPushButton:default:hover {
    background: $accent_hover;
}
QLineEdit {
    background: $surface;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: $accent;
    selection-color: #FFFFFF;
}
QLineEdit:focus {
    border-color: $accent;
}
QPushButton:disabled {
    background: $window;
    color: $text_disabled;
    border-color: $border;
}

QFrame#thumbnailPanel {
    background: $surface;
    border: none;
    border-right: 1px solid $border;
}
QListWidget#thumbnailList {
    background: $surface;
    border: none;
    outline: none;
    color: $text_muted;
}
QListWidget#thumbnailList::item {
    border-radius: 6px;
    padding: 4px;
}
QListWidget#thumbnailList::item:hover {
    background: $hover;
}
QListWidget#thumbnailList::item:selected {
    background: $accent_soft;
    color: $accent;
}

QFrame#searchBar {
    background: $surface;
    border: none;
    border-bottom: 1px solid $border;
}
QFrame#searchBar QLineEdit {
    padding: 4px 8px;
    min-width: 220px;
}
QToolButton#searchButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px;
}
QToolButton#searchButton:hover {
    background: $hover;
}
QToolButton#searchButton:pressed {
    background: $pressed;
}
QToolButton#searchButton:disabled {
    background: transparent;
}
QLabel#searchStatus {
    color: $text_muted;
    padding: 0 6px;
}

QFrame#propertiesPanel {
    background: $surface;
    border: none;
    border-left: 1px solid $border;
}
QLabel#panelTitle {
    color: $text;
    font-weight: bold;
    font-size: 14px;
}
QLabel#panelHint {
    color: $text_muted;
}
QLabel#fieldLabel {
    color: $text_muted;
}
QToolButton#styleToggle {
    background: $surface;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    min-width: 34px;
    min-height: 28px;
}
QToolButton#styleToggle:hover {
    background: $hover;
}
QToolButton#styleToggle:checked {
    background: $accent_soft;
    border-color: $accent;
    color: $accent;
}
QToolButton#styleToggle:disabled {
    background: $window;
    color: $text_disabled;
    border-color: $border;
}
QPushButton#dangerButton:hover {
    background: #FDECEC;
    border-color: #F2B8B5;
    color: #B42318;
}
QPushButton#dangerButton:disabled {
    background: $window;
    color: $text_disabled;
    border-color: $border;
}
"""
)


def stylesheet() -> str:
    return _QSS.substitute(
        window=COLOR_WINDOW,
        surface=COLOR_SURFACE,
        border=COLOR_BORDER,
        border_strong=COLOR_BORDER_STRONG,
        text=COLOR_TEXT,
        text_muted=COLOR_TEXT_MUTED,
        text_disabled=COLOR_TEXT_DISABLED,
        hover=COLOR_HOVER,
        pressed=COLOR_PRESSED,
        accent=COLOR_ACCENT,
        accent_hover=COLOR_ACCENT_HOVER,
        accent_soft=COLOR_ACCENT_SOFT,
    )


def _build_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLOR_WINDOW))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLOR_TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLOR_SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLOR_WINDOW))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLOR_TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLOR_SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLOR_TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLOR_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLOR_TEXT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(
            QPalette.ColorGroup.Disabled, role, QColor(COLOR_TEXT_DISABLED)
        )
    return palette


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setPalette(_build_palette())

    font = QFont()
    font.setFamilies(
        ["Segoe UI", "Inter", "Noto Sans", "Helvetica Neue", "Arial"]
    )
    font.setPointSize(10)
    app.setFont(font)

    app.setStyleSheet(stylesheet())
