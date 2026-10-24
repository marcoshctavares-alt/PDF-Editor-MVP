# PDF Editor MVP

<img width="836" height="716" alt="Captura de tela 2026-10-24 105822" src="https://github.com/user-attachments/assets/d77dbbbe-b5c6-4f6e-9a91-2fab30e752f4" />


Leitor e editor de PDF minimalista em Python. Interface em PySide6, engine de
manipulação com PyMuPDF. O código é separado em duas camadas — `pdfcore`
(engine, sem dependência de Qt) e `pdfapp` (interface) — para que a lógica de
PDF seja testável independentemente e o projeto possa crescer sem virar uma
bagunça.

Ainda está em desenvolvimento. O que funciona hoje: abrir, visualizar,
navegar, inserir texto e salvar como. O resto está na seção de roadmap.


## Funcionalidades

Já implementado:

- Abrir PDFs via diálogo nativo
- Renderizar páginas com DPI configurável
- Navegar entre páginas (botões e atalhos de teclado)
- Inserir texto clicando na posição desejada da página (`Ctrl+T`)
- Exportar o PDF editado com "Salvar Como"

Roadmap (sem ordem definida):

- Inserir imagens com posicionamento interativo
- Busca e substituição de texto
- Anotações (grifar, sublinhar)
- Controle de zoom
- Painel de miniaturas
- Extração de texto


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

Abra um PDF com `Ctrl+O`, navegue com `PgUp`/`PgDn`, exporte com `Ctrl+Shift+S`. Para inserir texto, clique em **Inserir Texto** na toolbar (ou `Ctrl+T`), depois clique na posição desejada da página e digite o conteúdo. Esc cancela a inserção.

O PyMuPDF não sobrescreve o arquivo aberto, então o "Salvar Como" sempre exige um caminho novo. A aplicação bloqueia a tentativa de sobrescrever para não gerar confusão.

## Estrutura

    pdf-editor-mvp/
    ├── main.py
    ├── requirements.txt
    ├── README.md
    ├── LICENSE
    ├── .gitignore
    └── src/
        ├── __init__.py
        ├── pdfcore/           # engine, sem Qt
        │   ├── __init__.py
        │   └── document.py
        └── pdfapp/            # interface
            ├── __init__.py
            ├── main_window.py
            ├── qt_image.py    # conversão Pixmap -> QImage
            └── viewer.py

## Testando a engine sem interface

A engine roda sem Qt. Para validar rápido:

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
