"""Validação com os arquivos reais do cliente (não versionados). Defina SAMPLES_DIR para executar."""
import os
from datetime import date
from pathlib import Path

import pytest

from app.engine import reconcile
from app.parsers import parse_file

DIR = os.getenv("SAMPLES_DIR")
pytestmark = pytest.mark.skipif(not DIR, reason="SAMPLES_DIR não definido (arquivos reais não versionados)")


def test_real_sicoob_sipag(settings):
    d = Path(DIR)
    bank = parse_file("extrato.ofx", (d / "extrato.ofx").read_bytes(), "bank", settings)
    bank_x = parse_file("extrato.xlsx", (d / "extrato.xlsx").read_bytes(), "bank", settings)
    assert len(bank["records"]) == len(bank_x["records"]) == 113
    assert bank["meta"]["valor_total"] == "-3037.05"
    erp = parse_file("erp.csv", (d / "erp.csv").read_bytes(), "erp", settings)
    acq = parse_file("adquirente.csv", (d / "adquirente.csv").read_bytes(), "acquirer", settings)
    assert len(erp["records"]) == 16 and len(acq["records"]) == 71
    res = reconcile({"bank": bank["records"], "erp": erp["records"], "acquirer": acq["records"]}, settings,
                    (date(2026, 11, 1), date(2026, 11, 11)))
    acq_status = [t["status"] for t in res["transactions"] if t["source"] == "acquirer"]
    assert acq_status.count("conciliado") == 70 and acq_status.count("estorno_cancelamento") == 1
    erp_status = [t["status"] for t in res["transactions"] if t["source"] == "erp"]
    assert erp_status.count("conciliado") == 12 and erp_status.count("divergencia_valor") == 2
    assert erp_status.count("divergencia_data") == 1 and erp_status.count("pendente_liquidacao") == 1
