"""Gera arquivos FICTÍCIOS de demonstração (as quatro fontes), coerentes entre si.

DADOS DE DEMONSTRAÇÃO — nenhuma pessoa, empresa ou conta real.
Uso: python scripts/gerar_demo.py [pasta_destino]
"""
import csv
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent.parent / "public" / "demo")
OUT.mkdir(parents=True, exist_ok=True)
rnd = random.Random(20261001)
C = Decimal("0.01")
START, END = date(2026, 10, 1), date(2026, 10, 10)
RATES = {("debito", 1): Decimal("1.59"), ("credito", 1): Decimal("1.79"), ("credito", 3): Decimal("2.29")}
NAMES = ["CLIENTE DEMO ALFA", "CLIENTE DEMO BETA", "CLIENTE DEMO GAMA", "CLIENTE DEMO DELTA", "CLIENTE DEMO EPSILON",
         "CLIENTE DEMO ZETA", "CLIENTE DEMO ETA", "CLIENTE DEMO TETA"]


def q(v):
    return Decimal(v).quantize(C, rounding=ROUND_HALF_UP)


def br(v: Decimal, prefix=True):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + ("R$ " if prefix else "") + s


def bdays(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------- vendas (máquina)
sales = []
nsu = 7000100
day = date(2026, 8, 25)
while day <= date(2026, 10, 9):
    if day.weekday() < 6:
        for _ in range(rnd.randint(1, 3)):
            nsu += rnd.randint(3, 40)
            brand = rnd.choice(["Mastercard", "Visa", "Visa", "Mastercard", "Elo"])
            mod = rnd.choice(["debito", "debito", "credito", "credito", "credito_parc"])
            amount = q(rnd.choice([35, 49.9, 60, 89.9, 120, 145.5, 180, 230, 310, 450, 689.7]))
            n = 3 if mod == "credito_parc" else 1
            if n == 3:
                amount = q(amount * 3)
            sales.append({"date": day, "time": f"{rnd.randint(8, 19):02d}:{rnd.randint(0, 59):02d}:00",
                          "nsu": str(nsu), "auth": f"{rnd.randint(100000, 999999)}", "brand": brand,
                          "mod": "credito" if mod.startswith("credito") else "debito", "n": n, "amount": amount,
                          "status": "Aprovada"})
    day += timedelta(days=1)
# casos especiais
sales[-5]["status"] = "Cancelada"
sales.append({**sales[10], "nsu": "7999991", "status": "Negada"})  # negada: não entra

# ---------------------------------------------------------------- adquirente (parcelas liquidadas)
acq_rows = []
for s in sales:
    if s["status"] == "Negada":
        continue
    rate = RATES[(s["mod"], s["n"])] if (s["mod"], s["n"]) in RATES else RATES[("credito", 3)]
    if s["brand"] == "Elo" and s["mod"] == "credito":
        rate = Decimal("2.29") if s["n"] == 1 else Decimal("3.19")
    per = q(s["amount"] / s["n"])
    for k in range(1, s["n"] + 1):
        gross = per if k < s["n"] else s["amount"] - per * (s["n"] - 1)
        settle = bdays(s["date"] + timedelta(days=1 if s["mod"] == "debito" else 30 * k))
        if not (START <= settle <= END + timedelta(days=10)):
            continue
        fee = q(gross * rate / 100)
        acq_rows.append({"s": s, "k": k, "gross": gross, "fee": fee, "net": gross - fee, "settle": settle,
                         "cancel": False})
# taxa cobrada acima do contrato em uma venda
fee_case = next(r for r in acq_rows if r["s"]["mod"] == "credito" and r["s"]["n"] == 1 and r["settle"] <= END)
fee_case["fee"] = q(fee_case["gross"] * Decimal("2.50") / 100)
fee_case["net"] = fee_case["gross"] - fee_case["fee"]
# cancelamento: estorno abatido na liquidação seguinte
canc = sales[-6] if sales[-6]["status"] == "Cancelada" else next(s for s in sales if s["status"] == "Cancelada")
acq_rows.append({"s": canc, "k": 1, "gross": -canc["amount"], "fee": Decimal(0), "net": -canc["amount"],
                 "settle": bdays(canc["date"] + timedelta(days=1)), "cancel": True})
acq_rows = [r for r in acq_rows if not (r["s"] is canc and not r["cancel"] and r["settle"] > END)]

with open(OUT / "4_adquirente_DEMO.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["Relatório de vendas recebidas — DADOS DE DEMONSTRAÇÃO"])
    w.writerow(["Estabelecimento(s)", "DEMO-000000001"])
    w.writerow(["Nº do estabelecimento", "Data da transação", "Nº da transação", "ID Venda", "Bandeira",
                "Forma de Pagamento", "Plano de venda", "Parcela", "Total de parcela", "Número da autorização",
                "Número do cartão", "Indicador Crédito/Débito", "Indicador de cancelamento da venda",
                "Data prevista de liquidação", "Status", "Data do pagamento", "Valor parcela bruto",
                "Desconto parcela", "Valor parcela liquido", "Total plano de venda"])
    for r in sorted(acq_rows, key=lambda x: (x["settle"], x["s"]["nsu"])):
        s = r["s"]
        paid = r["settle"] <= END
        w.writerow(["DEMO-000000001", s["date"].strftime("%d/%m/%Y ") + s["time"],
                    "0" if r["cancel"] else s["nsu"], f"RRN: 9{s['nsu']}" if not r["cancel"] else "-", s["brand"],
                    "Débito" if s["mod"] == "debito" else "Crédito", "A vista" if s["n"] == 1 else "Parcelado Loja",
                    r["k"], s["n"], s["auth"] if not r["cancel"] else "0", "999999******0000",
                    "D" if r["cancel"] else "C", "001" if r["cancel"] else "000", r["settle"].strftime("%d/%m/%Y"),
                    "Pagamento Realizado" if paid else "Pagamento Previsto",
                    r["settle"].strftime("%d/%m/%Y") if paid else "-", br(r["gross"]), br(r["fee"]), br(r["net"]),
                    br(s["amount"] * (-1 if r["cancel"] else 1))])

with open(OUT / "3_maquina_cartao_DEMO.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["Data", "Hora", "NSU", "Autorização", "Bandeira", "Tipo", "Parcelas", "Valor", "Status"])
    settled = {id(r["s"]) for r in acq_rows}
    for s in sales:
        if id(s) not in settled and s["date"] < date(2026, 10, 1) and s["status"] != "Negada":
            continue
        w.writerow([s["date"].strftime("%d/%m/%Y"), s["time"], s["nsu"], s["auth"], s["brand"],
                    "Débito" if s["mod"] == "debito" else ("Crédito à vista" if s["n"] == 1 else "Crédito parcelado"),
                    s["n"], br(s["amount"], False), s["status"]])

# ---------------------------------------------------------------- banco
bank = []
groups = defaultdict(Decimal)
for r in acq_rows:
    if r["settle"] <= END:
        groups[(r["settle"], r["s"]["brand"], r["s"]["mod"])] += r["net"]
names = {"Mastercard": {"credito": "DEMOPAG_Cred._Mastercard", "debito": "DEMOPAG_Deb._Maestro"},
         "Visa": {"credito": "DEMOPAG_Cred._Visa", "debito": "DEMOPAG_Deb._Visa Electron"},
         "Elo": {"credito": "DEMOPAG_Cred._Elo", "debito": "DEMOPAG_Deb._Elo"}}
fee_key = (fee_case["settle"], fee_case["s"]["brand"], fee_case["s"]["mod"])
skipped_group = [k for k in sorted(groups) if k != fee_key][3]  # um grupo que o banco não creditou
for (d, b, m), v in sorted(groups.items()):
    if (d, b, m) == skipped_group:
        continue
    bank.append((d, v, f"CR COMPRAS {b.upper()}", names[b][m], f"88{rnd.randint(1000000, 9999999)}"))
bank.append((date(2026, 10, 7), Decimal("333.33"), "CR COMPRAS VISA", "DEMOPAG_Cred._Visa", "8800000001"))

erp = []  # (data lancamento, data pagamento, valor, fornecedor/cliente, forma, doc, descricao, natureza)
doc = 5000


def pay(d, v, who, forma, bank_memo, bank_name="", bank_date=None, bank_value=None, in_bank=True, in_erp=True):
    global doc
    doc += 1
    if in_erp:
        erp.append((d, d, v, who, forma, str(doc), f"Pagamento {who}", "Despesa" if v < 0 else "Receita"))
    if in_bank:
        bank.append((bank_date or d, bank_value if bank_value is not None else v, bank_memo, bank_name,
                     f"9{doc}" if forma == "Boleto" else "Pix"))


pay(date(2026, 10, 1), Decimal("-3450.00"), "IMOBILIARIA DEMO", "Boleto", "DÉB.TIT.COMPE EFETIVADO")
pay(date(2026, 10, 2), Decimal("-1280.40"), "DISTRIBUIDORA DEMO RAÇÕES", "Boleto", "DÉB.TIT.COMPE EFETIVADO",
    bank_date=date(2026, 10, 3))  # divergência de data
pay(date(2026, 10, 5), Decimal("-890.00"), "FORNECEDOR DEMO PETS", "Boleto", "DÉB.TIT.COMPE EFETIVADO",
    bank_value=Decimal("-897.12"))  # juros: divergência de valor
pay(date(2026, 10, 6), Decimal("-2500.00"), "COLABORADOR DEMO UM", "Depósito em conta", "PIX EMITIDO OUTRA IF",
    "Pagamento Pix COLABORADOR DEMO UM")
pay(date(2026, 10, 6), Decimal("-2500.00"), "COLABORADOR DEMO DOIS", "Depósito em conta", "PIX EMITIDO OUTRA IF",
    "Pagamento Pix COLABORADOR DEMO DOIS")
pay(date(2026, 10, 8), Decimal("-610.75"), "CONTABILIDADE DEMO", "Boleto", "DÉB.TIT.COMPE EFETIVADO", in_bank=False)
pay(date(2026, 10, 14), Decimal("-610.75"), "CONTABILIDADE DEMO", "Boleto", "", in_bank=False)  # futuro: pendente
for i, (d, v) in enumerate([(date(2026, 10, 2), "150.00"), (date(2026, 10, 2), "150.00"), (date(2026, 10, 7), "420.00")]):
    who = NAMES[i]
    pay(d, Decimal(v), who, "Pix", "PIX RECEBIDO - OUTRA IF", f"Recebimento Pix {who}")
bank.append((date(2026, 10, 9), Decimal("-29.90"), "DÉBITO PACOTE SERVIÇOS", "", "129"))
bank.append((date(2026, 10, 9), Decimal("1200.00"), "CRED.TED OUTRO BANCO", "REM.: EMPRESA DEMO PARCEIRA", "3071"))
erp.append(erp[0])  # lançamento duplicado no ERP

with open(OUT / "1_sistema_erp_DEMO.csv", "w", encoding="cp1252", newline="") as f:
    w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_ALL)
    w.writerow(["Data", "Conta", "Categoria", "Descrição", "Fornecedor", "Parcela", "Competência", "Receita",
                "Despesa", "Vencimento", "Pagamento", "Valor pago", "Forma pagamento", "Documento", "Natureza",
                "Observação"])
    for d, pd, v, who, forma, dc, desc, nat in erp:
        w.writerow([d.strftime("%d/%m/%Y"), "Banco Demonstração", "Fornecedores" if v < 0 else "Vendas",
                    desc + " (DEMONSTRAÇÃO)", who, "", d.strftime("%d/%m/%Y"),
                    br(v, False) if v > 0 else "", br(v, False) if v < 0 else "", pd.strftime("%d/%m/%Y"),
                    pd.strftime("%d/%m/%Y") if pd <= END else "", br(abs(v), False) if pd <= END else "", forma, dc,
                    nat, "DADOS FICTÍCIOS"])

bank.sort(key=lambda x: (x[0], -x[1]))
lines = ["OFXHEADER:100", "DATA:OFXSGML", "VERSION:102", "SECURITY:NONE", "ENCODING:USASCII", "CHARSET:1252",
         "COMPRESSION:NONE", "OLDFILEUID:NONE", "NEWFILEUID:NONE", "<OFX>", "<SIGNONMSGSRSV1>", "<SONRS>",
         "<STATUS>", "<CODE>0</CODE>", "<SEVERITY>INFO</SEVERITY>", "</STATUS>",
         "<DTSERVER>20261010120000[-3:BRT]</DTSERVER>", "<LANGUAGE>POR</LANGUAGE>",
         "<FI>", "<ORG>Banco Demonstração (FICTÍCIO)</ORG>", "<FID>999</FID>", "</FI>", "</SONRS>",
         "</SIGNONMSGSRSV1>", "<BANKMSGSRSV1>", "<STMTTRNRS>", "<TRNUID>1</TRNUID>", "<STATUS>", "<CODE>0</CODE>",
         "<SEVERITY>INFO</SEVERITY>", "</STATUS>", "<STMTRS>", "<CURDEF>BRL</CURDEF>", "<BANKACCTFROM>",
         "<BANKID>999</BANKID>", "<BRANCHID>0001-0</BRANCHID>", "<ACCTID>12345-6</ACCTID>",
         "<ACCTTYPE>CHECKING</ACCTTYPE>", "</BANKACCTFROM>", "<BANKTRANLIST>",
         f"<DTSTART>{START:%Y%m%d}120000[-3:BRT]</DTSTART>", f"<DTEND>{END:%Y%m%d}120000[-3:BRT]</DTEND>"]
for i, (d, v, memo, name, chk) in enumerate(bank, start=1):
    lines += ["<STMTTRN>", f"<TRNTYPE>{'CREDIT' if v > 0 else 'DEBIT'}</TRNTYPE>",
              f"<DTPOSTED>{d:%Y%m%d}120000[-3:BRT]</DTPOSTED>", f"<TRNAMT>{v:.2f}</TRNAMT>",
              f"<FITID>{d:%Y%m%d}{i:05d}</FITID>", f"<CHECKNUM>{chk if chk.isdigit() else 0}</CHECKNUM>",
              f"<REFNUM>{chk}</REFNUM>", f"<MEMO>{memo}</MEMO>"] + ([f"<NAME>{name}</NAME>"] if name else []) + \
             ["</STMTTRN>"]
lines += ["</BANKTRANLIST>", "<LEDGERBAL>", "<BALAMT>10000.00</BALAMT>", f"<DTASOF>{END:%Y%m%d}</DTASOF>",
          "</LEDGERBAL>", "</STMTRS>", "</STMTTRNRS>", "</BANKMSGSRSV1>", "</OFX>"]
(OUT / "2_extrato_bancario_DEMO.ofx").write_bytes("\r\n".join(lines).encode("cp1252"))
print(f"Arquivos de demonstração gerados em {OUT}")
