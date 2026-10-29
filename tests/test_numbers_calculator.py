import pytest

from tabletrace.schema import CellRef
from tabletrace.tools.calculator import CalcError, compute, evaluate_expression
from tabletrace.tools.numbers import format_number, header_unit, parse_number


@pytest.mark.parametrize("text,value,unit", [
    ("1,234", 1234.0, None), ("0.451", 0.451, None), ("12.5%", 12.5, "%"), ("−3.2 kJ/mol", -3.2, "kJ/mol"),
    ("6.60 × 10−5", 6.6e-5, None), ("60명", 60.0, "명"), ("22,000", 22000.0, None), ("457 K", 457.0, "K"),
    ("1.00 × 10−6", 1e-6, None), ("38 g/mol", 38.0, "g/mol"), ("  7 ", 7.0, None),
])
def test_parse_number(text, value, unit):
    p = parse_number(text)
    assert p is not None
    assert p.value == pytest.approx(value)
    assert p.unit == unit


@pytest.mark.parametrize("text", ["1994–2010", "2017년 12월 20일", "abc", "", "1.2.3", "3 × 10^999", "12 and 13", "서울"])
def test_parse_number_rejects(text):
    assert parse_number(text) is None


@pytest.mark.parametrize("header,unit", [
    ("매출액 (억원)", "억원"), ("Density (g/mL)", "g/mL"), ("Temperature, °C", "°C"), ("관객수 (명)", "명"),
    ("Radial nodes (no.)", None), ("ln[H2O2]", None), ("[H2O2] (M)", "M"), ("Year (2015)", None), ("득표율(%)", "%"),
])
def test_header_unit(header, unit):
    assert header_unit(header) == unit


def test_format_number():
    assert format_number(1062201.0) == "1,062,201"
    assert format_number(4.51) == "4.51"
    assert format_number(3.92805755) == "3.9281"
    assert format_number(6.6e-5) == "6.600e-05"


def test_safe_expression_rejects_code():
    assert evaluate_expression("(60 - 40) / 40 * 100") == pytest.approx(50.0)
    for bad in ["__import__('os')", "2 ** 100000", "a + 1", "1; 2", "max(1,2)", "1 if 1 else 2"]:
        with pytest.raises(CalcError):
            evaluate_expression(bad)
    with pytest.raises(CalcError):
        evaluate_expression("1 / 0")


def test_compute_diff_sum_avg(medal_table):
    c = compute(medal_table, "diff", [CellRef(table_id="t_medal", row=1, col=5), CellRef(table_id="t_medal", row=2, col=5)])
    assert c.result == 52 and c.expression == "112.0 - 60.0" and c.formatted == "52"
    c = compute(medal_table, "sum", [CellRef(table_id="t_medal", row=0, col=2), CellRef(table_id="t_medal", row=1, col=2)])
    assert c.result == 84
    c = compute(medal_table, "avg", [CellRef(table_id="t_medal", row=0, col=2), CellRef(table_id="t_medal", row=1, col=2)])
    assert c.result == 42


def test_compute_unit_mismatch_abstains(sales_table):
    with pytest.raises(CalcError, match="unit mismatch"):
        compute(sales_table, "diff", [CellRef(table_id="t_sales", row=0, col=1), CellRef(table_id="t_sales", row=0, col=2)])
    with pytest.raises(CalcError, match="not a single number"):
        compute(sales_table, "sum", [CellRef(table_id="t_sales", row=2, col=2), CellRef(table_id="t_sales", row=1, col=2)])
    c = compute(sales_table, "diff", [CellRef(table_id="t_sales", row=1, col=1), CellRef(table_id="t_sales", row=0, col=1)])
    assert c.unit == "억원" and c.formatted == "150 억원"


def test_compute_rejects_foreign_table(medal_table):
    with pytest.raises(CalcError, match="belongs to table"):
        compute(medal_table, "diff", [CellRef(table_id="other", row=0, col=5), CellRef(table_id="t_medal", row=1, col=5)])


def test_compute_negative_and_sci(chem_table):
    c = compute(chem_table, "diff", [CellRef(table_id="t_crit", row=2, col=1), CellRef(table_id="t_crit", row=1, col=1)])
    assert c.result == pytest.approx(342.9) and c.unit == "°C"
    c = compute(chem_table, "ratio", [CellRef(table_id="t_crit", row=2, col=2), CellRef(table_id="t_crit", row=0, col=2)])
    assert c.result == pytest.approx(22000 / 1300)
