from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path

import pymupdf

from src.pdfcore.annotation_items import (
    KIND_COLORS,
    KIND_LABELS,
    KINDS,
    AnnotationItem,
    NoTextInAreaError,
    contains_point,
    text_in_area,
    words_in_area,
)
from src.pdfcore.geometry import Rect
from src.pdfcore.image_items import (
    ImageItem,
    default_rect,
    fit_rect,
    normalize_rect,
)
from src.pdfcore.search import MAX_SEARCH_HITS, SearchHit, SearchResults
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
    channels: int


__all__ = [
    "RenderedPage",
    "PdfDocument",
    "TextItem",
    "ImageItem",
    "SearchHit",
    "SearchResults",
    "AnnotationItem",
    "NoTextInAreaError",
]

_EDITABLE_FIELDS = frozenset(
    {"text", "family", "bold", "italic", "size", "color", "x", "y"}
)

MAX_HISTORY = 100


@dataclass(frozen=True)
class _PageSpec:
    source: int
    rotation: int = 0


@dataclass(frozen=True)
class _State:
    items: dict[int, TextItem]
    images: dict[int, ImageItem]
    annotations: dict[int, AnnotationItem]
    pages: tuple[_PageSpec, ...]


@dataclass(frozen=True)
class _Entry:
    label: str
    before: _State
    after: _State


class PdfDocument:
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
        self._images: dict[int, ImageItem] = {}
        self._next_image_id = 1
        self._image_data: dict[int, bytes] = {}
        self._annotations: dict[int, AnnotationItem] = {}
        self._next_annotation_id = 1
        self._fonts: dict[str, pymupdf.Font] = {}
        self._undo_stack: list[_Entry] = []
        self._redo_stack: list[_Entry] = []
        self._saved_top: object | None = None
        self._pages: tuple[_PageSpec, ...] = tuple(
            _PageSpec(index) for index in range(self._doc.page_count)
        )

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
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return RenderedPage(
            samples=pix.samples,
            width=pix.width,
            height=pix.height,
            stride=pix.stride,
            channels=pix.n,
        )

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
        self._check_page(page_index)
        before = self._snapshot()
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

        self._rebuild_page(page_index, self.text_items(page_index) + [item])

        self._items[item.id] = item
        self._next_item_id += 1
        self._record("Inserir texto", before)
        return item

    def update_text(self, item_id: int, **changes: object) -> TextItem:
        unknown = set(changes) - _EDITABLE_FIELDS
        if unknown:
            raise ValueError(f"Campos não editáveis: {', '.join(sorted(unknown))}.")

        old = self.get_text_item(item_id)
        new = self._validated(replace(old, **changes))
        before = self._snapshot()

        items = [
            new if it.id == item_id else it
            for it in self.text_items(old.page_index)
        ]
        self._rebuild_page(old.page_index, items)

        self._items[item_id] = new
        if new != old:
            if set(changes) == {"text"}:
                label = "Editar texto"
            elif set(changes) <= {"x", "y"}:
                label = "Mover texto"
            else:
                label = "Alterar formatação"
            self._record(label, before)
        return new

    def remove_text(self, item_id: int) -> None:
        old = self.get_text_item(item_id)
        before = self._snapshot()
        items = [it for it in self.text_items(old.page_index) if it.id != item_id]
        self._rebuild_page(old.page_index, items)

        del self._items[item_id]
        self._record("Apagar texto", before)

    def get_text_item(self, item_id: int) -> TextItem:
        try:
            return self._items[item_id]
        except KeyError:
            raise KeyError(f"Texto inexistente: {item_id}") from None

    def text_items(self, page_index: int) -> list[TextItem]:
        return [
            it
            for it in sorted(self._items.values(), key=lambda it: it.id)
            if it.page_index == page_index
        ]

    def item_rect(self, item: TextItem | int) -> Rect:
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
        for item in reversed(self.text_items(page_index)):
            left, top, right, bottom = self.item_rect(item)
            if (
                left - tolerance <= x <= right + tolerance
                and top - tolerance <= y <= bottom + tolerance
            ):
                return item
        return None

    def add_image(
        self,
        page_index: int,
        rect: Rect,
        image_path: str | Path,
    ) -> ImageItem:
        self._check_page(page_index)
        data, image_w, image_h = self._read_image(image_path)
        before = self._snapshot()
        item = ImageItem(
            id=self._next_image_id,
            page_index=page_index,
            rect=fit_rect(normalize_rect(rect), image_w, image_h),
            path=Path(image_path),
        )

        self._image_data[item.id] = data
        try:
            self._rebuild_page(
                page_index, images=self.image_items(page_index) + [item]
            )
        except Exception:
            del self._image_data[item.id]
            raise

        self._images[item.id] = item
        self._next_image_id += 1
        self._record("Inserir imagem", before)
        return item

    def default_image_rect(
        self,
        page_index: int,
        x: float,
        y: float,
        image_path: str | Path,
    ) -> Rect:
        self._check_page(page_index)
        _, image_w, image_h = self._read_image(image_path)
        page_rect = self._doc.load_page(page_index).rect
        return default_rect(
            x, y, image_w, image_h, page_rect.width, page_rect.height
        )

    def remove_image(self, image_id: int) -> None:
        old = self.get_image_item(image_id)
        before = self._snapshot()
        images = [
            im for im in self.image_items(old.page_index) if im.id != image_id
        ]
        self._rebuild_page(old.page_index, images=images)

        del self._images[image_id]
        self._record("Apagar imagem", before)

    def update_image(self, image_id: int, rect: Rect) -> ImageItem:
        old = self.get_image_item(image_id)
        new = replace(old, rect=normalize_rect(rect))
        if new == old:
            return old

        before = self._snapshot()
        images = [
            new if im.id == image_id else im
            for im in self.image_items(old.page_index)
        ]
        self._rebuild_page(old.page_index, images=images)

        self._images[image_id] = new
        old_w, old_h = old.rect[2] - old.rect[0], old.rect[3] - old.rect[1]
        new_w, new_h = new.rect[2] - new.rect[0], new.rect[3] - new.rect[1]
        same_size = abs(new_w - old_w) < 1e-6 and abs(new_h - old_h) < 1e-6
        self._record("Mover imagem" if same_size else "Redimensionar imagem", before)
        return new

    def add_annotation(
        self, page_index: int, kind: str, area: Rect
    ) -> AnnotationItem:
        self._check_page(page_index)
        if kind not in KINDS:
            raise ValueError(f"Tipo de anotação inválido: {kind}")

        words = self._doc.load_page(page_index).get_text("words")
        rects = words_in_area(words, area)
        if not rects:
            raise NoTextInAreaError("Nenhum texto na área selecionada.")

        item = AnnotationItem(
            id=self._next_annotation_id,
            page_index=page_index,
            kind=kind,
            rects=tuple(rects),
        )
        before = self._snapshot()
        self._rebuild_page(
            page_index, annotations=self.annotation_items(page_index) + [item]
        )

        self._annotations[item.id] = item
        self._next_annotation_id += 1
        self._record(KIND_LABELS[kind], before)
        return item

    def extract_text(self, page_index: int, area: Rect) -> str:
        self._check_page(page_index)
        words = self._doc.load_page(page_index).get_text("words")
        text = text_in_area(words, area)
        if not text:
            raise NoTextInAreaError("Nenhum texto na área selecionada.")
        return text

    def page_rotation(self, page_index: int) -> int:
        self._check_page(page_index)
        return self._doc.load_page(page_index).rotation % 360

    def rotate_page(self, page_index: int, degrees: int) -> None:
        self._check_page(page_index)
        if degrees % 90 != 0 or degrees % 360 == 0:
            raise ValueError("A rotação deve ser um múltiplo de 90° diferente de 360°.")
        before = self._snapshot()
        spec = self._pages[page_index]
        page = self._doc.load_page(page_index)
        page.set_rotation((page.rotation + degrees) % 360)
        self._pages = (
            self._pages[:page_index]
            + (replace(spec, rotation=(spec.rotation + degrees) % 360),)
            + self._pages[page_index + 1 :]
        )
        self._record("Girar página", before)

    def delete_page(self, page_index: int) -> None:
        self._check_page(page_index)
        if self.page_count == 1:
            raise ValueError("Não é possível apagar a única página do documento.")
        before = self._snapshot()
        target = _State(
            self._without_page(self._items, page_index),
            self._without_page(self._images, page_index),
            self._without_page(self._annotations, page_index),
            self._pages[:page_index] + self._pages[page_index + 1 :],
        )
        self._rebuild_document(target)
        self._commit(target)
        self._record("Apagar página", before)

    def page_order(self) -> list[int]:
        return [spec.source for spec in self._pages]

    def move_page(self, page_index: int, new_index: int) -> None:
        self._check_page(page_index)
        self._check_page(new_index)
        if page_index == new_index:
            return
        before = self._snapshot()
        pages = list(self._pages)
        pages.insert(new_index, pages.pop(page_index))

        def remap(index: int) -> int:
            if index == page_index:
                return new_index
            if page_index < index <= new_index:
                return index - 1
            if new_index <= index < page_index:
                return index + 1
            return index

        target = _State(
            self._remapped(self._items, remap),
            self._remapped(self._images, remap),
            self._remapped(self._annotations, remap),
            tuple(pages),
        )
        self._rebuild_document(target)
        self._commit(target)
        self._record("Mover página", before)

    @staticmethod
    def _remapped(registry: dict, remap: Callable[[int], int]) -> dict:
        return {
            key: replace(value, page_index=remap(value.page_index))
            for key, value in registry.items()
        }

    @staticmethod
    def _without_page(registry: dict, page_index: int) -> dict:
        return {
            key: (
                replace(value, page_index=value.page_index - 1)
                if value.page_index > page_index
                else value
            )
            for key, value in registry.items()
            if value.page_index != page_index
        }

    def _commit(self, target: _State) -> None:
        self._items = dict(target.items)
        self._images = dict(target.images)
        self._annotations = dict(target.annotations)
        self._pages = target.pages

    def _rebuild_document(self, target: _State) -> None:
        old = self._doc
        new = pymupdf.open()
        self._doc = new
        try:
            for index, spec in enumerate(target.pages):
                self._draw_page(
                    index,
                    sorted(
                        (it for it in target.items.values() if it.page_index == index),
                        key=lambda it: it.id,
                    ),
                    sorted(
                        (im for im in target.images.values() if im.page_index == index),
                        key=lambda im: im.id,
                    ),
                    sorted(
                        (
                            an
                            for an in target.annotations.values()
                            if an.page_index == index
                        ),
                        key=lambda an: an.id,
                    ),
                    spec,
                    replace_existing=False,
                )
        except Exception:
            self._doc = old
            new.close()
            raise
        old.close()

    def remove_annotation(self, annotation_id: int) -> None:
        old = self.get_annotation_item(annotation_id)
        before = self._snapshot()
        remaining = [
            an
            for an in self.annotation_items(old.page_index)
            if an.id != annotation_id
        ]
        self._rebuild_page(old.page_index, annotations=remaining)

        del self._annotations[annotation_id]
        self._record("Apagar anotação", before)

    def get_annotation_item(self, annotation_id: int) -> AnnotationItem:
        try:
            return self._annotations[annotation_id]
        except KeyError:
            raise KeyError(f"Anotação inexistente: {annotation_id}") from None

    def annotation_items(self, page_index: int) -> list[AnnotationItem]:
        return [
            an
            for an in sorted(self._annotations.values(), key=lambda an: an.id)
            if an.page_index == page_index
        ]

    def find_annotation_at(
        self, page_index: int, x: float, y: float, tolerance: float = 2.0
    ) -> AnnotationItem | None:
        for annotation in reversed(self.annotation_items(page_index)):
            if contains_point(annotation.rects, x, y, tolerance):
                return annotation
        return None

    def search(
        self,
        query: str,
        pages: Iterable[int] | None = None,
        limit: int = MAX_SEARCH_HITS,
    ) -> SearchResults:
        if limit < 1:
            raise ValueError("O limite de resultados deve ser pelo menos 1.")
        if pages is None:
            indices = list(range(self.page_count))
        else:
            indices = sorted(set(pages))
            for index in indices:
                self._check_page(index)
        if not query.strip():
            return SearchResults()

        hits: list[SearchHit] = []
        for index in indices:
            page = self._doc.load_page(index)
            for rect in page.search_for(query):
                if len(hits) == limit:
                    return SearchResults(hits, truncated=True)
                hits.append(
                    SearchHit(
                        index,
                        (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])),
                    )
                )
        return SearchResults(hits)

    def get_image_item(self, image_id: int) -> ImageItem:
        try:
            return self._images[image_id]
        except KeyError:
            raise KeyError(f"Imagem inexistente: {image_id}") from None

    def image_items(self, page_index: int) -> list[ImageItem]:
        return [
            im
            for im in sorted(self._images.values(), key=lambda im: im.id)
            if im.page_index == page_index
        ]

    def find_image_at(
        self, page_index: int, x: float, y: float, tolerance: float = 2.0
    ) -> ImageItem | None:
        for image in reversed(self.image_items(page_index)):
            left, top, right, bottom = image.rect
            if (
                left - tolerance <= x <= right + tolerance
                and top - tolerance <= y <= bottom + tolerance
            ):
                return image
        return None

    @property
    def modified(self) -> bool:
        top = self._undo_stack[-1] if self._undo_stack else None
        return top is not self._saved_top

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def undo_label(self) -> str | None:
        return self._undo_stack[-1].label if self._undo_stack else None

    @property
    def redo_label(self) -> str | None:
        return self._redo_stack[-1].label if self._redo_stack else None

    def undo(self) -> list[int]:
        if not self._undo_stack:
            raise ValueError("Não há nada para desfazer.")
        entry = self._undo_stack[-1]
        pages = self._apply_state(entry.before)
        self._undo_stack.pop()
        self._redo_stack.append(entry)
        return pages

    def redo(self) -> list[int]:
        if not self._redo_stack:
            raise ValueError("Não há nada para refazer.")
        entry = self._redo_stack[-1]
        pages = self._apply_state(entry.after)
        self._redo_stack.pop()
        self._undo_stack.append(entry)
        return pages

    def save(self, target: str | Path) -> None:
        target = Path(target)
        if target.resolve() == self.path.resolve():
            raise ValueError(
                "Salve em outro caminho; o PyMuPDF não sobrescreve o arquivo aberto."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        self._doc.save(target, garbage=3, deflate=True)
        self._saved_top = self._undo_stack[-1] if self._undo_stack else None

    def close(self) -> None:
        try:
            self._base.close()
        finally:
            self._doc.close()

    def _check_page(self, page_index: int) -> None:
        if not (0 <= page_index < self.page_count):
            raise IndexError(page_index)

    def _snapshot(self) -> _State:
        return _State(
            dict(self._items),
            dict(self._images),
            dict(self._annotations),
            self._pages,
        )

    def _record(self, label: str, before: _State) -> None:
        self._undo_stack.append(_Entry(label, before, self._snapshot()))
        if len(self._undo_stack) > MAX_HISTORY:
            if self._saved_top is None:
                self._saved_top = object()
            del self._undo_stack[:-MAX_HISTORY]
        self._redo_stack.clear()

    def _differing_pages(self, target: _State) -> list[int]:
        pages: set[int] = set()
        for current, wanted in (
            (self._items, target.items),
            (self._images, target.images),
            (self._annotations, target.annotations),
        ):
            for key in current.keys() | wanted.keys():
                old, new = current.get(key), wanted.get(key)
                if old != new:
                    pages.update(i.page_index for i in (old, new) if i is not None)
        return sorted(pages)

    def _apply_state(self, target: _State) -> list[int]:
        if [spec.source for spec in target.pages] != [
            spec.source for spec in self._pages
        ]:
            self._rebuild_document(target)
            self._commit(target)
            return list(range(len(target.pages)))

        pages = sorted(
            set(self._differing_pages(target))
            | {
                index
                for index, (old, new) in enumerate(zip(self._pages, target.pages))
                if old != new
            }
        )
        done: list[int] = []
        try:
            for page_index in pages:
                items = sorted(
                    (it for it in target.items.values() if it.page_index == page_index),
                    key=lambda it: it.id,
                )
                images = sorted(
                    (im for im in target.images.values() if im.page_index == page_index),
                    key=lambda im: im.id,
                )
                annotations = sorted(
                    (
                        an
                        for an in target.annotations.values()
                        if an.page_index == page_index
                    ),
                    key=lambda an: an.id,
                )
                self._rebuild_page(
                    page_index, items, images, annotations, target.pages[page_index]
                )
                done.append(page_index)
        except Exception:
            for page_index in done:
                try:
                    self._rebuild_page(page_index)
                except Exception:
                    pass
            raise
        self._commit(target)
        return pages

    @staticmethod
    def _read_image(image_path: str | Path) -> tuple[bytes, int, int]:
        path = Path(image_path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"Não foi possível abrir a imagem: {path}") from exc
        try:
            pixmap = pymupdf.Pixmap(data)
            return data, pixmap.width, pixmap.height
        except Exception as exc:
            raise ValueError(
                f"O arquivo não é uma imagem válida: {path.name}"
            ) from exc

    def _font(self, code: str) -> pymupdf.Font:
        font = self._fonts.get(code)
        if font is None:
            font = pymupdf.Font(code)
            self._fonts[code] = font
        return font

    @staticmethod
    def _validated(item: TextItem) -> TextItem:
        if not item.text.strip():
            raise ValueError("O texto não pode ser vazio.")
        if not (MIN_FONT_SIZE <= item.size <= MAX_FONT_SIZE):
            raise ValueError(
                f"O tamanho deve estar entre {MIN_FONT_SIZE:g} e {MAX_FONT_SIZE:g} pt."
            )
        font_code(item.family, item.bold, item.italic)
        return replace(item, color=normalize_color(item.color))

    def _draw_text(self, page: pymupdf.Page, item: TextItem) -> None:
        font = self._font(item.font_code)
        baseline_y = item.y + font.ascender * item.size
        page.insert_text(
            pymupdf.Point(item.x, baseline_y),
            item.text,
            fontsize=item.size,
            fontname=item.font_code,
            color=item.color,
        )

    def _rebuild_page(
        self,
        page_index: int,
        items: list[TextItem] | None = None,
        images: list[ImageItem] | None = None,
        annotations: list[AnnotationItem] | None = None,
        spec: _PageSpec | None = None,
    ) -> None:
        if items is None:
            items = self.text_items(page_index)
        if images is None:
            images = self.image_items(page_index)
        if annotations is None:
            annotations = self.annotation_items(page_index)

        try:
            self._draw_page(page_index, items, images, annotations, spec)
        except Exception:
            try:
                self._draw_page(
                    page_index,
                    self.text_items(page_index),
                    self.image_items(page_index),
                    self.annotation_items(page_index),
                )
            except Exception:
                pass
            raise

    @staticmethod
    def _draw_annotation(page: pymupdf.Page, annotation: AnnotationItem) -> None:
        add = {
            "highlight": page.add_highlight_annot,
            "underline": page.add_underline_annot,
            "strikeout": page.add_strikeout_annot,
        }[annotation.kind]
        annot = add(quads=[pymupdf.Rect(*rect) for rect in annotation.rects])
        annot.set_colors(stroke=KIND_COLORS[annotation.kind])
        annot.update()

    def _draw_page(
        self,
        page_index: int,
        items: list[TextItem],
        images: list[ImageItem],
        annotations: list[AnnotationItem],
        spec: _PageSpec | None = None,
        replace_existing: bool = True,
    ) -> None:
        spec = spec or self._pages[page_index]
        if replace_existing:
            self._doc.insert_pdf(
                self._base,
                from_page=spec.source,
                to_page=spec.source,
                start_at=page_index,
            )
            self._doc.delete_page(page_index + 1)
        else:
            self._doc.insert_pdf(
                self._base, from_page=spec.source, to_page=spec.source
            )

        page = self._doc.load_page(page_index)
        for image in images:
            page.insert_image(
                pymupdf.Rect(*image.rect),
                stream=self._image_data[image.id],
                keep_proportion=False,
            )
        for item in items:
            self._draw_text(page, item)
        for annotation in annotations:
            self._draw_annotation(page, annotation)
        if spec.rotation:
            page.set_rotation((page.rotation + spec.rotation) % 360)
