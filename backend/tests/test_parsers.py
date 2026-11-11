import io
from decimal import Decimal

import openpyxl
import pytest

from app.parsers import ParseError, parse_file

OFX_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<?OFX OFXHEADER="200" VERSION="220" SECURITY="NONE" OLDFILEUID="NONE" NEWFILEUID="NONE"?>
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL</CURDEF>
<BANKACCTFROM><BANKID>001</BANKID><BRANCHID>1234</BRANCHID><ACCTID>998877</ACCTID></BANKACCTFROM>
<BANKTRANLIST><DTSTART>20261001</DTSTART><DTEND>20261031</DTEND>
<STMTTRN><TRNTYPE>CREDIT</TRNTYPE><DTPOSTED>20261005</DTPOSTED><TRNAMT>150.75</TRNAMT><FITID>A1</FITID>
<MEMO>PIX RECEBIDO</MEMO><NAME>CLIENTE TESTE</NAME></STMTTRN>
<STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20261006</DTPOSTED><TRNAMT>-80.00</TRNAMT><FITID>A2</FITID>
<CHECKNUM>555</CHECKNUM><MEMO>TARIFA</MEMO></STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


def test_ofx_sgml_cp1252(demo_bytes, settings):
    name, data = demo_bytes["bank"]
    r = parse_file(name, data, "bank", settings)
    assert r["format"] == "ofx" and not r["needs_mapping"]
    assert r["meta"]["periodo_inicio"] == "2026-10-01" and r["meta"]["periodo_fim"] == "2026-10-10"
    assert r["meta"]["conta"].endswith("45-6") and "12345" not in r["meta"]["conta"]  # conta mascarada
    debits = [x for x in r["records"] if Decimal(x["amount"]) < 0]
    assert any("DÉB.TIT.COMPE" in x["description"] for x in debits)  # acentos Windows-1252 preservados
    assert all("fitid" in x["ids"] for x in r["records"])


def test_ofx_xml(settings):
    r = parse_file("extrato.ofx", OFX_XML, "bank", settings)
    assert [x["amount"] for x in r["records"]] == ["150.75", "-80.00"]
    assert r["records"][1]["ids"]["checknum"] == "555"
    assert r["meta"]["moeda"] == "BRL"


def test_ofx_only_for_bank(settings):
    with pytest.raises(ParseError):
        parse_file("x.ofx", OFX_XML, "erp", settings)


def test_acquirer_csv_with_preamble(demo_bytes, settings):
    name, data = demo_bytes["acquirer"]
    r = parse_file(name, data, "acquirer", settings)
    assert not r["needs_mapping"] and r["header_row"] == 2
    rec = r["records"][0]
    assert {"gross", "fee", "net", "settle_date", "brand", "modality"} <= rec.keys()
    assert Decimal(rec["gross"]) - Decimal(rec["fee"]) == Decimal(rec["net"])
    assert any(x["kind"] == "cancelamento" and Decimal(x["amount"]) < 0 for x in r["records"])
    assert all(x["counterparty"].startswith("****") for x in r["records"])  # cartão mascarado
    assert any(x["installments"] == 3 for x in r["records"])


def test_erp_cp1252_signs(demo_bytes, settings):
    name, data = demo_bytes["erp"]
    r = parse_file(name, data, "erp", settings)
    amounts = [Decimal(x["amount"]) for x in r["records"]]
    assert any(a < 0 for a in amounts) and any(a > 0 for a in amounts)
    assert r["mapping"]["settle_date"] != r["mapping"]["date"]


def test_machine_ignores_declined(demo_bytes, settings):
    name, data = demo_bytes["machine"]
    r = parse_file(name, data, "machine", settings)
    assert r["warnings"] and all(x["ids"].get("nsu") != "7999991" for x in r["records"])


def test_xlsx_bank_statement_skips_balance_rows(settings):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["EXTRATO CONTA CORRENTE"])
    ws.append(["DATA", "DOCUMENTO", "HISTÓRICO", "INFORMAÇÕES COMPLEMENTARES", "VALOR"])
    ws.append(["11/11/2026", "Pix", "PIX RECEBIDO - OUTRA IF", "Recebimento Pix\nFULANO\n***.296.379-**", 354])
    ws.append(["11/11/2026", "98810840", "DÉB.TIT.COMPE EFETIVADO", "", -437])
    ws.append(["11/11/2026", "", "SALDO DO DIA", "", 3851.92])
    buf = io.BytesIO()
    wb.save(buf)
    r = parse_file("extrato.xlsx", buf.getvalue(), "bank", settings)
    assert [x["amount"] for x in r["records"]] == ["354", "-437"]
    assert r["records"][0]["counterparty"].startswith("Recebimento Pix FULANO")


def test_unknown_columns_require_mapping_then_manual_mapping(settings):
    data = "col_a;col_b;col_c\n05/10/2026;Venda balcão;150,00\n06/10/2026;Venda site;80,00\n".encode()
    r = parse_file("x.csv", data, "erp", settings)
    assert r["needs_mapping"] and r["missing"] and r["columns"] == ["col_a", "col_b", "col_c"]
    r2 = parse_file("x.csv", data, "erp", settings, mapping={"date": 0, "description": 1, "amount": 2}, header_row=0)
    assert not r2["needs_mapping"] and [x["amount"] for x in r2["records"]] == ["150.00", "80.00"]


@pytest.mark.parametrize("name,data", [
    ("a.exe", b"MZ\x90\x00"), ("a.csv", b"\x00\x01\x02binario"), ("a.csv", b""),
    ("a.xlsx", b"PK\x03\x04qualquercoisa"), ("a.csv", b"<!DOCTYPE html><html></html>"),
])
def test_rejects_invalid_files(name, data, settings):
    with pytest.raises(ParseError):
        parse_file(name, data, "erp", settings)


def test_pdf_with_table(settings):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4).build([Table([["Data", "Histórico", "Valor"],
                                                      ["01/10/2026", "PIX RECEBIDO", "150,00"],
                                                      ["02/10/2026", "TARIFA", "-9,90"]])])
    r = parse_file("extrato.pdf", buf.getvalue(), "bank", settings)
    assert r["format"] == "pdf"
    assert [x["amount"] for x in r["records"]] == ["150.00", "-9.90"]
