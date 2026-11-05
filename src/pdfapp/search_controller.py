from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from src.pdfcore.geometry import Rect
from src.pdfcore.search import SearchState

if TYPE_CHECKING:
    from src.pdfapp.search_bar import SearchBar
    from src.pdfapp.viewer import PdfViewer
    from src.pdfcore.document import PdfDocument


class SearchController:
    def __init__(
        self,
        bar: SearchBar,
        viewer: PdfViewer,
        get_document: Callable[[], PdfDocument | None],
        get_page: Callable[[], int],
        go_to_page: Callable[[int], None],
        px_from_pt: Callable[[float], float],
        show_error: Callable[[str, BaseException], None],
        on_active_changed: Callable[[], None],
    ) -> None:
        self._bar = bar
        self._viewer = viewer
        self._get_document = get_document
        self._get_page = get_page
        self._go_to_page = go_to_page
        self._px_from_pt = px_from_pt
        self._show_error = show_error
        self._on_active_changed = on_active_changed

        self.state = SearchState()
        self._active = False

        bar.query_changed.connect(self._on_query_changed)
        bar.next_requested.connect(self.next)
        bar.previous_requested.connect(self.previous)
        bar.closed.connect(self._on_closed)

    @property
    def active(self) -> bool:
        return self._active

    def has_focus(self) -> bool:
        return self._bar.has_focus()

    def open(self) -> None:
        if self._get_document() is None:
            return
        self._active = True
        self._bar.open_bar()
        self._on_active_changed()

    def close(self) -> None:
        self._bar.close_bar()

    def next(self) -> None:
        self._step(self.state.next)

    def previous(self) -> None:
        self._step(self.state.previous)

    def apply_highlights(self) -> None:
        page = self._get_page()
        doc = self._get_document()
        rotated = doc is not None and doc.page_rotation(page) != 0
        rects = (
            []
            if rotated
            else [self._px_rect(hit.rect) for hit in self.state.hits_on_page(page)]
        )
        self._viewer.set_search_highlights(rects, self.state.current_on_page(page))

    def refresh(self, pages: list[int]) -> None:
        doc = self._get_document()
        if doc is None or not self.state.query:
            return
        try:
            results = doc.search(self.state.query, pages=pages)
        except Exception as exc:
            self._show_error("Erro ao buscar", exc)
            return
        self.state.replace_pages(pages, results.hits)
        self._update_status()

    def _step(self, step: Callable[[], object]) -> None:
        if self._get_document() is None:
            return
        if not self._active:
            self.open()
            return
        if step() is not None:
            self._show_current_hit()

    def _on_query_changed(self, text: str) -> None:
        doc = self._get_document()
        if doc is None:
            return
        if not text.strip():
            self._clear_results()
            return
        try:
            results = doc.search(text)
        except Exception as exc:
            self._clear_results()
            self._show_error("Erro ao buscar", exc)
            return
        self.state.set_results(
            text,
            results.hits,
            start_page=self._get_page(),
            truncated=results.truncated,
        )
        self._show_current_hit()

    def _on_closed(self) -> None:
        self.state.clear()
        self._active = False
        self.apply_highlights()
        self._on_active_changed()

    def _clear_results(self) -> None:
        self.state.clear()
        self.apply_highlights()
        self._update_status()

    def _show_current_hit(self) -> None:
        hit = self.state.current_hit
        if hit is not None and hit.page_index != self._get_page():
            self._go_to_page(hit.page_index)
        else:
            self.apply_highlights()
        self._update_status()
        if hit is not None:
            self._viewer.scroll_to_rect(self._px_rect(hit.rect))

    def _update_status(self) -> None:
        self._bar.set_status(
            self.state.current_index, self.state.count, self.state.truncated
        )

    def _px_rect(self, rect: Rect) -> Rect:
        left, top, right, bottom = rect
        return (
            self._px_from_pt(left),
            self._px_from_pt(top),
            self._px_from_pt(right),
            self._px_from_pt(bottom),
        )
