from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class RenderedPage:
    samples: bytes
    width: int
    height: int
    stride: int
    channels: int  # 3 = RGB, 4 = RGBA


class PdfDocument:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._doc = pymupdf.open(self.path)
        if not self._doc.is_pdf:
            self._doc.close()
            raise ValueError(f"Não é um PDF: {path}")

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

    def insert_text(
        self,
        page_index: int,
        x: float,
        y: float,
        text: str,
        size: float = 12.0,
        color: tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        page = self._doc.load_page(page_index)
        page.insert_text(pymupdf.Point(x, y), text, fontsize=size, color=color)

    def insert_image(
        self,
        page_index: int,
        rect: tuple[float, float, float, float],
        image_path: str | Path,
    ) -> None:
        page = self._doc.load_page(page_index)
        page.insert_image(pymupdf.Rect(*rect), filename=str(image_path))

    def save(self, target: str | Path) -> None:
        target = Path(target)
        if target.resolve() == self.path.resolve():
            raise ValueError(
                "Salve em outro caminho; o PyMuPDF não sobrescreve o arquivo aberto."
            )
        self._doc.save(target)

    def close(self) -> None:
        self._doc.close()
