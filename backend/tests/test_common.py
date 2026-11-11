from datetime import date, datetime
from decimal import Decimal

import pytest

from app.parsers.common import clean_id, mask_card, parse_date, parse_decimal, scrub


@pytest.mark.parametrize("raw,hint,expected", [
    ("R$ 1.234,56", None, "1234.56"), ("-R$ 99,90", None, "-99.90"), ("-1.108,87", None, "-1108.87"),
    ("1108.87", None, "1108.87"), ("(1.234,56)", None, "-1234.56"), ("12,50 D", None, "-12.50"),
    ("12,50 C", None, "12.50"), ("354.00", ".", "354.00"), ("1.500", ",", "1500"), ("1,234,567.89", None, "1234567.89"),
    ("100-", None, "-100"), (354.0, None, "354.00"), (-437, None, "-437"), ("", None, None), ("-", None, None),
    ("abc", None, None),
])
def test_parse_decimal(raw, hint, expected):
    v = parse_decimal(raw, hint)
    assert (v is None and expected is None) or v == Decimal(expected)


@pytest.mark.parametrize("raw,expected", [
    ("10/11/2026", date(2026, 11, 10)), ("10/11/2026 17:26:42", date(2026, 11, 10)),
    ("2026-11-10", date(2026, 11, 10)), ("20261110120000[-3:BRT]", date(2026, 11, 10)),
    ("10/11/26", date(2026, 11, 10)), (datetime(2026, 11, 10, 8, 0), date(2026, 11, 10)),
    (46336, date(2026, 11, 10)), ("31/02/2026", None), ("", None), ("Total", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_ids_and_privacy():
    assert clean_id("RRN: 360200599038") == "360200599038"
    assert clean_id("000123") == "123"
    assert clean_id("0") is None
    assert clean_id("-") is None
    assert mask_card("515894******0704") == "**** 0704"
    assert "123.456.789-09" not in scrub("Pix de Fulano 123.456.789-09")
