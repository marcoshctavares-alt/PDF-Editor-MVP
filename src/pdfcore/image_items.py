from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.pdfcore.geometry import Rect

CORNERS: tuple[str, ...] = ("nw", "ne", "sw", "se")

MIN_IMAGE_SIDE = 4.0
DEFAULT_IMAGE_WIDTH = 200.0
DEFAULT_IMAGE_PAGE_FRACTION = 0.8

IMAGE_EXTENSIONS: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
)


@dataclass(frozen=True)
class ImageItem:
    id: int
    page_index: int
    rect: Rect
    path: Path


def normalize_rect(rect: Rect) -> Rect:
    try:
        x0, y0, x1, y1 = (float(v) for v in rect)
    except (TypeError, ValueError):
        raise ValueError(
            "O retângulo deve ser (esquerda, topo, direita, base) em pontos."
        ) from None

    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    if right - left < MIN_IMAGE_SIDE or bottom - top < MIN_IMAGE_SIDE:
        raise ValueError(
            f"A imagem ficou pequena demais (mínimo {MIN_IMAGE_SIDE:g} pt de lado). "
            "Arraste uma área maior."
        )
    return (left, top, right, bottom)


def fit_rect(box: Rect, image_width: float, image_height: float) -> Rect:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("A imagem tem dimensões inválidas.")

    left, top, right, bottom = box
    box_w, box_h = right - left, bottom - top
    scale = min(box_w / image_width, box_h / image_height)
    width, height = image_width * scale, image_height * scale
    x0 = left + (box_w - width) / 2
    y0 = top + (box_h - height) / 2
    return (x0, y0, x0 + width, y0 + height)


def default_rect(
    x: float,
    y: float,
    image_width: float,
    image_height: float,
    page_width: float,
    page_height: float,
) -> Rect:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("A imagem tem dimensões inválidas.")

    width = min(DEFAULT_IMAGE_WIDTH, image_width * 0.75)
    width = min(width, page_width * DEFAULT_IMAGE_PAGE_FRACTION)
    height = width * image_height / image_width
    max_height = page_height * DEFAULT_IMAGE_PAGE_FRACTION
    if height > max_height:
        width *= max_height / height
        height = max_height

    left = max(0.0, min(x, page_width - width))
    top = max(0.0, min(y, page_height - height))
    return (left, top, left + width, top + height)


def corner_point(rect: Rect, corner: str) -> tuple[float, float]:
    left, top, right, bottom = rect
    return (
        left if corner in ("nw", "sw") else right,
        top if corner in ("nw", "ne") else bottom,
    )


def opposite_corner(corner: str) -> str:
    return {"nw": "se", "ne": "sw", "sw": "ne", "se": "nw"}[corner]


def resize_keep_aspect(
    rect: Rect,
    corner: str,
    point: tuple[float, float],
    min_side: float,
    bounds: tuple[float, float],
) -> Rect:
    if corner not in CORNERS:
        raise ValueError(f"Canto inválido: {corner}")

    left, top, right, bottom = rect
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise ValueError("O retângulo tem dimensões inválidas.")
    aspect = width / height

    anchor_x, anchor_y = corner_point(rect, opposite_corner(corner))
    sign_x = 1.0 if corner in ("ne", "se") else -1.0
    sign_y = 1.0 if corner in ("sw", "se") else -1.0

    wanted_x = (point[0] - anchor_x) * sign_x
    wanted_y = (point[1] - anchor_y) * sign_y
    new_width = max(wanted_x, wanted_y * aspect)

    room_x = bounds[0] - anchor_x if sign_x > 0 else anchor_x
    room_y = bounds[1] - anchor_y if sign_y > 0 else anchor_y
    new_width = min(new_width, room_x, room_y * aspect)
    new_width = max(new_width, min_side * max(1.0, aspect))
    new_height = new_width / aspect

    x0, x1 = (
        (anchor_x, anchor_x + new_width)
        if sign_x > 0
        else (anchor_x - new_width, anchor_x)
    )
    y0, y1 = (
        (anchor_y, anchor_y + new_height)
        if sign_y > 0
        else (anchor_y - new_height, anchor_y)
    )
    return (x0, y0, x1, y1)
