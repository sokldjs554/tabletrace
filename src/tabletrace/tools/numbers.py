"""Number and unit parsing for table cells (Korean and English).

This is deliberately conservative: a cell either parses to exactly one number with an optional
unit, or it does not parse at all. Ranges ("1994–2010"), dates and mixed text are rejected so
the calculator never silently computes with the wrong value.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# unit tokens we recognise next to a number or in a header, longest first
UNIT_TOKENS = [
    "mol L−1 s−1", "mol/L", "mol/kg", "kJ/mol", "kJ mol−1", "J/(g·°C)", "J/g·°C", "J/mol·K", "J/(mol·K)",
    "g/mol", "g/cm3", "g/cm³", "g/mL", "g/L", "mg/L", "kg/m3", "kg/m³", "mmHg", "kPa", "MPa", "atm", "bar", "torr",
    "°C", "℃", "°F", "K", "nm", "pm", "µm", "μm", "mm", "cm", "km", "m", "mL", "L", "kg", "mg", "g", "ppm", "%",
    "kJ", "J", "eV", "D", "s", "min", "h",
    "억원", "백만원", "만원", "천원", "원", "달러", "명", "개", "회", "대", "경기", "점", "골", "승", "패", "무",
    "세", "년", "월", "일", "석", "표", "건", "곳", "호", "위", "분", "초", "㎡", "km²", "km2", "m²", "톤", "t",
]
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(UNIT_TOKENS, key=len, reverse=True))
_NUM = r"[-−–+]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_SCI = r"(?:\s*[×x]\s*10\s*(?:\^|\*\*)?\s*[-−–+]?\d+|[eE][-−+]?\d+)?"
NUMBER_RE = re.compile(rf"^\s*(?P<num>{_NUM}){_SCI}\s*(?P<unit>{_UNIT_ALT})?\s*$")
SCI_RE = re.compile(r"[×x]\s*10\s*(?:\^|\*\*)?\s*([-−–+]?\d+)|[eE]([-−+]?\d+)")
HEADER_UNIT_RE = re.compile(rf"[\(（]\s*(?:단위\s*[:：]\s*)?(?P<unit>{_UNIT_ALT}|[A-Za-zµμ°Ω%/·⋅\-\d^ ]{{1,10}})\s*[\)）]\s*$")
_NOT_UNITS = {"no", "no.", "approx", "approx.", "est", "est.", "n", "a", "b", "c", "d", "e", "x", "y", "z", "i", "ii", "iii"}
TRAILING_UNIT_RE = re.compile(rf"(?P<unit>{_UNIT_ALT})\s*$")


@dataclass(frozen=True)
class ParsedNumber:
    value: float
    unit: str | None
    raw: str


def normalize_minus(s: str) -> str:
    return s.replace("−", "-").replace("–", "-").replace("—", "-")


def parse_number(text: str, default_unit: str | None = None) -> ParsedNumber | None:
    """Parse '1,234', '0.451', '12.5%', '−3.2 kJ/mol', '6.60 × 10−5', '60명' -> ParsedNumber or None."""
    if text is None:
        return None
    raw = text.strip()
    if not raw:
        return None
    s = normalize_minus(raw)
    # scientific notation: pull exponent out before the strict match
    exp = 0
    m_sci = SCI_RE.search(s)
    if m_sci:
        exp = int(normalize_minus(m_sci.group(1) or m_sci.group(2)))
        s = s[: m_sci.start()] + s[m_sci.end():]
    m = NUMBER_RE.match(s)
    if not m:
        return None
    num = m.group("num").replace(",", "").replace(" ", "")
    if abs(exp) > 30:
        return None
    try:
        value = float(num) * (10.0**exp)
    except (ValueError, OverflowError):
        return None
    unit = m.group("unit") or default_unit
    if unit == "℃":
        unit = "°C"
    return ParsedNumber(value=value, unit=unit, raw=raw)


def header_unit(header: str) -> str | None:
    """'매출액 (억원)' -> '억원'; 'Density (g/mL)' -> 'g/mL'; 'Temperature, °C' -> '°C'."""
    if not header:
        return None
    m = HEADER_UNIT_RE.search(header.strip())
    if m:
        u = m.group("unit").strip()
        if u.lower() in _NOT_UNITS or u.isdigit():
            return None
        return "°C" if u == "℃" else u
    m = re.search(rf",\s*(?P<unit>{_UNIT_ALT})\s*$", header)
    if m:
        return m.group("unit")
    return None


def format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9 and abs(value) < 1e15:
        return f"{round(value):,}"
    if abs(value) >= 1e5 or (abs(value) < 1e-3 and value != 0):
        return f"{value:.3e}"
    s = f"{value:,.4f}".rstrip("0").rstrip(".")
    return s
