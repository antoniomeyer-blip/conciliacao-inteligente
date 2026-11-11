"""Teste de ponta a ponta: cadastro → upload dos 4 arquivos → processamento → análise → exportações."""
import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def register(email, company="Empresa Demo"):
    r = client.post("/api/auth/register", json={"company": company, "name": "Analista Demo", "email": email,
                                                "password": "senha-forte-123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def auth():
    return register("demo@exemplo.com")


def upload(h, source, name, data, **form):
    return client.post("/api/files/parse", headers=h, data={"source": source, **form}, files={"file": (name, data)})


def test_requires_auth():
    assert client.get("/api/reconciliations").status_code == 401
    assert client.get("/api/health").json()["status"] == "ok"


def test_full_flow(auth, demo_bytes):
    ids = {}
    for source, (name, data) in demo_bytes.items():
        r = upload(auth, source, name, data)
        assert r.status_code == 200, r.text
        body = r.json()
        assert not body["needs_mapping"] and body["count"] > 0 and body["staged_id"]
        ids[source] = body["staged_id"]

    r = client.post("/api/reconciliations", headers=auth, json={"files": ids})
    assert r.status_code == 200, r.text
    rec = r.json()
    rid = rec["id"]
    tot = rec["totals"]
    assert rec["version"] == 1 and rec["period_start"] == "2026-10-01"
    assert set(tot["registros_por_fonte"]) == {"erp", "bank", "machine", "acquirer"}
    assert 0 < tot["percentual_conciliacao"] <= 100 and tot["sugestoes_pendentes"] >= 1

    # arquivos temporários são descartados após o processamento
    assert client.get(f"/api/files/staged/{ids['bank']}", headers=auth).status_code == 404

    # filtros, busca e ordenação
    r = client.get(f"/api/reconciliations/{rid}/transactions", headers=auth,
                   params={"status": ["divergencia_valor"], "sort": "amount", "dir": "desc"})
    items = r.json()["items"]
    assert items and all(i["status"] == "divergencia_valor" for i in items)
    assert client.get(f"/api/reconciliations/{rid}/transactions", headers=auth,
                      params={"q": "897,12"}).json()["total"] >= 1
    assert client.get(f"/api/reconciliations/{rid}/transactions", headers=auth,
                      params={"source": ["bank"], "date_from": "2026-10-05", "date_to": "2026-10-05"}).json()["total"] > 0

    # detalhe com lançamentos relacionados
    tid = items[0]["id"]
    d = client.get(f"/api/reconciliations/{rid}/transactions/{tid}", headers=auth).json()
    assert d["matches"] and d["related"]

    # aprovar uma sugestão e rejeitar outra (se houver)
    sugg = client.get(f"/api/reconciliations/{rid}", headers=auth).json()["suggestions"]
    m = sugg[0]
    r = client.post(f"/api/reconciliations/{rid}/matches/{m['id']}/decision", headers=auth,
                    json={"decision": "aprovar", "note": "Juros por atraso confirmados"})
    assert r.status_code == 200 and r.json()["state"] == "aprovado"
    assert client.post(f"/api/reconciliations/{rid}/matches/{m['id']}/decision", headers=auth,
                       json={"decision": "rejeitar"}).status_code == 409

    # observação
    r = client.post(f"/api/reconciliations/{rid}/transactions/{tid}/note", headers=auth, json={"note": "Conferido"})
    assert r.json()["note"].startswith("Conferido")

    # exportações
    x = client.get(f"/api/reconciliations/{rid}/export", headers=auth, params={"type": "xlsx"})
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert "Resumo" in wb.sheetnames and "Conciliado" in wb.sheetnames and "Vínculos (auditoria)" in wb.sheetnames
    assert "Divergência de valor" in wb.sheetnames
    c = client.get(f"/api/reconciliations/{rid}/export", headers=auth, params={"type": "csv"})
    assert c.content.decode("utf-8-sig").startswith("Data;")
    for t in ("pdf", "divergencias"):
        p = client.get(f"/api/reconciliations/{rid}/export", headers=auth, params={"type": t})
        assert p.status_code == 200 and p.content.startswith(b"%PDF")
    assert "Indicador" in client.get(f"/api/reconciliations/{rid}/export", headers=auth,
                                     params={"type": "resumo"}).content.decode("utf-8-sig")

    # duplicidade de processamento: alerta e versão nova somente com confirmação
    ids2 = {s: upload(auth, s, n, b).json()["staged_id"] for s, (n, b) in demo_bytes.items()}
    r = client.post("/api/reconciliations", headers=auth, json={"files": ids2})
    assert r.status_code == 409 and r.json()["detail"]["existing"]["id"] == rid
    r = client.post("/api/reconciliations", headers=auth, json={"files": ids2, "force": True})
    assert r.status_code == 200 and r.json()["version"] == 2

    # reprocessamento com controle de versão
    r = client.post(f"/api/reconciliations/{rid}/reprocess", headers=auth)
    assert r.status_code == 200 and r.json()["version"] == 3 and r.json()["parent_id"] == rid
    versions = client.get(f"/api/reconciliations/{rid}", headers=auth).json()["versions"]
    assert [v["version"] for v in versions] == [1, 2, 3]

    # histórico e dashboard
    assert len(client.get("/api/reconciliations", headers=auth).json()) == 3
    assert client.get("/api/dashboard", headers=auth).json()["latest"]["version"] == 3

    # isolamento entre empresas
    other = register("outra@exemplo.com", "Outra Empresa")
    assert client.get(f"/api/reconciliations/{rid}", headers=other).status_code == 404
    assert client.get("/api/reconciliations", headers=other).json() == []

    # auditoria
    actions = {a["action"] for a in client.get("/api/audit", headers=auth).json()}
    assert {"processar_conciliacao", "vinculo_aprovado", "exportar", "reprocessar_conciliacao"} <= actions


def test_manual_mapping_and_template(auth):
    data = "col_a;col_b;col_c\n05/10/2026;Venda balcão;150,00\n".encode()
    r = upload(auth, "erp", "erp.csv", data)
    assert r.json()["needs_mapping"] and r.json()["staged_id"] is None
    r = upload(auth, "erp", "erp.csv", data, mapping='{"date": 0, "description": 1, "amount": 2}', header_row="0",
               save_template="true", template_name="ERP simples")
    assert r.status_code == 200 and not r.json()["needs_mapping"] and r.json()["template"]["name"] == "ERP simples"
    r = upload(auth, "erp", "outro_nome.csv", data)  # modelo salvo aplicado automaticamente
    assert not r.json()["needs_mapping"] and r.json()["template"]
    assert any(t["name"] == "ERP simples" for t in client.get("/api/templates", headers=auth).json())


def test_rejected_upload_and_settings(auth):
    r = upload(auth, "bank", "virus.exe", b"MZ\x90\x00")
    assert r.status_code == 422 and "não suportada" in r.json()["detail"]
    s = client.get("/api/settings", headers=auth).json()["settings"]
    s["tolerancia_dias"] = 5
    assert client.put("/api/settings", headers=auth, json=s).json()["settings"]["tolerancia_dias"] == 5
    s["tolerancia_dias"] = 999
    assert client.put("/api/settings", headers=auth, json=s).status_code == 422
