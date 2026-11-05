from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from src.pdfcore.geometry import Rect

MAX_SEARCH_HITS = 5000


@dataclass(frozen=True)
class SearchHit:
    page_index: int
    rect: Rect


@dataclass(frozen=True)
class SearchResults:
    hits: list[SearchHit] = field(default_factory=list)
    truncated: bool = False


class SearchState:
    def __init__(self) -> None:
        self._query = ""
        self._hits: list[SearchHit] = []
        self._current: int | None = None
        self._truncated = False

    @property
    def query(self) -> str:
        return self._query

    @property
    def count(self) -> int:
        return len(self._hits)

    @property
    def truncated(self) -> bool:
        return self._truncated

    @property
    def current_index(self) -> int | None:
        return self._current

    @property
    def current_hit(self) -> SearchHit | None:
        if self._current is None:
            return None
        return self._hits[self._current]

    def clear(self) -> None:
        self._query = ""
        self._hits = []
        self._current = None
        self._truncated = False

    def set_results(
        self,
        query: str,
        hits: Iterable[SearchHit],
        start_page: int = 0,
        truncated: bool = False,
    ) -> None:
        self._query = query
        self._hits = list(hits)
        self._truncated = truncated
        self._current = self._first_from(start_page)

    def next(self) -> SearchHit | None:
        if self._current is None:
            return None
        self._current = (self._current + 1) % len(self._hits)
        return self._hits[self._current]

    def previous(self) -> SearchHit | None:
        if self._current is None:
            return None
        self._current = (self._current - 1) % len(self._hits)
        return self._hits[self._current]

    def hits_on_page(self, page_index: int) -> list[SearchHit]:
        return [hit for hit in self._hits if hit.page_index == page_index]

    def current_on_page(self, page_index: int) -> int | None:
        if self._current is None:
            return None
        current = self._hits[self._current]
        if current.page_index != page_index:
            return None
        return self._current - self._first_index_on_page(page_index)

    def replace_pages(
        self, pages: Iterable[int], new_hits: Iterable[SearchHit]
    ) -> None:
        refreshed = set(pages)
        previous = self.current_hit
        previous_page = 0 if previous is None else previous.page_index

        kept = [hit for hit in self._hits if hit.page_index not in refreshed]
        merged = sorted(kept + list(new_hits), key=lambda hit: hit.page_index)
        self._hits = merged

        if previous is not None and previous.page_index not in refreshed:
            self._current = merged.index(previous)
        else:
            self._current = self._first_from(previous_page)

    def _first_from(self, page_index: int) -> int | None:
        if not self._hits:
            return None
        for index, hit in enumerate(self._hits):
            if hit.page_index >= page_index:
                return index
        return 0

    def _first_index_on_page(self, page_index: int) -> int:
        for index, hit in enumerate(self._hits):
            if hit.page_index == page_index:
                return index
        return 0
