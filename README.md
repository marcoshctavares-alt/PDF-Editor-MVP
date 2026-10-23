# PDF-Editor-MVP
MVP de leitor e editor de PDF em Python. Interface em PySide6, engine de manipulação com PyMuPDF. O código é separado em duas camadas — pdfcore (engine, sem dependência de Qt) e pdfapp (interface) — para que a lógica de PDF seja testável independentemente e o projeto possa crescer sem virar uma bagunça.
