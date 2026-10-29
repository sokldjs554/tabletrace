import pytest

from tabletrace.schema import Table


@pytest.fixture
def medal_table() -> Table:
    return Table(
        id="t_medal", doc_id="d_medal", title="2008년 하계 올림픽 메달 집계",
        header=["순위", "국가", "금", "은", "동", "합계"],
        rows=[["1", "중국", "48", "22", "30", "100"], ["2", "미국", "36", "39", "37", "112"],
              ["3", "러시아", "24", "13", "23", "60"], ["4", "영국", "19", "13", "15", "47"]],
        lang="ko",
    )


@pytest.fixture
def sales_table() -> Table:
    return Table(
        id="t_sales", doc_id="d_sales", title="분기 매출",
        header=["분기", "매출액 (억원)", "영업이익 (백만원)", "성장률(%)"],
        rows=[["2023 1Q", "1,200", "35,000", "3.5"], ["2023 2Q", "1,350", "41,200", "12.5"], ["2024 1Q", "1,410", "", "4.4"]],
        units={1: "억원", 2: "백만원", 3: "%"}, lang="ko",
    )


@pytest.fixture
def chem_table() -> Table:
    return Table(
        id="t_crit", doc_id="d_crit", title="Critical constants",
        header=["Substance", "Critical Temperature (°C)", "Critical Pressure (kPa)"],
        rows=[["hydrogen", "−240.0", "1300"], ["carbon dioxide", "31.1", "7400"], ["water", "374.0", "22,000"]],
        units={1: "°C", 2: "kPa"}, lang="en",
    )
