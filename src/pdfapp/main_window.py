import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from src.pdfapp.qt_image import rendered_to_qpixmap
from src.pdfapp.text_panel import TextPropertiesPanel
from src.pdfapp.theme import make_icon
from src.pdfapp.viewer import PdfViewer
from src.pdfcore.document import PdfDocument
from src.pdfcore.text_items import (
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_FONT_SIZE,
    TextItem,
)

APP_TITLE = "Leitor de PDF"
PDF_FILTER = "PDF (*.pdf)"
RENDER_DPI = 120
INSERT_MODE_HINT = "Clique na página para inserir texto (Esc cancela)"
TOOLBAR_ICON_SIZE = 20


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._doc: PdfDocument | None = None
        self._path: str | None = None
        self._page_index: int = 0
        self._insert_mode: bool = False

        # Texto selecionado na página atual (id do TextItem) e a aparência
        # usada nos próximos textos inseridos.
        self._selected_id: int | None = None
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

        self._panel = TextPropertiesPanel()
        self._panel.property_changed.connect(self._on_property_changed)
        self._panel.edit_requested.connect(self._edit_selected_text)
        self._panel.delete_requested.connect(self._delete_selected_text)
        self._panel.set_values(**self._defaults)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._viewer, 1)
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
        # Sem documento, Editar/Apagar começam desabilitados.
        self._sync_selection_ui()

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    @staticmethod
    def _set_tooltip(action: QAction, name: str | None = None) -> None:
        """Tooltip no formato 'Nome (atalho)'."""
        name = name or action.text().replace("&", "").rstrip(".")
        shortcut = action.shortcut().toString(
            QKeySequence.SequenceFormat.NativeText
        )
        action.setToolTip(f"{name} ({shortcut})" if shortcut else name)

    def _create_actions(self) -> None:
        self._open_action = QAction("Abrir", self)
        self._open_action.setIcon(make_icon("open"))
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.triggered.connect(self.open_pdf)
        self._set_tooltip(self._open_action)

        self._save_as_action = QAction("Salvar Como", self)
        self._save_as_action.setIcon(make_icon("save"))
        self._save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._save_as_action.triggered.connect(self.save_pdf_as)
        self._set_tooltip(self._save_as_action)

        self._prev_action = QAction("Anterior", self)
        self._prev_action.setIcon(make_icon("prev"))
        self._prev_action.setShortcut(QKeySequence("PgUp"))
        self._prev_action.triggered.connect(self.previous_page)
        self._set_tooltip(self._prev_action)

        self._next_action = QAction("Próxima", self)
        self._next_action.setIcon(make_icon("next"))
        self._next_action.setShortcut(QKeySequence("PgDn"))
        self._next_action.triggered.connect(self.next_page)
        self._set_tooltip(self._next_action)

        # Marcável: o botão fica "afundado" enquanto o modo de inserção
        # estiver ativo. Usa toggled (e não triggered) para o estado visual
        # e o modo nunca ficarem fora de sincronia.
        self._insert_text_action = QAction("Inserir Texto", self)
        self._insert_text_action.setIcon(make_icon("text"))
        self._insert_text_action.setShortcut(QKeySequence("Ctrl+T"))
        self._insert_text_action.setCheckable(True)
        self._insert_text_action.toggled.connect(self._on_insert_toggled)
        self._set_tooltip(self._insert_text_action)

        # Só habilitadas quando há um texto selecionado.
        self._edit_text_action = QAction("Editar", self)
        self._edit_text_action.setIcon(make_icon("edit"))
        self._edit_text_action.setShortcut(QKeySequence("F2"))
        self._edit_text_action.triggered.connect(self._edit_selected_text)
        self._set_tooltip(self._edit_text_action, "Editar o texto selecionado")

        self._delete_action = QAction("Apagar", self)
        self._delete_action.setIcon(make_icon("trash"))
        self._delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self._delete_action.triggered.connect(self._delete_selected_text)
        self._set_tooltip(self._delete_action, "Apagar o texto selecionado")

        # Esc cancela o modo de inserção ou, se não houver, tira a seleção.
        self._escape_action = QAction("Cancelar", self)
        self._escape_action.setShortcut(QKeySequence("Escape"))
        self._escape_action.setEnabled(False)
        self._escape_action.triggered.connect(self._on_escape)
        self.addAction(self._escape_action)

        self._zoom_in_action = QAction("Zoom +", self)
        self._zoom_in_action.setIcon(make_icon("zoom_in"))
        self._zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        self._zoom_in_action.triggered.connect(self._viewer.zoom_in)
        self._set_tooltip(self._zoom_in_action)

        self._zoom_out_action = QAction("Zoom −", self)
        self._zoom_out_action.setIcon(make_icon("zoom_out"))
        self._zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self._zoom_out_action.triggered.connect(self._viewer.zoom_out)
        self._set_tooltip(self._zoom_out_action)

        self._zoom_reset_action = QAction("100%", self)
        self._zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
        self._zoom_reset_action.triggered.connect(self._viewer.reset_zoom)
        self._set_tooltip(self._zoom_reset_action)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Principal", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        toolbar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        # Grupo: arquivo
        toolbar.addAction(self._open_action)
        toolbar.addAction(self._save_as_action)
        toolbar.addSeparator()
        # Grupo: navegação
        toolbar.addAction(self._prev_action)
        toolbar.addAction(self._next_action)
        toolbar.addSeparator()
        # Grupo: edição
        toolbar.addAction(self._insert_text_action)
        toolbar.addAction(self._edit_text_action)
        toolbar.addAction(self._delete_action)

        # Empurra o grupo de zoom para a direita.
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        toolbar.addWidget(spacer)

        # Grupo: zoom
        toolbar.addAction(self._zoom_out_action)
        toolbar.addAction(self._zoom_reset_action)
        toolbar.addAction(self._zoom_in_action)

        # Os botões de zoom mostram só o ícone; o resto mostra ícone + texto.
        for action in (self._zoom_out_action, self._zoom_in_action):
            button = toolbar.widgetForAction(action)
            if isinstance(button, QToolButton):
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonIconOnly
                )

        self.addToolBar(toolbar)

    # ------------------------------------------------------------------
    # Utilitários internos
    # ------------------------------------------------------------------
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
        # O DPI passado aqui precisa ser o mesmo usado na conversão
        # pixel <-> ponto (_pt_from_px e _px_from_pt).
        rendered = doc.render_page(index, dpi=RENDER_DPI)
        return rendered_to_qpixmap(rendered)

    @staticmethod
    def _pt_from_px(value: float) -> float:
        """Pixels do pixmap -> pontos do PDF (1 pt = 1/72 polegada)."""
        return value * 72 / RENDER_DPI

    @staticmethod
    def _px_from_pt(value: float) -> float:
        """Pontos do PDF -> pixels do pixmap."""
        return value * RENDER_DPI / 72

    @staticmethod
    def _is_same_path(a: str, b: str) -> bool:
        if os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b):
            return True
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
            os.path.realpath(b)
        )

    @staticmethod
    def _set_pill(label: QLabel, text: str) -> None:
        """Atualiza um rótulo da barra de status e o esconde se vazio."""
        label.setText(text)
        label.setVisible(bool(text))

    def _update_ui(self) -> None:
        doc = self._doc
        has_doc = doc is not None

        self._save_as_action.setEnabled(has_doc)
        self._insert_text_action.setEnabled(has_doc)
        self._zoom_in_action.setEnabled(has_doc)
        self._zoom_out_action.setEnabled(has_doc)
        self._zoom_reset_action.setEnabled(has_doc)
        self._panel.setEnabled(has_doc)

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

    # ------------------------------------------------------------------
    # Seleção de texto
    # ------------------------------------------------------------------
    def _current_item(self) -> TextItem | None:
        """Texto selecionado, ou None (e limpa a seleção se ele sumiu)."""
        doc = self._doc
        if doc is None or self._selected_id is None:
            return None
        try:
            return doc.get_text_item(self._selected_id)
        except KeyError:
            self._selected_id = None
            return None

    def _item_at(self, x_px: float, y_px: float) -> TextItem | None:
        """Texto inserido sob um ponto da página (em pixels do pixmap)."""
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

    def _set_selection(self, item_id: int | None) -> None:
        self._selected_id = item_id
        self._sync_selection_ui()

    def _sync_selection_ui(self) -> None:
        """Atualiza destaque, painel e ações conforme a seleção atual."""
        item = self._current_item()
        doc = self._doc

        highlight: tuple[float, float, float, float] | None = None
        if item is not None and doc is not None:
            try:
                left, top, right, bottom = doc.item_rect(item)
                highlight = (
                    self._px_from_pt(left),
                    self._px_from_pt(top),
                    self._px_from_pt(right - left),
                    self._px_from_pt(bottom - top),
                )
            except Exception as exc:
                self._selected_id = None
                item = None
                self._show_error("Erro ao medir o texto", exc)

        self._viewer.set_selection(highlight)
        if item is None:
            self._panel.set_values(**self._defaults)
        else:
            self._panel.set_values(
                item.family, item.bold, item.italic, item.size, item.color
            )
        self._panel.set_has_selection(item is not None)

        has_selection = item is not None
        self._edit_text_action.setEnabled(has_selection)
        self._delete_action.setEnabled(has_selection)
        self._update_escape_enabled()

    def _update_escape_enabled(self) -> None:
        self._escape_action.setEnabled(
            self._insert_mode or self._selected_id is not None
        )

    def _on_escape(self) -> None:
        if self._insert_mode:
            self._exit_insert_mode()
        elif self._selected_id is not None:
            self._set_selection(None)

    def _on_property_changed(self, key: str, value: object) -> None:
        """Painel mudou: vale para o texto selecionado e para os próximos."""
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

    def _delete_selected_text(self) -> None:
        item = self._current_item()
        doc = self._doc
        if item is None or doc is None:
            return
        try:
            doc.remove_text(item.id)
        except Exception as exc:
            self._show_error("Erro ao apagar o texto", exc)
            return
        self._selected_id = None
        self._go_to_page(self._page_index)
        self.statusBar().showMessage("Texto apagado", 3000)

    # ------------------------------------------------------------------
    # Modo de inserção de texto
    # ------------------------------------------------------------------
    def _set_insert_mode(self, active: bool) -> None:
        """Ponto único de entrada/saída do modo de inserção."""
        if active and self._doc is None:
            active = False

        self._insert_mode = active

        # Mantém o botão marcado em sincronia sem disparar toggled de novo.
        if self._insert_text_action.isChecked() != active:
            self._insert_text_action.blockSignals(True)
            self._insert_text_action.setChecked(active)
            self._insert_text_action.blockSignals(False)

        if active:
            # O painel passa a mostrar a aparência do próximo texto.
            self._selected_id = None
            self._sync_selection_ui()
            self._viewer.setCursor(Qt.CursorShape.CrossCursor)
            self.statusBar().showMessage(INSERT_MODE_HINT)
        else:
            self._viewer.unsetCursor()
            self.statusBar().clearMessage()
        self._update_escape_enabled()

    def _on_insert_toggled(self, checked: bool) -> None:
        self._set_insert_mode(checked)

    def _enter_insert_mode(self) -> None:
        self._set_insert_mode(True)

    def _exit_insert_mode(self) -> None:
        self._set_insert_mode(False)

    def _on_page_clicked(self, x: float, y: float) -> None:
        doc = self._doc
        if doc is None:
            self._exit_insert_mode()
            return

        # Fora do modo de inserção, o clique seleciona (ou desmarca) um texto.
        if not self._insert_mode:
            item = self._item_at(x, y)
            self._set_selection(item.id if item is not None else None)
            return

        try:
            text, ok = QInputDialog.getText(
                self, "Inserir Texto", "Texto a inserir:"
            )
            if not ok or not text.strip():
                return

            # O ponto clicado vira o canto superior esquerdo do texto.
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

        # Só chega aqui se a inserção foi bem-sucedida: o novo texto já fica
        # selecionado, e o painel mostra as propriedades dele.
        self._selected_id = item.id
        self._go_to_page(self._page_index)

    def _on_page_double_clicked(self, x: float, y: float) -> None:
        if self._insert_mode or self._doc is None:
            return
        item = self._item_at(x, y)
        if item is None:
            return
        self._set_selection(item.id)
        self._edit_selected_text()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def open_pdf(self) -> None:
        start_dir = str(Path(self._path).parent) if self._path else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir PDF", start_dir, PDF_FILTER
        )
        if not path:
            return

        new_doc: PdfDocument | None = None
        try:
            new_doc = PdfDocument(path)
            if new_doc.page_count < 1:
                raise ValueError("O PDF não possui nenhuma página.")
            pixmap = self._render_page(new_doc, 0)
            self._viewer.show_pixmap(pixmap)
        except Exception as exc:
            self._close_document(new_doc)
            self._show_error("Erro ao abrir o PDF", exc)
            return

        # O novo documento foi aberto com sucesso: agora fecha o anterior.
        old_doc = self._doc
        self._doc = new_doc
        self._path = path
        self._page_index = 0
        self._selected_id = None
        self._exit_insert_mode()
        self._close_document(old_doc)
        self._update_ui()
        self._sync_selection_ui()

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
                # Os textos pertencem a uma página: trocar de página
                # desfaz a seleção.
                self._selected_id = None
            self._page_index = index
        except Exception as exc:
            self._show_error("Erro ao renderizar a página", exc)
        self._update_ui()
        self._sync_selection_ui()

    def previous_page(self) -> None:
        self._go_to_page(self._page_index - 1)

    def next_page(self) -> None:
        self._go_to_page(self._page_index + 1)

    def _on_zoom_changed(self, zoom: float) -> None:
        self._set_pill(self._zoom_label, f"Zoom: {round(zoom * 100)}%")

    def save_pdf_as(self) -> None:
        doc = self._doc
        original = self._path
        if doc is None or original is None:
            return

        original_path = Path(original)
        suggested = str(original_path.with_name(f"{original_path.stem}_editado.pdf"))

        try:
            target, _ = QFileDialog.getSaveFileName(
                self, "Salvar Como", suggested, PDF_FILTER
            )
            if not target:
                return

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
                return

            doc.save(target)
            self.statusBar().showMessage(f"Salvo em: {target}", 5000)
        except Exception as exc:
            self._show_error("Erro ao salvar o PDF", exc)

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        doc = self._doc
        self._doc = None
        self._path = None
        self._close_document(doc)
        event.accept()