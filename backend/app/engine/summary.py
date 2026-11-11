"""Cálculo dos totais e indicadores do dashboard a partir das transações e vínculos."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

ACTIVE = ("auto", "aprovado")
DIVERGENCE = ("divergencia_valor", "divergencia_data", "taxa_divergente", "analise_manual", "duplicidade")


def _d(v) -> Decimal:
    return Decimal(str(v)) if v not in (None, "") else Decimal(0)


def summarize(transactions: list[dict], matches: list[dict]) -> dict:
    states = {m["id"]: m["state"] for m in matches}

    def reconciled(t) -> bool:
        return any(states.get(mid) in ACTIVE for mid in (t.get("match_ids") or []))

    by_source = defaultdict(lambda: {"registros": 0, "valor": Decimal(0), "conciliados": 0})
    by_status = defaultdict(lambda: {"registros": 0, "valor": Decimal(0)})
    by_day = defaultdict(lambda: {"conciliado": Decimal(0), "nao_conciliado": Decimal(0)})
    valid = [t for t in transactions if t["status"] != "duplicidade"]
    for t in transactions:
        amt = _d(t["amount"])
        s = by_source[t["source"]]
        s["registros"] += 1
        s["valor"] += amt
        s["conciliados"] += 1 if reconciled(t) else 0
        st = by_status[t["status"]]
        st["registros"] += 1
        st["valor"] += abs(amt)
        if t["source"] == "bank" and t.get("date"):
            by_day[t["date"]]["conciliado" if reconciled(t) else "nao_conciliado"] += abs(amt)

    has_machine = any(t["source"] == "machine" for t in transactions)
    sales_src = "machine" if has_machine else "acquirer"
    total_vendas = sum((_d(t.get("gross") or t["amount"]) for t in transactions
                        if t["source"] == sales_src and t.get("kind") in (None, "venda")), Decimal(0))
    bank = [t for t in transactions if t["source"] == "bank" and t["status"] != "duplicidade"]
    total_recebido = sum((_d(t["amount"]) for t in bank if _d(t["amount"]) > 0), Decimal(0))
    bank_abs = sum((abs(_d(t["amount"])) for t in bank), Decimal(0))
    bank_rec = sum((abs(_d(t["amount"])) for t in bank if reconciled(t)), Decimal(0))
    total_conciliado = bank_rec
    pend = sum((abs(_d(t["amount"])) for t in transactions if t["status"] == "pendente_liquidacao"), Decimal(0))
    div_count = sum(1 for t in transactions if t["status"] in DIVERGENCE)
    diffs = [_d(m["difference"]) for m in matches if m["state"] != "rejeitado" and _d(m["difference"]) != 0]
    rec_count = sum(1 for t in valid if reconciled(t))
    taxas = sum((_d(t.get("fee")) for t in transactions if t["source"] == "acquirer" and t.get("kind") == "venda"),
                Decimal(0))

    def money(d: dict) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}

    return {
        "registros_por_fonte": {k: money(v) for k, v in by_source.items()},
        "valor_total_vendas": str(total_vendas),
        "valor_total_recebido": str(total_recebido),
        "total_conciliado": str(total_conciliado),
        "total_divergencias": div_count,
        "valor_divergencias": str(sum((abs(x) for x in diffs), Decimal(0))),
        "total_pendente": str(pend),
        "percentual_conciliacao": round(rec_count / len(valid) * 100, 2) if valid else 0.0,
        "percentual_conciliacao_valor_banco": round(float(bank_rec / bank_abs * 100), 2) if bank_abs else 0.0,
        "diferencas_financeiras": str(sum(diffs, Decimal(0))),
        "taxas_adquirencia": str(taxas),
        "transacoes": len(transactions),
        "conciliadas": rec_count,
        "sugestoes_pendentes": sum(1 for m in matches if m["state"] == "sugerido"),
        "por_status": {k: money(v) for k, v in by_status.items()},
        "por_dia": [{"data": d, **money(v)} for d, v in sorted(by_day.items())],
        "por_divergencia": {k: by_status[k]["registros"] for k in DIVERGENCE if k in by_status},
        "por_nivel": {str(lv): sum(1 for m in matches if m["level"] == lv and m["state"] in ACTIVE) for lv in range(1, 6)},
    }
