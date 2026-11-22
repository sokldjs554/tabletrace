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
    review = {r["qid"]: r["verdict"] for f in ("data/ko/custom_eval_review.jsonl", "data/chem/custom_eval_review.jsonl", "data/chem_papers/custom_eval_review.jsonl")
              for r in read_jsonl(ROOT / f)}
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
    assert set(stored_planners) == {"exaone", "ownloop", "kochem", "koonly", "ref7", "ref1", "neural"}
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
    owner = {k: p["totals"]["ko_owner"]["right"] for k, p in INDEX["planners"].items() if "ko_owner" in p["totals"]}
    assert owner == {"exaone": 24, "ownloop": 24, "kochem": 22, "ref7": 20, "ref1": 13, "neural": 8, "heuristic": 7}
    analysis = json.loads((ROOT / "experiments/eval/owner_eval_analysis.json").read_text(encoding="utf-8"))
    gpu = analysis["gpu_planners"]
    assert gpu["exaone_full_data"]["owner_first_pass"]["correct"] == owner["exaone"]
    assert gpu["exaone_full_data_owner_loop"]["owner_first_pass"]["correct"] == owner["ownloop"]
    assert gpu["exaone_7p8b_untuned"]["owner_first_pass"]["correct"] == owner["ref7"]
    assert gpu["exaone_1p2b_untuned"]["owner_first_pass"]["correct"] == owner["ref1"]


def test_the_chemistry_documents_show_the_exaone_models_with_the_numbers_of_the_reruns():
    """The chemistry sets carry three EXAONE planners from the runs that kept per-question predictions (notebook 2,
    sections N and O): tuned on Korean and chemistry, tuned on Korean only, untuned. Their totals are the ones the
    analysis files report."""
    rerun = json.loads((ROOT / "experiments/eval/chem_rerun_analysis.json").read_text(encoding="utf-8"))
    share = json.loads((ROOT / "experiments/eval/chem_share_analysis.json").read_text(encoding="utf-8"))
    for set_key in ("chem_custom", "chem_papers"):
        shown = {k: p["totals"][set_key]["right"] for k, p in INDEX["planners"].items() if set_key in p["totals"]}
        r = rerun["chemistry"][set_key]
        assert shown == {"kochem": r["tuned"]["correct"], "koonly": share["chemistry"][set_key]["korean_only"]["correct"], "ref1": r["untuned_six_examples"]["correct"],
                         "neural": r["mt5_small_final"]["correct"], "heuristic": r["heuristic"]["correct"]}
        assert max(shown, key=shown.get) == "kochem"          # what "auto" shows on a chemistry question
        for key, finished in (("kochem", rerun["finished"]), ("ref1", rerun["finished"]), ("koonly", share["finished"])):
            source = INDEX["planners"][key]["source"]
            assert "Colab" in source["where"][set_key] and source["generated"][set_key] == finished[:10]
    assert "Kaggle" in INDEX["planners"]["ref1"]["source"]["where"]["ko_owner"]
    # the Korean-only model is shown on the chemistry documents only; on the Korean sets the same command's model is "exaone"
    assert set(INDEX["planners"]["koonly"]["totals"]) == {"chem_custom", "chem_papers"} and "화학 문서에만" in INDEX["planners"]["koonly"]["note"]


def test_a_long_table_is_shown_to_the_planner_as_the_evaluation_showed_it():
    """Runs on a table that did not fit the input budget say how many rows the planner saw."""
    cut = [r for p in INDEX["planners"].values() for r in p["runs"] if "rows_shown" in r]
    assert cut and all(r["rows_shown"][0] < r["rows_shown"][1] for r in cut)
    assert any("rows_list" in r for r in INDEX["planners"]["neural"]["runs"])      # the paper tables: rows chosen by overlap


def test_the_first_result_a_visitor_sees_is_a_right_calculation_on_the_owners_questions():
    """The question browser opens on the same question as the first screen."""
    run = next(r for r in INDEX["planners"]["exaone"]["runs"] if r["id"] == INDEX["featured"])
    assert EXAMPLES[run["id"]]["set"] == "ko_owner" and run["mark"] == "correct" and run["result"]["calculation"]
    assert INDEX["featured"] == INDEX["tour"]["scenes"][0]["id"]


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
    assert INDEX["planner_order"] == ["exaone", "ownloop", "kochem", "koonly", "ref7", "ref1", "neural", "heuristic"] and "planner_order" in js
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


# ---------------------------------------------------------------- the first screen: three stored results, one question at a time

def _tour_run(scene: dict) -> dict:
    return next(r for r in INDEX["planners"][scene["planner"]]["runs"] if r["id"] == scene["id"])


def _proposal(run: dict) -> dict:
    return next(s["output"]["parsed"] for s in run["result"]["trace"] if s["step"] == "propose" and s["output"] and s["output"].get("parsed"))


def test_the_first_screen_shows_three_stored_results_picked_by_rule():
    """The static demo opens on a walk through three results. They are stored runs on questions the owner wrote, found
    when the results are recorded (scripts/make_recorded_runs.py, pick_tour), and each is what its tab says it is. What
    the first scene is about was the owner's choice among three candidates (2026-11-22); which run fits it is a rule."""
    tour = INDEX["tour"]
    assert [s["kind"] for s in tour["scenes"]] == ["recalc", "repair", "hold"]
    runs = [_tour_run(s) for s in tour["scenes"]]
    assert all(EXAMPLES[r["id"]]["set"] == "ko_owner" for r in runs)                       # the owner's questions
    assert all("EXAONE" in INDEX["planners"][s["planner"]]["model_id"] for s in tour["scenes"])   # stored model outputs, not the baseline
    failed = lambda r: [c["name"] for c in r["result"]["verdict"]["checks"] if not c["passed"]]  # noqa: E731
    recalc, repaired, held = runs
    # 1. the model cited the gold cells and wrote a number that is not their result: only that check failed, and the
    #    answer sent is the value the tool computed, which is the gold answer
    ids = lambda cs: sorted(f"r{c['row']}c{c['col']}" for c in cs)  # noqa: E731
    assert recalc["mark"] == "correct" and failed(recalc) == ["answer_matches_calc"] and recalc["result"]["calculation"]
    assert ids(_proposal(recalc)["cells"]) == ids(recalc["result"]["evidence_cells"]) == sorted(EXAMPLES[recalc["id"]]["gold"]["cells"])
    assert recalc["result"]["answer"] == recalc["result"]["calculation"]["formatted"] != _proposal(recalc)["answer"]
    assert recalc["result"]["answer"] in EXAMPLES[recalc["id"]]["gold"]["answers"]
    # 2. a right answer whose cited cell did not hold it: same row, another column, and the verifier moved the evidence
    cited, kept = _proposal(repaired)["cells"], repaired["result"]["evidence_cells"]
    assert repaired["mark"] == "correct" and "evidence_repaired" in failed(repaired) and len(cited) == len(kept) == 1
    assert cited[0]["row"] == kept[0]["row"] and cited[0]["col"] != kept[0]["col"]
    # 3. the model answered an unanswerable question, a check failed, nothing was sent
    assert held["mark"] == "hold_ok" and held["result"]["status"] == "abstained" and failed(held) and _proposal(held)["op"] != "abstain"
    assert EXAMPLES[held["id"]]["gold"]["status"] == "abstained"
    # and what the verifier does not catch is one link away: an unanswerable question that was answered and passed
    missed = _tour_run(tour["missed"])
    assert missed["mark"] == "answered_unanswerable" and missed["result"]["status"] == "answered"


def test_the_first_screen_does_not_open_on_the_table_the_owner_set_aside():
    """The owner asked (2026-11-22) that the page not open on the 2002 K-League table. No scene, nor the question the
    third scene links to, nor the question the browser opens on, is on a table listed in TOUR_AVOID_TABLES; and the rule
    for the first scene finds one run, so the choice of a kind of scene did not hide a choice between runs."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_recorded_runs as m

    tour = INDEX["tour"]
    shown = [s["id"] for s in tour["scenes"]] + [tour["missed"]["id"], INDEX["featured"]]
    assert m.TOUR_AVOID_TABLES and not {EXAMPLES[i]["table_id"] for i in shown} & m.TOUR_AVOID_TABLES
    failed = lambda r: [c["name"] for c in r["result"]["verdict"]["checks"] if not c["passed"]]  # noqa: E731
    fits = [r["id"] for r in INDEX["planners"]["exaone"]["runs"] if EXAMPLES[r["id"]]["set"] == "ko_owner" and r["mark"] == "correct" and failed(r) == ["answer_matches_calc"]]
    assert fits == [tour["scenes"][0]["id"]]


def test_the_page_has_two_tabs_and_keeps_every_earlier_view():
    """The tabs are the two screens a visitor operates. The research summary repeats the portfolio and the README, so it
    is a link at the foot of the page (2026-11-21); its address and its content are unchanged."""
    html = (ROOT / "console" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "console" / "app.js").read_text(encoding="utf-8")
    import re
    tabs = re.findall(r'<a href="#(\w+)" data-view="\w+" class="navlink[^"]*">([^<]+)</a>', html)
    assert tabs == [("tour", "한눈에 보기"), ("workbench", "전체 문항 탐색")]
    for view in ("view-tour", "view-workbench", "view-matrix", "view-research", "view-about"):      # nothing was removed, three views moved one step back
        assert f'id="{view}"' in html, view
    assert 'data-sub="matrix"' in html and 'href="#about"' in html
    foot = html[html.index('<footer class="foot">'):html.index("</footer>")]
    assert 'href="#research"' in foot and 'href="#about"' in foot
    tour = js[js.index("async function renderTour"):js.index("function tourFit")]
    assert "#research" not in tour and "research.json" not in tour                              # the first screen does not repeat the summary
    assert 'const VIEWS = ["tour", "workbench", "matrix", "research", "about"]' in js and "state.recorded.tour" in js and "renderTour" in js
    # the walk-through keeps its own class names, so the question browser's marks on a table cannot be mistaken for it
    assert "tv-ev" in js and "tv-cited" in js and 'class="tv-cell' in js and "is-evidence" not in js[js.index("async function renderTour"):js.index("async function renderMatrix")]
