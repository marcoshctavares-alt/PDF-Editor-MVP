from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pymupdf

from src.pdfcore.text_items import (
    DEFAULT_COLOR,
    DEFAULT_FAMILY,
    DEFAULT_FONT_SIZE,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    TextItem,
    font_code,
    normalize_color,
)


@dataclass(frozen=True)
class RenderedPage:
    samples: bytes
    width: int
    height: int
    stride: int
    channels: int  # 3 = RGB, 4 = RGBA


__all__ = ["RenderedPage", "PdfDocument", "TextItem"]

# Campos de um TextItem que update_text aceita alterar.
_EDITABLE_FIELDS = frozenset(
    {"text", "family", "bold", "italic", "size", "color", "x", "y"}
)


class PdfDocument:
    """PDF aberto para leitura e edição.

    `_doc` é o documento de trabalho (o que é renderizado e salvo). `_base` é
    uma segunda abertura do mesmo arquivo, nunca modificada. Textos e imagens
    inseridos ficam registrados em listas; para apagar ou editar um texto, a
    página é restaurada a partir de `_base` e tudo o que sobrou é redesenhado.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._doc = pymupdf.open(self.path)
        if not self._doc.is_pdf:
            self._doc.close()
            raise ValueError(f"Não é um PDF: {path}")
        try:
            self._base = pymupdf.open(self.path)
        except Exception:
            self._doc.close()
            raise

        self._items: dict[int, TextItem] = {}
        self._next_item_id = 1
        # Imagens inseridas por página: [(rect, caminho), ...]
        self._images: dict[int, list[tuple[tuple[float, float, float, float], Path]]] = {}
        self._fonts: dict[str, pymupdf.Font] = {}

    def __enter__(self) -> "PdfDocument":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.close()
        return False

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def render_page(self, index: int, dpi: int = 120) -> RenderedPage:
        if not (0 <= index < self.page_count):
            raise IndexError(index)
        page = self._doc.load_page(index)
        pix = page.get_pixmap(dpi=dpi, alpha=False)  # força RGB
        return RenderedPage(
            samples=pix.samples,
            width=pix.width,
            height=pix.height,
            stride=pix.stride,
            channels=pix.n,
        )

    # ------------------------------------------------------------------
    # Textos inseridos (editáveis)
    # ------------------------------------------------------------------
    def add_text(
        self,
        page_index: int,
        x: float,
        y: float,
        text: str,
        size: float = DEFAULT_FONT_SIZE,
        color: tuple[float, float, float] = DEFAULT_COLOR,
        family: str = DEFAULT_FAMILY,
        bold: bool = False,
        italic: bool = False,
    ) -> TextItem:
        """Insere um texto e devolve o item criado.

        (x, y) é o canto superior esquerdo da caixa do texto, em pontos.
        """
        self._check_page(page_index)
        item = self._validated(
            TextItem(
                id=self._next_item_id,
                page_index=page_index,
                x=float(x),
                y=float(y),
                text=text,
                family=family,
                bold=bold,
                italic=italic,
                size=float(size),
                color=color,
            )
        )

        # Redesenha antes de registrar: se falhar, nada fica pela metade.
        self._rebuild_page(page_index, self.text_items(page_index) + [item])

        self._items[item.id] = item
        self._next_item_id += 1
        return item

    def update_text(self, item_id: int, **changes: object) -> TextItem:
        """Altera campos de um texto já inserido (texto, fonte, tamanho, cor...)."""
        unknown = set(changes) - _EDITABLE_FIELDS
        if unknown:
            raise ValueError(f"Campos não editáveis: {', '.join(sorted(unknown))}.")

        old = self.get_text_item(item_id)
        new = self._validated(replace(old, **changes))

        items = [
            new if it.id == item_id else it
            for it in self.text_items(old.page_index)
        ]
        self._rebuild_page(old.page_index, items)

        self._items[item_id] = new
        return new

    def remove_text(self, item_id: int) -> None:
        """Apaga um texto inserido (somente os que foram inseridos aqui)."""
        old = self.get_text_item(item_id)
        items = [it for it in self.text_items(old.page_index) if it.id != item_id]
        self._rebuild_page(old.page_index, items)

        del self._items[item_id]

    def get_text_item(self, item_id: int) -> TextItem:
        try:
            return self._items[item_id]
        except KeyError:
            raise KeyError(f"Texto inexistente: {item_id}") from None

    def text_items(self, page_index: int) -> list[TextItem]:
        """Textos inseridos na página, do mais antigo para o mais recente."""
        return [
            it
            for it in sorted(self._items.values(), key=lambda it: it.id)
            if it.page_index == page_index
        ]

    def item_rect(
        self, item: TextItem | int
    ) -> tuple[float, float, float, float]:
        """Caixa do texto (esquerda, topo, direita, base), em pontos."""
        if isinstance(item, int):
            item = self.get_text_item(item)
        font = self._font(item.font_code)
        lines = item.text.split("\n")
        width = max(font.text_length(line, fontsize=item.size) for line in lines)
        line_height = (font.ascender - font.descender) * item.size
        return (
            item.x,
            item.y,
            item.x + width,
            item.y + line_height * len(lines),
        )

    def find_text_item_at(
        self, page_index: int, x: float, y: float, tolerance: float = 2.0
    ) -> TextItem | None:
        """Texto inserido sob o ponto (x, y) em pontos; o mais recente vence."""
        for item in reversed(self.text_items(page_index)):
            left, top, right, bottom = self.item_rect(item)
            if (
                left - tolerance <= x <= right + tolerance
                and top - tolerance <= y <= bottom + tolerance
            ):
                return item
        return None

    def insert_text(
        self,
        page_index: int,
        x: float,
        y: float,
        text: str,
        size: float = 12.0,
        color: tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        """Compatibilidade: (x, y) é o ponto da linha de base do texto."""
        ascender = self._font(font_code(DEFAULT_FAMILY)).ascender
        self.add_text(page_index, x, y - ascender * size, text, size=size, color=color)

    # ------------------------------------------------------------------
    # Imagens
    # ------------------------------------------------------------------
    def insert_image(
        self,
        page_index: int,
        rect: tuple[float, float, float, float],
        image_path: str | Path,
    ) -> None:
        page = self._doc.load_page(page_index)
        page.insert_image(pymupdf.Rect(*rect), filename=str(image_path))
        # Registra a imagem para que ela sobreviva ao redesenho da página.
        self._images.setdefault(page_index, []).append(
            (tuple(rect), Path(image_path))
        )

    # ------------------------------------------------------------------
    # Salvar e fechar
    # ------------------------------------------------------------------
    def save(self, target: str | Path) -> None:
        target = Path(target)
        if target.resolve() == self.path.resolve():
            raise ValueError(
                "Salve em outro caminho; o PyMuPDF não sobrescreve o arquivo aberto."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        self._doc.save(target, garbage=3, deflate=True)

    def close(self) -> None:
        try:
            self._base.close()
        finally:
            self._doc.close()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _check_page(self, page_index: int) -> None:
        if not (0 <= page_index < self.page_count):
            raise IndexError(page_index)

    def _font(self, code: str) -> pymupdf.Font:
        font = self._fonts.get(code)
        if font is None:
            font = pymupdf.Font(code)
            self._fonts[code] = font
        return font

    @staticmethod
    def _validated(item: TextItem) -> TextItem:
        """Valida os campos e devolve o item com a cor normalizada."""
        if not item.text.strip():
            raise ValueError("O texto não pode ser vazio.")
        if not (MIN_FONT_SIZE <= item.size <= MAX_FONT_SIZE):
            raise ValueError(
                f"O tamanho deve estar entre {MIN_FONT_SIZE:g} e {MAX_FONT_SIZE:g} pt."
            )
        font_code(item.family, item.bold, item.italic)  # ValueError se inválida
        return replace(item, color=normalize_color(item.color))

    def _draw_text(self, page: pymupdf.Page, item: TextItem) -> None:
        font = self._font(item.font_code)
        # O PyMuPDF posiciona o texto pela linha de base; o item guarda o topo.
        baseline_y = item.y + font.ascender * item.size
        page.insert_text(
            pymupdf.Point(item.x, baseline_y),
            item.text,
            fontsize=item.size,
            fontname=item.font_code,
            color=item.color,
        )

    def _rebuild_page(self, page_index: int, items: list[TextItem]) -> None:
        """Restaura a página a partir do original e redesenha imagens e textos."""
        # Insere uma cópia limpa da página original na mesma posição e remove
        # a versão antiga (que passou a ocupar o índice seguinte).
        self._doc.insert_pdf(
            self._base,
            from_page=page_index,
            to_page=page_index,
            start_at=page_index,
        )
        self._doc.delete_page(page_index + 1)

        page = self._doc.load_page(page_index)
        for rect, image_path in self._images.get(page_index, []):
            page.insert_image(pymupdf.Rect(*rect), filename=str(image_path))
        for item in items:
            self._draw_text(page, item)