import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QWidget,
)

from src.pdfapp.qt_image import rendered_to_qpixmap
from src.pdfapp.viewer import PdfViewer
from src.pdfcore.document import PdfDocument

APP_TITLE = "Leitor de PDF"
PDF_FILTER = "PDF (*.pdf)"
RENDER_DPI = 120
INSERT_MODE_HINT = "Clique na página para inserir texto (Esc cancela)"


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._doc: PdfDocument | None = None
        self._path: str | None = None
        self._page_index: int = 0
        self._insert_mode: bool = False

        self.setWindowTitle(APP_TITLE)
        self.resize(900, 1000)

        self._viewer = PdfViewer()
        self._viewer.page_clicked.connect(self._on_page_clicked)
        self.setCentralWidget(self._viewer)

        self._page_label = QLabel("")
        self.statusBar().addPermanentWidget(self._page_label)

        self._create_actions()
        self._create_toolbar()
        self._update_ui()

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    def _create_actions(self) -> None:
        self._open_action = QAction("Abrir...", self)
        self._open_action.setShortcut(QKeySequence.StandardKey.Open)
        self._open_action.triggered.connect(self.open_pdf)

        self._save_as_action = QAction("Salvar Como...", self)
        self._save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._save_as_action.triggered.connect(self.save_pdf_as)

        self._prev_action = QAction("Anterior", self)
        self._prev_action.setShortcut(QKeySequence("PgUp"))
        self._prev_action.triggered.connect(self.previous_page)

        self._next_action = QAction("Próxima", self)
        self._next_action.setShortcut(QKeySequence("PgDn"))
        self._next_action.triggered.connect(self.next_page)

        self._insert_text_action = QAction("Inserir Texto", self)
        self._insert_text_action.setShortcut(QKeySequence("Ctrl+T"))
        self._insert_text_action.triggered.connect(self._enter_insert_mode)

        # Esc só fica habilitado enquanto o modo de inserção estiver ativo.
        self._cancel_insert_action = QAction("Cancelar inserção", self)
        self._cancel_insert_action.setShortcut(QKeySequence("Escape"))
        self._cancel_insert_action.setEnabled(False)
        self._cancel_insert_action.triggered.connect(self._exit_insert_mode)
        self.addAction(self._cancel_insert_action)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Principal", self)
        toolbar.setMovable(False)
        toolbar.addAction(self._open_action)
        toolbar.addAction(self._save_as_action)
        toolbar.addSeparator()
        toolbar.addAction(self._prev_action)
        toolbar.addAction(self._next_action)
        toolbar.addSeparator()
        toolbar.addAction(self._insert_text_action)
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
        # pixel -> ponto em _on_page_clicked.
        rendered = doc.render_page(index, dpi=RENDER_DPI)
        return rendered_to_qpixmap(rendered)

    @staticmethod
    def _is_same_path(a: str, b: str) -> bool:
        if os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b):
            return True
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
            os.path.realpath(b)
        )

    def _update_ui(self) -> None:
        doc = self._doc
        has_doc = doc is not None

        self._save_as_action.setEnabled(has_doc)
        self._insert_text_action.setEnabled(has_doc)

        if doc is None:
            self._prev_action.setEnabled(False)
            self._next_action.setEnabled(False)
            self._page_label.setText("")
            self.setWindowTitle(APP_TITLE)
            return

        last_index = doc.page_count - 1
        self._prev_action.setEnabled(self._page_index > 0)
        self._next_action.setEnabled(self._page_index < last_index)
        self._page_label.setText(
            f"Página {self._page_index + 1} de {doc.page_count}"
        )
        name = Path(self._path).name if self._path else ""
        self.setWindowTitle(f"{name} — {APP_TITLE}" if name else APP_TITLE)

    # ------------------------------------------------------------------
    # Modo de inserção de texto
    # ------------------------------------------------------------------
    def _enter_insert_mode(self) -> None:
        if self._doc is None:
            return
        self._insert_mode = True
        self._viewer.setCursor(Qt.CursorShape.CrossCursor)
        self._cancel_insert_action.setEnabled(True)
        self.statusBar().showMessage(INSERT_MODE_HINT)

    def _exit_insert_mode(self) -> None:
        self._insert_mode = False
        self._viewer.unsetCursor()
        self._cancel_insert_action.setEnabled(False)
        self.statusBar().clearMessage()

    def _on_page_clicked(self, x: float, y: float) -> None:
        if not self._insert_mode:
            return

        doc = self._doc
        if doc is None:
            self._exit_insert_mode()
            return

        try:
            text, ok = QInputDialog.getText(
                self, "Inserir Texto", "Texto a inserir:"
            )
            if not ok or not text.strip():
                return

            # Pixels do pixmap -> pontos do PDF (1 pt = 1/72 polegada).
            pt_x = x * 72 / RENDER_DPI
            pt_y = y * 72 / RENDER_DPI

            doc.insert_text(self._page_index, pt_x, pt_y, text)
        except Exception as exc:
            self._show_error("Erro ao inserir texto", exc)
            return
        finally:
            self._exit_insert_mode()

        # Só chega aqui se a inserção foi bem-sucedida.
        self._go_to_page(self._page_index)

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
        self._exit_insert_mode()
        self._close_document(old_doc)
        self._update_ui()

    def _go_to_page(self, index: int) -> None:
        doc = self._doc
        if doc is None:
            return
        if index < 0 or index >= doc.page_count:
            return
        try:
            pixmap = self._render_page(doc, index)
            self._viewer.show_pixmap(pixmap)
            self._page_index = index
        except Exception as exc:
            self._show_error("Erro ao renderizar a página", exc)
        self._update_ui()

    def previous_page(self) -> None:
        self._go_to_page(self._page_index - 1)

    def next_page(self) -> None:
        self._go_to_page(self._page_index + 1)

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