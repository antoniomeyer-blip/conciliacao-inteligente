"""Parser OFX: suporta OFX SGML 1.0x (tags sem fechamento) e OFX 2.x XML,
inclusive arquivos em Windows-1252 (CHARSET:1252)."""
from __future__ import annotations

import re
from decimal import Decimal

from .common import ParseError, clean_id, decode_text, mask_account, parse_date, parse_decimal, scrub

_TAG_VALUE = re.compile(r"<([A-Z0-9\.]+)>([^<\r\n]*)", re.I)


def looks_like_ofx(data: bytes) -> bool:
    head = data[:4096].upper()
    return b"OFXHEADER" in head or b"<OFX>" in head or b"<?OFX" in head


def _fields(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag, value in _TAG_VALUE.findall(block):
        value = value.strip()
        if value and tag.upper() not in out:
            out[tag.upper()] = value
    return out


def _header_charset(text: str) -> str | None:
    m = re.search(r"CHARSET:\s*(\S+)", text[:1024], re.I)
    if m and m.group(1).strip().isdigit():
        return "cp" + m.group(1).strip()
    m = re.search(r'encoding="([^"]+)"', text[:1024], re.I)
    return m.group(1) if m else None


def parse_ofx(data: bytes) -> dict:
    # Decodifica primeiro em latin-1 só para ler o cabeçalho; depois decodifica de verdade.
    declared = _header_charset(data[:1024].decode("latin-1"))
    text = decode_text(data, declared)
    if "<OFX>" not in text.upper():
        raise ParseError("Arquivo OFX inválido: bloco <OFX> não encontrado.")

    body = text[text.upper().index("<OFX>"):]
    upper = body.upper()

    # Cabeçalho da conta (antes da lista de transações)
    first_trn = upper.find("<STMTTRN>")
    head_fields = _fields(body[: first_trn if first_trn >= 0 else len(body)])
    tail_fields = _fields(body[upper.rfind("</BANKTRANLIST>"):] if "</BANKTRANLIST>" in upper else "")

    meta = {
        "formato": "OFX " + ("XML" if "</STMTTRN>" in upper and "<?OFX" in text[:200].upper() else "SGML"),
        "banco": head_fields.get("ORG") or head_fields.get("BANKID"),
        "codigo_banco": head_fields.get("BANKID") or head_fields.get("FID"),
        "agencia": mask_account(head_fields.get("BRANCHID")),
        "conta": mask_account(head_fields.get("ACCTID")),
        "moeda": head_fields.get("CURDEF", "BRL"),
        "periodo_inicio": (d.isoformat() if (d := parse_date(head_fields.get("DTSTART"))) else None),
        "periodo_fim": (d.isoformat() if (d := parse_date(head_fields.get("DTEND"))) else None),
        "saldo_final": tail_fields.get("BALAMT"),
    }

    blocks = re.split(r"<STMTTRN>", body, flags=re.I)[1:]
    records = []
    for idx, block in enumerate(blocks, start=1):
        block = re.split(r"</STMTTRN>|</BANKTRANLIST>", block, flags=re.I)[0]
        f = _fields(block)
        amount = parse_decimal(f.get("TRNAMT"), ".")
        posted = parse_date(f.get("DTPOSTED"))
        if amount is None or posted is None:
            continue
        memo = scrub(f.get("MEMO"))
        name = scrub(f.get("NAME"))
        records.append({
            "row": idx,
            "date": posted.isoformat(),
            "amount": str(amount),
            "description": memo,
            "counterparty": name,
            "ids": {k: v for k, v in {
                "fitid": clean_id(f.get("FITID")),
                "checknum": clean_id(f.get("CHECKNUM")),
                "refnum": clean_id(f.get("REFNUM")),
            }.items() if v},
            "extra": {"trntype": f.get("TRNTYPE")},
        })
    if not records:
        raise ParseError("Nenhuma transação (<STMTTRN>) encontrada no arquivo OFX.")
    if not meta["periodo_inicio"]:
        dates = sorted(r["date"] for r in records)
        meta["periodo_inicio"], meta["periodo_fim"] = dates[0], dates[-1]
    meta["total_creditos"] = str(sum((Decimal(r["amount"]) for r in records if Decimal(r["amount"]) > 0), Decimal(0)))
    meta["total_debitos"] = str(sum((Decimal(r["amount"]) for r in records if Decimal(r["amount"]) < 0), Decimal(0)))
    return {"meta": meta, "records": records}
