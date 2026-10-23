from PySide6.QtGui import QImage, QPixmap

from src.pdfcore.document import RenderedPage


def rendered_to_qimage(rp: RenderedPage) -> QImage:
    fmt = QImage.Format_RGBA8888 if rp.channels == 4 else QImage.Format_RGB888
    # .copy() é OBRIGATÓRIO: QImage não assume a posse do buffer
    return QImage(rp.samples, rp.width, rp.height, rp.stride, fmt).copy()


def rendered_to_qpixmap(rp: RenderedPage) -> QPixmap:
    return QPixmap.fromImage(rendered_to_qimage(rp))