"""Leitura de arquivos tabulares (CSV, TXT, XLSX, XLS, PDF) para uma grade de células.

- Nenhuma macro é executada: XLSX é lido com openpyxl (somente dados), XLS com xlrd.
- O conteúdo é validado pela assinatura binária, não pela extensão.
"""
from __future__ import annotations

import csv
import io
import re

from .common import ParseError, decode_text

MAX_ROWS = 50000


def _sniff_delimiter(text: str) -> str:
    sample = [ln for ln in text.splitlines()[:40] if ln.strip()]
    best, best_score = ";", -1
    for delim in [";", ",", "\t", "|"]:
        counts = [ln.count(delim) for ln in sample]
        if not counts:
            continue
        # Prefere o delimitador mais frequente e consistente nas linhas mais longas
        top = sorted(counts, reverse=True)[: max(3, len(counts) // 2)]
        score = min(top) * 10 + sum(top) / len(top)
        if score > best_score:
            best, best_score = delim, score
    return best


def read_text_table(data: bytes) -> list[list]:
    if b"\x00" in data[:4096]:
        raise ParseError("O arquivo parece ser binário e não um CSV/TXT de texto.")
    text = decode_text(data)
    delim = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim, quotechar='"')
    rows = []
    for i, row in enumerate(reader):
        if i > MAX_ROWS:
            raise ParseError(f"Arquivo excede o limite de {MAX_ROWS} linhas.")
        rows.append([c.strip() if isinstance(c, str) else c for c in row])
    # TXT sem delimitador: tenta colunas separadas por 2+ espaços
    if rows and max(len(r) for r in rows) == 1:
        rows = [re.split(r"\s{2,}|\t", r[0].strip()) if r else [] for r in rows]
    return rows


def read_xlsx(data: bytes) -> list[list]:
    import openpyxl  # leitura apenas de valores; macros nunca são executadas

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Não foi possível abrir a planilha XLSX: {exc}") from exc
    best: list[list] = []
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i > MAX_ROWS:
                raise ParseError(f"Planilha excede o limite de {MAX_ROWS} linhas.")
            rows.append(list(row))
        if sum(1 for r in rows if any(c not in (None, "") for c in r)) > \
           sum(1 for r in best if any(c not in (None, "") for c in r)):
            best = rows
    wb.close()
    return best


def read_xls(data: bytes) -> list[list]:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Não foi possível abrir a planilha XLS: {exc}") from exc
    best: list[list] = []
    for sheet in book.sheets():
        rows = []
        for r in range(min(sheet.nrows, MAX_ROWS)):
            out = []
            for c in range(sheet.ncols):
                cell = sheet.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    out.append(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
                else:
                    out.append(cell.value)
            rows.append(out)
        if len(rows) > len(best):
            best = rows
    return best


def read_pdf(data: bytes) -> list[list]:
    import pdfplumber

    rows: list[list] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > 200:
                raise ParseError("PDF com mais de 200 páginas não é suportado.")
            for page in pdf.pages:
                tables = page.extract_tables() or page.extract_tables(
                    {"vertical_strategy": "text", "horizontal_strategy": "text"}) or []
                if tables:
                    for t in tables:
                        rows.extend([[(c or "").replace("\n", " ").strip() for c in r] for r in t])
                else:
                    for line in (page.extract_text() or "").splitlines():
                        parts = re.split(r"\s{2,}", line.strip())
                        if len(parts) > 1:
                            rows.append(parts)
    except ParseError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Não foi possível ler o PDF: {exc}") from exc
    if not rows:
        raise ParseError("O PDF não contém dados tabulares extraíveis (pode ser uma imagem digitalizada).")
    return rows


def detect_format(filename: str, data: bytes) -> str:
    """Identifica o formato pelo conteúdo (assinatura), usando a extensão só como dica."""
    from .ofx import looks_like_ofx

    if not data:
        raise ParseError("Arquivo vazio.")
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        head = data[:2000]
        if b"vbaProject" in data or filename.lower().endswith((".xlsm", ".xltm")):
            # Aceitamos, mas os dados são lidos sem executar macros.
            pass
        if b"[Content_Types].xml" in head or b"xl/" in data[:200000]:
            return "xlsx"
        raise ParseError("Arquivo compactado não reconhecido como planilha XLSX.")
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "xls"
    if looks_like_ofx(data):
        return "ofx"
    if b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ParseError("Tipo de arquivo não suportado (conteúdo binário desconhecido).")
    head = data[:2048].lstrip()
    if head.startswith((b"<html", b"<!DOCTYPE", b"<HTML")):
        raise ParseError("O arquivo é uma página HTML, não um relatório tabular.")
    return "csv"


def read_grid(fmt: str, data: bytes) -> list[list]:
    if fmt == "xlsx":
        return read_xlsx(data)
    if fmt == "xls":
        return read_xls(data)
    if fmt == "pdf":
        return read_pdf(data)
    return read_text_table(data)
