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
    assert [h["id"] for h in DATA["highlights"]] == ["accuracy", "evidence", "verifier", "rl", "owner", "risk"]
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


def test_results_that_went_against_expectations_are_listed():
    text = " ".join(u["text"] for u in DATA["unexpected"])
    assert f"{100 * _em('rl_v3_ko_test'):.1f}%" in text and f"{100 * _em('heuristic_ko_test'):.1f}%" in text
    assert f"{100 * _em('exaone_grpo3_vllm_ko_test'):.1f}%" in text and "넘지 못했다" in text and "0개" in text


def test_every_experiment_record_is_kept_and_belongs_to_a_group():
    assert sum(g["sections"] for g in DATA["groups"]) == len(DATA["sections"]) >= 35
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
