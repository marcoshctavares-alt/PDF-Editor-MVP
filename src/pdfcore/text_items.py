"""Modelo de texto inserido no PDF (sem Qt).

Cada texto inserido é um TextItem imutável. A engine guarda a lista de itens
e redesenha a página a partir do original sempre que algo muda; é assim que
apagar e editar funcionam, já que o PyMuPDF não desfaz um `insert_text`.

Convenção de coordenadas: `x` e `y` são o canto SUPERIOR ESQUERDO da caixa do
texto, em pontos do PDF (1 pt = 1/72 polegada), origem no canto superior
esquerdo da página, como no `render_page`.
"""

from __future__ import annotations

from dataclasses import dataclass

Color = tuple[float, float, float]

FONT_FAMILIES: tuple[str, ...] = ("Helvetica", "Times", "Courier")
DEFAULT_FAMILY = "Helvetica"
DEFAULT_FONT_SIZE = 12.0
MIN_FONT_SIZE = 4.0
MAX_FONT_SIZE = 200.0
DEFAULT_COLOR: Color = (0.0, 0.0, 0.0)

# (família, negrito, itálico) -> nome curto da fonte base-14 no PyMuPDF.
_FONT_CODES: dict[tuple[str, bool, bool], str] = {
    ("Helvetica", False, False): "helv",
    ("Helvetica", True, False): "hebo",
    ("Helvetica", False, True): "heit",
    ("Helvetica", True, True): "hebi",
    ("Times", False, False): "tiro",
    ("Times", True, False): "tibo",
    ("Times", False, True): "tiit",
    ("Times", True, True): "tibi",
    ("Courier", False, False): "cour",
    ("Courier", True, False): "cobo",
    ("Courier", False, True): "coit",
    ("Courier", True, True): "cobi",
}


def font_code(family: str, bold: bool = False, italic: bool = False) -> str:
    """Nome curto da fonte base-14. Levanta ValueError se a família não existe."""
    try:
        return _FONT_CODES[(family, bool(bold), bool(italic))]
    except KeyError:
        raise ValueError(
            f"Fonte desconhecida: {family!r}. Opções: {', '.join(FONT_FAMILIES)}."
        ) from None


def normalize_color(color: tuple[float, float, float]) -> Color:
    """Valida uma cor RGB com componentes de 0.0 a 1.0."""
    try:
        r, g, b = (float(c) for c in color)
    except (TypeError, ValueError):
        raise ValueError(
            "A cor deve ser uma tupla (r, g, b) com valores de 0 a 1."
        ) from None
    for component in (r, g, b):
        if not (0.0 <= component <= 1.0):
            raise ValueError("Os componentes da cor devem estar entre 0 e 1.")
    return (r, g, b)


@dataclass(frozen=True)
class TextItem:
    id: int
    page_index: int
    x: float
    y: float
    text: str
    family: str = DEFAULT_FAMILY
    bold: bool = False
    italic: bool = False
    size: float = DEFAULT_FONT_SIZE
    color: Color = DEFAULT_COLOR

    @property
    def font_code(self) -> str:
        return font_code(self.family, self.bold, self.italic)