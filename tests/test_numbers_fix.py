"""Tests for fixing issues 40 and 41 in tools/numbers.py (docs/rewrite/09_numbers_fix.md).

Written by the AI coding tool as the specification the owner's fix must meet. The tests for each defect were skipped
until the owner fixed it (the module the owner wrote is not changed by the AI tool); the owner did on 2026-11-20
(PR #10), so nothing is skipped any more. The other tests guard what the fix must NOT change.
"""
import json
from pathlib import Path

import pytest

from tabletrace.tools.numbers import format_number, header_unit, parse_number

ROOT = Path(__file__).resolve().parents[1]
FIXED_40 = format_number(1.602e-19) != "0"
FIXED_41 = header_unit("i (predicted)") is None
need_40 = pytest.mark.skipif(not FIXED_40, reason="issue 40 is not fixed yet (docs/rewrite/09_numbers_fix.md)")
need_41 = pytest.mark.skipif(not FIXED_41, reason="issue 41 is not fixed yet (docs/rewrite/09_numbers_fix.md)")


# ---------------------------------------------------------------- issue 40: format_number

@need_40
@pytest.mark.parametrize("value, text", [
    (1.602e-19, "1.602e-19"),     # the charge of an electron in coulombs: a training answer said "0"
    (2.31e-27, "2.310e-27"), (1.672e-24, "1.672e-24"), (3.348e-24, "3.348e-24"),
    (-5e-12, "-5.000e-12"), (5e-10, "5.000e-10"), (9.99e-10, "9.990e-10"),
])
def test_tiny_nonzero_values_are_written_in_scientific_notation(value, text):
    assert format_number(value) == text


@pytest.mark.parametrize("value, text", [
    (0, "0"), (0.0, "0"), (-0.0, "0"),                         # zero stays zero
    (1e-9, "1.000e-09"), (0.0005, "5.000e-04"), (6.6e-5, "6.600e-05"), (0.001, "0.001"), (0.001000000001, "0.001"),
    (1062201.0, "1,062,201"), (-3.0, "-3"), (2.0000000001, "2"), (0.9999999999, "1"),   # float noise around an integer
    (4.51, "4.51"), (3.92805755, "3.9281"), (-0.25, "-0.25"), (99999.5, "99,999.5"),
    (123456.7, "1.235e+05"), (1e15, "1.000e+15"),
])
def test_format_number_is_unchanged_elsewhere(value, text):
    """Only values with 0 < |x| < 1e-9 change. These hold before and after the fix."""
    assert format_number(value) == text


# ---------------------------------------------------------------- issue 41: header_unit

NOT_UNITS = [   # every word in brackets in the three corpora that the loose rule takes for a unit but that is not one
    ("발생일시 (UTC)", "ko"), ("최우수선수상 (MVP)", "ko"), ("관동(NTV)", "ko"), ("칸사이(YTV)", "ko"), ("삿포로(STV)", "ko"),
    ("높이 (max)", "ko"), ("층수 (t1/t2)", "ko"),
    ("Symbol (state)", "chem"), ("i (predicted)", "chem"), ("i (measured)", "chem"), ("pKwpKw = –log10(Kw)", "chem"),
    ("CCSD(T)", "chem_papers"),
]
UNITS = [       # the ones that are units: the fix must keep them
    ("[NO] (M)", "M"), ("Mass (amu)", "amu"), ("Surface Tension (mN/m)", "mN/m"), ("S°(J/K·mol)", "J/K·mol"),
    ("Specific Heat (J/g °C)", "J/g °C"), ("b (L/mol)", "L/mol"), ("Viscosity (mPa·s)", "mPa·s"), ("Viscosity (mPa s)", "mPa s"),
    ("Initial Rate (mol/L/s)", "mol/L/s"), ("k (L/mol/s)", "L/mol/s"), ("E° (V)", "V"), ("Vapor Pressure (Pa)", "Pa"),
    ("Δ G (kJ mol^-1)", "kJ mol^-1"), ("10^20 ×κ^DGT (Jm^5)", "Jm^5"), ("DN (kcal / mol)", "kcal / mol"),
    ("Molar Mass (g / mol)", "g / mol"), ("높이 (ft)", "ft"), ("생산량 (MT)", "MT"), ("설비용량 (kW)", "kW"),
]


@need_41
@pytest.mark.parametrize("header, corpus", NOT_UNITS)
def test_words_in_brackets_that_are_not_units(header, corpus):
    assert header_unit(header) is None


@pytest.mark.parametrize("header, unit", UNITS)
def test_units_in_brackets_are_kept(header, unit):
    assert header_unit(header) == unit


@pytest.mark.parametrize("header, unit", [
    ("매출액 (억원)", "억원"), ("Density (g/mL)", "g/mL"), ("Temperature, °C", "°C"), ("관객수 (명)", "명"), ("관객수 （명）", "명"),
    ("값 (단위: 명)", "명"), ("Radial nodes (no.)", None), ("ln[H2O2]", None), ("Year (2015)", None), ("득표율(%)", "%"),
    ("Rate, measured", None),
])
def test_other_headers_are_unchanged(header, unit):
    assert header_unit(header) == unit


@pytest.mark.parametrize("cell", ["5 M", "0.25 V", "3 T", "10 Pa", "2 ft", "4 kW", "1.5 amu", "7 MT", "2 mN/m"])
def test_reading_cells_is_unchanged(cell):
    """parse_number reads cells with UNIT_TOKENS. The step-1 rewrite settled that these are not cell units (no "M",
    for one), and 34,561 stored cells are read with that rule. A fix that adds header units to UNIT_TOKENS changes it."""
    assert parse_number(cell) is None


# ---------------------------------------------------------------- the stored data follows the code

HAND_SET = {"cp_2609_13018_t0"}   # units turned off by hand in data/chem_papers/sources.json


def test_stored_table_units_are_what_header_unit_gives():
    """Each table stores the units of its headers (data/*/documents.jsonl). After changing header_unit, run
    `python scripts/numbers_fix.py data` so the stored units, and the synthetic questions built from them, follow."""
    stale = []
    for corpus in ("data/ko/documents.jsonl", "data/chem/documents.jsonl", "data/chem_papers/documents.jsonl"):
        for line in (ROOT / corpus).read_text(encoding="utf-8").splitlines():
            for t in json.loads(line).get("tables", []):
                stored = {str(k): v for k, v in (t.get("units") or {}).items()}
                derived = {str(j): u for j, h in enumerate(t["header"]) if (u := header_unit(h))}
                if t["id"] in HAND_SET:
                    assert stored == {}, t["id"]
                elif stored != derived:
                    stale.append((t["id"], stored, derived))
    assert not stale, f"{len(stale)} tables store other units than header_unit gives, e.g. {stale[:3]}"


# ---------------------------------------------------------------- what the fix changed, as measured (PR #10)

def test_the_stored_impact_of_the_fix_and_what_the_documents_say_about_it():
    """experiments/eval/numbers_fix_impact.json compares the merged fix with the commit before it. The documents say that
    no cell is read differently and no stored verdict changed; they may say so only while this file does."""
    impact = json.loads((ROOT / "experiments/eval/numbers_fix_impact.json").read_text(encoding="utf-8"))
    s = impact["summary"]
    assert FIXED_40 and FIXED_41
    assert s["cells_read_differently"] == 0 and s["verdicts_changed"] == 0 and s["verdict_inputs"] > 30000
    assert s["headers_changed"] == len(NOT_UNITS)                      # exactly the words listed above, nothing else
    assert {k.split("header:")[1] for k in impact["functions"]["differ"] if k.startswith("header:")} == {h for h, _ in NOT_UNITS}
    assert all(old == "0" and new != "0" for k, (old, new) in impact["functions"]["differ"].items() if k.startswith("format:"))
    changed = s["synthetic_answers_changed"]
    assert changed["chem_synthetic_train"] == s["synthetic_answers_changed_total"] == 10 and sum(changed.values()) == 10
    report = (ROOT / "docs/REPORT.md").read_text(encoding="utf-8")
    sec = report[report.index("## 33. 다시 쓰다가 찾은 결함 두 개를 소유자가 고쳤다"):]
    for needle in ("소유자가 닫힌 목록을 골랐다", "고친 정답으로 다시 학습하지 않았다", "나머지 말뭉치의 저장된 단위는 그대로다", "AI 도구가 준비한 범위의 빈틈", "PR #10"):
        assert needle in sec, needle
    log = (ROOT / "docs/dev/issues-log.md").read_text(encoding="utf-8")
    rows = {line.split("|")[1].strip(): line for line in log.splitlines() if line.startswith("| ")}
    assert "**수정(2026-11-20" in rows["40"] and "**수정(2026-11-20" in rows["41"] and "**미수정" in rows["88"]
    handoff = (ROOT / "docs/HANDOFF.md").read_text(encoding="utf-8")
    for needle in ("직접 고쳤다", '"고친 데이터로 다시 학습했다"', '"모든 말뭉치의 단위를 바로잡았다"'):
        assert needle in handoff, needle

