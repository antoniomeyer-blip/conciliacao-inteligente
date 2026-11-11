"""Utilidades de parsing: valores monetários, datas, codificação e normalização de texto.

Todas as funções são determinísticas e não usam IA. Valores monetários são sempre
tratados como Decimal (nunca float) para garantir precisão financeira.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


class ParseError(ValueError):
    """Erro de leitura com mensagem amigável ao usuário."""


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def norm(text) -> str:
    """Normaliza texto para comparação: minúsculas, sem acentos, espaços simples."""
    if text is None:
        return ""
    s = re.sub(r"[º°ª]", "", str(text))
    s = strip_accents(s).lower().replace("�", "")
    s = re.sub(r"[^a-z0-9/%\.\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def to_cents(value: Decimal) -> int:
    return int(q2(value) * 100)


_EMPTY = {"", "-", "--", "nan", "none", "null", "n/a"}


def parse_decimal(raw, decimal_hint: str | None = None) -> Decimal | None:
    """Converte textos como 'R$ 1.234,56', '-R$ 99,90', '(1.234,56)', '1234.56', '12,5 D'.

    decimal_hint: ',' ou '.' quando a coluna já teve o separador decimal inferido.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int,)):
        return Decimal(raw)
    if isinstance(raw, float):
        if raw != raw:  # NaN
            return None
        return q2(Decimal(repr(raw)))
    if isinstance(raw, Decimal):
        return raw
    s = str(raw).strip()
    if s.lower() in _EMPTY:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    s_up = s.upper()
    if re.search(r"\s*D$", s_up) and re.search(r"\d", s_up):
        negative, s = True, re.sub(r"\s*[Dd]$", "", s)
    elif re.search(r"\s*C$", s_up) and re.search(r"\d", s_up):
        s = re.sub(r"\s*[Cc]$", "", s)
    s = s.replace("R$", "").replace("BRL", "").replace(" ", "").replace(" ", "")
    if s.startswith("-"):
        negative, s = (not negative), s[1:]
    elif s.endswith("-"):
        negative, s = (not negative), s[:-1]
    if s.startswith("+"):
        s = s[1:]
    if not re.fullmatch(r"[\d\.,]+", s or "x"):
        return None
    has_c, has_d = "," in s, "." in s
    if has_c and has_d:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
    elif has_c:
        dec = "," if (decimal_hint in (None, ",") or s.count(",") == 1 and len(s.split(",")[1]) != 3) else "."
        if s.count(",") > 1:
            dec = "."  # vírgula como milhar: 1,234,567
    elif has_d:
        if s.count(".") > 1:
            dec = ","  # ponto como milhar: 1.234.567
        elif decimal_hint == "," and len(s.split(".")[1]) == 3:
            dec = ","  # '1.500' em coluna brasileira = mil e quinhentos
        else:
            dec = "."
    else:
        dec = "."
    thousands = "." if dec == "," else ","
    s = s.replace(thousands, "").replace(dec, ".")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def infer_decimal_hint(values) -> str | None:
    """Infere o separador decimal predominante de uma coluna."""
    comma = dot = 0
    for v in values:
        if not isinstance(v, str):
            continue
        t = v.strip()
        if re.search(r",\d{1,2}(\s*[CD])?\)?$", t):
            comma += 1
        elif re.search(r"\.\d{1,2}(\s*[CD])?\)?$", t):
            dot += 1
    if comma == dot == 0:
        return None
    return "," if comma >= dot else "."


_DATE_PATTERNS = [
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})"), "dmy"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})"), "dmy"),
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})"), "dmy"),
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})"), "ymd"),
    (re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})"), "ymd"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})(?!\d)"), "dmy2"),
    (re.compile(r"^(\d{4})(\d{2})(\d{2})"), "ymd"),
]


def parse_date(raw) -> date | None:
    """Datas brasileiras (DD/MM/AAAA), ISO, OFX (AAAAMMDD...), datetime e serial do Excel."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if 20000 < raw < 80000:  # serial do Excel
            return date(1899, 12, 30) + timedelta(days=int(raw))
        return None
    s = str(raw).strip()
    if s.lower() in _EMPTY:
        return None
    for pattern, kind in _DATE_PATTERNS:
        m = pattern.match(s)
        if not m:
            continue
        a, b, c = (int(x) for x in m.groups())
        try:
            if kind == "dmy":
                return date(c, b, a)
            if kind == "dmy2":
                return date(2000 + c, b, a)
            return date(a, b, c)
        except ValueError:
            return None
    return None


def decode_text(data: bytes, declared: str | None = None) -> str:
    """Decodifica bytes de texto: UTF-8 (com/sem BOM) e depois Windows-1252/Latin-1."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in ([declared] if declared else []) + ["cp1252", "latin-1"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1", errors="replace")


def mask_card(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) >= 4:
        return "**** " + digits[-4:]
    return "****"


def mask_account(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    return ("*" * max(len(v) - 4, 2)) + v[-4:] if len(v) > 4 else "***" + v[-2:]


_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def scrub(text: str | None) -> str:
    """Remove dados pessoais desnecessários (CPF completo) de descrições."""
    if not text:
        return ""
    return _CPF_RE.sub("***.***.***-**", str(text)).replace("�", "?").strip()


def clean_id(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _EMPTY:
        return None
    s = re.sub(r"^(rrn|nsu|aut)[:\s]*", "", s, flags=re.I).strip()
    if re.fullmatch(r"0+", s):
        return None
    if re.fullmatch(r"\d+\.0", s):  # números vindos do Excel como float
        s = s[:-2]
    return (s.lstrip("0") or None) if s.isdigit() else s
