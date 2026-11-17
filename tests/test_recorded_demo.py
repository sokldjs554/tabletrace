"""The recorded demo must show real outputs: stored model outputs replayed through the pipeline, never typed in,
and every question of the evaluation files, each with its gold answer and whether the stored result is right."""
import json
from pathlib import Path

from tabletrace.corpus.store import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
INDEX = json.loads((ROOT / "console" / "data" / "recorded" / "index.json").read_text(encoding="utf-8"))
DATA = json.loads((ROOT / "console" / "data" / "examples.json").read_text(encoding="utf-8"))
EXAMPLES = {e["id"]: e for e in DATA["examples"]}
SET_FILES = {"ko_owner": "data/ko/owner_eval.jsonl", "ko_custom": "data/ko/custom_eval.jsonl",
             "chem_custom": "data/chem/custom_eval.jsonl", "chem_papers": "data/chem_papers/custom_eval.jsonl"}
RIGHT = ("correct", "hold_ok")


def test_the_demo_lists_every_question_of_each_evaluation_file():
    """No picking: a set in the demo is the whole file, in the file's order, with the file's questions."""
    assert [s["key"] for s in DATA["sets"]] == list(SET_FILES)
    for s in DATA["sets"]:
        rows = read_jsonl(ROOT / SET_FILES[s["key"]])
        shown = [e for e in DATA["examples"] if e["set"] == s["key"]]
        assert [e["id"] for e in shown] == [r["qid"] for r in rows] and s["n"] == len(rows)
        assert all(e["question"] == r["question"] and e["doc_id"] == r["doc_id"] for e, r in zip(shown, rows, strict=True))
    assert next(s for s in DATA["sets"] if s["key"] == "ko_owner")["author"] == "owner"
    assert all(s["author"] == "ai" for s in DATA["sets"] if s["key"] != "ko_owner")


def test_the_owners_review_is_carried_to_the_questions_it_flags():
    review = {r["qid"]: r["verdict"] for r in read_jsonl(ROOT / "data/ko/custom_eval_review.jsonl")}
    flagged = {i for i, v in review.items() if v != "ok"}
    assert flagged and {e["id"] for e in DATA["examples"] if e.get("review", {}).get("verdict", "ok") != "ok"} == flagged


def test_every_recorded_run_belongs_to_a_question():
    for key, planner in INDEX["planners"].items():
        assert planner["runs"], key
        for run in planner["runs"]:
            assert run["id"] in EXAMPLES and run["question"] == EXAMPLES[run["id"]]["question"], (key, run["id"])
            assert run["result"]["status"] in ("answered", "abstained"), (key, run["id"])
            assert run["mark"] in DATA["marks"], (key, run["id"])


HEURISTIC_RUNS = {"ko_owner": "experiments/eval/heuristic_ko_owner", "ko_custom": "experiments/eval/heuristic_ko_custom",
                  "chem_custom": "experiments/eval/heuristic_chem_custom", "chem_papers": "experiments/eval/heuristic_chem_papers"}


def _same_as_the_evaluation(key, planner, eval_dirs):
    """Each recorded run against the evaluation's row for the same question: status, answer, evidence cells, verdict."""
    rows = {}
    for rel in eval_dirs.values():
        rows.update({r["question"]: r for r in read_jsonl(ROOT / rel / "predictions.jsonl")})
    assert len(planner["runs"]) == len(rows), key
    for run in planner["runs"]:
        row, res = rows[run["question"]], run["result"]
        assert res["status"] == row["pred_status"] and res["answer"] == row["pred_answer"], (key, run["id"])
        assert [f"r{c['row']}c{c['col']}" for c in res["evidence_cells"]] == row["pred_cells"], (key, run["id"])
        assert res["verdict"]["reason"] == row["pred_reason"], (key, run["id"])
        assert (run["mark"] in RIGHT) == bool(row["verified_correct"]), (key, run["id"])
        first = next(s for s in res["trace"] if s["step"] == "propose")
        assert first["output"]["raw"] == row["raw_output"], (key, run["id"])
    return rows


def test_stored_model_outputs_match_the_evaluation_they_come_from():
    """A stored planner replays raw outputs from evaluation runs on that evaluation's inputs and settings. Every recorded
    run must be that evaluation's result: the same output, status, answer, evidence cells and verdict."""
    assert INDEX["settings"]["entity_check"] is False and INDEX["settings"]["fallback"] is False
    stored_planners = {k: p for k, p in INDEX["planners"].items() if p["source"]}
    assert set(stored_planners) == {"exaone", "ownloop", "kochem", "ref7", "ref1", "neural"}
    for key, planner in stored_planners.items():
        assert set(planner["source"]["where"]) == set(planner["source"]["eval_dirs"]) == set(planner["totals"])
        for set_key, rel in planner["source"]["eval_dirs"].items():
            meta = json.loads((ROOT / rel / "metrics.json").read_text(encoding="utf-8"))["meta"]
            assert planner["source"]["generated"][set_key] == meta["finished"][:10]
            assert meta["entity_check"] is False
        rows = _same_as_the_evaluation(key, planner, planner["source"]["eval_dirs"])
        for run in planner["runs"]:
            assert run["engine_ms"] == round(rows[run["question"]]["ms"], 1)
            assert run["result"]["planner"]["model_id"] == planner["model_id"]
            assert run["eval_correct"] == bool(rows[run["question"]]["verified_correct"])


def test_the_heuristic_planner_is_executed_not_typed():
    """The heuristic runs are produced when the demo is recorded, on the inputs of the stored heuristic evaluations;
    they must come out as those evaluations did, proposal included."""
    planner = INDEX["planners"]["heuristic"]
    assert planner["source"] is None and len(planner["runs"]) == len(EXAMPLES)
    _same_as_the_evaluation("heuristic", planner, HEURISTIC_RUNS)
    assert all(r["result"]["planner"]["mode"] == "heuristic" for r in planner["runs"])


def test_totals_shown_are_the_reported_numbers():
    """The totals of the per-question view are counted from the marks, and on the owner's questions they are the
    numbers the documents report (experiments/eval/owner_eval_analysis.json)."""
    for key, planner in INDEX["planners"].items():
        for set_key, t in planner["totals"].items():
            runs = [r for r in planner["runs"] if r["set"] == set_key]
            assert t["n"] == len(runs) == next(s["n"] for s in DATA["sets"] if s["key"] == set_key), (key, set_key)
            assert t["right"] == sum(r["mark"] in RIGHT for r in runs)
    owner = {k: p["totals"]["ko_owner"]["right"] for k, p in INDEX["planners"].items()}
    assert owner == {"exaone": 24, "ownloop": 24, "kochem": 22, "ref7": 20, "ref1": 13, "neural": 8, "heuristic": 7}
    analysis = json.loads((ROOT / "experiments/eval/owner_eval_analysis.json").read_text(encoding="utf-8"))
    gpu = analysis["gpu_planners"]
    assert gpu["exaone_full_data"]["owner_first_pass"]["correct"] == owner["exaone"]
    assert gpu["exaone_full_data_owner_loop"]["owner_first_pass"]["correct"] == owner["ownloop"]
    assert gpu["exaone_7p8b_untuned"]["owner_first_pass"]["correct"] == owner["ref7"]
    assert gpu["exaone_1p2b_untuned"]["owner_first_pass"]["correct"] == owner["ref1"]


def test_the_chemistry_documents_show_an_exaone_model_with_the_numbers_of_the_rerun():
    """The chemistry sets carry the EXAONE tuned on Korean and chemistry and the untuned 1.2B, from the run that kept
    per-question predictions (notebook 2, section N); their totals are the ones experiments/eval/chem_rerun_analysis.json reports."""
    rerun = json.loads((ROOT / "experiments/eval/chem_rerun_analysis.json").read_text(encoding="utf-8"))
    for set_key in ("chem_custom", "chem_papers"):
        shown = {k: p["totals"][set_key]["right"] for k, p in INDEX["planners"].items() if set_key in p["totals"]}
        assert set(shown) == {"kochem", "ref1", "neural", "heuristic"}
        r = rerun["chemistry"][set_key]
        assert shown == {"kochem": r["tuned"]["correct"], "ref1": r["untuned_six_examples"]["correct"],
                         "neural": r["mt5_small_final"]["correct"], "heuristic": r["heuristic"]["correct"]}
        assert max(shown, key=shown.get) == "kochem"          # what "auto" shows on a chemistry question
        for key in ("kochem", "ref1"):
            source = INDEX["planners"][key]["source"]
            assert "Colab" in source["where"][set_key] and source["generated"][set_key] == rerun["finished"][:10]
    assert "Kaggle" in INDEX["planners"]["ref1"]["source"]["where"]["ko_owner"]


def test_a_long_table_is_shown_to_the_planner_as_the_evaluation_showed_it():
    """Runs on a table that did not fit the input budget say how many rows the planner saw."""
    cut = [r for p in INDEX["planners"].values() for r in p["runs"] if "rows_shown" in r]
    assert cut and all(r["rows_shown"][0] < r["rows_shown"][1] for r in cut)
    assert any("rows_list" in r for r in INDEX["planners"]["neural"]["runs"])      # the paper tables: rows chosen by overlap


def test_the_first_result_a_visitor_sees_is_a_right_calculation_on_the_owners_questions():
    run = next(r for r in INDEX["planners"]["exaone"]["runs"] if r["id"] == INDEX["featured"])
    assert EXAMPLES[run["id"]]["set"] == "ko_owner" and run["mark"] == "correct" and run["result"]["calculation"]


def test_evidence_cells_carry_how_the_number_parser_read_them():
    from tabletrace.tools.numbers import parse_number

    docs = json.loads((ROOT / "console" / "data" / "recorded" / "documents.json").read_text(encoding="utf-8"))
    tables = {t["id"]: t for d in docs.values() for t in d["tables"]}
    seen_header_unit = False
    for planner in INDEX["planners"].values():
        for run in planner["runs"]:
            cells = run["result"]["evidence_cells"]
            assert len(run["values"]) == len(cells)
            for c, v in zip(cells, run["values"], strict=True):
                t = tables[c["table_id"]]
                raw = t["rows"][c["row"]][c["col"]]
                num = parse_number(raw, default_unit=t["units"].get(str(c["col"])))
                assert v["raw"] == raw and v["value"] == (num.value if num else None) and v["unit"] == (num.unit if num else None)
                seen_header_unit = seen_header_unit or v["unit_from"] == "header"
    assert seen_header_unit


def test_console_offers_the_stored_planners_and_marks_cited_cells():
    js = (ROOT / "console" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "console" / "styles.css").read_text(encoding="utf-8")
    assert INDEX["planner_order"] == ["exaone", "ownloop", "kochem", "ref7", "ref1", "neural", "heuristic"] and "planner_order" in js
    assert "is-cited" in js and "td.is-cited" in css and "badge-fix" in js and ".badge-fix" in css
    assert "is-gold" in js and "td.is-gold" in css and "renderCompare" in js and "renderProposal" in js and "renderMatrix" in js


def test_a_repaired_answer_is_among_the_stored_runs():
    """The demo needs at least one answer whose cited cell the verifier repaired, to show the two cells apart."""
    repaired = [(k, r) for k, p in INDEX["planners"].items() for r in p["runs"]
                if any(c["name"] == "evidence_repaired" for c in r["result"]["verdict"]["checks"])]
    assert repaired
    for _key, run in repaired:
        first = next(s for s in run["result"]["trace"] if s["step"] == "propose")
        cited = {(c["row"], c["col"]) for c in first["output"]["parsed"]["cells"]}
        evidence = {(c["row"], c["col"]) for c in run["result"]["evidence_cells"]}
        assert cited and evidence and not cited & evidence
