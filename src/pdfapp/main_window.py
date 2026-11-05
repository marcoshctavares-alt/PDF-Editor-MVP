import contextlib
import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.pdfapp.qt_image import rendered_to_qpixmap
from src.pdfapp.search_bar import SearchBar
from src.pdfapp.search_controller import SearchController
from src.pdfapp.text_panel import TextPropertiesPanel
from src.pdfapp.thumbnails import THUMB_WIDTH, ThumbnailPanel
from src.pdfapp.theme import make_icon
from src.pdfapp.viewer import PdfViewer
from src.pdfcore.annotation_items import AnnotationItem, NoTextInAreaError, bounds
from src.pdfcore.document import PdfDocument
from src.pdfcore.image_items import IMAGE_EXTENSIONS, ImageItem
from src.pdfcore.text_items import (
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_FONT_SIZE,
    TextItem,
)

APP_TITLE = "Leitor de PDF"
PDF_FILTER = "PDF (*.pdf)"
RENDER_DPI = 120
THUMB_RENDER_DPI = 36
INSERT_MODE_HINT = "Clique na página para inserir texto (Esc cancela)"
IMAGE_MODE_HINT = (
    "Arraste na página para definir a área da imagem, ou clique para o "
    "tamanho padrão (Esc cancela)"
)
ANNOTATION_MODE_HINT = "Arraste sobre o texto para anotar (Esc cancela)"
COPY_MODE = "copy"
COPY_MODE_HINT = "Arraste sobre o texto para copiar (Esc cancela)"
COPY_DONE = "Texto copiado"
ANNOTATE_ERRORS = {False: "Erro ao anotar o texto", True: "Erro ao copiar o texto"}
SAVED_IN_PLACE = "Salvo. Textos, imagens e anotações agora fazem parte do PDF"
ROTATED_PAGE_MESSAGE = (
    "Edição indisponível em páginas giradas: gire de volta para 0° para editar"
)
NO_TEXT_MESSAGE = "Nenhum texto na área selecionada"
ANNOTATION_DONE = {
    "highlight": "Texto destacado",
    "underline": "Texto sublinhado",
    "strikeout": "Texto riscado",
}
IMAGE_FILTER = "Imagens (" + " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS) + ")"
TOOLBAR_ICON_SIZE = 20
NUDGE_STEP_PT = 1.0
NUDGE_BIG_STEP_PT = 10.0
NUDGE_KEYS = {
    "Left": (-1, 0),
    "Right": (1, 0),
    "Up": (0, -1),
    "Down": (0, 1),
}


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._doc: PdfDocument | None = None
        self._path: str | None = None
        self._page_index: int = 0
        self._insert_mode: bool = False
        self._image_mode: bool = False
        self._pending_image: str | None = None
        self._thumb_error_shown: bool = False
        self._known_order: list[int] = []

        self._selected_id: int | None = None
        self._selected_image_id: int | None = None
        self._selected_annotation_id: int | None = None
        self._annotation_mode: str | None = None
        self._defaults: dict[str, object] = {
            "family": DEFAULT_FAMILY,
            "bold": False,
            "italic": False,
            "size": DEFAULT_FONT_SIZE,
            "color": DEFAULT_COLOR,
        }

        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 1000)
        self.setMinimumSize(760, 480)

        self._viewer = PdfViewer()
        self._viewer.page_clicked.connect(self._on_page_clicked)
        self._viewer.page_double_clicked.connect(self._on_page_double_clicked)
        self._viewer.rect_drawn.connect(self._on_rect_drawn)
        self._viewer.selection_moved.connect(self._on_selection_moved)
        self._viewer.selection_resized.connect(self._on_selection_resized)

        self._panel = TextPropertiesPanel()
        self._panel.property_changed.connect(self._on_property_changed)
        self._panel.edit_requested.connect(self._edit_selected_text)
        self._panel.delete_requested.connect(self._delete_selected)
        self._panel.set_values(**self._defaults)

        self._thumbs = ThumbnailPanel(self._render_thumbnail)
        self._thumbs.page_requested.connect(self._go_to_page)

        self._search_bar = SearchBar()
        self._search = SearchController(
            self._search_bar,
            self._viewer,
            lambda: self._doc,
            lambda: self._page_index,
            self._go_to_page,
            self._px_from_pt,
            self._show_error,
            self._update_escape_enabled,
        )

        reader = QWidget()
        reader_layout = QVBoxLayout(reader)
        reader_layout.setContentsMargins(0, 0, 0, 0)
        reader_layout.setSpacing(0)
        reader_layout.addWidget(self._search_bar)
        reader_layout.addWidget(self._viewer, 1)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._thumbs)
        central_layout.addWidget(reader, 1)
        central_layout.addWidget(self._panel)
        self.setCentralWidget(central)

        self._page_label = QLabel("")
        self._page_label.setObjectName("statusPill")
        self.statusBar().addPermanentWidget(self._page_label)

        self._zoom_label = QLabel("")
        self._zoom_label.setObjectName("statusPill")
        self.statusBar().addPermanentWidget(self._zoom_label)
        self._viewer.zoom_changed.connect(self._on_zoom_changed)

        self.statusBar().setSizeGripEnabled(False)

        self._create_actions()
        self._create_toolbar()
        self._update_ui()
        self._sync_selection_ui()

    @staticmethod
    def _set_tooltip(action: QAction, name: str | None = None) -> None:
        name = name or action.text().replace("&", "").rstrip(".")
        shortcut = action.shortcut().toString(
            QKeySequence.SequenceFormat.NativeText
        )
        action.setToolTip(f"{name} ({shortcut})" if shortcut else name)

    def _make_action(
        self,
        text: str,
        icon: str | None = None,
        shortcut: QKeySequence.StandardKey | str | None = None,
        slot: Callable[..., object] | None = None,
        tooltip: str | None = None,
        checkable: bool = False,
        toggled: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(make_icon(icon))
        if isinstance(shortcut, str):
            action.setShortcut(QKeySequence(shortcut))
        elif shortcut is not None:
            action.setShortcut(shortcut)
        if checkable:
            action.setCheckable(True)
        if slot is not None:
            (action.toggled if toggled else action.triggered).connect(slot)
        if icon is not None:
            self._set_tooltip(action, tooltip)
        return action

    def _make_history_action(
        self,
        text: str,
        icon: str,
        key: QKeySequence.StandardKey,
        slot: Callable[..., object],
    ) -> QAction:
        action = QAction(text, self)
        action.setIcon(make_icon(icon))
        action.setShortcuts(QKeySequence.keyBindings(key))
        action.triggered.connect(slot)
        return action

    def _make_hidden_action(
        self,
        text: str,
        shortcut: QKeySequence.StandardKey | str,
        slot: Callable[..., object],
        enabled: bool = True,
    ) -> QAction:
        action = self._make_action(text, shortcut=shortcut, slot=slot)
        action.setEnabled(enabled)
        self.addAction(action)
        return action

    def _create_actions(self) -> None:
        self._create_file_actions()
        self._create_edit_actions()
        self._create_page_actions()
        self._create_view_actions()

    def _create_file_actions(self) -> None:
        self._open_action = self._make_action(
            "Abrir", "open", QKeySequence.StandardKey.Open, self.open_pdf
        )
        self._save_action = self._make_action(
            "Salvar", "save", QKeySequence.StandardKey.Save, self.save_pdf
        )
        self._save_as_action = self._make_action(
            "Salvar Como", "save", QKeySequence.StandardKey.SaveAs, self.save_pdf_as
        )
        self._prev_action = self._make_action(
            "Anterior", "prev", "PgUp", self.previous_page
        )
        self._next_action = self._make_action(
            "Próxima", "next", "PgDn", self.next_page
        )

    def _create_edit_actions(self) -> None:
        self._undo_action = self._make_history_action(
            "Desfazer", "undo", QKeySequence.StandardKey.Undo, self.undo
        )
        self._redo_action = self._make_history_action(
            "Refazer", "redo", QKeySequence.StandardKey.Redo, self.redo
        )
        self._insert_text_action = self._make_action(
            "Inserir Texto", "text", "Ctrl+T", self._on_insert_toggled,
            checkable=True, toggled=True,
        )
        self._insert_image_action = self._make_action(
            "Inserir Imagem", "image", "Ctrl+Shift+I", self._on_insert_image_toggled,
            checkable=True, toggled=True,
        )

        self._annotation_actions: dict[str, QAction] = {}
        for kind, name, shortcut in (
            ("highlight", "Destacar", "Ctrl+Shift+H"),
            ("underline", "Sublinhar", "Ctrl+Shift+U"),
            ("strikeout", "Riscar", "Ctrl+Shift+K"),
            (COPY_MODE, "Copiar", "Ctrl+Shift+C"),
        ):
            self._annotation_actions[kind] = self._make_action(
                name,
                kind,
                shortcut,
                lambda checked, kind=kind: self._on_annotation_toggled(kind, checked),
                f"{name} texto",
                checkable=True,
                toggled=True,
            )

        self._edit_text_action = self._make_action(
            "Editar", "edit", "F2", self._edit_selected_text,
            "Editar o texto selecionado",
        )
        self._delete_action = self._make_action(
            "Apagar", "trash", QKeySequence.StandardKey.Delete, self._delete_selected,
            "Apagar o texto, a imagem ou a anotação selecionada",
        )
        self._escape_action = self._make_hidden_action(
            "Cancelar", "Escape", self._on_escape, enabled=False
        )
        self._create_nudge_actions()

    def _create_nudge_actions(self) -> None:
        self._nudge_actions: list[QAction] = []
        for prefix, step in (("", NUDGE_STEP_PT), ("Shift+", NUDGE_BIG_STEP_PT)):
            for key, (sign_x, sign_y) in NUDGE_KEYS.items():
                action = self._make_action(
                    f"Mover texto ({prefix}{key})",
                    None,
                    f"{prefix}{key}",
                    lambda checked=False, dx=sign_x * step, dy=sign_y * step: self._nudge(dx, dy),
                )
                action.setShortcutContext(
                    Qt.ShortcutContext.WidgetWithChildrenShortcut
                )
                action.setEnabled(False)
                self._viewer.addAction(action)
                self._nudge_actions.append(action)

    def _nudge(self, dx_pt: float, dy_pt: float) -> None:
        if self._current_item() is None:
            return
        self._on_selection_moved(self._px_from_pt(dx_pt), self._px_from_pt(dy_pt))

    def _create_page_actions(self) -> None:
        self._rotate_left_action = self._make_action(
            "Girar à esquerda", "rotate_left", "Ctrl+Shift+R",
            lambda: self._rotate_page(-90), "Girar a página 90° à esquerda",
        )
        self._rotate_right_action = self._make_action(
            "Girar à direita", "rotate_right", "Ctrl+R",
            lambda: self._rotate_page(90), "Girar a página 90° à direita",
        )
        self._move_page_up_action = self._make_action(
            "Mover página para cima", "up", "Ctrl+Shift+PgUp",
            lambda: self._move_page(-1), "Mover a página atual para cima",
        )
        self._move_page_down_action = self._make_action(
            "Mover página para baixo", "down", "Ctrl+Shift+PgDown",
            lambda: self._move_page(1), "Mover a página atual para baixo",
        )
        self._delete_page_action = self._make_action(
            "Apagar página", "delete_page", "Ctrl+Del", self._delete_page,
            "Apagar a página atual",
        )

    def _create_view_actions(self) -> None:
        self._zoom_in_action = self._make_action(
            "Zoom +", "zoom_in", "Ctrl+=", self._viewer.zoom_in
        )
        self._zoom_out_action = self._make_action(
            "Zoom −", "zoom_out", "Ctrl+-", self._viewer.zoom_out
        )
        self._zoom_reset_action = self._make_action(
            "100%", None, "Ctrl+0", self._viewer.reset_zoom
        )
        self._set_tooltip(self._zoom_reset_action)
        self._find_action = self._make_action(
            "Buscar", "search", QKeySequence.StandardKey.Find, self._search.open,
            "Buscar texto no documento",
        )
        self._find_next_action = self._make_hidden_action(
            "Próximo resultado", QKeySequence.StandardKey.FindNext, self._search.next
        )
        self._find_previous_action = self._make_hidden_action(
            "Resultado anterior",
            QKeySequence.StandardKey.FindPrevious,
            self._search.previous,
        )
        self._thumbs_action = self._make_action(
            "Miniaturas", "sidebar", "F4", None,
            "Mostrar ou ocultar as miniaturas", checkable=True,
        )
        self._thumbs_action.setChecked(True)
        self._thumbs_action.toggled.connect(self._apply_thumbs_visibility)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        toolbar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        toolbar.addAction(self._open_action)
        toolbar.addAction(self._save_action)
        toolbar.addAction(self._save_as_action)
        toolbar.addSeparator()
        toolbar.addAction(self._thumbs_action)
        toolbar.addAction(self._find_action)
        toolbar.addSeparator()
        toolbar.addAction(self._prev_action)
        toolbar.addAction(self._next_action)
        toolbar.addSeparator()
        toolbar.addAction(self._rotate_left_action)
        toolbar.addAction(self._rotate_right_action)
        toolbar.addAction(self._move_page_up_action)
        toolbar.addAction(self._move_page_down_action)
        toolbar.addAction(self._delete_page_action)
        toolbar.addSeparator()
        toolbar.addAction(self._undo_action)
        toolbar.addAction(self._redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self._insert_text_action)
        toolbar.addAction(self._insert_image_action)
        for action in self._annotation_actions.values():
            toolbar.addAction(action)
        toolbar.addAction(self._edit_text_action)
        toolbar.addAction(self._delete_action)

        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        toolbar.addWidget(spacer)

        toolbar.addAction(self._zoom_out_action)
        toolbar.addAction(self._zoom_reset_action)
        toolbar.addAction(self._zoom_in_action)

        for action in (
            *self._annotation_actions.values(),
            self._rotate_left_action,
            self._rotate_right_action,
            self._move_page_up_action,
            self._move_page_down_action,
            self._delete_page_action,
            self._thumbs_action,
            self._find_action,
            self._zoom_out_action,
            self._zoom_in_action,
            self._undo_action,
            self._redo_action,
        ):
            button = toolbar.widgetForAction(action)
            if isinstance(button, QToolButton):
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonIconOnly
                )

        self.addToolBar(toolbar)

    def _show_error(self, title: str, exc: BaseException) -> None:
        detail = str(exc).strip() or exc.__class__.__name__
        QMessageBox.critical(self, title, detail)

    def _close_document(self, doc: PdfDocument | None) -> None:
        if doc is None:
            return
        try:
            doc.close()
        except Exception as exc:
            self._show_error("Erro ao fechar o documento", exc)

    def _render_page(self, doc: PdfDocument, index: int) -> QPixmap:
        rendered = doc.render_page(index, dpi=RENDER_DPI)
        return rendered_to_qpixmap(rendered)

    def _render_thumbnail(self, index: int) -> QPixmap | None:
        doc = self._doc
        if doc is None or index < 0 or index >= doc.page_count:
            return None
        try:
            rendered = doc.render_page(index, dpi=THUMB_RENDER_DPI)
            pixmap = rendered_to_qpixmap(rendered)
        except Exception as exc:
            if not self._thumb_error_shown:
                self._thumb_error_shown = True
                self._show_error("Erro ao gerar miniaturas", exc)
            return None
        return pixmap.scaledToWidth(
            THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation
        )

    @staticmethod
    def _pt_from_px(value: float) -> float:
        return value * 72 / RENDER_DPI

    @staticmethod
    def _px_from_pt(value: float) -> float:
        return value * RENDER_DPI / 72

    @staticmethod
    def _is_same_path(a: str, b: str) -> bool:
        if os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b):
            return True
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
            os.path.realpath(b)
        )

    def _update_history_actions(self) -> None:
        doc = self._doc
        can_undo = doc is not None and doc.can_undo
        can_redo = doc is not None and doc.can_redo
        self._undo_action.setEnabled(can_undo)
        self._redo_action.setEnabled(can_redo)
        self._set_tooltip(
            self._undo_action,
            f"Desfazer: {doc.undo_label}" if can_undo else "Desfazer",
        )
        self._set_tooltip(
            self._redo_action,
            f"Refazer: {doc.redo_label}" if can_redo else "Refazer",
        )

    def _apply_thumbs_visibility(self, *_: object) -> None:
        self._thumbs.setVisible(
            self._doc is not None and self._thumbs_action.isChecked()
        )

    @staticmethod
    def _set_pill(label: QLabel, text: str) -> None:
        label.setText(text)
        label.setVisible(bool(text))

    def _update_ui(self) -> None:
        doc = self._doc
        has_doc = doc is not None

        self._save_action.setEnabled(has_doc)
        self._save_as_action.setEnabled(has_doc)
        self._insert_text_action.setEnabled(has_doc)
        self._insert_image_action.setEnabled(has_doc)
        self._zoom_in_action.setEnabled(has_doc)
        self._zoom_out_action.setEnabled(has_doc)
        self._zoom_reset_action.setEnabled(has_doc)
        self._panel.setEnabled(has_doc)
        self._thumbs_action.setEnabled(has_doc)
        self._find_action.setEnabled(has_doc)
        self._rotate_left_action.setEnabled(has_doc)
        self._rotate_right_action.setEnabled(has_doc)
        self._move_page_up_action.setEnabled(has_doc and self._page_index > 0)
        self._move_page_down_action.setEnabled(
            has_doc and self._page_index < doc.page_count - 1
        )
        self._delete_page_action.setEnabled(has_doc and doc.page_count > 1)
        for action in self._annotation_actions.values():
            action.setEnabled(has_doc)
        self._find_next_action.setEnabled(has_doc)
        self._find_previous_action.setEnabled(has_doc)
        self._apply_thumbs_visibility()
        self._update_history_actions()

        if doc is None:
            self._prev_action.setEnabled(False)
            self._next_action.setEnabled(False)
            self._set_pill(self._page_label, "")
            self._set_pill(self._zoom_label, "")
            self.setWindowTitle(APP_TITLE)
            return

        last_index = doc.page_count - 1
        self._prev_action.setEnabled(self._page_index > 0)
        self._next_action.setEnabled(self._page_index < last_index)
        self._set_pill(
            self._page_label,
            f"Página {self._page_index + 1} de {doc.page_count}",
        )
        self._set_pill(
            self._zoom_label, f"Zoom: {round(self._viewer.zoom * 100)}%"
        )
        name = Path(self._path).name if self._path else ""
        self.setWindowTitle(f"{name} — {APP_TITLE}" if name else APP_TITLE)

    def _page_locked(self) -> bool:
        doc = self._doc
        return doc is not None and doc.page_rotation(self._page_index) != 0

    def _clear_selection(self) -> None:
        self._selected_id = None
        self._selected_image_id = None
        self._selected_annotation_id = None

    def _sync_page_structure(self) -> None:
        doc = self._doc
        if doc is None or doc.page_order() == self._known_order:
            return
        self._known_order = doc.page_order()
        self._page_index = min(self._page_index, doc.page_count - 1)
        self._clear_selection()
        self._search.close()
        self._thumbs.set_pages(doc.page_count)

    def _rotate_page(self, degrees: int) -> None:
        doc = self._doc
        if doc is None:
            return
        index = self._page_index
        try:
            doc.rotate_page(index, degrees)
        except Exception as exc:
            self._show_error("Erro ao girar a página", exc)
            return
        self._clear_selection()
        self._thumbs.invalidate([index])
        self._search.refresh([index])
        self._go_to_page(index)
        self.statusBar().showMessage("Página girada", 3000)

    def _move_page(self, step: int) -> None:
        doc = self._doc
        if doc is None:
            return
        index = self._page_index
        new_index = index + step
        try:
            doc.move_page(index, new_index)
        except Exception as exc:
            self._show_error("Erro ao mover a página", exc)
            return
        self._sync_page_structure()
        self._go_to_page(new_index)
        self.statusBar().showMessage("Página movida", 3000)

    def _delete_page(self) -> None:
        doc = self._doc
        if doc is None:
            return
        index = self._page_index
        try:
            doc.delete_page(index)
        except Exception as exc:
            self._show_error("Erro ao apagar a página", exc)
            return
        self._sync_page_structure()
        self._go_to_page(min(index, doc.page_count - 1))
        self.statusBar().showMessage("Página apagada", 3000)

    def _current_item(self) -> TextItem | None:
        doc = self._doc
        if doc is None or self._selected_id is None:
            return None
        try:
            return doc.get_text_item(self._selected_id)
        except KeyError:
            self._selected_id = None
            return None

    def _item_at(self, x_px: float, y_px: float) -> TextItem | None:
        doc = self._doc
        if doc is None:
            return None
        try:
            return doc.find_text_item_at(
                self._page_index,
                self._pt_from_px(x_px),
                self._pt_from_px(y_px),
            )
        except Exception as exc:
            self._show_error("Erro ao localizar o texto", exc)
            return None

    def _current_image(self) -> ImageItem | None:
        doc = self._doc
        if doc is None or self._selected_image_id is None:
            return None
        try:
            return doc.get_image_item(self._selected_image_id)
        except KeyError:
            self._selected_image_id = None
            self._selected_annotation_id = None
            return None

    def _image_at(self, x_px: float, y_px: float) -> ImageItem | None:
        doc = self._doc
        if doc is None:
            return None
        try:
            return doc.find_image_at(
                self._page_index,
                self._pt_from_px(x_px),
                self._pt_from_px(y_px),
            )
        except Exception as exc:
            self._show_error("Erro ao localizar a imagem", exc)
            return None

    def _current_annotation(self) -> AnnotationItem | None:
        doc = self._doc
        if doc is None or self._selected_annotation_id is None:
            return None
        try:
            return doc.get_annotation_item(self._selected_annotation_id)
        except KeyError:
            self._selected_annotation_id = None
            return None

    def _annotation_at(self, x_px: float, y_px: float) -> AnnotationItem | None:
        doc = self._doc
        if doc is None:
            return None
        try:
            return doc.find_annotation_at(
                self._page_index,
                self._pt_from_px(x_px),
                self._pt_from_px(y_px),
            )
        except Exception as exc:
            self._show_error("Erro ao localizar a anotação", exc)
            return None

    def _set_selection(self, item_id: int | None) -> None:
        self._selected_id = item_id
        self._selected_image_id = None
        self._selected_annotation_id = None
        self._sync_selection_ui()

    def _set_image_selection(self, image_id: int | None) -> None:
        self._selected_id = None
        self._selected_image_id = image_id
        self._selected_annotation_id = None
        self._sync_selection_ui()

    def _set_annotation_selection(self, annotation_id: int | None) -> None:
        self._selected_id = None
        self._selected_image_id = None
        self._selected_annotation_id = annotation_id
        self._sync_selection_ui()

    def _sync_selection_ui(self) -> None:
        item = self._current_item()
        image = self._current_image() if item is None else None
        annotation = (
            self._current_annotation() if item is None and image is None else None
        )
        doc = self._doc

        box: tuple[float, float, float, float] | None = None
        if doc is not None and (
            item is not None or image is not None or annotation is not None
        ):
            try:
                if item is not None:
                    box = doc.item_rect(item)
                elif image is not None:
                    box = image.rect
                else:
                    box = bounds(annotation.rects)
            except Exception as exc:
                self._selected_id = None
                self._selected_image_id = None
                self._selected_annotation_id = None
                item = None
                image = None
                annotation = None
                self._show_error("Erro ao medir a seleção", exc)

        highlight: tuple[float, float, float, float] | None = None
        if box is not None:
            left, top, right, bottom = box
            highlight = (
                self._px_from_pt(left),
                self._px_from_pt(top),
                self._px_from_pt(right - left),
                self._px_from_pt(bottom - top),
            )

        self._viewer.set_selection(
            highlight,
            movable=item is not None or image is not None,
            resizable=image is not None,
        )

        if item is None:
            self._panel.set_values(**self._defaults)
        else:
            self._panel.set_values(
                item.family, item.bold, item.italic, item.size, item.color
            )
        self._panel.set_has_selection(item is not None)

        self._edit_text_action.setEnabled(item is not None)
        for action in self._nudge_actions:
            action.setEnabled(item is not None)
        self._delete_action.setEnabled(
            item is not None or image is not None or annotation is not None
        )
        self._update_escape_enabled()

    def _has_selection(self) -> bool:
        return (
            self._selected_id is not None
            or self._selected_image_id is not None
            or self._selected_annotation_id is not None
        )

    def _update_escape_enabled(self) -> None:
        self._escape_action.setEnabled(
            self._insert_mode
            or self._image_mode
            or self._annotation_mode is not None
            or self._has_selection()
            or self._search.active
        )

    def _on_escape(self) -> None:
        if self._image_mode:
            self._set_image_mode(False)
        elif self._insert_mode:
            self._exit_insert_mode()
        elif self._annotation_mode is not None:
            self._set_annotation_mode(None)
        elif self._search.active and (
            self._search.has_focus() or not self._has_selection()
        ):
            self._search.close()
        elif self._has_selection():
            self._set_selection(None)

    def _on_property_changed(self, key: str, value: object) -> None:
        self._defaults[key] = value

        item = self._current_item()
        doc = self._doc
        if item is None or doc is None:
            return
        try:
            doc.update_text(item.id, **{key: value})
        except Exception as exc:
            self._show_error("Erro ao atualizar o texto", exc)
            self._sync_selection_ui()
            return
        self._go_to_page(self._page_index)

    def _edit_selected_text(self) -> None:
        item = self._current_item()
        doc = self._doc
        if item is None or doc is None:
            return
        try:
            text, ok = QInputDialog.getText(
                self, "Editar Texto", "Texto:", text=item.text
            )
            if not ok or not text.strip() or text == item.text:
                return
            doc.update_text(item.id, text=text)
        except Exception as exc:
            self._show_error("Erro ao editar o texto", exc)
            return
        self._go_to_page(self._page_index)

    def _delete_selected(self) -> None:
        doc = self._doc
        if doc is None:
            return
        item = self._current_item()
        image = self._current_image() if item is None else None
        annotation = (
            self._current_annotation() if item is None and image is None else None
        )
        if item is None and image is None and annotation is None:
            return

        try:
            if item is not None:
                doc.remove_text(item.id)
                message = "Texto apagado"
            elif image is not None:
                doc.remove_image(image.id)
                message = "Imagem apagada"
            else:
                doc.remove_annotation(annotation.id)
                message = "Anotação apagada"
        except Exception as exc:
            self._show_error("Erro ao apagar", exc)
            return
        self._selected_id = None
        self._selected_image_id = None
        self._selected_annotation_id = None
        self._go_to_page(self._page_index)
        self.statusBar().showMessage(message, 3000)

    def _set_insert_mode(self, active: bool) -> None:
        if active and self._doc is None:
            active = False

        if active and self._image_mode:
            self._set_image_mode(False)
        if active and self._annotation_mode is not None:
            self._set_annotation_mode(None)

        self._insert_mode = active

        if self._insert_text_action.isChecked() != active:
            self._insert_text_action.blockSignals(True)
            self._insert_text_action.setChecked(active)
            self._insert_text_action.blockSignals(False)

        if active:
            self._selected_id = None
            self._selected_image_id = None
            self._selected_annotation_id = None
            self._sync_selection_ui()
            self._viewer.setCursor(Qt.CursorShape.CrossCursor)
            self.statusBar().showMessage(INSERT_MODE_HINT)
        elif not self._image_mode and self._annotation_mode is None:
            self._viewer.unsetCursor()
            self.statusBar().clearMessage()
        self._update_escape_enabled()

    def _on_insert_toggled(self, checked: bool) -> None:
        self._set_insert_mode(checked)

    def _enter_insert_mode(self) -> None:
        self._set_insert_mode(True)

    def _exit_insert_mode(self) -> None:
        self._set_insert_mode(False)

    def _on_insert_image_toggled(self, checked: bool) -> None:
        if checked:
            self._begin_image_mode()
        else:
            self._set_image_mode(False)

    def _begin_image_mode(self) -> None:
        if self._doc is None:
            self._set_image_mode(False)
            return

        start_dir = str(Path(self._path).parent) if self._path else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem", start_dir, IMAGE_FILTER
        )
        if not path:
            self._set_image_mode(False)
            return

        self._pending_image = path
        self._set_image_mode(True)

    def _set_image_mode(self, active: bool) -> None:
        if active and (self._doc is None or self._pending_image is None):
            active = False

        if active and self._insert_mode:
            self._set_insert_mode(False)
        if active and self._annotation_mode is not None:
            self._set_annotation_mode(None)

        self._image_mode = active
        if not active:
            self._pending_image = None

        if self._insert_image_action.isChecked() != active:
            self._insert_image_action.blockSignals(True)
            self._insert_image_action.setChecked(active)
            self._insert_image_action.blockSignals(False)

        self._viewer.set_rect_mode(active or self._annotation_mode is not None)

        if active:
            self._selected_id = None
            self._selected_image_id = None
            self._selected_annotation_id = None
            self._sync_selection_ui()
            self._viewer.setCursor(Qt.CursorShape.CrossCursor)
            self.statusBar().showMessage(IMAGE_MODE_HINT)
        elif not self._insert_mode and self._annotation_mode is None:
            self._viewer.unsetCursor()
            self.statusBar().clearMessage()
        self._update_escape_enabled()

    def _on_annotation_toggled(self, kind: str, checked: bool) -> None:
        self._set_annotation_mode(kind if checked else None)

    def _set_annotation_mode(self, kind: str | None) -> None:
        if kind is not None and self._doc is None:
            kind = None

        if kind is not None:
            if self._insert_mode:
                self._set_insert_mode(False)
            if self._image_mode:
                self._set_image_mode(False)

        self._annotation_mode = kind

        for name, action in self._annotation_actions.items():
            wanted = name == kind
            if action.isChecked() != wanted:
                action.blockSignals(True)
                action.setChecked(wanted)
                action.blockSignals(False)

        self._viewer.set_rect_mode(kind is not None or self._image_mode)

        if kind is not None:
            self._selected_id = None
            self._selected_image_id = None
            self._selected_annotation_id = None
            self._sync_selection_ui()
            self._viewer.setCursor(Qt.CursorShape.CrossCursor)
            self.statusBar().showMessage(
                COPY_MODE_HINT if kind == COPY_MODE else ANNOTATION_MODE_HINT
            )
        elif not self._insert_mode and not self._image_mode:
            self._viewer.unsetCursor()
            self.statusBar().clearMessage()
        self._update_escape_enabled()

    def _annotate(self, x0: float, y0: float, x1: float, y1: float) -> None:
        doc = self._doc
        kind = self._annotation_mode
        if doc is None or kind is None:
            return
        area = (
            self._pt_from_px(x0),
            self._pt_from_px(y0),
            self._pt_from_px(x1),
            self._pt_from_px(y1),
        )
        try:
            if kind == COPY_MODE:
                QApplication.clipboard().setText(
                    doc.extract_text(self._page_index, area)
                )
            else:
                doc.add_annotation(self._page_index, kind, area)
        except NoTextInAreaError:
            self.statusBar().showMessage(NO_TEXT_MESSAGE, 3000)
            return
        except Exception as exc:
            self._show_error(ANNOTATE_ERRORS[kind == COPY_MODE], exc)
            return
        if kind == COPY_MODE:
            self.statusBar().showMessage(COPY_DONE, 3000)
            return
        self._go_to_page(self._page_index)
        self.statusBar().showMessage(ANNOTATION_DONE[kind], 3000)

    def _on_selection_moved(self, dx_px: float, dy_px: float) -> None:
        doc = self._doc
        if doc is None:
            return
        item = self._current_item()
        image = self._current_image() if item is None else None
        if item is None and image is None:
            return

        dx, dy = self._pt_from_px(dx_px), self._pt_from_px(dy_px)
        try:
            if item is not None:
                doc.update_text(item.id, x=item.x + dx, y=item.y + dy)
            else:
                left, top, right, bottom = image.rect
                doc.update_image(
                    image.id, (left + dx, top + dy, right + dx, bottom + dy)
                )
        except Exception as exc:
            self._show_error(
                "Erro ao mover o texto" if item is not None else "Erro ao mover a imagem",
                exc,
            )
            self._sync_selection_ui()
            return
        self._go_to_page(self._page_index)
        self.statusBar().showMessage(
            "Texto movido" if item is not None else "Imagem movida", 3000
        )

    def _on_selection_resized(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> None:
        doc = self._doc
        image = self._current_image()
        if doc is None or image is None:
            return
        try:
            doc.update_image(
                image.id,
                (
                    self._pt_from_px(x0),
                    self._pt_from_px(y0),
                    self._pt_from_px(x1),
                    self._pt_from_px(y1),
                ),
            )
        except Exception as exc:
            self._show_error("Erro ao redimensionar a imagem", exc)
            self._sync_selection_ui()
            return
        self._go_to_page(self._page_index)
        self.statusBar().showMessage("Imagem redimensionada", 3000)

    def _on_rect_drawn(self, x0: float, y0: float, x1: float, y1: float) -> None:
        if self._doc is not None and self._page_locked():
            self.statusBar().showMessage(ROTATED_PAGE_MESSAGE, 4000)
            return
        if self._annotation_mode is not None:
            self._annotate(x0, y0, x1, y1)
            return

        doc = self._doc
        path = self._pending_image
        if doc is None or path is None or not self._image_mode:
            self._set_image_mode(False)
            return

        image: ImageItem | None = None
        try:
            if x1 <= x0 and y1 <= y0:
                rect = doc.default_image_rect(
                    self._page_index,
                    self._pt_from_px(x0),
                    self._pt_from_px(y0),
                    path,
                )
            else:
                rect = (
                    self._pt_from_px(x0),
                    self._pt_from_px(y0),
                    self._pt_from_px(x1),
                    self._pt_from_px(y1),
                )
            image = doc.add_image(self._page_index, rect, path)
        except Exception as exc:
            self._show_error("Erro ao inserir a imagem", exc)
        finally:
            self._set_image_mode(False)

        if image is None:
            return

        self._selected_id = None
        self._selected_image_id = image.id
        self._selected_annotation_id = None
        self._go_to_page(self._page_index)

    def _on_page_clicked(self, x: float, y: float) -> None:
        doc = self._doc
        if doc is None:
            self._exit_insert_mode()
            return

        if self._page_locked():
            self.statusBar().showMessage(ROTATED_PAGE_MESSAGE, 4000)
            return

        if not self._insert_mode:
            item = self._item_at(x, y)
            if item is not None:
                self._set_selection(item.id)
                return
            image = self._image_at(x, y)
            if image is not None:
                self._set_image_selection(image.id)
                return
            annotation = self._annotation_at(x, y)
            if annotation is not None:
                self._set_annotation_selection(annotation.id)
            else:
                self._set_selection(None)
            return

        try:
            text, ok = QInputDialog.getText(
                self, "Inserir Texto", "Texto a inserir:"
            )
            if not ok or not text.strip():
                return

            item = doc.add_text(
                self._page_index,
                self._pt_from_px(x),
                self._pt_from_px(y),
                text,
                size=float(self._defaults["size"]),
                color=self._defaults["color"],
                family=str(self._defaults["family"]),
                bold=bool(self._defaults["bold"]),
                italic=bool(self._defaults["italic"]),
            )
        except Exception as exc:
            self._show_error("Erro ao inserir texto", exc)
            return
        finally:
            self._exit_insert_mode()

        self._selected_id = item.id
        self._go_to_page(self._page_index)

    def _on_page_double_clicked(self, x: float, y: float) -> None:
        if self._insert_mode or self._image_mode or self._doc is None:
            return
        if self._page_locked():
            return
        item = self._item_at(x, y)
        if item is None:
            return
        self._set_selection(item.id)
        self._edit_selected_text()

    def open_pdf(self) -> None:
        start_dir = str(Path(self._path).parent) if self._path else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir PDF", start_dir, PDF_FILTER
        )
        if not path or not self._confirm_discard():
            return

        new_doc = self._load_document(path)
        if new_doc is not None:
            self._install_document(new_doc, path)

    def _load_document(self, path: str, page_index: int = 0) -> PdfDocument | None:
        new_doc: PdfDocument | None = None
        try:
            new_doc = PdfDocument(path)
            if new_doc.page_count < 1:
                raise ValueError("O PDF não possui nenhuma página.")
            index = min(page_index, new_doc.page_count - 1)
            self._viewer.show_pixmap(self._render_page(new_doc, index))
        except Exception as exc:
            self._close_document(new_doc)
            self._show_error("Erro ao abrir o PDF", exc)
            return None
        return new_doc

    def _install_document(
        self, new_doc: PdfDocument, path: str, page_index: int = 0
    ) -> None:
        index = min(page_index, new_doc.page_count - 1)
        old_doc = self._doc
        self._doc = new_doc
        self._path = path
        self._page_index = index
        self._selected_id = None
        self._selected_image_id = None
        self._selected_annotation_id = None
        self._exit_insert_mode()
        self._set_image_mode(False)
        self._set_annotation_mode(None)
        self._close_document(old_doc)
        self._search.close()
        self._thumb_error_shown = False
        self._known_order = new_doc.page_order()
        self._thumbs.set_pages(new_doc.page_count)
        self._thumbs.set_current(index)
        self._update_ui()
        self._sync_selection_ui()

    def save_pdf(self) -> bool:
        doc = self._doc
        path = self._path
        if doc is None or path is None:
            return False

        target = Path(path)
        temp = target.with_name(f".{target.stem}.salvando.pdf")
        page_index = self._page_index
        try:
            doc.save(temp)
        except Exception as exc:
            with contextlib.suppress(OSError):
                temp.unlink(missing_ok=True)
            self._show_error("Erro ao salvar o PDF", exc)
            return False

        self._doc = None
        self._close_document(doc)
        try:
            os.replace(temp, target)
        except Exception as exc:
            source = str(temp) if temp.exists() else path
            recovered = self._load_document(source, page_index)
            if recovered is not None:
                self._install_document(recovered, path, page_index)
            self._show_error("Erro ao salvar o PDF", exc)
            return False

        new_doc = self._load_document(path, page_index)
        if new_doc is None:
            self._update_ui()
            self._sync_selection_ui()
            return True
        self._install_document(new_doc, path, page_index)
        self.statusBar().showMessage(SAVED_IN_PLACE, 5000)
        return True

    def _go_to_page(self, index: int) -> None:
        doc = self._doc
        if doc is None:
            return
        if index < 0 or index >= doc.page_count:
            return
        try:
            pixmap = self._render_page(doc, index)
            self._viewer.show_pixmap(pixmap)
            if index != self._page_index:
                self._selected_id = None
                self._selected_image_id = None
                self._selected_annotation_id = None
            else:
                self._thumbs.invalidate([index])
                self._search.refresh([index])
            self._page_index = index
            if self._page_locked():
                self._clear_selection()
            self._search.apply_highlights()
        except Exception as exc:
            self._show_error("Erro ao renderizar a página", exc)
        self._thumbs.set_current(self._page_index)
        self._update_ui()
        self._sync_selection_ui()

    def undo(self) -> None:
        doc = self._doc
        if doc is None or not doc.can_undo:
            return
        self._run_history(doc.undo, f"Desfeito: {doc.undo_label}", "Erro ao desfazer")

    def redo(self) -> None:
        doc = self._doc
        if doc is None or not doc.can_redo:
            return
        self._run_history(doc.redo, f"Refeito: {doc.redo_label}", "Erro ao refazer")

    def _run_history(
        self, operation: Callable[[], list[int]], message: str, error_title: str
    ) -> None:
        self._exit_insert_mode()
        self._set_image_mode(False)
        try:
            pages = operation()
        except Exception as exc:
            self._show_error(error_title, exc)
            self._go_to_page(self._page_index)
            return

        self._sync_page_structure()
        target = self._page_index
        if pages and target not in pages:
            target = pages[0]
        self._thumbs.invalidate(pages)
        self._search.refresh(pages)
        self._go_to_page(target)
        self.statusBar().showMessage(message, 3000)

    def previous_page(self) -> None:
        self._go_to_page(self._page_index - 1)

    def next_page(self) -> None:
        self._go_to_page(self._page_index + 1)

    def _on_zoom_changed(self, zoom: float) -> None:
        self._set_pill(self._zoom_label, f"Zoom: {round(zoom * 100)}%")

    def save_pdf_as(self) -> bool:
        doc = self._doc
        original = self._path
        if doc is None or original is None:
            return False

        original_path = Path(original)
        suggested = str(original_path.with_name(f"{original_path.stem}_editado.pdf"))

        try:
            target, _ = QFileDialog.getSaveFileName(
                self, "Salvar Como", suggested, PDF_FILTER
            )
            if not target:
                return False

            if not Path(target).suffix:
                target += ".pdf"

            if self._is_same_path(original, target):
                QMessageBox.warning(
                    self,
                    "Não é possível sobrescrever",
                    "O PyMuPDF não consegue sobrescrever o arquivo que está "
                    "aberto. Escolha um nome ou uma pasta diferente para "
                    "salvar a cópia.",
                )
                return False

            doc.save(target)
            self.statusBar().showMessage(f"Salvo em: {target}", 5000)
            return True
        except Exception as exc:
            self._show_error("Erro ao salvar o PDF", exc)
            return False

    def _confirm_discard(self) -> bool:
        doc = self._doc
        if doc is None or not doc.modified:
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self,
            "Alterações não salvas",
            "O documento tem alterações que ainda não foram salvas. "
            "Deseja salvar antes de continuar?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Save:
            return self.save_pdf()
        return answer == buttons.Discard

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        doc = self._doc
        self._doc = None
        self._path = None
        self._close_document(doc)
        event.accept()
