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
    assert row["value"] == _em("exaone_full_vllm_ko_test") and len(row["ticks"]) == 7 and min(row["ticks"]) >= row["value"]      # eight full-data trainings, the eighth from section O
    assert f"{100 * row['value']:.1f}%" in DATA["highlights"][0]["title"]
    assert sorted(row["ticks"])[-1] == _em("exaone_full_vllm_ko_test_run2")


def test_the_chemistry_conclusion_sets_the_korean_only_model_beside_the_one_that_saw_chemistry():
    """The chart is counted from the per-question files of the two reruns. The conclusion does not credit the chemistry
    questions with the whole gain over the untuned model: it leads with the model that never saw chemistry, says the
    two tuned models are not told apart on this set, where they do part, and that this split was made after the result.
    The earlier, higher number of the run without files is given too."""
    h = next(h for h in DATA["highlights"] if h["id"] == "chem")
    rows = {r["label"]: r["value"] for r in h["rows"]}
    ko, both = rows["EXAONE 1.2B LoRA, 한국어만 튜닝"], rows["EXAONE 1.2B LoRA, 한국어와 화학을 함께 튜닝"]
    assert (ko, both) == (_em("exaone_koonly_vllm_chem_papers"), _em("exaone_kochem2_vllm_chem_papers"))
    assert rows["EXAONE 1.2B, 튜닝 없음 (화학 예시 6개)"] == _em("ref_1p2b_chem_papers")
    assert rows["휴리스틱 기준선 (모델 아님)"] == _em("heuristic_chem_papers") and rows["mT5-small 최종"] == _em("rl_v3_chem_papers") and len(rows) == 5
    assert h["title"].index(f"{100 * ko:.1f}%") < h["title"].index(f"{100 * both:.1f}%") and "한국어 표만으로" in h["title"]
    for needle in ("화학 문항을 한 번도 보지 않았다", "차이가 유의하지 않다", "답 없는 질문에서 갈린다", "결과를 본 뒤에 찾은 것이라", "미리 적어 두고",
                   "한국어 전용 모델은 한 번만 학습했고", "검수하지 않았다"):
        assert needle in h["caption"], needle
    # the repeat of the Korean-and-chemistry training is drawn as a tick on that bar, and the check written down before it is quoted
    repeat = json.loads((ROOT / "experiments/eval/chem_repeat_analysis.json").read_text(encoding="utf-8"))
    bar = next(r for r in h["rows"] if r["label"] == "EXAONE 1.2B LoRA, 한국어와 화학을 함께 튜닝")
    assert bar["ticks"] == [_em("exaone_kochem3_vllm_chem_papers")] and h["tick_label"]
    t = repeat["checks"]["unanswerable"]["repeat_vs_korean_only"]
    assert f"{t['only_candidate']} 대 {t['only_reference']}, p {t['p_display']}" in h["caption"]
    earlier = json.loads((ROOT / "experiments/gpu2_2026-11-14/recovered.json").read_text(encoding="utf-8"))["evals"]["exaone_kochem_vllm_chem_papers"]["v1"]["metrics"]["verified_em"]
    assert earlier > both and f"{100 * earlier:.1f}%" in h["caption"]
    record = next(s for s in DATA["sections"] if s["title"].startswith(h["more"]))
    assert record["group"] == "영어 화학" and any("한계" in n for n in record["notes"]) and any("짝 검정을 할 수 없다" in n for n in record["notes"])
    assert any(row[0].startswith("EXAONE 1.2B LoRA, 한국어만 튜닝") for row in record["rows"]) and any("실행 전에 정해 둔 이 세 비교는 어느 것도 유의하지 않고" in n for n in record["notes"])
    # the link opens a question on which the two tuned models part: unanswerable, the Korean-only model sent an answer
    index = json.loads((ROOT / "console/data/recorded/index.json").read_text(encoding="utf-8"))
    shown = h["link"]["href"].split("/")
    marks = {k: next(r["mark"] for r in index["planners"][k]["runs"] if r["id"] == shown[1]) for k in ("koonly", "kochem")}
    assert shown[0] == "#workbench" and shown[2] == "koonly" and marks == {"koonly": "answered_unanswerable", "kochem": "hold_ok"}


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
