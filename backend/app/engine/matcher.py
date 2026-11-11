"""Motor de conciliação por regras determinísticas.

Cada vínculo (match) registra nível, regra aplicada, confiança e justificativa, para
que o resultado seja rastreável e auditável. Nenhuma IA é usada: quando há mais de
um candidato possível, a conciliação NÃO é feita automaticamente.

Níveis:
  1 - Identificador único (FITID, NSU, autorização, ID da venda, documento, ordem de pagamento)
  2 - Valor e data exatos
  3 - Valor com tolerância de data
  4 - Valores agrupados (vários lançamentos = uma liquidação), por soma exata
  5 - Valor líquido (bruto - taxa esperada)
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from ..parsers.common import norm, q2, to_cents
from ..parsers.mapping import detect_brand

# ----------------------------------------------------------------------------- status
STATUS_LABELS = {
    "conciliado": "Conciliado",
    "divergencia_valor": "Divergência de valor",
    "divergencia_data": "Divergência de data",
    "taxa_divergente": "Taxa divergente",
    "pendente_liquidacao": "Pendente de liquidação",
    "nao_localizado_banco": "Não localizado no banco",
    "nao_localizado_sistema": "Não localizado no sistema",
    "duplicidade": "Duplicidade",
    "estorno_cancelamento": "Estorno/cancelamento",
    "analise_manual": "Necessita análise manual",
}
SOURCE_LABELS = {"erp": "ERP", "bank": "Banco", "machine": "Máquina", "acquirer": "Adquirente"}
LEVEL_LABELS = {1: "Identificador único", 2: "Valor e data exatos", 3: "Valor com tolerância de data",
                4: "Valores agrupados", 5: "Valor líquido (taxas)"}

BANK_KIND_LABELS = {
    "cartao": "crédito de cartão (adquirente)", "cartao_debito": "débito de adquirente", "pix": "PIX",
    "boleto": "boleto/título", "tarifa": "tarifa bancária", "aplicacao": "aplicação/resgate (movimentação interna)",
    "transferencia": "TED/transferência", "convenio": "débito de convênio/automático", "emprestimo": "empréstimo",
    "estorno": "estorno/devolução", "outros": "lançamento sem identificação",
}


@dataclass
class Txn:
    uid: str
    source: str
    rec: dict
    date: date | None
    settle: date | None
    amount: Decimal
    cents: int
    ids: dict
    desc: str
    party: str
    brand: str | None = None
    modality: str | None = None
    kind: str | None = None
    method_kinds: set | None = None  # ERP: tipos de lançamento bancário compatíveis
    gross: Decimal | None = None
    fee: Decimal | None = None
    status: str | None = None
    justification: str = ""
    unmatched_status: str | None = None
    unmatched_justification: str = ""
    match_ids: list = field(default_factory=list)
    level: int | None = None
    confidence: float | None = None
    found: Decimal | None = None
    difference: Decimal | None = None
    excluded: bool = False  # duplicado/pendente: fora do cruzamento
    notes: list = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return bool(self.match_ids)


@dataclass
class Match:
    id: str
    level: int
    rule: str
    confidence: float
    state: str  # auto | sugerido
    status: str
    left: list
    right: list
    left_total: Decimal
    right_total: Decimal
    justification: str

    @property
    def difference(self) -> Decimal:
        return q2(self.right_total - self.left_total)


def _d(v) -> Decimal | None:
    if v is None or v == "":
        return None
    return Decimal(str(v))


def _date(v) -> date | None:
    return date.fromisoformat(v) if v else None


def _brl(v: Decimal | None) -> str:
    if v is None:
        return "-"
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-R$ " if v < 0 else "R$ ") + s


def _fmt_date(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "-"


_STOP = {"pix", "recebimento", "pagamento", "fav", "rem", "ltda", "de", "da", "do", "dos", "das", "outra",
         "transf", "transferencia", "realizada", "sicoob", "emitido", "recebido", "com", "eireli", "me", "sa",
         "folha", "pro-labore", "labore", "pro"}


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z]{2,}", norm(text)) if w not in _STOP}


class Engine:
    def __init__(self, records: dict[str, list[dict]], settings: dict, period: tuple[date, date] | None = None):
        self.s = settings
        self.tol = int(settings.get("tolerancia_valor_centavos", 0))
        self.tol_days = int(settings.get("tolerancia_dias", 3))
        self.div_pct = Decimal(str(settings.get("divergencia_valor_max_percentual", 5)))
        self.fee_tol = int(settings.get("tolerancia_taxa_centavos", 1))
        self.max_group = int(settings.get("max_itens_agrupamento", 40))
        self.rules = settings.get("regras", {})
        self.matches: list[Match] = []
        self.txns: dict[str, list[Txn]] = {}
        self.log: list[str] = []
        for source, recs in records.items():
            self.txns[source] = [self._build(source, i, r) for i, r in enumerate(recs or [])]
        self.period = period or self._infer_period()

    # ------------------------------------------------------------------ construção
    def _build(self, source: str, i: int, r: dict) -> Txn:
        amount = _d(r.get("amount")) or Decimal(0)
        t = Txn(uid=f"{source}:{i}", source=source, rec=r, date=_date(r.get("date")),
                settle=_date(r.get("settle_date")), amount=q2(amount), cents=to_cents(amount),
                ids={k: str(v) for k, v in (r.get("ids") or {}).items() if v}, desc=r.get("description") or "",
                party=r.get("counterparty") or "", brand=r.get("brand"), modality=r.get("modality"),
                kind=r.get("kind"), gross=_d(r.get("gross")), fee=_d(r.get("fee")))
        if source == "bank":
            self._classify_bank(t)
        elif source == "erp":
            t.method_kinds = self._erp_method_kinds(r.get("method"))
        return t

    def _classify_bank(self, t: Txn) -> None:
        text = norm(f"{t.desc} {t.party}")
        descriptors = [norm(d) for d in self.s.get("descritores_cartao_banco", [])]
        is_card = any(d and re.search(r"(^|[^a-z])" + re.escape(d) + r"($|[^a-z])", text) for d in descriptors)
        if is_card and "pix" not in text:
            t.kind = "cartao" if t.amount > 0 else "cartao_debito"
            party = norm(t.party)
            t.modality = "debito" if ("deb" in party.split(" ")[1:2] or re.search(r"\bdeb\b|maestro|electron", text)
                                      or "deb." in party) else "credito"
            t.brand = detect_brand(f"{t.party} {t.desc}", self.s.get("bandeiras", []))
            return
        rules = [
            ("pix", r"\bpix\b"), ("boleto", r"tit\.?\s?compe|boleto|titulo"),
            ("tarifa", r"tarifa|pacote serv|cesta|anuidade|\btar\b"),
            ("aplicacao", r"\brdc\b|aplicac|resgate|\bcdb\b|poupanca|invest"),
            ("transferencia", r"\bted\b|\bdoc\b|transf"), ("emprestimo", r"emprest|financiam"),
            ("estorno", r"estorno|devoluc"), ("convenio", r"conv\b|conv\.|convenio|deb\.? autom|debito autom"),
        ]
        t.kind = next((k for k, rx in rules if re.search(rx, text)), "outros")

    @staticmethod
    def _erp_method_kinds(method) -> set | None:
        m = norm(method)
        if not m:
            return None
        if "boleto" in m or "titulo" in m:
            return {"boleto"}
        if any(x in m for x in ("deposito", "transfer", "pix", "ted", "doc")):
            return {"pix", "transferencia"}
        if "cartao" in m or "credito" in m or "debito" in m and "autom" not in m:
            return {"cartao", "cartao_debito"}
        if "autom" in m or "convenio" in m:
            return {"convenio", "tarifa"}
        if "dinheiro" in m or "especie" in m:
            return set()
        return None

    def _infer_period(self) -> tuple[date, date] | None:
        dates = [t.date for t in self.txns.get("bank", []) if t.date]
        if not dates:
            dates = [t.date for ts in self.txns.values() for t in ts if t.date]
        return (min(dates), max(dates)) if dates else None

    # ------------------------------------------------------------------ utilidades
    def _new_match(self, level, rule, conf, status, left, right, justification, state=None) -> Match:
        lt = q2(sum((t.amount for t in left), Decimal(0)))
        rt = q2(sum((t.amount for t in right), Decimal(0)))
        if state is None:
            state = "sugerido" if status in ("divergencia_valor", "analise_manual") else "auto"
        m = Match(id=f"M{len(self.matches) + 1}", level=level, rule=rule, confidence=conf, state=state,
                  status=status, left=[t.uid for t in left], right=[t.uid for t in right],
                  left_total=lt, right_total=rt, justification=justification)
        self.matches.append(m)
        for side, other_total in ((left, rt), (right, lt)):
            for t in side:
                t.match_ids.append(m.id)
                if t.status in (None, "conciliado") or status != "conciliado":
                    t.status = status
                    t.level, t.confidence = level, conf
                    t.found = other_total
                    own = q2(sum((x.amount for x in side), Decimal(0)))
                    t.difference = q2(other_total - own)
                    grp = f" Grupo com {len(side)} lançamento(s) somando {_brl(own)}." if len(side) > 1 else ""
                    t.justification = justification + grp
        return m

    def _within_amount(self, a: int, b: int) -> bool:
        return abs(a - b) <= self.tol

    def _days(self, a: date | None, b: date | None) -> int:
        if not a or not b:
            return 9999
        return abs((a - b).days)

    def _unique_pairs(self, lefts, rights, pred, tie=None):
        """Retorna pares (l, r) com correspondência mutuamente única. Ambíguos ficam de fora."""
        cand_l = {l.uid: [r for r in rights if pred(l, r)] for l in lefts}
        cand_r = defaultdict(list)
        for l in lefts:
            for r in cand_l[l.uid]:
                cand_r[r.uid].append(l)
        pairs, ambiguous = [], []
        for l in lefts:
            cs = cand_l[l.uid]
            if not cs:
                continue
            if len(cs) == 1 and len(cand_r[cs[0].uid]) == 1:
                pairs.append((l, cs[0], False))
                continue
            if tie:
                best = self._tie_break(l, cs, tie)
                if best is not None and self._tie_break(best, cand_r[best.uid], tie) is l:
                    pairs.append((l, best, True))
                    continue
            ambiguous.append((l, cs))
        return pairs, ambiguous

    @staticmethod
    def _tie_break(item, candidates, scorer):
        scored = sorted(((scorer(item, c), c) for c in candidates), key=lambda x: -x[0])
        if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return scored[0][1]
        return None

    @staticmethod
    def _name_score(a: Txn, b: Txn) -> int:
        return len(_tokens(f"{a.party} {a.desc}") & _tokens(f"{b.party} {b.desc}"))

    def _unique_subset(self, items: list[Txn], target: int):
        """Busca um subconjunto ÚNICO cuja soma = alvo (± tolerância). Retorna lista, 'ambiguo' ou None."""
        if len(items) > self.max_group:
            return "complexo"
        vals = [t.cents for t in items]
        positive = all(v > 0 for v in vals)
        states: dict[int, tuple[int, tuple]] = {0: (1, ())}
        for idx, v in enumerate(vals):
            new = dict(states)
            for s, (cnt, path) in states.items():
                ns = s + v
                if positive and ns > target + self.tol:
                    continue
                if ns in new:
                    c0, p0 = new[ns]
                    new[ns] = (min(2, c0 + cnt), p0)
                else:
                    new[ns] = (cnt, path + (idx,))
            states = new
            if len(states) > 400_000:
                return "complexo"
        hits = [(s, states[s]) for s in range(target - self.tol, target + self.tol + 1) if s in states and s != 0]
        total = sum(c for _, (c, _) in hits)
        if total == 0:
            return None
        if total > 1:
            return "ambiguo"
        return [items[i] for i in hits[0][1][1]]

    # ------------------------------------------------------------------ duplicidades
    def mark_duplicates(self):
        for source, txns in self.txns.items():
            seen: dict[tuple, Txn] = {}
            for t in txns:
                key = None
                if source == "bank":
                    if t.ids.get("fitid"):
                        key = ("fitid", t.ids["fitid"])
                    elif (c := t.ids.get("checknum")) and c.isdigit() and len(c) >= 5:
                        key = ("doc", c, t.date, t.cents, norm(t.desc))
                elif source == "erp":
                    key = ("erp", t.date, t.cents, t.ids.get("doc"), norm(t.party), norm(t.desc),
                           t.rec.get("installment"), t.rec.get("installments"))
                else:
                    ident = t.ids.get("nsu") or t.ids.get("sale_id")
                    if ident:
                        key = ("card", ident, t.rec.get("installment"), t.cents, t.kind)
                if key is None:
                    continue
                if key in seen:
                    t.status, t.excluded = "duplicidade", True
                    t.justification = (f"Registro em duplicidade com a linha {seen[key].rec.get('row')} "
                                       f"do mesmo arquivo (mesmos identificadores, data e valor).")
                    t.unmatched_status, t.unmatched_justification = t.status, t.justification
                else:
                    seen[key] = t

    # ------------------------------------------------------------------ máquina x adquirente
    def machine_vs_acquirer(self):
        machine = [t for t in self.txns.get("machine", []) if not t.excluded]
        acq = [t for t in self.txns.get("acquirer", []) if not t.excluded]
        for m in machine:
            m.unmatched_status = "estorno_cancelamento" if m.kind in ("cancelamento", "chargeback") else "pendente_liquidacao"
            m.unmatched_justification = ("Cancelamento/estorno registrado na máquina sem correspondência na adquirente."
                                         if m.kind in ("cancelamento", "chargeback") else
                                         "Venda da máquina ainda sem liquidação no relatório da adquirente.")
        if not machine or not acq:
            return
        by_id = defaultdict(list)
        for a in acq:
            for k in ("nsu", "sale_id"):
                if a.ids.get(k):
                    by_id[(k, a.ids[k])].append(a)
        used = set()
        if self.rules.get("nivel1_identificador", True):
            for m in machine:
                group = []
                for k in ("nsu", "sale_id"):
                    if m.ids.get(k):
                        group = [a for a in by_id.get((k, m.ids[k]), []) if a.uid not in used]
                        if group:
                            break
                if not group and m.ids.get("auth"):
                    group = [a for a in acq if a.uid not in used and a.ids.get("auth") == m.ids["auth"]
                             and a.date == m.date and (not m.brand or not a.brand or a.brand == m.brand)]
                if not group:
                    continue
                sale_total = _d(group[0].rec.get("plan_total")) or sum((a.gross or a.amount for a in group), Decimal(0))
                diff = to_cents(sale_total) - abs(m.cents)
                status = "conciliado" if abs(diff) <= self.tol else "divergencia_valor"
                ids = ", ".join(f"{k.upper()} {v}" for k, v in m.ids.items())
                just = (f"Nível 1: venda da máquina localizada na adquirente pelo identificador ({ids}). "
                        f"Valor da venda {_brl(m.amount)}; total do plano na adquirente {_brl(sale_total)}.")
                mt = self._new_match(1, "maquina_adquirente_identificador", 1.0 if status == "conciliado" else 0.9,
                                     status, [m], [], just)
                mt.right = [a.uid for a in group]
                mt.right_total = q2(sale_total)
                m.found, m.difference = q2(sale_total), q2(sale_total - abs(m.amount))
                for a in group:
                    used.add(a.uid)
                    a.notes.append(f"Venda localizada no arquivo da máquina (linha {m.rec.get('row')}).")
        remaining_m = [m for m in machine if not m.matched]
        remaining_a = [a for a in acq if a.uid not in used and (a.rec.get("installment") in (None, 1))]
        for level, pred_days in ((2, 0), (3, self.tol_days)):
            if not self.rules.get("nivel2_valor_data" if level == 2 else "nivel3_tolerancia_data", True):
                continue

            def pred(m, a, days=pred_days):
                total = _d(a.rec.get("plan_total")) or a.gross or a.amount
                return (self._within_amount(abs(m.cents), to_cents(total)) and self._days(m.date, a.date) <= days
                        and (not m.brand or not a.brand or m.brand == a.brand)
                        and (not m.modality or not a.modality or m.modality == a.modality))
            pairs, _ = self._unique_pairs(remaining_m, remaining_a, pred)
            for m, a, _tie in pairs:
                st = "conciliado" if m.date == a.date else "divergencia_data"
                self._new_match(level, "maquina_adquirente_valor_data", 0.95 if level == 2 else 0.85, st, [m], [a],
                                f"Nível {level}: venda da máquina corresponde à venda da adquirente por valor, "
                                f"bandeira e data ({_fmt_date(m.date)} x {_fmt_date(a.date)}).")
                used.add(a.uid)
            remaining_m = [m for m in remaining_m if not m.matched]
            remaining_a = [a for a in remaining_a if a.uid not in used]
        machine_dates = [m.date for m in machine if m.date]
        if machine_dates:
            lo, hi = min(machine_dates), max(machine_dates)
            for a in acq:
                if a.uid not in used and a.date and lo <= a.date <= hi and a.kind == "venda":
                    a.notes.append("Venda não localizada no arquivo da máquina de cartão.")

    # ------------------------------------------------------------------ adquirente x banco
    def _expected_fee(self, t: Txn) -> tuple[Decimal | None, Decimal | None]:
        if t.gross is None or not t.modality:
            return None, None
        n = int(t.rec.get("installments") or 1)
        best, best_spec = None, -1
        for rule in self.s.get("taxas", []):
            if rule.get("modalidade") and rule["modalidade"] != t.modality:
                continue
            b = (rule.get("bandeira") or "*").lower()
            if b not in ("*", "", t.brand or ""):
                continue
            if not (int(rule.get("parcelas_min", 1)) <= n <= int(rule.get("parcelas_max", 99))):
                continue
            spec = 1 if b not in ("*", "") else 0
            if spec > best_spec:
                best, best_spec = rule, spec
        if not best:
            return None, None
        rate = Decimal(str(best["taxa"]))
        return q2(abs(t.gross) * rate / 100), rate

    def acquirer_vs_bank(self):
        acq_all = [t for t in self.txns.get("acquirer", []) if not t.excluded]
        if not acq_all:
            return
        start, end = self.period or (None, None)
        has_bank = bool(self.txns.get("bank"))
        acq = []
        for a in acq_all:
            st = norm(a.rec.get("status_src") or "")
            when = a.settle or a.date
            a.unmatched_status = "nao_localizado_banco"
            a.unmatched_justification = (f"Liquidação de {_brl(a.amount)} prevista para {_fmt_date(when)} "
                                         f"não localizada no extrato bancário.")
            if a.kind in ("cancelamento", "chargeback"):
                a.unmatched_status = "estorno_cancelamento"
                a.unmatched_justification = (f"{'Chargeback' if a.kind == 'chargeback' else 'Cancelamento/estorno'} "
                                             f"de {_brl(a.amount)} não localizado como abatimento no extrato.")
            pending_flag = any(x in st for x in ("previst", "agendad", "pendente", "futur", "a pagar", "aguardando"))
            if (end and when and when > end) or pending_flag or not has_bank:
                a.status, a.excluded = "pendente_liquidacao", True
                a.justification = (f"Liquidação prevista para {_fmt_date(when)}, após o fim do extrato "
                                   f"({_fmt_date(end)})." if end and when and when > end else
                                   "Liquidação ainda não realizada segundo a adquirente.")
                a.unmatched_status, a.unmatched_justification = a.status, a.justification
                continue
            if start and when and when < start - timedelta(days=self.tol_days):
                a.status, a.excluded = "nao_localizado_banco", True
                a.justification = f"Liquidação em {_fmt_date(when)}, anterior ao período do extrato bancário."
                a.unmatched_status, a.unmatched_justification = a.status, a.justification
                continue
            acq.append(a)
        bank = [b for b in self.txns.get("bank", []) if not b.excluded and b.kind in ("cartao", "cartao_debito")
                and not b.matched]

        def key_ok(a: Txn, b: Txn) -> bool:
            return (not a.brand or not b.brand or a.brand == b.brand) and \
                   (not a.modality or not b.modality or a.modality == b.modality)

        # Nível 1: ordem de pagamento da adquirente = documento do crédito no banco
        if self.rules.get("nivel1_identificador", True):
            groups = defaultdict(list)
            for a in acq:
                if a.ids.get("payment_order"):
                    groups[a.ids["payment_order"]].append(a)
            for po, items in groups.items():
                cands = [b for b in bank if not b.matched and po in b.ids.values()]
                if len(cands) == 1:
                    b = cands[0]
                    diff = abs(sum(i.cents for i in items) - b.cents)
                    st = "conciliado" if diff <= self.tol else "divergencia_valor"
                    self._new_match(1, "adquirente_banco_ordem_pagamento", 1.0 if st == "conciliado" else 0.9, st,
                                    items, [b], f"Nível 1: ordem de pagamento {po} da adquirente localizada no extrato.")

        def remaining():
            return [a for a in acq if not a.matched], [b for b in bank if not b.matched]

        def gkey(t: Txn, d: date | None):
            return (d, t.brand, t.modality)

        # Nível 4a: soma do grupo (data de pagamento + bandeira + modalidade) = um único crédito
        if self.rules.get("nivel4_agrupado", True):
            ra, rb = remaining()
            groups = defaultdict(list)
            for a in ra:
                groups[gkey(a, a.settle or a.date)].append(a)
            for (d, brand, mod), items in sorted(groups.items(), key=lambda x: str(x[0])):
                if len(items) < 2:
                    continue
                total = sum(i.cents for i in items)
                cands = [b for b in rb if not b.matched and b.date == d and key_ok(items[0], b)
                         and self._within_amount(b.cents, total)]
                if len(cands) == 1:
                    self._new_match(4, "adquirente_banco_grupo_dia_bandeira", 0.97, "conciliado", items, cands,
                                    f"Nível 4: crédito de {_brl(cands[0].amount)} em {_fmt_date(d)} corresponde à soma "
                                    f"líquida de {len(items)} transações {brand or ''} {mod or ''} liquidadas no dia.")

        # Níveis 2 e 3: 1 para 1
        for level, days in ((2, 0), (3, self.tol_days)):
            if not self.rules.get("nivel2_valor_data" if level == 2 else "nivel3_tolerancia_data", True):
                continue
            ra, rb = remaining()
            pairs, _ = self._unique_pairs(
                ra, rb, lambda a, b, dd=days: self._within_amount(a.cents, b.cents) and key_ok(a, b)
                and self._days(a.settle or a.date, b.date) <= dd)
            for a, b, _ in pairs:
                same = (a.settle or a.date) == b.date
                self._new_match(level, "adquirente_banco_valor_data", 0.95 if level == 2 else 0.85,
                                "conciliado" if same else "divergencia_data", [a], [b],
                                f"Nível {level}: liquidação de {_brl(a.amount)} ({_fmt_date(a.settle or a.date)}) "
                                f"localizada no extrato em {_fmt_date(b.date)}.")

        if self.rules.get("nivel4_agrupado", True):
            # Nível 4b: N para M por data+bandeira+modalidade
            ra, rb = remaining()
            ga, gb = defaultdict(list), defaultdict(list)
            for a in ra:
                ga[gkey(a, a.settle or a.date)].append(a)
            for b in rb:
                gb[gkey(b, b.date)].append(b)
            for k, items in ga.items():
                credits = gb.get(k, [])
                if len(credits) >= 2 and self._within_amount(sum(i.cents for i in items), sum(c.cents for c in credits)):
                    self._new_match(4, "adquirente_banco_grupo_n_m", 0.9, "conciliado", items, credits,
                                    f"Nível 4: {len(items)} liquidações somam exatamente os {len(credits)} créditos "
                                    f"de {k[1] or ''} {k[2] or ''} em {_fmt_date(k[0])}.")
            # Nível 4c: subconjunto único de liquidações = um crédito
            ra, rb = remaining()
            for b in sorted(rb, key=lambda x: (x.date or date.min, -x.cents)):
                pool = [a for a in ra if not a.matched and (a.settle or a.date) == b.date and key_ok(a, b)]
                if len(pool) < 2:
                    continue
                res = self._unique_subset(pool, b.cents)
                if isinstance(res, list) and len(res) >= 2:
                    self._new_match(4, "adquirente_banco_subconjunto", 0.88, "conciliado", res, [b],
                                    f"Nível 4: crédito de {_brl(b.amount)} corresponde à soma de um único subconjunto "
                                    f"de {len(res)} liquidações do dia {_fmt_date(b.date)}.")
                elif res == "ambiguo":
                    b.notes.append("Mais de uma combinação de liquidações soma este valor: requer análise manual.")

        # Nível 5: valor líquido calculado (bruto - taxa esperada) quando a adquirente não informa líquido
        if self.rules.get("nivel5_liquido", True):
            ra, rb = remaining()
            for a in ra:
                if a.rec.get("net") or a.gross is None:
                    continue
                fee, rate = self._expected_fee(a)
                if fee is None:
                    continue
                expected = to_cents(a.gross - fee)
                cands = [b for b in rb if not b.matched and abs(b.cents - expected) <= max(self.tol, self.fee_tol)
                         and self._days(a.settle or a.date, b.date) <= self.tol_days and key_ok(a, b)]
                if len(cands) == 1:
                    self._new_match(5, "adquirente_banco_liquido_taxa", 0.8, "conciliado", [a], cands,
                                    f"Nível 5: bruto {_brl(a.gross)} - taxa esperada {rate}% = {_brl(a.gross - fee)}, "
                                    f"localizado no extrato.")

        # Verificação de taxas e status finais
        for a in acq_all:
            fee_exp, rate = self._expected_fee(a)
            if a.fee is not None and fee_exp is not None and a.kind == "venda" \
                    and abs(to_cents(a.fee) - to_cents(fee_exp)) > self.fee_tol:
                msg = (f"Taxa cobrada {_brl(a.fee)} ({(a.fee / abs(a.gross) * 100):.2f}%) difere da esperada "
                       f"{_brl(fee_exp)} ({rate}%) para {a.brand or ''} {a.modality or ''} "
                       f"{a.rec.get('installments') or 1}x.")
                a.notes.append(msg)
                if a.matched and a.status in ("conciliado", "divergencia_data"):
                    a.status = "taxa_divergente"
                    a.justification = msg + " " + a.justification
            if a.kind in ("cancelamento", "chargeback") and a.matched:
                a.status = "estorno_cancelamento"
                a.justification = ("Estorno/cancelamento abatido na liquidação: " + a.justification)
        for b in self.txns.get("bank", []):
            if b.kind in ("cartao", "cartao_debito") and not b.matched and not b.excluded:
                b.unmatched_status = "nao_localizado_sistema"
                b.unmatched_justification = (f"Crédito de cartão {b.brand or ''} {b.modality or ''} sem liquidação "
                                             f"correspondente no relatório da adquirente (verifique outros "
                                             f"estabelecimentos/terminais ou o período do relatório).")

    # ------------------------------------------------------------------ ERP x banco
    def erp_vs_bank(self):
        erp_all = [t for t in self.txns.get("erp", []) if not t.excluded]
        if not erp_all:
            return
        start, end = self.period or (None, None)
        erp = []
        for e in erp_all:
            e.unmatched_status = "nao_localizado_banco"
            e.unmatched_justification = f"Lançamento de {_brl(e.amount)} em {_fmt_date(e.date)} não localizado no extrato."
            if e.method_kinds == set():
                e.unmatched_justification += " Forma de pagamento em dinheiro não transita pelo banco."
            if e.rec.get("extra", {}).get("pago") is False:
                e.status, e.excluded = "pendente_liquidacao", True
                e.justification = "Título em aberto no sistema (sem data de pagamento)."
            elif end and e.date and e.date > end:
                e.status, e.excluded = "pendente_liquidacao", True
                e.justification = (f"Pagamento/recebimento previsto para {_fmt_date(e.date)}, após o fim do extrato "
                                   f"({_fmt_date(end)}).")
            elif start and e.date and e.date < start - timedelta(days=self.tol_days):
                e.status, e.excluded = "nao_localizado_banco", True
                e.justification = f"Lançamento em {_fmt_date(e.date)}, anterior ao período do extrato."
            if e.excluded:
                e.unmatched_status, e.unmatched_justification = e.status, e.justification
                continue
            erp.append(e)

        def bank_pool():
            return [b for b in self.txns.get("bank", []) if not b.matched and not b.excluded]

        def compatible(e: Txn, b: Txn, strict=True) -> bool:
            if (e.amount > 0) != (b.amount > 0):
                return False
            if e.method_kinds is None or not strict:
                return True
            return b.kind in e.method_kinds

        def rem():
            return [e for e in erp if not e.matched], bank_pool()

        # Nível 1: documento do ERP igual ao identificador bancário
        if self.rules.get("nivel1_identificador", True):
            ra, rb = rem()
            for e in ra:
                doc = e.ids.get("doc")
                if not doc or len(doc) < 4:
                    continue
                cands = [b for b in rb if not b.matched and doc in b.ids.values() and compatible(e, b, False)]
                if len(cands) == 1:
                    b = cands[0]
                    st = "conciliado" if self._within_amount(e.cents, b.cents) else "divergencia_valor"
                    self._new_match(1, "erp_banco_documento", 1.0 if st == "conciliado" else 0.9, st, [e], [b],
                                    f"Nível 1: documento {doc} do sistema igual ao identificador do extrato.")

        for level, days in ((2, 0), (3, self.tol_days)):
            if not self.rules.get("nivel2_valor_data" if level == 2 else "nivel3_tolerancia_data", True):
                continue
            for strict in (True, False):
                while True:
                    ra, rb = rem()
                    pairs, _ = self._unique_pairs(
                        ra, rb, lambda e, b, dd=days, st=strict: compatible(e, b, st)
                        and self._within_amount(e.cents, b.cents) and self._days(e.date, b.date) <= dd,
                        tie=self._name_score)
                    if not pairs:
                        break
                    for e, b, tie in pairs:
                        method_ok = e.method_kinds is None or b.kind in e.method_kinds
                        same = e.date == b.date
                        reason = f"Nível {level}: mesmo valor ({_brl(e.amount)})"
                        reason += " e mesma data" if same else f" com {self._days(e.date, b.date)} dia(s) de diferença"
                        reason += f" ({_fmt_date(e.date)} x {_fmt_date(b.date)})"
                        if tie:
                            reason += "; desempate pelo nome do favorecido/pagador"
                        if method_ok and e.method_kinds:
                            reason += f"; forma de pagamento compatível ({e.rec.get('method')} x {BANK_KIND_LABELS.get(b.kind, b.kind)})"
                        elif e.method_kinds:
                            reason += f"; ATENÇÃO: forma de pagamento diferente ({e.rec.get('method')} x {BANK_KIND_LABELS.get(b.kind, b.kind)})"
                        conf = (0.95 if level == 2 else 0.85) - (0.05 if tie else 0) - (0.1 if not method_ok else 0)
                        st = "conciliado" if same else "divergencia_data"
                        state = "sugerido" if not method_ok else None
                        if state:
                            st = "analise_manual"
                        self._new_match(level, "erp_banco_valor_data", round(conf, 2), st, [e], [b], reason + ".", state)

        # Nível 4: agrupamentos (um pagamento no banco = vários lançamentos no ERP e vice-versa)
        if self.rules.get("nivel4_agrupado", True):
            ra, rb = rem()
            for b in sorted(rb, key=lambda x: (x.date or date.min, x.cents)):
                pool = [e for e in ra if not e.matched and e.date == b.date and compatible(e, b)]
                if len(pool) >= 2:
                    res = self._unique_subset(pool, b.cents) if b.cents > 0 else None
                    if b.cents < 0:
                        neg = [Txn(**{**e.__dict__, "cents": -e.cents}) for e in pool]
                        r2 = self._unique_subset(neg, -b.cents)
                        res = [pool[neg.index(x)] for x in r2] if isinstance(r2, list) else r2
                    if isinstance(res, list) and len(res) >= 2:
                        self._new_match(4, "erp_banco_agrupado", 0.85, "conciliado", res, [b],
                                        f"Nível 4: lançamento bancário de {_brl(b.amount)} corresponde à soma de "
                                        f"{len(res)} lançamentos do sistema na mesma data.")
            ra, rb = rem()
            for e in ra:
                pool = [b for b in rb if not b.matched and b.date == e.date and compatible(e, b)]
                if len(pool) >= 2:
                    sign = 1 if e.cents > 0 else -1
                    mirror = [Txn(**{**b.__dict__, "cents": sign * b.cents}) for b in pool]
                    res = self._unique_subset(mirror, abs(e.cents))
                    if isinstance(res, list) and len(res) >= 2:
                        chosen = [pool[mirror.index(x)] for x in res]
                        self._new_match(4, "erp_banco_agrupado", 0.8, "conciliado", [e], chosen,
                                        f"Nível 4: lançamento do sistema de {_brl(e.amount)} corresponde à soma de "
                                        f"{len(chosen)} lançamentos bancários na mesma data.")

        # Nível 5: recebimento em cartão no ERP (bruto) x crédito no banco (líquido de taxa)
        if self.rules.get("nivel5_liquido", True):
            ra, rb = rem()
            rates = sorted({Decimal(str(r["taxa"])) for r in self.s.get("taxas", [])})
            for e in ra:
                if e.amount <= 0 or not e.method_kinds or "cartao" not in e.method_kinds:
                    continue
                found = []
                for rate in rates:
                    expected = to_cents(e.amount - q2(e.amount * rate / 100))
                    for b in rb:
                        if not b.matched and b.kind == "cartao" and abs(b.cents - expected) <= max(self.tol, self.fee_tol) \
                                and self._days(e.date, b.date) <= self.tol_days + 30:
                            found.append((b, rate))
                if len({b.uid for b, _ in found}) == 1:
                    b, rate = found[0]
                    self._new_match(5, "erp_banco_liquido_taxa", 0.75, "conciliado",
                                    [e], [b], f"Nível 5: valor bruto {_brl(e.amount)} menos taxa de {rate}% "
                                    f"corresponde ao crédito de {_brl(b.amount)} em {_fmt_date(b.date)}.")

        # Sugestões de divergência de valor (sempre exigem aprovação manual)
        if self.rules.get("sugerir_divergencia_valor", True):
            ra, rb = rem()

            def near(e, b):
                if not compatible(e, b) or self._days(e.date, b.date) > self.tol_days:
                    return False
                diff = abs(e.cents - b.cents)
                return 0 < diff and Decimal(diff) <= abs(Decimal(e.cents)) * self.div_pct / 100

            pairs, _ = self._unique_pairs(ra, rb, near, tie=lambda e, b: -abs(e.cents - b.cents) + 10**9)
            for e, b, _ in pairs:
                self._new_match(2 if e.date == b.date else 3, "erp_banco_divergencia_valor", 0.6, "divergencia_valor",
                                [e], [b],
                                f"Sugestão: mesmo tipo de lançamento e data próxima, porém valor diferente "
                                f"(sistema {_brl(e.amount)} x banco {_brl(b.amount)}; diferença "
                                f"{_brl(b.amount - e.amount)}). Possíveis juros, multa, desconto ou pagamento parcial.")

        ambiguous_note = "Há mais de um lançamento bancário possível com o mesmo valor: requer análise manual."
        ra, rb = rem()
        for e in ra:
            cands = [b for b in rb if compatible(e, b, False) and self._within_amount(e.cents, b.cents)
                     and self._days(e.date, b.date) <= self.tol_days]
            if len(cands) > 1:
                e.unmatched_status = "analise_manual"
                e.unmatched_justification = ambiguous_note + " Candidatos: " + "; ".join(
                    f"{_fmt_date(b.date)} {b.desc[:30]} {b.party[:30]}" for b in cands[:5])

    # ------------------------------------------------------------------ finalização
    def finalize(self):
        for source, txns in self.txns.items():
            for t in txns:
                if t.unmatched_status is None:
                    if source == "bank":
                        t.unmatched_status = "nao_localizado_sistema"
                        t.unmatched_justification = (f"Lançamento bancário ({BANK_KIND_LABELS.get(t.kind, t.kind)}) "
                                                     f"sem correspondência nos demais arquivos.")
                    elif source == "erp":
                        t.unmatched_status = "nao_localizado_banco"
                        t.unmatched_justification = "Lançamento do sistema não localizado no extrato."
                    elif source == "acquirer":
                        t.unmatched_status = "nao_localizado_banco"
                        t.unmatched_justification = "Liquidação não localizada no extrato."
                    else:
                        t.unmatched_status = "pendente_liquidacao"
                        t.unmatched_justification = "Venda sem liquidação identificada."
                if t.status is None:
                    t.status, t.justification = t.unmatched_status, t.unmatched_justification
                if t.notes:
                    extra = " ".join(n for n in t.notes if n not in t.justification)
                    if extra:
                        t.justification = (t.justification + " " + extra).strip()

    def run(self) -> dict:
        self.mark_duplicates()
        self.machine_vs_acquirer()
        self.acquirer_vs_bank()
        self.erp_vs_bank()
        self.finalize()
        return self.result()

    def result(self) -> dict:
        txns = []
        for source in ("erp", "bank", "machine", "acquirer"):
            for t in self.txns.get(source, []):
                ident = next((f"{k.upper()} {v}" for k, v in t.ids.items()
                              if k in ("nsu", "fitid", "doc", "auth", "sale_id", "checknum")), "")
                txns.append({
                    "uid": t.uid, "source": source, "row": t.rec.get("row"),
                    "date": t.date.isoformat() if t.date else None,
                    "settle_date": t.settle.isoformat() if t.settle else None,
                    "identifier": ident, "description": t.desc, "counterparty": t.party,
                    "amount": str(t.amount), "found_amount": str(t.found) if t.found is not None else None,
                    "difference": str(t.difference) if t.difference is not None else None,
                    "status": t.status, "justification": t.justification.strip(),
                    "unmatched_status": t.unmatched_status, "unmatched_justification": t.unmatched_justification,
                    "level": t.level, "confidence": t.confidence, "match_ids": t.match_ids,
                    "kind": t.kind, "brand": t.brand, "modality": t.modality,
                    "gross": str(t.gross) if t.gross is not None else None,
                    "fee": str(t.fee) if t.fee is not None else None,
                    "data": t.rec,
                })
        matches = [{
            "id": m.id, "level": m.level, "rule": m.rule, "confidence": m.confidence, "state": m.state,
            "status": m.status, "left": m.left, "right": m.right, "left_total": str(m.left_total),
            "right_total": str(m.right_total), "difference": str(m.difference), "justification": m.justification,
        } for m in self.matches]
        return {"transactions": txns, "matches": matches,
                "period": [self.period[0].isoformat(), self.period[1].isoformat()] if self.period else None}


def reconcile(records: dict[str, list[dict]], settings: dict, period: tuple[date, date] | None = None) -> dict:
    return Engine(records, settings, period).run()
