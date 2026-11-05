"""Teste de fumaça da engine com o PyMuPDF REAL (sem Qt, sem janela).

Rode na raiz do projeto:

    python check_engine.py

Cria um PDF temporário, insere, edita e apaga textos, salva uma cópia e confere
o conteúdo do arquivo salvo. Não altera nenhum arquivo seu.
"""

import tempfile
from pathlib import Path

import pymupdf

from src.pdfcore.document import PdfDocument


def make_pdf(path: Path) -> None:
    doc = pymupdf.open()
    for n in (1, 2):
        page = doc.new_page()
        page.insert_text((72, 72), f"Original da pagina {n}", fontsize=14)
    doc.save(path)
    doc.close()


def make_png(path: Path) -> None:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40), False)
    pix.clear_with(180)
    pix.save(str(path))


def page_text(path: Path, index: int) -> str:
    with pymupdf.open(path) as doc:
        return doc[index].get_text()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FALHOU: {message}")
    print(f"ok  - {message}")


with tempfile.TemporaryDirectory() as tmp:
    original = Path(tmp) / "original.pdf"
    saved = Path(tmp) / "editado.pdf"
    make_pdf(original)

    with PdfDocument(original) as doc:
        a = doc.add_text(0, 100, 200, "Texto A", size=20, family="Times", bold=True)
        b = doc.add_text(0, 100, 300, "Texto B")
        c = doc.add_text(1, 50, 50, "Texto C", color=(1, 0, 0))
        check(len(doc.text_items(0)) == 2, "duas inserções na página 1")

        hit = doc.find_text_item_at(0, a.x + 1, a.y + 1)
        check(hit is not None and hit.id == a.id, "clique dentro do texto A o encontra")
        check(doc.find_text_item_at(0, 500, 700) is None, "clique no vazio não acha nada")

        a = doc.update_text(a.id, text="Texto A2", size=30, italic=True)
        check(a.text == "Texto A2" and a.size == 30, "editar texto e tamanho")

        doc.remove_text(b.id)
        check([i.id for i in doc.text_items(0)] == [a.id], "apagar o texto B")

        # --- imagens ---
        png = Path(tmp) / "imagem.png"
        make_png(png)  # 60 x 40 px, proporção 3:2

        img = doc.add_image(0, (100, 400, 300, 500), png)
        left, top, right, bottom = img.rect
        check(abs((right - left) / (bottom - top) - 1.5) < 0.01, "imagem mantém a proporção 3:2")
        check(
            100 <= left and right <= 300 and 400 <= top and bottom <= 500,
            "imagem cabe dentro da área escolhida",
        )
        center = ((left + right) / 2, (top + bottom) / 2)
        hit_img = doc.find_image_at(0, *center)
        check(hit_img is not None and hit_img.id == img.id, "clique na imagem a encontra")
        check(len(doc.text_items(0)) == 1, "o texto da página 1 sobrevive ao redesenho")

        # Insere e apaga numa página que tem texto: o texto tem que continuar.
        temp = doc.add_image(1, (50, 200, 150, 300), png)
        doc.remove_image(temp.id)
        check(doc.image_items(1) == [], "apagar a imagem da página 2")

        default = doc.default_image_rect(0, 20, 20, png)
        check(default[0] == 20 and default[1] == 20, "clique simples usa o ponto como canto")

        rendered = doc.render_page(0)
        check(rendered.width > 0 and rendered.channels == 3, "renderiza a página editada")

        doc.save(saved)

    page1 = page_text(saved, 0)
    page2 = page_text(saved, 1)
    check("Texto A2" in page1, "PDF salvo tem o texto editado")
    check("Texto B" not in page1, "PDF salvo NÃO tem o texto apagado")
    check("Original da pagina 1" in page1, "conteúdo original da página 1 preservado")
    check("Texto C" in page2 and "Original da pagina 2" in page2, "página 2 correta")
    check("Texto" not in page_text(original, 0), "arquivo original não foi alterado")

    with pymupdf.open(saved) as result:
        check(len(result[0].get_images()) == 1, "PDF salvo tem a imagem da página 1")
        check(len(result[1].get_images()) == 0, "PDF salvo NÃO tem a imagem apagada")
    with pymupdf.open(original) as untouched:
        check(len(untouched[0].get_images()) == 0, "original continua sem imagens")

with tempfile.TemporaryDirectory() as tmp2:
    original2 = Path(tmp2) / "original.pdf"
    png2 = Path(tmp2) / "imagem.png"
    parcial = Path(tmp2) / "parcial.pdf"
    completo = Path(tmp2) / "completo.pdf"
    make_pdf(original2)
    make_png(png2)

    with PdfDocument(original2) as doc:
        check(not doc.can_undo and not doc.can_redo, "documento novo não tem histórico")
        doc.add_text(0, 100, 200, "Primeiro")
        segundo = doc.add_text(0, 100, 300, "Segundo")
        doc.add_image(1, (50, 200, 150, 300), png2)
        check(doc.undo_label == "Inserir imagem", "o histórico sabe o nome da última operação")

        check(doc.undo() == [1], "desfazer a imagem afeta a página 2")
        check(doc.image_items(1) == [], "a imagem saiu do registro")
        check(doc.undo() == [0], "desfazer o segundo texto afeta a página 1")
        check([i.text for i in doc.text_items(0)] == ["Primeiro"], "só o primeiro texto ficou")
        check(doc.render_page(0).width > 0, "renderiza depois de desfazer")

        doc.undo()
        check(not doc.can_undo and doc.can_redo, "tudo desfeito: só dá para refazer")
        doc.redo()
        doc.save(parcial)

        doc.redo()
        doc.redo()
        check(doc.get_text_item(segundo.id).text == "Segundo", "refazer devolve o texto com o mesmo id")
        doc.save(completo)

        doc.undo()
        doc.update_text(segundo.id, size=40)
        check(not doc.can_redo, "uma nova edição descarta o refazer")

    check("Primeiro" in page_text(parcial, 0), "salvo no meio do histórico: tem o primeiro texto")
    check("Segundo" not in page_text(parcial, 0), "salvo no meio do histórico: não tem o segundo")
    with pymupdf.open(parcial) as result:
        check(len(result[1].get_images()) == 0, "salvo no meio do histórico: sem imagem")
    check("Segundo" in page_text(completo, 0), "salvo depois de refazer: tem o segundo texto")
    with pymupdf.open(completo) as result:
        check(len(result[1].get_images()) == 1, "salvo depois de refazer: tem a imagem")

with tempfile.TemporaryDirectory() as tmp3:
    original3 = Path(tmp3) / "original.pdf"
    movido = Path(tmp3) / "movido.pdf"
    make_pdf(original3)

    with PdfDocument(original3) as doc:
        t = doc.add_text(0, 100, 200, "Mover")
        doc.update_text(t.id, x=300, y=400)
        check(doc.undo_label == "Mover texto", "mover entra no histórico com o nome certo")
        check((doc.get_text_item(t.id).x, doc.get_text_item(t.id).y) == (300, 400), "posição nova registrada")
        doc.save(movido)

        doc.undo()
        check((doc.get_text_item(t.id).x, doc.get_text_item(t.id).y) == (100, 200), "desfazer volta à posição antiga")
        doc.redo()
        check((doc.get_text_item(t.id).x, doc.get_text_item(t.id).y) == (300, 400), "refazer leva de novo ao destino")

    with pymupdf.open(movido) as result:
        words = [w for w in result[0].get_text("words") if w[4] == "Mover"]
    check(len(words) == 1, "o texto aparece uma única vez no PDF salvo (não ficou cópia na posição antiga)")
    x0, y0 = words[0][0], words[0][1]
    check(abs(x0 - 300) < 3 and abs(y0 - 400) < 8, f"o texto está no destino (encontrei x={x0:.0f}, y={y0:.0f})")

with tempfile.TemporaryDirectory() as tmp4:
    original4 = Path(tmp4) / "original.pdf"
    png4 = Path(tmp4) / "imagem.png"
    editado4 = Path(tmp4) / "editado.pdf"
    make_pdf(original4)
    make_png(png4)

    with PdfDocument(original4) as doc:
        img = doc.add_image(0, (100, 300, 220, 380), png4)
        l0, t0, r0, b0 = img.rect
        moved = doc.update_image(img.id, (l0 + 50, t0 + 40, r0 + 50, b0 + 40))
        check(doc.undo_label == "Mover imagem", "mover imagem entra no histórico com o nome certo")
        big = doc.update_image(img.id, (150, 340, 150 + 240, 340 + 160))
        check(doc.undo_label == "Redimensionar imagem", "redimensionar imagem entra no histórico")
        doc.save(editado4)

        doc.undo()
        check(doc.get_image_item(img.id).rect == moved.rect, "desfazer redimensionar volta ao tamanho anterior")
        doc.undo()
        check(doc.get_image_item(img.id).rect == img.rect, "desfazer mover volta à posição original")
        doc.redo()
        doc.redo()
        check(doc.get_image_item(img.id).rect == big.rect, "refazer leva ao retângulo final")

    with pymupdf.open(editado4) as result:
        infos = result[0].get_image_info()
        check(len(infos) == 1, "o PDF salvo tem uma única imagem (sem cópia na posição antiga)")
        x0, y0, x1, y1 = infos[0]["bbox"]
        check(
            abs(x0 - 150) < 1 and abs(y0 - 340) < 1 and abs(x1 - 390) < 1 and abs(y1 - 500) < 1,
            f"a imagem está no retângulo final (bbox {x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f})",
        )

with tempfile.TemporaryDirectory() as tmp5:
    original5 = Path(tmp5) / "original.pdf"
    make_pdf(original5)

    with PdfDocument(original5) as doc:
        hits = doc.search("original").hits
        check([h.page_index for h in hits] == [0, 1], "busca acha o texto original em cada página (sem diferenciar maiúsculas)")
        left, top, right, bottom = hits[0].rect
        check(abs(left - 72) < 3 and right > left and bottom > top and 40 < top < 90, f"retângulo do resultado perto de onde o texto foi escrito ({left:.0f},{top:.0f},{right:.0f},{bottom:.0f})")
        check(doc.search("inexistente").hits == [] and doc.search("   ").hits == [], "sem resultado e consulta vazia devolvem lista vazia")
        check([h.page_index for h in doc.search("original", pages=[1]).hits] == [1], "busca restrita a uma página")
        cut = doc.search("original", limit=1)
        check(len(cut.hits) == 1 and cut.truncated, "limite de resultados marca truncado")
        check(not doc.search("original", limit=2).truncated, "exatamente no limite não é truncado")

        novo = doc.add_text(0, 100, 300, "Banana madura")
        check([h.page_index for h in doc.search("banana").hits] == [0], "texto inserido também é encontrado")
        doc.undo()
        check(doc.search("banana").hits == [], "depois de desfazer, deixa de ser encontrado")
        doc.redo()
        doc.update_text(novo.id, text="Laranja")
        check(doc.search("banana").hits == [] and len(doc.search("laranja").hits) == 1, "editar o texto atualiza a busca")

with tempfile.TemporaryDirectory() as tmp6:
    original6 = Path(tmp6) / "original.pdf"
    marcado6 = Path(tmp6) / "marcado.pdf"
    make_pdf(original6)

    from src.pdfcore.annotation_items import NoTextInAreaError

    with PdfDocument(original6) as doc:
        area = (60, 40, 400, 90)
        destaque = doc.add_annotation(0, "highlight", area)
        check(len(destaque.rects) == 1 and destaque.rects[0][0] < 80, f"destacar a linha gera um retângulo sobre as palavras {tuple(round(v) for v in destaque.rects[0])}")
        sublinhado = doc.add_annotation(0, "underline", area)
        riscado = doc.add_annotation(1, "strikeout", area)
        check(doc.undo_label == "Riscar texto", "histórico com o nome da anotação")

        try:
            doc.add_annotation(0, "highlight", (300, 500, 400, 600))
        except NoTextInAreaError:
            check(True, "área sem texto é recusada com NoTextInAreaError")
        else:
            raise SystemExit("FALHOU: área sem texto deveria ser recusada")

        left, top, right, bottom = destaque.rects[0]
        achada = doc.find_annotation_at(0, left + 5, (top + bottom) / 2)
        check(achada is not None and achada.id == sublinhado.id, "clique sobre as anotações sobrepostas acha a mais recente")
        check(doc.render_page(0).width > 0, "renderiza a página anotada")

        doc.remove_annotation(sublinhado.id)
        check([a.id for a in doc.annotation_items(0)] == [destaque.id], "apagar tira só o sublinhado")
        doc.undo()
        check([a.id for a in doc.annotation_items(0)] == [destaque.id, sublinhado.id], "desfazer devolve o sublinhado com o mesmo id")
        doc.save(marcado6)

    with pymupdf.open(marcado6) as result:
        tipos0 = sorted(a.type[1] for a in result[0].annots())
        tipos1 = sorted(a.type[1] for a in result[1].annots())
        check(tipos0 == ["Highlight", "Underline"], f"PDF salvo: página 1 tem destaque e sublinhado ({tipos0})")
        check(tipos1 == ["StrikeOut"], f"PDF salvo: página 2 tem o riscado ({tipos1})")
        check("Original" in result[0].get_text(), "o texto continua selecionável no PDF salvo")
    with pymupdf.open(original6) as untouched:
        check(not list(untouched[0].annots()), "o arquivo original não foi alterado")

with tempfile.TemporaryDirectory() as tmp7:
    original7 = Path(tmp7) / "original.pdf"
    make_pdf(original7)
    with PdfDocument(original7) as doc:
        check(not doc.modified, "documento novo não está modificado")
        doc.add_text(0, 72, 72, "Alterado")
        check(doc.modified, "editar marca como modificado")
        doc.save(Path(tmp7) / "copia.pdf")
        check(not doc.modified, "salvar limpa o estado de modificado")
        doc.undo()
        check(doc.modified, "desfazer depois de salvar volta a marcar")

print("\nTudo certo: a engine funciona com o PyMuPDF real.")
