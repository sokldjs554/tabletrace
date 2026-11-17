"""The top layer of the 연구 결과 view: conclusions with one chart each, built from result files, over the folded detail."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_highlights as H  # noqa: E402

DATA = json.loads((ROOT / "console/data/research.json").read_text(encoding="utf-8"))


def _em(run):
    return json.loads((ROOT / "experiments/eval" / run / "metrics.json").read_text(encoding="utf-8"))["metrics"]["verified_em"]


def test_the_stored_highlights_are_what_the_result_files_give_now():
    """console/data/research.json must not lag behind the artifacts it summarises."""
    assert DATA["highlights"] == H.highlights()
    assert DATA["unexpected"] == H.unexpected()


def test_every_highlight_has_a_chart_form_a_caption_and_one_experiment_record_to_point_to():
    assert [h["id"] for h in DATA["highlights"]] == ["accuracy", "evidence", "verifier", "rl", "owner", "chem", "risk"]
    assert {h["kind"] for h in DATA["highlights"]} == {"bars", "stack", "dumbbell", "meter", "line"}
    for h in DATA["highlights"] + DATA["unexpected"]:
        assert len([s for s in DATA["sections"] if s["title"].startswith(h["more"])]) == 1, h["more"]
    assert all(h["title"] and h["caption"] for h in DATA["highlights"])


def test_the_headline_is_the_lowest_of_the_full_data_trainings():
    """The bar the first chart accents is the first, lowest training; the other trainings are given as a range."""
    row = next(r for r in DATA["highlights"][0]["rows"] if r.get("emphasis"))
    assert row["value"] == _em("exaone_full_vllm_ko_test") and len(row["ticks"]) == 6 and min(row["ticks"]) >= row["value"]
    assert f"{100 * row['value']:.1f}%" in DATA["highlights"][0]["title"]
    assert sorted(row["ticks"])[-1] == _em("exaone_full_vllm_ko_test_run2")


def test_the_chemistry_conclusion_is_the_run_that_kept_its_predictions_and_says_the_earlier_number():
    """The chart is counted from the per-question files of the rerun, and the caption gives the earlier, higher number
    (recovered from the notebook's output) next to it instead of leaving it out."""
    h = next(h for h in DATA["highlights"] if h["id"] == "chem")
    rows = {r["label"].split(" ")[0] + ("+" if r.get("emphasis") else ""): r["value"] for r in h["rows"]}
    assert rows["EXAONE+"] == _em("exaone_kochem2_vllm_chem_papers") and rows["EXAONE"] == _em("ref_1p2b_chem_papers")
    assert rows["휴리스틱"] == _em("heuristic_chem_papers") and rows["mT5-small"] == _em("rl_v3_chem_papers")
    earlier = json.loads((ROOT / "experiments/gpu2_2026-11-14/recovered.json").read_text(encoding="utf-8"))["evals"]["exaone_kochem_vllm_chem_papers"]["v1"]["metrics"]["verified_em"]
    assert earlier > rows["EXAONE+"] and f"{100 * earlier:.1f}%" in h["caption"] and "학습 한 번" in h["caption"] and "검수하지 않았다" in h["caption"]
    record = next(s for s in DATA["sections"] if s["title"].startswith(h["more"]))
    assert record["group"] == "영어 화학" and any("한계" in n for n in record["notes"]) and any("짝 검정을 할 수 없다" in n for n in record["notes"])
    index = json.loads((ROOT / "console/data/recorded/index.json").read_text(encoding="utf-8"))
    shown = h["link"]["href"].split("/")
    assert shown[0] == "#workbench" and shown[2] == "kochem" and any(r["id"] == shown[1] and r["mark"] == "correct" for r in index["planners"]["kochem"]["runs"])


def test_results_that_went_against_expectations_are_listed():
    text = " ".join(u["text"] for u in DATA["unexpected"])
    assert f"{100 * _em('rl_v3_ko_test'):.1f}%" in text and f"{100 * _em('heuristic_ko_test'):.1f}%" in text
    assert f"{100 * _em('exaone_grpo3_vllm_ko_test'):.1f}%" in text and "넘지 못했다" in text and "0개" in text


def test_every_experiment_record_is_kept_and_belongs_to_a_group():
    assert sum(g["sections"] for g in DATA["groups"]) == len(DATA["sections"]) >= 36
    names = [g["name"] for g in DATA["groups"]]
    assert all(s["group"] in names for s in DATA["sections"])
    assert all(s.get("artifact") or s["status"] != "done" or s.get("columns") for s in DATA["sections"])


def test_the_page_loads_the_chart_code_and_the_single_file_build_carries_it():
    html = (ROOT / "console/index.html").read_text(encoding="utf-8")
    assert html.index('<script src="charts.js"></script>') < html.index('<script src="app.js"></script>')
    charts = (ROOT / "console/charts.js").read_text(encoding="utf-8")
    assert all(f"function {k}(" in charts for k in ("bars", "stack", "dumbbell", "meter", "line")) and "표로 보기" in charts
    assert "innerHTML" not in charts.split("function bind(")[1]        # the tooltip takes its text with textContent
    assert "charts.js" in (ROOT / "scripts/build_artifact_page.py").read_text(encoding="utf-8")
