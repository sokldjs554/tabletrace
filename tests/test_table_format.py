"""Table formats for the model input (model/serialize.py): `plain` must stay byte-identical, `colid` labels columns."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tabletrace.model import serialize
from tabletrace.model.approx_tokenizer import ApproxTokenizer
from tabletrace.training.data import build_examples, load_docs, read_records

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _restore_format():
    before = serialize.get_table_format()
    yield
    serialize.set_table_format(before)


def test_plain_is_the_default_and_unchanged(medal_table):
    assert serialize.get_table_format() == "plain"
    text = serialize.table_to_text(medal_table, max_rows=2)
    assert text == "header: 순위 | 국가 | 금 | 은 | 동 | 합계 ; r0: 1 | 중국 | 48 | 22 | 30 | 100 ; r1: 2 | 미국 | 36 | 39 | 37 | 112"


def test_colid_labels_every_cell_with_its_column(medal_table, sales_table):
    text = serialize.table_to_text(medal_table, max_rows=1, table_format="colid")
    assert text == "header: c0 순위 | c1 국가 | c2 금 | c3 은 | c4 동 | c5 합계 ; r0: c0 1 | c1 중국 | c2 48 | c3 22 | c4 30 | c5 100"
    # an empty cell keeps its label, so later cells do not shift
    row = serialize.table_to_text(sales_table, table_format="colid").split(" ; ")[3]
    assert row == "r2: c0 2024 1Q | c1 1,410 | c2 | c3 4.4"


def test_setting_applies_to_build_input_and_is_validated(medal_table):
    serialize.set_table_format("colid")
    assert "r2: c0 3 | c1 러시아" in serialize.build_input("러시아의 합계는?", medal_table)
    with pytest.raises(ValueError):
        serialize.set_table_format("markdown")
    with pytest.raises(ValueError):
        serialize.table_to_text(medal_table, table_format="markdown")


def test_environment_variable_selects_the_format():
    code = "from tabletrace.model.serialize import get_table_format; print(get_table_format())"
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src"), "TABLETRACE_TABLE_FORMAT": "colid"}
    assert subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True).stdout.strip() == "colid"
    bad = subprocess.run([sys.executable, "-c", code], env={**env, "TABLETRACE_TABLE_FORMAT": "x"}, capture_output=True, text=True)
    assert bad.returncode != 0 and "TABLETRACE_TABLE_FORMAT" in bad.stderr


def test_colid_costs_tokens_so_the_same_budget_keeps_fewer_rows():
    docs = load_docs(ROOT / "data" / "ko" / "documents.jsonl")
    recs = read_records([ROOT / "data" / "ko" / "test.jsonl"])[:120]
    tok = ApproxTokenizer()
    plain = build_examples(recs, docs, tok, 400)
    serialize.set_table_format("colid")
    colid = build_examples(recs, docs, tok, 400)
    assert sum(e.rows_kept for e in colid) < sum(e.rows_kept for e in plain)
    assert all(c.target_text == p.target_text for c, p in zip(colid, plain, strict=True))     # the program to learn does not change


def test_replay_reuses_the_format_of_the_run_it_replays(tmp_path):
    """eval.run --replay-from without --table-format must rebuild inputs with the replayed run's format."""
    src = tmp_path / "src"
    data = ROOT / "data" / "ko" / "custom_eval.jsonl"
    base = [sys.executable, "-m", "tabletrace.eval.run", "--corpus", str(ROOT / "data/ko/documents.jsonl"), "--data", str(data), "--tokenizer", "approx"]
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([*base, "--planner", "heuristic", "--table-format", "colid", "--out", str(src)], env=env, capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-500:]
    assert json.loads((src / "metrics.json").read_text())["meta"]["table_format"] == "colid"
    out = tmp_path / "replay"
    r = subprocess.run([*base, "--planner", "heuristic", "--replay-from", str(src), "--out", str(out)], env=env, capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-500:]
    meta = json.loads((out / "metrics.json").read_text())["meta"]
    assert meta["table_format"] == "colid"
    a, b = (json.loads((d / "metrics.json").read_text())["metrics"] for d in (src, out))
    assert a["verified_em"] == b["verified_em"] and a["truncated_gold_rate"] == b["truncated_gold_rate"]
