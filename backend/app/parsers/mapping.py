"""Identificação automática de cabeçalhos/colunas e normalização dos registros por origem.

Nenhuma coluna é presumida: o cabeçalho é localizado por pontuação de sinônimos e,
quando os campos obrigatórios não são encontrados, o resultado pede mapeamento manual.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal

from .common import (ParseError, clean_id, infer_decimal_hint, mask_card, norm, parse_date,
                     parse_decimal, scrub)

SOURCES = {
    "erp": "Sistema financeiro/ERP",
    "bank": "Extrato bancário",
    "machine": "Máquina de cartão",
    "acquirer": "Adquirente/liquidação",
}

FIELD_LABELS = {
    "date": "Data da operação", "settle_date": "Data de pagamento/liquidação", "expected_date": "Data prevista",
    "due_date": "Vencimento", "time": "Hora", "amount": "Valor", "credit": "Valor crédito", "debit": "Valor débito",
    "gross": "Valor bruto", "fee": "Taxa/desconto", "net": "Valor líquido", "revenue": "Receita",
    "expense": "Despesa", "paid_amount": "Valor pago", "description": "Descrição/histórico",
    "complement": "Complemento", "counterparty": "Cliente/fornecedor/favorecido", "doc": "Documento",
    "nsu": "NSU/Nº transação", "auth": "Autorização", "sale_id": "ID da venda/RRN",
    "payment_order": "Ordem de pagamento", "brand": "Bandeira", "method": "Forma de pagamento/modalidade",
    "plan": "Plano de venda", "installment": "Parcela", "installments": "Total de parcelas",
    "plan_total": "Valor total da venda", "cancel_flag": "Indicador de cancelamento", "cd_flag": "Indicador C/D",
    "status": "Status/situação", "card": "Número do cartão", "nature": "Natureza (receita/despesa)",
    "category": "Categoria", "account": "Conta", "terminal": "Terminal",
}

SYNONYMS: dict[str, list[str]] = {
    "date": ["data", "data da transacao", "data transacao", "data da venda", "data venda", "data lancamento",
             "data do lancamento", "data movimento", "dt lancamento", "data operacao", "data/hora", "data hora",
             "data de emissao", "emissao", "data competencia"],
    "settle_date": ["data do pagamento", "data pagamento", "pagamento", "data de pagamento", "data liquidacao",
                    "data de liquidacao", "data do credito", "data credito", "data de recebimento",
                    "data recebimento", "data baixa", "data da baixa", "data de credito"],
    "expected_date": ["data prevista de liquidacao", "previsao de pagamento", "data prevista", "data prevista de pagamento"],
    "due_date": ["vencimento", "data de vencimento", "data vencimento"],
    "time": ["hora", "horario", "hora da transacao"],
    "amount": ["valor", "valor r$", "valor (r$)", "valor da transacao", "valor lancamento", "montante", "quantia",
               "valor total", "valor original"],
    "credit": ["credito", "creditos", "entrada", "entradas", "valor credito"],
    "debit": ["debito", "debitos", "saida", "saidas", "valor debito"],
    "gross": ["valor bruto", "valor parcela bruto", "bruto", "valor da venda", "valor venda", "valor bruto da parcela"],
    "fee": ["desconto parcela", "taxa", "valor taxa", "taxa adm", "taxa administrativa", "valor desconto", "mdr",
            "tarifa", "valor da taxa", "desconto"],
    "net": ["valor parcela liquido", "valor liquido", "liquido", "valor liquido da parcela", "valor a receber",
            "valor liquido parcela"],
    "revenue": ["receita", "receitas", "valor receita"],
    "expense": ["despesa", "despesas", "valor despesa"],
    "paid_amount": ["valor pago", "valor recebido", "valor baixado", "valor quitado"],
    "description": ["descricao", "historico", "descricao do lancamento", "memo", "lancamento", "detalhe"],
    "complement": ["informacoes complementares", "complemento", "observacao", "observacoes", "detalhes"],
    "counterparty": ["fornecedor", "cliente", "favorecido", "fornecedor/cliente", "cliente/fornecedor", "nome",
                     "pagador", "beneficiario", "contato", "razao social"],
    "doc": ["documento", "doc", "n documento", "numero documento", "num. doc", "nota fiscal", "nf", "n doc"],
    "nsu": ["nsu", "n da transacao", "numero da transacao", "n transacao", "cv/nsu", "codigo da transacao",
            "id transacao", "id da transacao", "nsu/doc"],
    "auth": ["numero da autorizacao", "autorizacao", "cod. autorizacao", "codigo de autorizacao", "cod autorizacao",
             "n autorizacao", "codigo autorizacao"],
    "sale_id": ["id venda", "codigo da venda", "cod venda", "id da venda", "rrn", "tid", "codigo venda"],
    "payment_order": ["n ordem de pagamento", "ordem de pagamento", "id pagamento", "numero do pagamento"],
    "brand": ["bandeira", "bandeira do cartao"],
    "method": ["forma de pagamento", "forma pagamento", "tipo", "modalidade", "produto", "tipo de pagamento",
               "meio de pagamento", "tipo de transacao", "tipo cartao"],
    "plan": ["plano de venda", "plano", "tipo de venda"],
    "installment": ["parcela", "n parcela", "numero da parcela"],
    "installments": ["total de parcela", "total de parcelas", "qtd parcelas", "quantidade de parcelas", "parcelas",
                     "numero de parcelas", "qtde parcelas"],
    "plan_total": ["total plano de venda", "valor total da venda", "valor total venda"],
    "cancel_flag": ["indicador de cancelamento da venda", "cancelamento", "cancelada", "indicador de cancelamento"],
    "cd_flag": ["indicador credito/debito", "c/d", "d/c", "natureza do lancamento"],
    "status": ["status", "situacao", "situacao do pagamento", "status da venda"],
    "card": ["numero do cartao", "cartao", "n cartao"],
    "nature": ["natureza", "tipo de lancamento"],
    "category": ["categoria", "plano de contas"],
    "account": ["conta", "conta bancaria", "conta corrente"],
    "terminal": ["numero do terminal", "terminal", "pos", "n terminal"],
}

SOURCE_FIELDS = {
    "bank": ["date", "amount", "credit", "debit", "description", "complement", "doc", "counterparty", "cd_flag"],
    "erp": ["date", "settle_date", "due_date", "amount", "revenue", "expense", "paid_amount", "description",
            "counterparty", "doc", "method", "installment", "nature", "category", "account", "complement", "status"],
    "machine": ["date", "time", "nsu", "auth", "sale_id", "brand", "method", "plan", "installments", "installment",
                "gross", "amount", "net", "fee", "status", "card", "terminal", "cancel_flag"],
    "acquirer": ["date", "settle_date", "expected_date", "nsu", "auth", "sale_id", "payment_order", "brand", "method",
                 "plan", "installment", "installments", "gross", "fee", "net", "amount", "plan_total", "cancel_flag",
                 "cd_flag", "status", "card"],
}

REQUIRED = {
    "bank": [["date"], ["amount", "credit", "debit"]],
    "erp": [["date", "settle_date", "due_date"], ["amount", "revenue", "expense", "paid_amount"]],
    "machine": [["date"], ["gross", "amount"]],
    "acquirer": [["settle_date", "expected_date", "date"], ["net", "gross", "amount"]],
}

_SYN_INDEX = {f: {norm(s) for s in syns} for f, syns in SYNONYMS.items()}


def header_signature(cells: list) -> str:
    joined = "|".join(norm(c) for c in cells if norm(c))
    return hashlib.sha1(joined.encode()).hexdigest()[:16]


def _score(field: str, header: str) -> int:
    if not header:
        return 0
    if header in _SYN_INDEX[field]:
        return 3
    for syn in _SYN_INDEX[field]:
        if len(syn) >= 5 and (header.startswith(syn + " ") or header.endswith(" " + syn)) \
                and len(header.split()) <= len(syn.split()) + 2:
            return 1
    return 0


def find_header_row(grid: list[list], source: str) -> int | None:
    fields = SOURCE_FIELDS[source]
    best_row, best_score = None, 1
    for i, row in enumerate(grid[:40]):
        cells = [norm(c) for c in row]
        score = sum(1 for c in cells if c and any(_score(f, c) == 3 for f in fields))
        if score > best_score:
            best_row, best_score = i, score
    return best_row


def auto_map(headers: list, source: str) -> dict[str, int]:
    fields = SOURCE_FIELDS[source]
    cands = []
    for col, h in enumerate(headers):
        hn = norm(h)
        for f in fields:
            s = _score(f, hn)
            if s:
                cands.append((s, -fields.index(f), -col, f, col))
    cands.sort(reverse=True)
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for _s, _fi, _c, f, col in cands:
        if f in mapping or col in used:
            continue
        mapping[f] = col
        used.add(col)
    return mapping


def missing_required(mapping: dict, source: str) -> list[str]:
    return [" ou ".join(FIELD_LABELS[f] for f in group) for group in REQUIRED[source]
            if not any(f in mapping for f in group)]


def _cell(row: list, col: int | None):
    if col is None or col >= len(row):
        return None
    v = row[col]
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def detect_modality(*texts) -> str | None:
    t = " ".join(norm(x) for x in texts if x)
    if not t:
        return None
    if "pix" in t:
        return "pix"
    if "voucher" in t or "refeic" in t or "aliment" in t or "beneficio" in t:
        return "voucher"
    if "deb" in t or "maestro" in t or "electron" in t:
        return "debito"
    if "cred" in t or "parcel" in t or "a vista" in t:
        return "credito"
    if "pre-pago" in t or "pre pago" in t:
        return "prepago"
    return None


def detect_brand(text, brands: list[dict]) -> str | None:
    t = norm(text)
    if not t:
        return None
    for b in brands:
        for p in b.get("padroes", []):
            if norm(p) and re.search(r"(^|[^a-z])" + re.escape(norm(p)), t):
                return b["chave"]
    return None


def _installments(text) -> tuple[int | None, int | None]:
    s = _text(text)
    m = re.match(r"^\s*(\d+)\s*(?:de|/)\s*(\d+)", s, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    if s.isdigit():
        return int(s), None
    return None, None


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _raw(headers, row) -> dict:
    out = {}
    for h, v in zip(headers, row):
        key = _text(h)
        if not key or v in (None, ""):
            continue
        nk = norm(key)
        if any(x in nk for x in ("agencia", "n da conta", "numero da conta")):
            continue  # não armazena dados bancários desnecessários
        val = v.isoformat() if isinstance(v, (date, datetime)) else _text(v)
        if "cartao" in nk and re.search(r"\d{4}", val):
            val = mask_card(val)
        out[key] = scrub(val)[:300]
    return out


def normalize_rows(grid, header_row: int, mapping: dict[str, int], source: str, settings: dict) -> tuple[list, list]:
    headers = grid[header_row]
    data_rows = grid[header_row + 1:]
    brands = settings.get("bandeiras", [])
    hints = {}
    for f in ("amount", "credit", "debit", "gross", "fee", "net", "revenue", "expense", "paid_amount", "plan_total"):
        if f in mapping:
            hints[f] = infer_decimal_hint([r[mapping[f]] for r in data_rows if mapping[f] < len(r)])
    warnings: list[str] = []
    records: list[dict] = []
    skipped = 0
    declined = 0

    def money(row, f):
        return parse_decimal(_cell(row, mapping.get(f)), hints.get(f)) if f in mapping else None

    for offset, row in enumerate(data_rows):
        line = header_row + offset + 2  # número da linha no arquivo (1-based, após cabeçalho)
        if not row or all(_cell(row, i) is None for i in range(len(row))):
            continue
        g = lambda f: _cell(row, mapping.get(f)) if f in mapping else None  # noqa: E731
        first = norm(_text(row[0])) if row else ""
        if first.startswith("total") or first.startswith("subtotal"):
            continue
        rec: dict = {"row": line, "ids": {}, "extra": {}, "raw": _raw(headers, row)}

        if source == "bank":
            d = parse_date(g("date"))
            desc = scrub(_text(g("description")))
            if not d or "saldo" in norm(desc)[:12]:
                skipped += d is None
                continue
            amount = money(row, "amount")
            if amount is None:
                c, db = money(row, "credit"), money(row, "debit")
                if c is None and db is None:
                    skipped += 1
                    continue
                amount = abs(c or 0) - abs(db or 0)
            flag = norm(_text(g("cd_flag")))
            if flag in ("d", "debito") and amount > 0:
                amount = -amount
            comp = scrub(_text(g("complement")))
            lines = [x.strip() for x in comp.splitlines() if x.strip()]
            rec.update(date=_iso(d), amount=str(amount), description=desc,
                       counterparty=" ".join(lines[:2]) or scrub(_text(g("counterparty"))))
            if (doc := clean_id(g("doc"))):
                rec["ids"]["checknum"] = doc

        elif source == "erp":
            settle = parse_date(g("settle_date"))
            d = parse_date(g("date"))
            due = parse_date(g("due_date"))
            paid = money(row, "paid_amount")
            rev, exp, amt = money(row, "revenue"), money(row, "expense"), money(row, "amount")
            base = paid if paid not in (None, Decimal(0)) else next(
                (x for x in (exp, rev, amt) if x not in (None, Decimal(0))), None)
            if base is None or not (settle or d or due):
                skipped += 1
                continue
            nature = norm(_text(g("nature")))
            if (exp not in (None, Decimal(0))) or "desp" in nature or "pagar" in nature:
                sign = -1
            elif (rev not in (None, Decimal(0))) or "receit" in nature or "receber" in nature:
                sign = 1
            else:
                sign = -1 if base < 0 else 1
            inst, insts = _installments(g("installment"))
            rec.update(date=_iso(settle or d or due), amount=str(sign * abs(base)),
                       description=scrub(_text(g("description"))).replace("\n", " "),
                       counterparty=scrub(_text(g("counterparty"))), method=_text(g("method")) or None,
                       installment=inst, installments=insts)
            rec["extra"].update(data_lancamento=_iso(d), vencimento=_iso(due), pago=bool(settle or paid),
                                categoria=_text(g("category")) or None, conta=_text(g("account")) or None,
                                status=_text(g("status")) or None)
            if (doc := clean_id(g("doc"))):
                rec["ids"]["doc"] = doc

        else:  # machine / acquirer
            d = parse_date(g("date"))
            settle = parse_date(g("settle_date")) or parse_date(g("expected_date"))
            gross, fee, net, amt = money(row, "gross"), money(row, "fee"), money(row, "net"), money(row, "amount")
            if gross is None and amt is not None:
                gross = amt
            if source == "acquirer" and net is None and gross is not None:
                net = gross - abs(fee or 0)
            if gross is None and net is not None:
                gross = net + abs(fee or 0)
            if gross is None or not (d or settle):
                skipped += 1
                continue
            status = _text(g("status"))
            ns = norm(status)
            if source == "machine" and any(x in ns for x in ("negad", "nao autoriz", "recusad", "desfeit")):
                declined += 1
                continue
            cancel = norm(_text(g("cancel_flag")))
            cd = norm(_text(g("cd_flag")))
            method_txt = " ".join(x for x in (_text(g("method")), _text(g("plan"))) if x)
            kind = "venda"
            if "chargeback" in ns or "chargeback" in norm(method_txt):
                kind = "chargeback"
            elif (cancel and cancel not in ("000", "0", "n", "nao", "-")) or cd == "d" or gross < 0 \
                    or any(x in ns for x in ("cancel", "estorn")):
                kind = "cancelamento"
            inst, insts = _installments(g("installment"))
            ti_a, ti_b = _installments(g("installments"))
            total_inst = ti_b or ti_a
            insts = total_inst or insts
            if inst and not insts and source == "machine":
                insts, inst = inst, None
            brand_txt = _text(g("brand"))
            rec.update(date=_iso(d or settle), settle_date=_iso(settle), gross=str(gross),
                       fee=str(abs(fee)) if fee is not None else None,
                       net=str(net) if net is not None else None,
                       amount=str(net if (source == "acquirer" and net is not None) else gross),
                       brand=detect_brand(brand_txt, brands) or (norm(brand_txt) or None),
                       modality=detect_modality(method_txt, brand_txt) or detect_modality(_text(g("method"))),
                       installment=inst, installments=insts, kind=kind, status_src=status or None,
                       description=" ".join(x for x in (brand_txt, method_txt) if x),
                       counterparty=mask_card(_text(g("card"))) if g("card") else "")
            pt = money(row, "plan_total")
            if pt is not None:
                rec["plan_total"] = str(pt)
            if g("time"):
                rec["extra"]["hora"] = _text(g("time"))
            for f in ("nsu", "auth", "sale_id", "payment_order"):
                if (v := clean_id(g(f))):
                    rec["ids"][f] = v
        records.append(rec)

    if skipped:
        warnings.append(f"{skipped} linha(s) ignorada(s) por não conterem data/valor válidos.")
    if declined:
        warnings.append(f"{declined} transação(ões) negada(s)/não autorizada(s) desconsiderada(s): não geram recebimento.")
    return records, warnings


def parse_grid(grid: list[list], source: str, settings: dict, mapping: dict | None = None,
               header_row: int | None = None) -> dict:
    grid = [list(r) for r in grid if r is not None]
    if not grid:
        raise ParseError("O arquivo não contém linhas de dados.")
    width = max(len(r) for r in grid)
    grid = [r + [None] * (width - len(r)) for r in grid]
    hr = header_row if header_row is not None else find_header_row(grid, source)
    if hr is None:
        hr = 0
    headers = [_text(h) or f"Coluna {i + 1}" for i, h in enumerate(grid[hr])]
    auto = mapping is None
    mp = {k: int(v) for k, v in (mapping or auto_map(headers, source)).items() if v is not None and v != ""}
    missing = missing_required(mp, source)
    preview = [[_text(c.isoformat() if isinstance(c, (date, datetime)) else c) for c in r]
               for r in grid[hr + 1: hr + 11]]
    result = {
        "header_row": hr, "columns": headers, "mapping": mp, "auto_mapped": auto, "missing": missing,
        "signature": header_signature(grid[hr]), "preview": preview,
        "fields": [{"key": f, "label": FIELD_LABELS[f],
                    "required": any(f in g for g in REQUIRED[source])} for f in SOURCE_FIELDS[source]],
        "raw_grid_head": [[_text(c) for c in r] for r in grid[:12]],
    }
    if missing:
        result.update(needs_mapping=True, records=[], warnings=[])
        return result
    records, warnings = normalize_rows(grid, hr, mp, source, settings)
    if not records:
        result.update(needs_mapping=True, records=[],
                      warnings=["Nenhum registro válido com o mapeamento atual. Revise as colunas."])
        return result
    result.update(needs_mapping=False, records=records, warnings=warnings)
    return result
