# PDF Editor MVP

<img width="836" height="716" alt="Captura de tela 2026-10-24 105822" src="https://github.com/user-attachments/assets/d77dbbbe-b5c6-4f6e-9a91-2fab30e752f4" />


Leitor e editor de PDF minimalista em Python. Interface em PySide6, engine de
manipulação com PyMuPDF. O código é separado em duas camadas — `pdfcore`
(engine, sem dependência de Qt) e `pdfapp` (interface) — para que a lógica de
PDF seja testável independentemente e o projeto possa crescer sem virar uma
bagunça.

Ainda está em desenvolvimento. O que funciona hoje está na seção de
funcionalidades; o que falta, no roadmap.


## Funcionalidades

- Abrir PDFs via diálogo nativo, com zoom e navegação por páginas
- Painel de miniaturas (`F4` mostra ou oculta)
- Inserir texto clicando na página, editar (`F2` ou duplo clique), mover por
  arrasto ou com as setas do teclado (1 pt; com `Shift`, 10 pt) e apagar
- Inserir imagens, arrastar e redimensionar mantendo a proporção
- Anotações sobre o texto existente: destacar, sublinhar e riscar, arrastando
  uma área; clique na anotação e `Delete` para remover
- Copiar o texto de uma área para a área de transferência
- Busca de texto com destaque dos resultados (`Ctrl+F`)
- Girar, apagar e mover páginas
- Desfazer e refazer em todas as edições (`Ctrl+Z` / `Ctrl+Y`)
- Salvar no próprio arquivo (`Ctrl+S`) ou exportar com "Salvar Como"
- Aviso ao fechar ou abrir outro PDF com alterações não salvas

Roadmap (sem ordem definida):

- Substituição de texto
- Reordenar páginas arrastando as miniaturas
- Edição em páginas giradas (hoje bloqueada, veja abaixo)
- Exportar o texto do PDF para um arquivo


## Atalhos

| Ação | Atalho |
| --- | --- |
| Abrir / Salvar / Salvar Como | `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` |
| Página anterior / próxima | `PgUp` / `PgDn` |
| Zoom + / − / 100% | `Ctrl+=` / `Ctrl+-` / `Ctrl+0` |
| Inserir texto / imagem | `Ctrl+T` / `Ctrl+Shift+I` |
| Destacar / sublinhar / riscar / copiar texto | `Ctrl+Shift+H` / `U` / `K` / `C` |
| Editar texto selecionado | `F2` |
| Apagar seleção | `Delete` |
| Mover texto selecionado | setas (`Shift` para 10 pt) |
| Girar página à direita / à esquerda | `Ctrl+R` / `Ctrl+Shift+R` |
| Mover página para cima / para baixo | `Ctrl+Shift+PgUp` / `Ctrl+Shift+PgDn` |
| Apagar página | `Ctrl+Del` |
| Buscar | `Ctrl+F` |
| Desfazer / refazer | `Ctrl+Z` / `Ctrl+Y` |
| Cancelar o modo ativo | `Esc` |


## Stack

- PySide6 — interface
- PyMuPDF — renderização, edição e exportação
- Python 3.10+

A regra de dependência é: `pdfapp` importa `pdfcore`, nunca o contrário. A
engine não sabe que o Qt existe, então dá para testar sem abrir janela.

## Requisitos

- Python 3.10 ou mais novo
- Linux, macOS ou Windows (o Qt cobre as três plataformas)

## Instalação

    git clone https://github.com/marcoshctavares-alt/pdf-editor-mvp.git
    cd pdf-editor-mvp

    python -m venv venv
    source venv/bin/activate        # Linux/macOS
    # venv\Scripts\activate         # Windows

    pip install -r requirements.txt

## Uso

    python main.py

Rode sempre a partir da pasta que contém `main.py` e `src`, porque o projeto
importa os módulos como `src.pdfapp...`. No VS Code, abra essa pasta e use o
terminal integrado em vez do botão de executar.

Abra um PDF com `Ctrl+O` e navegue com `PgUp`/`PgDn`. Para inserir texto, clique
em **Inserir Texto** na toolbar (ou `Ctrl+T`), depois clique na posição desejada
da página e digite o conteúdo. `Esc` cancela o modo ativo.

### Salvar

O PyMuPDF não sobrescreve o arquivo aberto. O "Salvar Como" sempre exige um
caminho novo e a aplicação bloqueia a tentativa de sobrescrever. O `Ctrl+S`
grava um arquivo temporário ao lado do original, troca o original por ele e
reabre o documento na mesma página. Depois disso, textos, imagens e anotações
passam a fazer parte do PDF: deixam de ser editáveis e o histórico de desfazer
é zerado.

### Páginas giradas

Em páginas com rotação (as que você girou e as que já vêm com `/Rotate`), a
edição fica bloqueada: inserir, anotar, copiar texto, selecionar e mover. Gire
a página de volta para 0° para editar. Os itens que já estavam na página giram
junto com ela.

## Estrutura

    pdf-editor-mvp/
    ├── main.py
    ├── check_engine.py
    ├── requirements.txt
    ├── README.md
    ├── LICENSE
    ├── .gitignore
    └── src/
        ├── __init__.py
        ├── pdfcore/               # engine, sem Qt
        │   ├── __init__.py
        │   ├── document.py        # PdfDocument: edição, histórico, busca, páginas
        │   ├── geometry.py
        │   ├── text_items.py
        │   ├── image_items.py
        │   ├── annotation_items.py
        │   └── search.py
        └── pdfapp/                # interface
            ├── __init__.py
            ├── main_window.py
            ├── viewer.py
            ├── theme.py
            ├── qt_image.py        # conversão Pixmap -> QImage
            ├── text_panel.py
            ├── thumbnails.py
            ├── thumbnail_queue.py
            ├── search_bar.py
            └── search_controller.py

## Testando a engine sem interface

A engine roda sem Qt. O `check_engine.py` cria um PDF temporário, exercita
texto, imagens, anotações, busca, histórico e o estado de modificado, e confere
o conteúdo dos arquivos salvos. Não altera nenhum arquivo seu:

    python check_engine.py

Para um teste rápido com um PDF seu:

    python -c "
    from src.pdfcore.document import PdfDocument
    d = PdfDocument('algum.pdf')
    rp = d.render_page(0)
    print('paginas:', d.page_count, '| tamanho:', rp.width, 'x', rp.height)
    d.close()
    "

Se isso imprime as dimensões, a engine está ok. É o primeiro lugar para olhar
quando algo quebrar.

## Licença

AGPL-3.0, para ficar compatível com a licença do PyMuPDF. Você pode usar,
modificar e distribuir desde que o código derivado permaneça aberto sob a
mesma licença. Uso comercial com código fechado exigiria uma licença comercial
do PyMuPDF.

## Contribuindo

É um projeto pessoal e o escopo é mantido pequeno de propósito. Issues e pull
requests são bem-vindos, mas vale abrir uma issue descrevendo o caso de uso
antes de mandar o código — evita trabalho dos dois lados se estiver fora do
escopo.

## Autor

MARCOS TAVARES — github.com/marcoshctavares-alt
