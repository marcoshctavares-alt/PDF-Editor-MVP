from __future__ import annotations

from collections.abc import Iterable


class ThumbnailQueue:
    def __init__(self, margin: int = 3) -> None:
        self.margin = margin
        self._count = 0
        self._rendered: set[int] = set()

    @property
    def count(self) -> int:
        return self._count

    def reset(self, count: int) -> None:
        self._count = max(0, count)
        self._rendered.clear()

    def is_rendered(self, row: int) -> bool:
        return row in self._rendered

    def mark_rendered(self, row: int) -> None:
        if 0 <= row < self._count:
            self._rendered.add(row)

    def mark_dirty(self, rows: Iterable[int]) -> None:
        for row in rows:
            self._rendered.discard(row)

    def next_row(self, first_visible: int, last_visible: int) -> int | None:
        if self._count == 0:
            return None

        first = max(0, min(first_visible, self._count - 1))
        last = max(first, min(last_visible, self._count - 1))
        low = max(0, first - self.margin)
        high = min(self._count - 1, last + self.margin)

        best: tuple[int, int] | None = None
        for row in range(low, high + 1):
            if row in self._rendered:
                continue
            if row < first:
                distance = first - row
            elif row > last:
                distance = row - last
            else:
                distance = 0
            key = (distance, row)
            if best is None or key < best:
                best = key
        return None if best is None else best[1]
