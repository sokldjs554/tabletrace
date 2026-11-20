"""Run the evaluation questions through the real pipeline and store the results for the static demo.

  python scripts/make_recorded_runs.py

Every question of four evaluation files is recorded, not a hand-picked few, and each stored result carries the gold
answer and whether the stored result is right:

  ko_owner     data/ko/owner_eval.jsonl            the repository owner's own 30 questions
  ko_custom    data/ko/custom_eval.jsonl           30 questions the AI tool wrote (the owner reviewed them)
  chem_custom  data/chem/custom_eval.jsonl         32 questions on chemistry textbook tables (AI-written, the owner reviewed them)
  chem_papers  data/chem_papers/custom_eval.jsonl  62 questions on tables of CC BY chemistry papers (AI-written, the owner reviewed them)

Planners. A "stored" planner answers with the raw output a model produced in an earlier evaluation run
(experiments/eval/<run>/predictions.jsonl); that output goes through the same graph, tools and verifier as a live
answer would. No model runs here. The heuristic planner is executed now (it is deterministic and needs no model).

Every run is recorded on the evaluation's own inputs and settings: the table rows and the passage text that
evaluation showed the planner (a long table is cut to the rows that fit the input budget, counted with the run's
tokenizer), no subject check, no second proposal. So a stored result is, question by question, the result the
reported numbers count; tests/test_recorded_demo.py holds every status and verdict against the evaluation files.

Needs what the evaluations counted their input budget with: the EXAONE tokenizer (models/exaone-4.0-1.2b-tokenizer), the
final mT5 model's tokenizer (experiments/rl_v3/model) and models/mt5-small-base. They are not in the repository, so this
script runs where the models are; the tests then hold its output against the evaluation files without them.

Writes console/data/examples.json (the sets and their questions with gold), console/data/recorded/index.json (runs + provenance),
console/data/recorded/documents.json (the documents those runs use), console/data/recorded/kiwi_tokens.json (the Korean
tokens the in-browser path reads) and console/data/graph.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from tabletrace import __version__
from tabletrace.agent.graph import AgentRuntime
from tabletrace.agent.program import ProgramParseError, parse
from tabletrace.corpus.store import CorpusStore, read_jsonl
from tabletrace.model.approx_tokenizer import load_tokenizer
from tabletrace.model.serialize import set_row_select
from tabletrace.retrieval.index import CorpusIndex
from tabletrace.schema import Document
from tabletrace.training.data import build_examples

ROOT = Path(__file__).resolve().parents[1]
EVAL = "experiments/eval"
sys.path.insert(0, str(ROOT / "console" / "live"))
from tt_browser import cell_values as _cell_values  # noqa: E402  (one implementation for the recorder and the browser path)
from tt_browser import mark_of  # noqa: E402


def cell_values(res, tables: dict) -> list[dict]:
    return _cell_values(res.evidence_cells, tables[res.table_id]) if res.evidence_cells else []


def kiwi_tokens(examples: list[dict], docs: dict) -> dict[str, list[list[str]]]:
    """What the Korean tokenizer returns for every Korean question and column header of the demo. The browser path cannot
    load the tokenizer (a compiled extension with a 109 MB model); console/live/shim/kiwipiepy.py hands these back instead."""
    from tabletrace.retrieval.tokenize import _kiwi

    texts = {e["question"] for e in examples if e["corpus"] == "ko_tables"}
    for doc_id in {e["doc_id"] for e in examples if e["corpus"] == "ko_tables"}:
        texts |= {h for t in docs[doc_id].tables for h in t.header}
    return {text: [[tok.form, tok.tag] for tok in _kiwi().tokenize(text)] for text in sorted(texts) if text.strip()}

# The question files, in the order the demo lists them. `gold` names an evaluation run whose predictions.jsonl carries
# the gold status and answer the evaluation resolved for each question (the same for every run on that file).
SETS = [
    {"key": "ko_owner", "corpus": "ko_tables", "data": "data/ko/owner_eval.jsonl", "gold": "heuristic_ko_owner", "author": "owner",
     "title": "소유자가 직접 쓴 30문항",
     "note": "저장소 소유자가 시험 분할의 표 15개를 보고 직접 쓴 평가 문항 전체입니다. 고른 것이 아닙니다."},
    {"key": "ko_custom", "corpus": "ko_tables", "data": "data/ko/custom_eval.jsonl", "gold": "heuristic_ko_custom", "author": "ai",
     "review": "data/ko/custom_eval_review.jsonl", "title": "AI 도구가 쓴 30문항",
     "note": "AI 도구가 쓴 평가 문항 전체입니다. 소유자가 한 문항씩 검수했고, 고쳐야 한다고 적은 문항에는 표시가 붙습니다."},
    {"key": "chem_custom", "corpus": "chem_docs", "data": "data/chem/custom_eval.jsonl", "gold": "heuristic_chem_custom", "author": "ai",
     "review": "data/chem/custom_eval_review.jsonl", "title": "화학 교과서 표 32문항",
     "note": "OpenStax Chemistry 2e의 표에 AI 도구가 쓴 평가 문항 전체입니다. 소유자가 한 문항씩 검수했고, 고쳐야 한다고 적은 문항에는 표시가 붙습니다."},
    {"key": "chem_papers", "corpus": "chem_docs", "data": "data/chem_papers/custom_eval.jsonl", "gold": "heuristic_chem_papers", "author": "ai",
     "docs": "data/chem_papers/documents.jsonl", "review": "data/chem_papers/custom_eval_review.jsonl", "title": "화학 논문 표 62문항",
     "note": "arXiv의 CC BY 4.0 화학 논문 12편의 표에 AI 도구가 쓴 평가 문항 전체입니다. 소유자가 한 문항씩 검수했고, 고쳐야 한다고 적은 문항에는 표시가 붙습니다. 어떤 학습에도 쓰지 않은 표입니다."},
]

# Planners, strongest first ("auto" in the demo shows the first one that has a result for the question).
PLANNERS = [
    {"key": "exaone", "model_id": "EXAONE-4.0-1.2B LoRA (전체 데이터)", "short": "EXAONE 1.2B LoRA",
     "runs": {"ko_owner": "exaone_full4_vllm_ko_owner", "ko_custom": "exaone_full4_vllm_ko_custom"},
     "where": "Kaggle Tesla T4의 vLLM 서버",
     "note": "전체 데이터 미세조정 가운데 여섯 번째 학습의 모델입니다(한국어 test 85.5%). 소유자의 문항으로 평가한 것이 이 모델입니다."},
    {"key": "ownloop", "model_id": "EXAONE-4.0-1.2B LoRA (전체 데이터, 소유자가 쓴 학습 루프)", "short": "EXAONE LoRA · 직접 쓴 루프",
     "runs": {"ko_owner": "exaone_ownloop_vllm_ko_owner", "ko_custom": "exaone_ownloop_vllm_ko_custom"},
     "where": "Colab Tesla T4의 vLLM 서버",
     "note": "같은 학습 명령을 소유자가 직접 쓴 학습 루프로 돌린 모델입니다(한국어 test 86.0%)."},
    {"key": "kochem", "model_id": "EXAONE-4.0-1.2B LoRA (한국어와 화학을 함께 튜닝)", "short": "EXAONE LoRA · 한국어+화학",
     "runs": {"ko_owner": "exaone_kochem2_vllm_ko_owner", "ko_custom": "exaone_kochem2_vllm_ko_custom",
              "chem_custom": "exaone_kochem2_vllm_chem_custom", "chem_papers": "exaone_kochem2_vllm_chem_papers"},
     "where": "Colab Tesla T4의 vLLM 서버",
     "note": "한국어 학습 문항에 화학 합성 문항을 더해 튜닝한 모델입니다(한국어 test 86.1%). 화학 문서에서 볼 수 있는 EXAONE은 이 모델입니다."},
    {"key": "koonly", "model_id": "EXAONE-4.0-1.2B LoRA (한국어만 튜닝, 화학 문항 없이)", "short": "EXAONE LoRA · 한국어만",
     "runs": {"chem_custom": "exaone_koonly_vllm_chem_custom", "chem_papers": "exaone_koonly_vllm_chem_papers"},
     "where": "Colab Tesla T4의 vLLM 서버",
     "note": "화학 문항을 한 번도 보지 않고 한국어 학습 문항만으로 튜닝한 모델입니다. 화학 문항을 더한 모델과 견주려고 화학 문서에만 실었습니다. "
             "한국어 문항에서는 같은 학습 명령으로 만든 \"EXAONE 1.2B LoRA\"가 그 자리에 있습니다."},
    {"key": "ref7", "model_id": "EXAONE-3.5-7.8B-Instruct AWQ (튜닝 없음, 예시 6개)", "short": "EXAONE 7.8B 튜닝 없음",
     "runs": {"ko_owner": "ref_7p8b_awq_ko_owner", "ko_custom": "ref_7p8b_awq_ko_custom"},
     "where": "Kaggle Tesla T4의 vLLM 서버", "note": "튜닝하지 않고 프롬프트에 예시 6개를 넣었습니다."},
    {"key": "ref1", "model_id": "EXAONE-4.0-1.2B (튜닝 없음, 예시 6개)", "short": "EXAONE 1.2B 튜닝 없음",
     "runs": {"ko_owner": "ref_1p2b_ko_owner", "ko_custom": "ref_1p2b_ko_custom", "chem_custom": "ref_1p2b_chem_custom", "chem_papers": "ref_1p2b_chem_papers"},
     "where": {"*": "Kaggle Tesla T4의 vLLM 서버", "chem_custom": "Colab Tesla T4의 vLLM 서버", "chem_papers": "Colab Tesla T4의 vLLM 서버"},
     "note": "튜닝하지 않고 프롬프트에 예시 6개를 넣었습니다. 화학 문항에서는 예시를 화학 학습 문항에서 골랐습니다."},
    {"key": "neural", "model_id": "mT5-small 최종 (강화학습 v3)", "short": "mT5-small",
     "runs": {"ko_owner": "rl_v3_ko_owner", "ko_custom": "rl_v3_ko_custom", "chem_custom": "rl_v3_chem_custom", "chem_papers": "rl_v3_chem_papers"},
     "where": "개발 환경의 CPU", "note": "3억 파라미터 모델입니다. 한국어 test에서 휴리스틱 기준선을 넘지 못했습니다."},
    {"key": "heuristic", "model_id": None, "short": "휴리스틱", "runs": None, "where": None,
     "note": "모델이 아닙니다. 질문과 표의 어휘 겹침으로 셀을 고르는 기준선이고, 기록할 때 실행했습니다."},
]

# The evaluation's settings (eval/run.py without --entity-check): no subject check, no second proposal from the heuristic
# planner. With them a stored result is the result the reported numbers count, question by question.
SETTINGS = {"entity_check": False, "evidence_repair": True, "fallback": False}

# What each evaluation counted the input budget with: (tokenizer, input tokens, row selection), per planner and, where a
# set was evaluated differently, per set. The rows a planner was shown follow from it. The evaluation files of that time
# do not record the budget, so the values are the ones that reproduce every stored result; tests hold the replays against
# the stored predictions, question by question, so a wrong entry here cannot pass.
EXAONE_BUDGET = ("models/exaone-4.0-1.2b-tokenizer", 672, "first")
EXAONE_PAPERS = ("models/exaone-4.0-1.2b-tokenizer", 672, "overlap")      # the paper tables: rows chosen by overlap with the question (notebook 2, sections G and N)
BUDGETS = {
    "exaone": {"*": EXAONE_BUDGET}, "ownloop": {"*": EXAONE_BUDGET}, "ref7": {"*": EXAONE_BUDGET},
    "kochem": {"*": EXAONE_BUDGET, "chem_papers": EXAONE_PAPERS}, "koonly": {"*": EXAONE_BUDGET, "chem_papers": EXAONE_PAPERS}, "ref1": {"*": EXAONE_BUDGET, "chem_papers": EXAONE_PAPERS},
    "neural": {"*": ("experiments/rl_v3/model", 512, "first"), "chem_papers": ("experiments/rl_v3/model", 512, "overlap")},
    "heuristic": {"*": (None, 512, "first"), "chem_papers": (None, 4096, "first")},     # the paper tables were read whole
}

MARKS = {"correct": "맞음", "wrong": "틀림", "hold_ok": "맞는 보류", "hold_miss": "답을 놓친 보류", "answered_unanswerable": "답이 없는데 답함"}
OPS = {"diff": "두 셀의 차이", "sum": "두 셀의 합", "avg": "평균", "ratio": "비율", "pct_change": "변화율"}


class StoredOutputPlanner:
    """Stands in for a served model: answers with the raw output that model produced in an earlier evaluation
    (experiments/eval/<run>/predictions.jsonl). Same interface as NeuralPlanner / EnginePlanner."""

    def __init__(self, eval_dirs: list[Path], model_id: str) -> None:
        self.model_id = model_id
        self.rows: dict[str, dict] = {}
        for d in eval_dirs:
            with open(d / "predictions.jsonl", encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    self.rows[r["question"]] = r

    def plan(self, question: str, table, context: str | None = None):
        r = self.rows[question]
        try:
            prog = parse(r["raw_output"], table.id)
        except ProgramParseError:
            prog = None
        return prog, r["raw_output"], None, r["ms"]      # rows shown to the model were not recorded


def load_examples() -> tuple[list[dict], dict[str, Document]]:
    """The questions of every set with their gold, and the extra documents a set brings (the chemistry paper tables)."""
    examples, extra_docs = [], {}
    for s in SETS:
        gold = {r["qid"]: r for r in read_jsonl(ROOT / EVAL / s["gold"] / "predictions.jsonl")}
        review = {r["qid"]: r for r in read_jsonl(ROOT / s["review"])} if s.get("review") else {}
        for d in read_jsonl(ROOT / s["docs"]) if s.get("docs") else []:
            extra_docs[d["id"]] = Document.model_validate(d)
        for r in read_jsonl(ROOT / s["data"]):
            g = gold[r["qid"]]
            assert g["question"] == r["question"], r["qid"]
            ex = {"id": r["qid"], "set": s["key"], "author": s["author"], "corpus": s["corpus"], "doc_id": r["doc_id"], "table_id": r.get("table_id"),
                  "category": r["category"], "label": OPS.get(r["op"], ""), "question": r["question"],
                  "gold": {"status": g["gold_status"], "answers": [a for a in [g["gold_answer"], *(r.get("alt_answers") or [])] if a is not None],
                           "cells": g["gold_cells"]}}
            if r["qid"] in review:
                ex["review"] = {"verdict": review[r["qid"]]["verdict"], "comment": review[r["qid"]].get("comment") or ""}
            examples.append(ex)
    return examples, extra_docs


def shown_inputs(examples: list[dict], docs: dict, budgets: dict) -> dict[str, dict]:
    """For each question, the table rows and passage text the evaluation showed the planner and verified against."""
    out = {}
    for s in SETS:
        recs = [r for r in read_jsonl(ROOT / s["data"]) if any(e["id"] == r["qid"] for e in examples)]
        if not recs:
            continue
        tok_spec, max_in, row_select = budgets.get(s["key"], budgets["*"])
        tok = load_tokenizer(str(ROOT / tok_spec) if tok_spec else None, fallback_dir=str(ROOT / "models/mt5-small-base"))
        set_row_select(row_select)
        try:
            built = build_examples(recs, docs, tok, max_in)
        finally:
            set_row_select("first")
        for rec, e in zip(recs, built, strict=True):
            doc = docs[rec["doc_id"]]
            pid = rec.get("context_passage") or (doc.passages[0].id if doc.passages else None)
            out[e.qid] = {"table": e.table, "context": e.context, "context_id": pid if e.context is not None else None,
                          "rows": (e.rows_kept, len(e.table_full.rows)), "rows_list": e.shown_rows}
    return out


def run_set(rt: AgentRuntime, examples: list[dict], mode: str, tables: dict, stored: dict | None, shown: dict) -> list[dict]:
    runs = []
    for ex in examples:
        t0 = time.time()
        given = shown[ex["id"]]
        res = rt.run(ex["question"], ex["corpus"], doc_id=ex["doc_id"], table_id=ex.get("table_id"), planner_mode=mode, given=given)
        run = {"id": ex["id"], "set": ex["set"], "question": ex["question"], "result": json.loads(res.model_dump_json()),
               "wall_s": round(time.time() - t0, 2), "mark": mark_of(res.status, res.answer, ex["gold"]), "values": cell_values(res, tables)}
        if given["rows"][0] < given["rows"][1]:
            run["rows_shown"] = list(given["rows"])            # the planner saw only some rows of a long table: the first ones,
            if given["rows_list"] is not None:                 # or (row selection by overlap with the question) these
                run["rows_list"] = given["rows_list"]
        if stored is not None:
            row = stored[ex["question"]]
            run["engine_ms"] = round(row["ms"], 1)              # latency of the original request to the engine
            run["eval_correct"] = bool(row["verified_correct"])  # the evaluation's verdict on the same output (its settings differ, see index.settings)
        runs.append(run)
    return runs


def pick_tour(planners: dict, examples: list[dict], tables: dict, featured: str) -> dict:
    """The first screen walks through three stored results, one question at a time. They are picked here by rule, not by
    id, from the questions the owner wrote, so the page cannot show a hand-made example:

      pass    the featured run: the full-data model, a calculation, every check passed
      repair  a right answer of a stored EXAONE model whose cited cell did not hold the answer (same row, another column),
              on the smallest table there is: the verifier moved the evidence
      hold    the full-data model proposed an answer to an unanswerable question, a check failed, and nothing was sent
      missed  what the verifier does not catch: the same model answered an unanswerable question and passed
    """
    by_id = {e["id"]: e for e in examples}
    failed = lambda r: [c["name"] for c in r["result"]["verdict"]["checks"] if not c["passed"]]  # noqa: E731
    proposal = lambda r: next(s["output"]["parsed"] for s in r["result"]["trace"] if s["step"] == "propose" and s["output"] and s["output"].get("parsed"))  # noqa: E731
    owner = lambda r: by_id[r["id"]]["set"] == "ko_owner"  # noqa: E731
    size = lambda r: len(tables[by_id[r["id"]]["table_id"]].rows) * len(tables[by_id[r["id"]]["table_id"]].header)  # noqa: E731

    first = next(r for r in planners["exaone"]["runs"] if r["id"] == featured)
    assert first["mark"] == "correct" and not failed(first) and owner(first)
    scene_pass = {"kind": "pass", "id": first["id"], "planner": "exaone"}
    # another row with the same value in the same column: choosing it gives the same answer (what scoring answers alone cannot see)
    ex, table, ev = by_id[first["id"]], tables[by_id[first["id"]]["table_id"]], first["result"]["evidence_cells"]
    rows = {c["row"] for c in ev}
    name_col = next((c for c in range(len(table.header)) if all(table.rows[r][c] and table.rows[r][c] in ex["question"] for r in rows)), None)
    twin = next((r for r in range(len(table.rows)) if r not in rows and table.rows[r][ev[0]["col"]] == table.rows[ev[0]["row"]][ev[0]["col"]]), None)
    if name_col is not None and twin is not None:
        scene_pass["twin"] = {"cell": f"r{twin}c{ev[0]['col']}", "name": table.rows[twin][name_col], "value": table.rows[twin][ev[0]["col"]]}

    repairs = []
    for k, p in planners.items():
        for r in p["runs"] if "EXAONE" in (p["model_id"] or "") else []:
            if not (owner(r) and r["mark"] == "correct" and "evidence_repaired" in failed(r)):
                continue
            cited, kept = proposal(r)["cells"], r["result"]["evidence_cells"]
            if len(cited) == len(kept) == 1 and cited[0]["row"] == kept[0]["row"] and cited[0]["col"] != kept[0]["col"]:
                repairs.append((size(r), list(planners).index(k), r["id"], k))
    assert repairs, "no stored EXAONE answer whose evidence the verifier repaired"
    _, _, rid, rk = min(repairs)
    holds = [r for r in planners["exaone"]["runs"] if owner(r) and r["mark"] == "hold_ok" and failed(r) and proposal(r)["op"] != "abstain"]
    assert holds, "no unanswerable question on which the verifier stopped the full-data model's answer"
    same_table = [r for r in holds if by_id[r["id"]]["table_id"] == by_id[rid]["table_id"]]
    hold = (same_table or holds)[0]
    out = {"scenes": [scene_pass, {"kind": "repair", "id": rid, "planner": rk}, {"kind": "hold", "id": hold["id"], "planner": "exaone"}]}
    missed = [r for r in planners["exaone"]["runs"] if owner(r) and r["mark"] == "answered_unanswerable"]
    near = [r for r in missed if by_id[r["id"]]["table_id"] == ex["table_id"]]
    if missed:
        out["missed"] = {"id": (near or missed)[0]["id"], "planner": "exaone"}
    return out


def totals(runs: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for r in runs:
        t = out.setdefault(r["set"], {"n": 0, "right": 0, **{m: 0 for m in MARKS}})
        t["n"] += 1
        t[r["mark"]] += 1
        t["right"] += r["mark"] in ("correct", "hold_ok")
        if "eval_correct" in r:
            t["eval_right"] = t.get("eval_right", 0) + r["eval_correct"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="console/data/recorded")
    a = ap.parse_args()
    examples, extra_docs = load_examples()
    store = CorpusStore.from_disk()
    corpora = {c: list(d) for c, d in store.corpora.items()}
    for d in extra_docs.values():
        corpora[d.corpus].append(d)
    indexes = {c: CorpusIndex(d, "ko" if c == "ko_tables" else "en") for c, d in corpora.items()}
    docs = {d.id: d for ds in corpora.values() for d in ds}
    tables = {t.id: t for d in docs.values() for t in d.tables}
    planners: dict[str, dict] = {}
    for p in PLANNERS:
        if p["runs"] is None:                                    # the heuristic planner: executed now
            covered, rt, mode, stored, source = examples, AgentRuntime(indexes, None, **SETTINGS), "heuristic", None, None
        else:
            dirs = {k: ROOT / EVAL / v for k, v in p["runs"].items()}
            planner = StoredOutputPlanner(list(dirs.values()), p["model_id"])
            covered = [ex for ex in examples if ex["set"] in dirs]
            rt, mode, stored = AgentRuntime(indexes, planner, **SETTINGS), "neural", planner.rows
            metas = {k: json.loads((d / "metrics.json").read_text(encoding="utf-8"))["meta"] for k, d in dirs.items()}
            where = p["where"] if isinstance(p["where"], dict) else {"*": p["where"]}
            source = {"where": {k: where.get(k, where["*"]) for k in dirs}, "generated": {k: m["finished"][:10] for k, m in metas.items()},
                      "eval_dirs": {k: f"{EVAL}/{v}" for k, v in p["runs"].items()}}
        runs = run_set(rt, covered, mode, tables, stored, shown_inputs(covered, docs, BUDGETS[p["key"]]))
        planners[p["key"]] = {"model_id": p["model_id"], "short": p["short"], "note": p["note"], "source": source, "totals": totals(runs), "runs": runs}
        print(f"{p['key']:10s}", {k: f"{t['right']}/{t['n']}" + (f" (eval {t['eval_right']})" if 'eval_right' in t else "") for k, t in planners[p["key"]]["totals"].items()})
    used = {ex["doc_id"] for ex in examples}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        commit = "unknown"
    # the first thing a visitor sees: the first calculation among the owner's questions that the strongest planner gets right
    first = next((r["id"] for r in planners["exaone"]["runs"] if r["mark"] == "correct" and r["result"]["calculation"]), examples[0]["id"])
    index = {"generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "commit": commit, "version": __version__,
             "hardware": "4 vCPU Intel Xeon 2.10GHz, no GPU (session container)",
             "settings": {**SETTINGS,
                          "note": "평가와 같은 설정으로 기록했습니다. 주어 검사를 끄고, 모델의 제안이 검증에 실패해도 휴리스틱 플래너로 다시 시도하지 않습니다. "
                                  "긴 표는 평가 때처럼 입력 길이에 들어가는 앞쪽 행까지만 플래너에 보여 줬습니다. "
                                  "그래서 이 화면의 맞음·틀림은 보고서의 평가 수치와 문항마다 같습니다. 서비스의 기본 설정(주어 검사와 보완 시도를 켬)은 "
                                  "백엔드를 띄운 실시간 모드에서 볼 수 있습니다."},
             "featured": first, "tour": pick_tour(planners, examples, tables, first), "counts": {"questions": len(examples), "runs": sum(len(p["runs"]) for p in planners.values()), "planners": len(planners)},
             "planner_order": [p["key"] for p in PLANNERS], "planners": planners}
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "documents.json").write_text(json.dumps({i: json.loads(docs[i].model_dump_json()) for i in sorted(used)}, ensure_ascii=False), encoding="utf-8")
    sets = [{k: s[k] for k in ("key", "corpus", "author", "title", "note")} | {"n": sum(1 for e in examples if e["set"] == s["key"])} for s in SETS]
    (ROOT / "console/data/examples.json").write_text(json.dumps({"sets": sets, "marks": MARKS, "examples": examples}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "kiwi_tokens.json").write_text(json.dumps(kiwi_tokens(examples, docs), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (ROOT / "console/data/graph.json").write_text(json.dumps({"mermaid": AgentRuntime(indexes, None).mermaid()}), encoding="utf-8")
    print("wrote", out, "featured", first, "tour", json.dumps(index["tour"], ensure_ascii=False), {f.name: f.stat().st_size for f in out.glob("*.json")})


if __name__ == "__main__":
    main()
