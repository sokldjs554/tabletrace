"""Run the representative questions through the real pipeline and store the results for the static demo.

  python scripts/make_recorded_runs.py --planners neural heuristic --model models/mt5-small-tabletrace
  python scripts/make_recorded_runs.py --planners heuristic            # no model available

Writes console/data/recorded/index.json (runs + provenance) and console/data/recorded/documents.json
(the documents those runs use) and console/data/graph.json (the LangGraph in Mermaid).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from tabletrace import __version__
from tabletrace.agent.graph import AgentRuntime
from tabletrace.corpus.store import CorpusStore
from tabletrace.retrieval.index import CorpusIndex

ROOT = Path(__file__).resolve().parents[1]


def run_set(rt: AgentRuntime, examples: list[dict], store: CorpusStore, planner: str) -> tuple[list[dict], dict]:
    runs, docs = [], {}
    for ex in examples:
        t0 = time.time()
        res = rt.run(ex["question"], ex["corpus"], doc_id=ex["doc_id"], table_id=ex.get("table_id"), planner_mode=planner)
        runs.append({"id": ex["id"], "corpus": ex["corpus"], "doc_id": ex["doc_id"], "table_id": ex.get("table_id"),
                     "category": ex["category"], "label": ex.get("label"), "question": ex["question"],
                     "result": json.loads(res.model_dump_json()), "wall_s": round(time.time() - t0, 2)})
        docs[ex["doc_id"]] = json.loads(store.doc(ex["doc_id"]).model_dump_json())
        print(f"{planner:9s} {ex['id']:16s} {res.status:9s} {str(res.answer)[:40]!r:44s} {res.planner.mode}")
    return runs, docs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planners", nargs="+", choices=["neural", "heuristic"], default=["neural", "heuristic"])
    ap.add_argument("--model", default="models/mt5-small-tabletrace")
    ap.add_argument("--out", default="console/data/recorded")
    a = ap.parse_args()
    examples = json.loads((ROOT / "console/data/examples.json").read_text(encoding="utf-8"))
    store = CorpusStore.from_disk()
    indexes = {c: CorpusIndex(d, "ko" if c == "ko_tables" else "en") for c, d in store.corpora.items()}
    neural = None
    if "neural" in a.planners:
        from tabletrace.model.planner import NeuralPlanner

        neural = NeuralPlanner(ROOT / a.model)
    rt = AgentRuntime(indexes, neural)
    planners, all_docs = {}, {}
    for pl in a.planners:
        runs, docs = run_set(rt, examples, store, pl)
        all_docs.update(docs)
        planners[pl] = {"model_id": neural.model_id if (pl == "neural" and neural) else None, "runs": runs,
                        "answered": sum(1 for r in runs if r["result"]["status"] == "answered"),
                        "abstained": sum(1 for r in runs if r["result"]["status"] == "abstained")}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        commit = "unknown"
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    index = {"generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "commit": commit, "version": __version__,
             "hardware": "4 vCPU Intel Xeon 2.10GHz, no GPU (session container)", "planners": planners}
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "documents.json").write_text(json.dumps(all_docs, ensure_ascii=False), encoding="utf-8")
    (ROOT / "console/data/graph.json").write_text(json.dumps({"mermaid": rt.mermaid()}), encoding="utf-8")
    print("wrote", out, {k: (v["answered"], v["abstained"]) for k, v in planners.items()})


if __name__ == "__main__":
    main()
