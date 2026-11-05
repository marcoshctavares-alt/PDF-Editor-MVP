from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.pdfcore.geometry import Rect

KINDS: tuple[str, ...] = ("highlight", "underline", "strikeout")

KIND_COLORS: dict[str, tuple[float, float, float]] = {
    "highlight": (1.0, 0.85, 0.0),
    "underline": (0.85, 0.1, 0.1),
    "strikeout": (0.85, 0.1, 0.1),
}

KIND_LABELS: dict[str, str] = {
    "highlight": "Destacar texto",
    "underline": "Sublinhar texto",
    "strikeout": "Riscar texto",
}


class NoTextInAreaError(ValueError):
    pass


@dataclass(frozen=True)
class AnnotationItem:
    id: int
    page_index: int
    kind: str
    rects: tuple[Rect, ...]


def ordered_area(area: Rect) -> Rect:
    x0, y0, x1, y1 = (float(v) for v in area)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def words_in_area(words: Iterable[Sequence], area: Rect) -> list[Rect]:
    left, top, right, bottom = ordered_area(area)
    lines: dict[tuple[int, int], Rect] = {}
    for word in words:
        x0, y0, x1, y1 = (float(v) for v in word[:4])
        center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
        if not (left <= center_x <= right and top <= center_y <= bottom):
            continue
        key = (int(word[5]), int(word[6]))
        current = lines.get(key)
        if current is None:
            lines[key] = (x0, y0, x1, y1)
        else:
            lines[key] = (
                min(current[0], x0),
                min(current[1], y0),
                max(current[2], x1),
                max(current[3], y1),
            )
    return [lines[key] for key in sorted(lines)]


def text_in_area(words: Iterable[Sequence], area: Rect) -> str:
    left, top, right, bottom = ordered_area(area)
    lines: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for word in words:
        x0, y0, x1, y1 = (float(v) for v in word[:4])
        center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
        if not (left <= center_x <= right and top <= center_y <= bottom):
            continue
        key = (int(word[5]), int(word[6]))
        lines.setdefault(key, []).append((int(word[7]), str(word[4])))
    return "\n".join(
        " ".join(text for _, text in sorted(lines[key])) for key in sorted(lines)
    )


def bounds(rects: Iterable[Rect]) -> Rect:
    boxes = list(rects)
    if not boxes:
        raise ValueError("Não há retângulos.")
    return (
        min(r[0] for r in boxes),
        min(r[1] for r in boxes),
        max(r[2] for r in boxes),
        max(r[3] for r in boxes),
    )


def contains_point(
    rects: Iterable[Rect], x: float, y: float, tolerance: float = 2.0
) -> bool:
    return any(
        left - tolerance <= x <= right + tolerance
        and top - tolerance <= y <= bottom + tolerance
        for left, top, right, bottom in rects
    )
