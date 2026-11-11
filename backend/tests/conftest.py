import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("JWT_SECRET", "segredo-de-teste")

DEMO = ROOT.parent / "public" / "demo"

import pytest  # noqa: E402

from app.defaults import DEFAULT_SETTINGS  # noqa: E402


@pytest.fixture
def settings():
    import copy
    return copy.deepcopy(DEFAULT_SETTINGS)


@pytest.fixture
def demo_bytes():
    return {
        "erp": ("1_sistema_erp_DEMO.csv", (DEMO / "1_sistema_erp_DEMO.csv").read_bytes()),
        "bank": ("2_extrato_bancario_DEMO.ofx", (DEMO / "2_extrato_bancario_DEMO.ofx").read_bytes()),
        "machine": ("3_maquina_cartao_DEMO.csv", (DEMO / "3_maquina_cartao_DEMO.csv").read_bytes()),
        "acquirer": ("4_adquirente_DEMO.csv", (DEMO / "4_adquirente_DEMO.csv").read_bytes()),
    }
