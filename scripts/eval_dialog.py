"""Does session memory make follow-up questions answerable?  (data/ko/dialog_eval.jsonl, two-turn dialogs)

Three conditions per planner, same follow-up, same table:

  no_memory      the follow-up is sent alone ("그럼 독전은?") with the table selected by hand
  memory         a conversation: the agent answers turn 1 itself, then completes the follow-up from that turn
  oracle_memory  the same, but turn 1's evidence is the gold cell (isolates the resolver from turn-1 mistakes)

A follow-up counts as correct when the verified answer matches the gold cell's text.

  python scripts/eval_dialog.py --planner heuristic
  python scripts/eval_dialog.py --planner neural --model experiments/rl_v3/model
  -> experiments/eval/dialog/<planner>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_error import wilson  # noqa: E402
from tabletrace.agent.graph import AgentRuntime  # noqa: E402
from tabletrace.chat.agent import ChatAgent  # noqa: E402
from tabletrace.chat.memory import Turn  # noqa: E402
from tabletrace.corpus.store import CorpusStore  # noqa: E402
from tabletrace.eval.metrics import answer_match  # noqa: E402
from tabletrace.retrieval.index import CorpusIndex  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", choices=["heuristic", "neural"], default="heuristic")
    ap.add_argument("--model", default=None, help="model directory for --planner neural")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    dialogs = [json.loads(line) for line in open(ROOT / "data/ko/dialog_eval.jsonl", encoding="utf-8")]
    if a.limit:
        dialogs = dialogs[: a.limit]
    store = CorpusStore.from_disk()
    neural = None
    if a.planner == "neural":
        from tabletrace.model.planner import NeuralPlanner

        neural = NeuralPlanner(ROOT / a.model)
    rt = AgentRuntime({"ko_tables": CorpusIndex(store.corpora["ko_tables"], "ko")}, neural, entity_check=False)
    chat = ChatAgent(rt, store)
    rows = []
    for i, d in enumerate(dialogs):
        gold = d["answer"]

        def ok(res) -> bool:
            status, answer = (res["status"], res["answer"]) if isinstance(res, dict) else (res.status, res.answer)
            return status == "answered" and answer_match(answer, gold)  # noqa: B023

        alone = rt.run(d["follow_up"], "ko_tables", doc_id=d["doc_id"], table_id=d["table_id"], planner_mode=a.planner)
        first = chat.handle(d["first"]["question"], table_id=d["table_id"], planner=a.planner)
        second = chat.handle(d["follow_up"], session_id=first["session_id"], planner=a.planner)
        # oracle: a conversation whose first turn is recorded with the gold evidence cell
        session = chat.sessions.open(None, None, "ko_tables")
        session.add(Turn(index=0, message=d["first"]["question"], intent="ask", question=d["first"]["question"], doc_id=d["doc_id"], table_id=d["table_id"],
                         status="answered", answer=d["first"]["answer"], op="lookup", evidence=d["first"]["gold_cells"]))
        oracle = chat.handle(d["follow_up"], session_id=session.session_id, planner=a.planner)
        rows.append({"id": d["id"], "kind": d["kind"], "follow_up": d["follow_up"], "gold": gold,
                     "first_correct": first["result"]["status"] == "answered" and answer_match(first["result"]["answer"], d["first"]["answer"]),
                     "no_memory": ok(alone), "memory": ok(second["result"]), "oracle_memory": ok(oracle["result"]),
                     "rewritten": second["question"], "rewritten_oracle": oracle["question"], "rewrite_kind": oracle["result"]["trace"][0]["output"]["rewrite"],
                     "answers": {"no_memory": alone.answer, "memory": second["result"]["answer"], "oracle_memory": oracle["result"]["answer"]}})
        if (i + 1) % 100 == 0:
            print(f"{i + 1}/{len(dialogs)}", flush=True)
    out: dict = {"planner": a.planner, "model": a.model if neural else None, "dialogs": len(rows),
                 "first_turn_correct": wilson(sum(r["first_correct"] for r in rows), len(rows)),
                 "resolver_kind_matches_template": wilson(sum(r["rewrite_kind"] == r["kind"] for r in rows), len(rows))}
    for cond in ("no_memory", "memory", "oracle_memory"):
        out[cond] = {"all": wilson(sum(r[cond] for r in rows), len(rows))}
        for kind in ("row_switch", "column_switch"):
            sub = [r for r in rows if r["kind"] == kind]
            out[cond][kind] = wilson(sum(r[cond] for r in sub), len(sub))
    ok_first = [r for r in rows if r["first_correct"]]
    out["memory_when_first_turn_correct"] = wilson(sum(r["memory"] for r in ok_first), len(ok_first))
    dest = ROOT / "experiments" / "eval" / "dialog"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{a.planner}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(dest / f"{a.planner}_predictions.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in out.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
