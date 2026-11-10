"""The recorded demo must show real outputs: stored model outputs replayed through the pipeline, never typed in."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = json.loads((ROOT / "console" / "data" / "recorded" / "index.json").read_text(encoding="utf-8"))
EXAMPLES = {e["id"]: e for e in json.loads((ROOT / "console" / "data" / "examples.json").read_text(encoding="utf-8"))}


def test_every_recorded_run_belongs_to_a_representative_question():
    for key, planner in INDEX["planners"].items():
        assert planner["runs"], key
        for run in planner["runs"]:
            assert run["id"] in EXAMPLES and run["question"] == EXAMPLES[run["id"]]["question"], (key, run["id"])
            assert run["result"]["status"] in ("answered", "abstained"), (key, run["id"])


def test_stored_model_outputs_match_the_evaluation_they_come_from():
    """The EXAONE planner in the demo replays raw outputs from an evaluation run; each must be that run's output."""
    planner = INDEX["planners"]["exaone"]
    src = planner["source"]
    stored = {}
    with open(ROOT / src["eval_dir"] / "predictions.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            stored[r["question"]] = r
    assert len(planner["runs"]) + src["examples_without_output"] == len(EXAMPLES)
    for run in planner["runs"]:
        first = next(s for s in run["result"]["trace"] if s["step"] == "propose")
        assert first["output"]["raw"] == stored[run["question"]]["raw_output"], run["id"]
        assert run["engine_ms"] == round(stored[run["question"]]["ms"], 1)
        assert run["result"]["planner"]["model_id"] == planner["model_id"]
    meta = json.loads((ROOT / src["eval_dir"] / "metrics.json").read_text(encoding="utf-8"))["meta"]
    assert src["generated"] == meta["finished"][:10]


def test_console_offers_the_stored_planner_and_marks_cited_cells():
    html = (ROOT / "console" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "console" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "console" / "styles.css").read_text(encoding="utf-8")
    assert 'option value="exaone"' in html
    assert 'PLANNER_ORDER = ["exaone", "neural", "heuristic"]' in js
    assert "is-cited" in js and "td.is-cited" in css and "badge-fix" in js and ".badge-fix" in css


def test_a_repaired_answer_is_among_the_stored_runs():
    """The demo needs at least one answer whose cited cell the verifier repaired, to show the two cells apart."""
    repaired = [r for r in INDEX["planners"]["exaone"]["runs"]
                if any(c["name"] == "evidence_repaired" for c in r["result"]["verdict"]["checks"])]
    assert repaired
    for run in repaired:
        first = next(s for s in run["result"]["trace"] if s["step"] == "propose")
        cited = {(c["row"], c["col"]) for c in first["output"]["parsed"]["cells"]}
        evidence = {(c["row"], c["col"]) for c in run["result"]["evidence_cells"]}
        assert cited and evidence and not cited & evidence
