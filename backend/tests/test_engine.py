from datetime import date

from app.engine import reconcile, summarize

P = (date(2026, 10, 1), date(2026, 10, 10))


def bank(d, amount, memo, name="", **ids):
    return {"date": d, "amount": amount, "description": memo, "counterparty": name, "ids": ids, "row": 1}


def acq(d, settle, gross, fee, brand="visa", modality="credito", n=1, **kw):
    from decimal import Decimal
    return {"date": d, "settle_date": settle, "gross": gross, "fee": fee,
            "net": str(Decimal(gross) - Decimal(fee)), "amount": str(Decimal(gross) - Decimal(fee)),
            "brand": brand, "modality": modality, "installments": n, "kind": kw.get("kind", "venda"),
            "ids": kw.get("ids", {}), "row": 1, "status_src": kw.get("status", "Pagamento Realizado")}


def erp(d, amount, who, method="Boleto", **ids):
    return {"date": d, "amount": amount, "counterparty": who, "description": who, "method": method, "ids": ids,
            "row": 1, "extra": {"pago": True}}


def by_uid(res):
    return {t["uid"]: t for t in res["transactions"]}


def test_grouped_settlement_level4(settings):
    res = reconcile({
        "acquirer": [acq("2026-09-05", "2026-10-05", "100.00", "1.79"), acq("2026-09-05", "2026-10-05", "200.00", "3.58")],
        "bank": [bank("2026-10-05", "294.63", "CR COMPRAS VISA", "SIPAG_Cred._Visa")],
    }, settings, P)
    t = by_uid(res)
    assert t["bank:0"]["status"] == "conciliado" and t["bank:0"]["level"] == 4
    assert t["acquirer:0"]["status"] == t["acquirer:1"]["status"] == "conciliado"


def test_brand_must_match(settings):
    res = reconcile({"acquirer": [acq("2026-09-05", "2026-10-05", "100.00", "1.79", brand="mastercard")],
                     "bank": [bank("2026-10-05", "98.21", "CR COMPRAS VISA", "SIPAG_Cred._Visa")]}, settings, P)
    assert by_uid(res)["bank:0"]["status"] == "nao_localizado_sistema"


def test_fee_divergence(settings):
    res = reconcile({"acquirer": [acq("2026-09-05", "2026-10-05", "100.00", "3.00")],
                     "bank": [bank("2026-10-05", "97.00", "CR COMPRAS VISA", "SIPAG_Cred._Visa")]}, settings, P)
    t = by_uid(res)["acquirer:0"]
    assert t["status"] == "taxa_divergente" and "1.79" in t["justification"]


def test_cancellation_offsets_group(settings):
    res = reconcile({"acquirer": [acq("2026-10-04", "2026-10-05", "100.00", "1.59", modality="debito"),
                                  acq("2026-10-04", "2026-10-05", "-40.00", "0", modality="debito", kind="cancelamento")],
                     "bank": [bank("2026-10-05", "58.41", "CR COMPRAS VISA ELECTRON", "SIPAG_Deb._Visa Electron")]},
                    settings, P)
    t = by_uid(res)
    assert t["bank:0"]["status"] == "conciliado"
    assert t["acquirer:1"]["status"] == "estorno_cancelamento"


def test_future_settlement_is_pending(settings):
    res = reconcile({"acquirer": [acq("2026-09-20", "2026-10-20", "100.00", "1.79")],
                     "bank": [bank("2026-10-05", "1.00", "TARIFA")]}, settings, P)
    assert by_uid(res)["acquirer:0"]["status"] == "pendente_liquidacao"


def test_ambiguous_is_never_auto_matched(settings):
    res = reconcile({"erp": [erp("2026-10-06", "-500.00", "", method="")],
                     "bank": [bank("2026-10-06", "-500.00", "PIX EMITIDO", "Pagamento Pix A"),
                              bank("2026-10-06", "-500.00", "PIX EMITIDO", "Pagamento Pix B")]}, settings, P)
    t = by_uid(res)
    assert t["erp:0"]["status"] == "analise_manual" and not t["erp:0"]["match_ids"]
    assert not res["matches"]


def test_tie_break_by_name(settings):
    res = reconcile({"erp": [erp("2026-10-06", "-500.00", "Maria Souza", "Pix"), erp("2026-10-06", "-500.00", "Joao Lima", "Pix")],
                     "bank": [bank("2026-10-06", "-500.00", "PIX EMITIDO", "Pagamento Pix JOAO LIMA"),
                              bank("2026-10-06", "-500.00", "PIX EMITIDO", "Pagamento Pix MARIA SOUZA")]}, settings, P)
    m = {tuple(x["left"] + x["right"]) for x in res["matches"]}
    assert m == {("erp:0", "bank:1"), ("erp:1", "bank:0")}


def test_date_tolerance_and_value_divergence(settings):
    res = reconcile({"erp": [erp("2026-10-02", "-1280.40", "Fornecedor A"), erp("2026-10-05", "-890.00", "Fornecedor B")],
                     "bank": [bank("2026-10-03", "-1280.40", "DEB.TIT.COMPE EFETIVADO"),
                              bank("2026-10-05", "-897.12", "DEB.TIT.COMPE EFETIVADO")]}, settings, P)
    t = by_uid(res)
    assert t["erp:0"]["status"] == "divergencia_data" and t["erp:0"]["level"] == 3
    assert t["erp:1"]["status"] == "divergencia_valor" and t["erp:1"]["difference"] == "-7.12"
    sug = [m for m in res["matches"] if m["state"] == "sugerido"]
    assert len(sug) == 1 and sug[0]["status"] == "divergencia_valor"


def test_date_tolerance_setting(settings):
    settings["tolerancia_dias"] = 0
    settings["regras"]["sugerir_divergencia_valor"] = False
    res = reconcile({"erp": [erp("2026-10-02", "-100.00", "X")],
                     "bank": [bank("2026-10-03", "-100.00", "DEB.TIT.COMPE")]}, settings, P)
    assert by_uid(res)["erp:0"]["status"] == "nao_localizado_banco"


def test_identifier_level1(settings):
    res = reconcile({"erp": [erp("2026-10-02", "-100.00", "X", "Boleto", doc="98810840")],
                     "bank": [bank("2026-10-08", "-100.00", "DEB.TIT.COMPE", checknum="98810840")]}, settings, P)
    assert by_uid(res)["erp:0"]["level"] == 1


def test_grouped_erp_payments(settings):
    res = reconcile({"erp": [erp("2026-10-02", "-100.00", "A"), erp("2026-10-02", "-250.00", "B"),
                             erp("2026-10-02", "-77.00", "C")],
                     "bank": [bank("2026-10-02", "-350.00", "DEB.TIT.COMPE")]}, settings, P)
    t = by_uid(res)
    assert t["bank:0"]["level"] == 4 and t["erp:2"]["status"] == "nao_localizado_banco"


def test_duplicates(settings):
    res = reconcile({"erp": [erp("2026-10-02", "-100.00", "A"), erp("2026-10-02", "-100.00", "A")],
                     "bank": [bank("2026-10-02", "-100.00", "DEB.TIT.COMPE", fitid="1"), bank("2026-10-02", "-100.00", "DEB.TIT.COMPE", fitid="1")]},
                    settings, P)
    st = [t["status"] for t in res["transactions"]]
    assert st.count("duplicidade") == 2 and st.count("conciliado") == 2


def test_machine_vs_acquirer_by_nsu(settings):
    machine = [{"date": "2026-09-05", "amount": "300.00", "gross": "300.00", "brand": "visa", "modality": "credito",
                "ids": {"nsu": "123"}, "kind": "venda", "row": 2}]
    a = acq("2026-09-05", "2026-10-05", "100.00", "2.29", n=3, ids={"nsu": "123"})
    a["plan_total"] = "300.00"
    res = reconcile({"machine": machine, "acquirer": [a],
                     "bank": [bank("2026-10-05", "97.71", "CR COMPRAS VISA", "SIPAG_Cred._Visa")]}, settings, P)
    t = by_uid(res)
    assert t["machine:0"]["status"] == "conciliado" and t["machine:0"]["level"] == 1
    assert t["acquirer:0"]["status"] == "conciliado"


def test_summary(settings):
    res = reconcile({"erp": [erp("2026-10-02", "-100.00", "A")],
                     "bank": [bank("2026-10-02", "-100.00", "DEB.TIT.COMPE"), bank("2026-10-03", "50.00", "PIX RECEBIDO")]},
                    settings, P)
    s = summarize(res["transactions"], res["matches"])
    assert s["valor_total_recebido"] == "50.00" and s["total_conciliado"] == "100.00"
    assert s["conciliadas"] == 2 and s["percentual_conciliacao"] == 66.67


def test_full_demo_dataset(demo_bytes, settings):
    from app.parsers import parse_file
    recs = {k: parse_file(n, b, k, settings)["records"] for k, (n, b) in demo_bytes.items()}
    res = reconcile(recs, settings, P)
    statuses = {t["status"] for t in res["transactions"]}
    expected = {"conciliado", "divergencia_valor", "divergencia_data", "taxa_divergente", "pendente_liquidacao",
                "nao_localizado_banco", "nao_localizado_sistema", "duplicidade", "estorno_cancelamento"}
    assert expected <= statuses
    # todo vínculo automático tem soma exata (dentro da tolerância), exceto divergências sugeridas
    for m in res["matches"]:
        if m["state"] == "auto" and m["status"] == "conciliado" and not m["rule"].startswith("maquina"):
            assert m["difference"] == "0.00", m
