"""Ponto de entrada dos parsers: valida o arquivo e devolve registros normalizados."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from .common import ParseError
from .mapping import SOURCES, parse_grid
from .ofx import parse_ofx
from .tabular import detect_format, read_grid

ALLOWED_EXT = {".xlsx", ".xlsm", ".xls", ".csv", ".ofx", ".txt", ".pdf", ".qfx"}
MAX_BYTES = 10 * 1024 * 1024

__all__ = ["ParseError", "parse_file", "SOURCES", "ALLOWED_EXT", "MAX_BYTES"]


def parse_file(filename: str, data: bytes, source: str, settings: dict,
               mapping: dict | None = None, header_row: int | None = None) -> dict:
    if source not in SOURCES:
        raise ParseError("Origem de arquivo inválida.")
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext and ext not in ALLOWED_EXT:
        raise ParseError(f"Extensão '{ext}' não suportada. Use XLSX, XLS, CSV, OFX, TXT ou PDF.")
    if len(data) > MAX_BYTES:
        raise ParseError("Arquivo maior que o limite de 10 MB.")
    fmt = detect_format(filename, data)
    sha = hashlib.sha256(data).hexdigest()

    if fmt == "ofx":
        if source != "bank":
            raise ParseError("Arquivos OFX são extratos bancários. Envie-o na área 'Extrato bancário'.")
        parsed = parse_ofx(data)
        result = {"needs_mapping": False, "records": parsed["records"], "meta": parsed["meta"],
                  "warnings": [], "columns": [], "mapping": {}, "preview": [], "missing": []}
    else:
        grid = read_grid(fmt, data)
        result = parse_grid(grid, source, settings, mapping, header_row)
        result["meta"] = {"formato": fmt.upper()}
        if result["records"]:
            dates = sorted(r["date"] for r in result["records"] if r.get("date"))
            if dates:
                result["meta"]["periodo_inicio"], result["meta"]["periodo_fim"] = dates[0], dates[-1]
    result.update(format=fmt, sha256=sha, size=len(data), filename=filename, source=source)
    recs = result["records"]
    result["meta"]["registros"] = len(recs)
    result["meta"]["valor_total"] = str(sum((Decimal(r["amount"]) for r in recs), Decimal(0)))
    return result
