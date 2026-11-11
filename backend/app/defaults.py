"""Configurações padrão da empresa. Todas podem ser alteradas em Configurações."""
import copy

DEFAULT_SETTINGS = {
    "tolerancia_valor_centavos": 0,
    "tolerancia_dias": 3,
    "divergencia_valor_max_percentual": 5.0,
    "tolerancia_taxa_centavos": 1,
    "max_itens_agrupamento": 40,
    "regras": {
        "nivel1_identificador": True,
        "nivel2_valor_data": True,
        "nivel3_tolerancia_data": True,
        "nivel4_agrupado": True,
        "nivel5_liquido": True,
        "sugerir_divergencia_valor": True,
    },
    # Taxas observadas no relatório SIPAG de exemplo (Sicoob). Confirme com seu contrato.
    "taxas": [
        {"operadora": "SIPAG", "bandeira": "*", "modalidade": "debito", "parcelas_min": 1, "parcelas_max": 1, "taxa": 1.59},
        {"operadora": "SIPAG", "bandeira": "*", "modalidade": "credito", "parcelas_min": 1, "parcelas_max": 1, "taxa": 1.79},
        {"operadora": "SIPAG", "bandeira": "*", "modalidade": "credito", "parcelas_min": 2, "parcelas_max": 12, "taxa": 2.29},
        {"operadora": "SIPAG", "bandeira": "elo", "modalidade": "credito", "parcelas_min": 1, "parcelas_max": 1, "taxa": 2.29},
        {"operadora": "SIPAG", "bandeira": "elo", "modalidade": "credito", "parcelas_min": 2, "parcelas_max": 12, "taxa": 3.19},
    ],
    "bandeiras": [
        {"nome": "Mastercard", "chave": "mastercard", "padroes": ["mastercard", "maestro", "master"]},
        {"nome": "Visa", "chave": "visa", "padroes": ["visa", "electron"]},
        {"nome": "Elo", "chave": "elo", "padroes": ["elo", "outras bandeiras"]},
        {"nome": "Hipercard", "chave": "hipercard", "padroes": ["hipercard", "hiper"]},
        {"nome": "American Express", "chave": "amex", "padroes": ["amex", "american express"]},
        {"nome": "Cabal", "chave": "cabal", "padroes": ["cabal"]},
        {"nome": "Diners", "chave": "diners", "padroes": ["diners"]},
    ],
    # Textos do extrato que identificam créditos de adquirentes (cartão)
    "descritores_cartao_banco": ["SIPAG", "CR COMPRAS", "CIELO", "REDE", "STONE", "GETNET", "PAGSEGURO",
                                 "SAFRAPAY", "MERCADO PAGO", "SUMUP", "VERO", "BIN"],
    "contas_bancarias": [],
}


def merged_settings(stored: dict | None) -> dict:
    out = copy.deepcopy(DEFAULT_SETTINGS)
    for k, v in (stored or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out
