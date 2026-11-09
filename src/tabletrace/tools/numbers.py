import math
import re
from dataclasses import dataclass


@dataclass
class ParsedNumber:
    value: float
    unit: str | None
    raw: str


UNIT_TOKENS = [
    "mol L−1 s−1", "mol/L", "mol/kg", "kJ/mol", "kJ mol−1", "J/(g·°C)", "J/g·°C", "J/mol·K", "J/(mol·K)",
    "g/mol", "g/cm3", "g/cm³", "g/mL", "g/L", "mg/L", "kg/m3", "kg/m³", "mmHg", "kPa", "MPa", "atm", "bar", "torr",
    "°C", "℃", "°F", "K", "nm", "pm", "µm", "μm", "mm", "cm", "km", "m", "mL", "L", "kg", "mg", "g", "ppm", "%",
    "kJ", "J", "eV", "D", "s", "min", "h",
    "억원", "백만원", "만원", "천원", "원", "달러", "명", "개", "회", "대", "경기", "점", "골", "승", "패", "무",
    "세", "년", "월", "일", "석", "표", "건", "곳", "호", "위", "분", "초", "㎡", "km²", "km2", "m²", "톤", "t",
]


def normalize_minus(s: str) -> str:
    return s.replace("−", "-").replace("–", "-")


def parse_number(text: str, default_unit: str | None = None) -> ParsedNumber | None:
    candidate = normalize_minus(text.strip())
    unit = default_unit
    for token in sorted(UNIT_TOKENS, key=len, reverse=True):
        if candidate.endswith(normalize_minus(token)):
            candidate = candidate[:-len(normalize_minus(token))].strip()
            unit = token
            break

    digits = r"(?:\d{1,3}(?:,\d{3})+|\d+)"
    mantissa = rf"[+-]?{digits}(?:\.\d+)?"
    match = re.fullmatch(
        rf"({mantissa})(?:\s*(?:[eE]\s*([+-]?\d+)|[×x]\s*10\s*(?:\^|\*\*)?\s*([+-]?\d+)))?",
        candidate,
    )
    if match is None:
        return None
    exponent = match.group(2) or match.group(3)
    try:
        power = int(exponent) if exponent is not None else 0
        if abs(power) > 30:
            return None
        value = float(match.group(1).replace(",", "")) * 10.0**power
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(value):
        return None
    return ParsedNumber(value=value, unit="°C" if unit == "℃" else unit, raw=text)


def header_unit(header: str) -> str | None:
    match = re.search(
        r"(?:\(([^()]*(?:\([^()]*\)[^()]*)*)\)|（([^（）]*)）|,\s*([^,]+))\s*$",
        header,
    )
    if not match:
        return None
    part = next(item for item in match.groups() if item is not None).strip()
    if match.group(3) is not None:
        return ("°C" if part == "℃" else part) if part in UNIT_TOKENS else None
    part = re.sub(r"^단위\s*[:：]\s*", "", part).strip()
    excluded = {"no", "no.", "approx", "approx.", "est", "est.", "n", "a", "b", "c", "d", "e", "x", "y", "z", "i", "ii", "iii"}
    if part.lower() in excluded or part.isdigit():
        return None
    if part in UNIT_TOKENS or re.fullmatch(r"[A-Za-zµμ°Ω%/·⋅\-^0-9 ]{1,10}", part):
        return "°C" if part == "℃" else part
    return None


def format_number(value: float) -> str:
    value = float(value)
    if abs(value) < 1e15 and abs(value - round(value)) < 1e-9:
        return f"{round(value):,}"
    if abs(value) >= 1e5 or (value != 0 and abs(value) < 1e-3):
        return f"{value:.3e}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")
