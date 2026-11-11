"""Exportação de relatórios: XLSX (abas por status), CSV, PDF executivo e PDF de divergências."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from ..engine import LEVEL_LABELS, SOURCE_LABELS, STATUS_LABELS

COLUMNS = [("date", "Data"), ("settle_date", "Data liquidação"), ("identifier", "Identificação"),
           ("description", "Descrição"), ("counterparty", "Cliente/Favorecido"), ("source", "Origem"),
           ("amount", "Valor original"), ("found_amount", "Valor encontrado"), ("difference", "Diferença"),
           ("status", "Status"), ("level", "Nível"), ("confidence", "Confiança"), ("justification", "Justificativa"),
           ("note", "Observação")]


def brl(v) -> str:
    if v in (None, ""):
        return "-"
    v = Decimal(str(v))
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-R$ " if v < 0 else "R$ ") + s


def br_date(v) -> str:
    if not v:
        return ""
    try:
        return date.fromisoformat(str(v)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(v)


def _row(t: dict) -> list:
    out = []
    for key, _ in COLUMNS:
        v = t.get(key)
        if key in ("date", "settle_date"):
            v = br_date(v)
        elif key == "source":
            v = SOURCE_LABELS.get(v, v)
        elif key == "status":
            v = STATUS_LABELS.get(v, v)
        elif key == "level":
            v = f"{v} - {LEVEL_LABELS[v]}" if v else ""
        elif key == "confidence":
            v = f"{round(v * 100)}%" if v else ""
        out.append(v)
    return out


def to_csv(transactions: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([label for _, label in COLUMNS])
    for t in transactions:
        row = _row(t)
        for i, (key, _) in enumerate(COLUMNS):
            if key in ("amount", "found_amount", "difference") and row[i] not in (None, ""):
                row[i] = str(row[i]).replace(".", ",")
        w.writerow(row)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(rec: dict, transactions: list[dict], matches: list[dict], summary_rows: list[tuple]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="0F3D3E")
    head_font = Font(color="FFFFFF", bold=True)
    money_fmt = '"R$" #,##0.00;[Red]-"R$" #,##0.00'

    ws = wb.active
    ws.title = "Resumo"
    ws.append(["Conciliação Inteligente — Resumo"])
    ws["A1"].font = Font(bold=True, size=14)
    for label, value in summary_rows:
        ws.append([label, value])
        if isinstance(value, (Decimal, float)):
            ws.cell(ws.max_row, 2).number_format = money_fmt
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 40

    def sheet(title: str, rows: list[dict]):
        s = wb.create_sheet(title[:31])
        s.append([label for _, label in COLUMNS])
        for c in s[1]:
            c.fill, c.font = head_fill, head_font
        for t in rows:
            r = _row(t)
            for i, (key, _) in enumerate(COLUMNS):
                if key in ("amount", "found_amount", "difference") and r[i] not in (None, ""):
                    r[i] = float(Decimal(str(r[i])))
            s.append(r)
            for i, (key, _) in enumerate(COLUMNS, start=1):
                if key in ("amount", "found_amount", "difference"):
                    s.cell(s.max_row, i).number_format = money_fmt
        widths = [12, 14, 22, 40, 32, 12, 15, 16, 13, 24, 26, 10, 80, 30]
        for i, w in enumerate(widths, start=1):
            s.column_dimensions[get_column_letter(i)].width = w
        s.freeze_panes = "A2"
        s.auto_filter.ref = s.dimensions
        for row in s.iter_rows(min_row=2, min_col=13, max_col=13):
            for c in row:
                c.alignment = Alignment(wrap_text=False)

    sheet("Todas", transactions)
    for status, label in STATUS_LABELS.items():
        rows = [t for t in transactions if t["status"] == status]
        if rows:
            sheet(label.replace("/", "-"), rows)

    ms = wb.create_sheet("Vínculos (auditoria)")
    ms.append(["Vínculo", "Nível", "Regra", "Situação", "Status", "Confiança", "Total A", "Total B", "Diferença",
               "Lançamentos A", "Lançamentos B", "Justificativa", "Observação"])
    for c in ms[1]:
        c.fill, c.font = head_fill, head_font
    for m in matches:
        ms.append([m["code"], f'{m["level"]} - {LEVEL_LABELS[m["level"]]}', m["rule"], m["state"],
                   STATUS_LABELS.get(m["status"], m["status"]), f'{round(m["confidence"] * 100)}%',
                   float(m["left_total"]), float(m["right_total"]), float(m["difference"]),
                   ", ".join(m["left"]), ", ".join(m["right"]), m["justification"], m.get("note", "")])
        for i in (7, 8, 9):
            ms.cell(ms.max_row, i).number_format = money_fmt
    for i, w in enumerate([10, 26, 34, 12, 22, 10, 14, 14, 12, 30, 30, 90, 30], start=1):
        ms.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf_doc(buf, title):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate

    return SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28,
                             bottomMargin=28, title=title, author="Conciliação Inteligente")


def _styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=18, textColor=colors.HexColor("#0F3D3E")),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=colors.HexColor("#0F3D3E")),
        "p": ParagraphStyle("p", parent=ss["BodyText"], fontSize=9, leading=12),
        "small": ParagraphStyle("s", parent=ss["BodyText"], fontSize=7, leading=9),
    }


def _table(data, widths, header_color="#0F3D3E"):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6F6")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D6D6")),
    ]))
    return t


def to_pdf_executive(rec: dict, totals: dict, transactions: list[dict]) -> bytes:
    from reportlab.platypus import Paragraph, Spacer

    st = _styles()
    buf = io.BytesIO()
    doc = _pdf_doc(buf, "Relatório executivo de conciliação")
    els = [Paragraph("Conciliação Inteligente — Relatório Executivo", st["h1"]),
           Paragraph(f"Processamento <b>{rec['code']}</b> (versão {rec['version']}) • Período "
                     f"{br_date(rec['period_start'])} a {br_date(rec['period_end'])} • Gerado em "
                     f"{datetime.now().strftime('%d/%m/%Y %H:%M')} • Responsável: {rec.get('user', '-')}", st["p"]),
           Spacer(1, 10), Paragraph("Resumo financeiro", st["h2"])]
    kpis = [["Indicador", "Valor"],
            ["Valor total de vendas (cartão)", brl(totals["valor_total_vendas"])],
            ["Valor total recebido no banco (créditos)", brl(totals["valor_total_recebido"])],
            ["Valor conciliado no extrato (créditos + débitos)", brl(totals["total_conciliado"])],
            ["Percentual de conciliação (registros)", f"{totals['percentual_conciliacao']:.2f}%".replace(".", ",")],
            ["Percentual de conciliação (valor do extrato)",
             f"{totals['percentual_conciliacao_valor_banco']:.2f}%".replace(".", ",")],
            ["Total pendente de liquidação", brl(totals["total_pendente"])],
            ["Registros com divergência", str(totals["total_divergencias"])],
            ["Diferenças financeiras identificadas (líquido)", brl(totals["diferencas_financeiras"])],
            ["Taxas de adquirência no período", brl(totals["taxas_adquirencia"])],
            ["Sugestões aguardando aprovação", str(totals["sugestoes_pendentes"])]]
    els.append(_table(kpis, [330, 200]))
    els += [Spacer(1, 10), Paragraph("Registros por origem", st["h2"])]
    src = [["Origem", "Registros", "Conciliados", "Valor líquido"]]
    for k, v in totals["registros_por_fonte"].items():
        src.append([SOURCE_LABELS.get(k, k), v["registros"], v["conciliados"], brl(v["valor"])])
    els.append(_table(src, [160, 90, 90, 140]))
    els += [Spacer(1, 10), Paragraph("Resultado por status", st["h2"])]
    sts = [["Status", "Registros", "Valor (absoluto)"]]
    for k, label in STATUS_LABELS.items():
        if k in totals["por_status"]:
            v = totals["por_status"][k]
            sts.append([label, v["registros"], brl(v["valor"])])
    els.append(_table(sts, [220, 90, 140]))
    div = [t for t in transactions if t["status"] in ("divergencia_valor", "divergencia_data", "taxa_divergente",
                                                       "analise_manual", "duplicidade")]
    if div:
        els += [Spacer(1, 10), Paragraph(f"Principais divergências ({min(len(div), 25)} de {len(div)})", st["h2"])]
        rows = [["Data", "Origem", "Descrição", "Valor", "Encontrado", "Diferença", "Status"]]
        for t in sorted(div, key=lambda x: -abs(Decimal(x["difference"] or 0)))[:25]:
            rows.append([br_date(t["date"]), SOURCE_LABELS[t["source"]], Paragraph(t["description"][:80], st["small"]),
                         brl(t["amount"]), brl(t["found_amount"]), brl(t["difference"]),
                         STATUS_LABELS[t["status"]]])
        els.append(_table(rows, [55, 60, 280, 75, 75, 65, 110]))
    els += [Spacer(1, 12), Paragraph(
        "As conciliações foram feitas exclusivamente por regras determinísticas (identificador, valor, data, "
        "agrupamento e valor líquido). Cada vínculo registra nível, regra e justificativa para auditoria.", st["small"])]
    doc.build(els)
    return buf.getvalue()


def to_pdf_divergences(rec: dict, transactions: list[dict], matches_by_code: dict) -> bytes:
    from reportlab.platypus import Paragraph, Spacer

    st = _styles()
    buf = io.BytesIO()
    doc = _pdf_doc(buf, "Relatório detalhado de divergências")
    els = [Paragraph("Relatório Detalhado de Divergências", st["h1"]),
           Paragraph(f"Processamento {rec['code']} • Período {br_date(rec['period_start'])} a "
                     f"{br_date(rec['period_end'])}", st["p"]), Spacer(1, 8)]
    groups = ["divergencia_valor", "divergencia_data", "taxa_divergente", "analise_manual", "duplicidade",
              "nao_localizado_banco", "nao_localizado_sistema", "pendente_liquidacao", "estorno_cancelamento"]
    for g in groups:
        rows = [t for t in transactions if t["status"] == g]
        if not rows:
            continue
        total = sum((abs(Decimal(t["amount"])) for t in rows), Decimal(0))
        els.append(Paragraph(f"{STATUS_LABELS[g]} — {len(rows)} registro(s), {brl(total)}", st["h2"]))
        data = [["Data", "Origem", "Identificação", "Descrição", "Valor", "Encontrado", "Dif.", "Justificativa"]]
        for t in rows[:400]:
            data.append([br_date(t["date"]), SOURCE_LABELS[t["source"]], Paragraph(t["identifier"] or "-", st["small"]),
                         Paragraph(f'{t["description"][:70]} {t["counterparty"][:40]}', st["small"]),
                         brl(t["amount"]), brl(t["found_amount"]), brl(t["difference"]),
                         Paragraph((t["justification"] or "")[:400] + (f' Obs.: {t["note"]}' if t.get("note") else ""),
                                   st["small"])])
        els.append(_table(data, [50, 52, 70, 160, 62, 62, 48, 282]))
        els.append(Spacer(1, 8))
    if len(els) == 3:
        els.append(Paragraph("Nenhuma divergência encontrada.", st["p"]))
    doc.build(els)
    return buf.getvalue()


def summary_rows(rec: dict, totals: dict) -> list[tuple]:
    return [
        ("Processamento", rec["code"]), ("Versão", rec["version"]),
        ("Período", f"{br_date(rec['period_start'])} a {br_date(rec['period_end'])}"),
        ("Responsável", rec.get("user", "-")), ("Data do processamento", br_date(rec["created_at"])),
        ("Arquivos", ", ".join(f"{SOURCE_LABELS.get(f['source'], f['source'])}: {f['filename']}" for f in rec["files"])),
        ("Valor total de vendas", Decimal(totals["valor_total_vendas"])),
        ("Valor total recebido (créditos no banco)", Decimal(totals["valor_total_recebido"])),
        ("Valor conciliado no extrato", Decimal(totals["total_conciliado"])),
        ("Total pendente", Decimal(totals["total_pendente"])),
        ("Diferenças financeiras (líquido)", Decimal(totals["diferencas_financeiras"])),
        ("Taxas de adquirência", Decimal(totals["taxas_adquirencia"])),
        ("Registros com divergência", totals["total_divergencias"]),
        ("% conciliação (registros)", f"{totals['percentual_conciliacao']}%"),
        ("% conciliação (valor do extrato)", f"{totals['percentual_conciliacao_valor_banco']}%"),
    ]


def summary_csv(rec: dict, totals: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Indicador", "Valor"])
    for k, v in summary_rows(rec, totals):
        w.writerow([k, str(v).replace(".", ",") if isinstance(v, Decimal) else v])
    w.writerow([])
    w.writerow(["Status", "Registros", "Valor"])
    for k, label in STATUS_LABELS.items():
        if k in totals["por_status"]:
            w.writerow([label, totals["por_status"][k]["registros"], totals["por_status"][k]["valor"].replace(".", ",")])
    return ("﻿" + buf.getvalue()).encode("utf-8")
