"""The TableTrace agent as a LangGraph state machine.

Why LangGraph: the answer pipeline is not a single LLM call but a small workflow with branches
(retrieve -> select table -> propose program -> execute tools -> verify -> answer | abstain, with
one bounded retry when the proposal fails verification). LangGraph gives us an explicit, inspectable
graph whose node boundaries are exactly the trace steps the console shows; every node is a plain
function over a typed state, so the same graph runs with the neural planner or the heuristic one.

Nothing here executes free text: the planner output is parsed by `agent.program.parse`, tools are
called through `tools.registry` with validated arguments, and document text is only ever data.
"""
from __future__ import annotations

import time
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from tabletrace.agent.heuristic import plan as heuristic_plan
from tabletrace.agent.program import serialize
from tabletrace.retrieval.index import CorpusIndex
from tabletrace.schema import AnswerResult, Corpus, Document, PlannerInfo, Program, Table, TraceStep
from tabletrace.verify.verifier import Resolution, resolve

MAX_PROPOSALS = 2


class AgentState(TypedDict, total=False):
    question: str
    corpus: Corpus
    doc_id: str | None
    table_id: str | None
    planner_mode: str
    # filled by nodes
    doc: Document | None
    table: Table | None
    context: str | None
    context_passage_id: str | None
    retrieval: dict
    program: Program | None
    raw_output: str | None
    attempts: int
    resolution: Resolution | None
    trace: list[TraceStep]
    result: AnswerResult | None
    t_start: float


class AgentRuntime:
    """Holds indexes and planners; builds one compiled graph that nodes close over."""

    def __init__(self, indexes: dict[str, CorpusIndex], neural_planner: Any | None = None) -> None:
        self.indexes = indexes
        self.neural = neural_planner
        self.graph = self._build()

    # ---- nodes -------------------------------------------------------------------------
    def retrieve(self, s: AgentState) -> AgentState:
        t0 = time.perf_counter()
        idx = self.indexes[s["corpus"]]
        trace = s.get("trace", [])
        doc = idx.docs.get(s["doc_id"]) if s.get("doc_id") else None
        table = None
        if s.get("table_id") and s["table_id"] in idx.tables:
            table = idx.tables[s["table_id"]]
            doc = idx.docs[table.doc_id]
        hits_t = idx.search_tables(s["question"], k=3, doc_id=doc.id if doc else None)
        hits_p = idx.search_passages(s["question"], k=3, doc_id=doc.id if doc else None)
        if table is None and hits_t:
            table = idx.tables[hits_t[0].id]
            doc = idx.docs[table.doc_id]
        if table is None and doc is not None and doc.tables:
            table = doc.tables[0]
        context, pid = None, None
        if hits_p:
            p = idx.passages[hits_p[0].id]
            context, pid = p.text[:300], p.id
        elif doc and doc.passages:
            context, pid = doc.passages[0].text[:300], doc.passages[0].id
        trace.append(TraceStep(step="retrieve", tool="bm25", input={"query": s["question"], "doc_id": doc.id if doc else None},
                               output={"tables": [h.__dict__ for h in hits_t], "passages": [h.__dict__ for h in hits_p],
                                       "selected_table": table.id if table else None, "context_passage": pid},
                               ms=(time.perf_counter() - t0) * 1000))
        return {"doc": doc, "table": table, "context": context, "context_passage_id": pid, "trace": trace,
                "retrieval": {"tables": [h.__dict__ for h in hits_t], "passages": [h.__dict__ for h in hits_p]},
                "attempts": 0}

    def propose(self, s: AgentState) -> AgentState:
        t0 = time.perf_counter()
        trace = s["trace"]
        table = s.get("table")
        if table is None:
            trace.append(TraceStep(step="propose", status="skipped", output={"reason": "no table"}))
            return {"program": None, "raw_output": None, "attempts": s.get("attempts", 0) + 1}
        mode = s.get("planner_mode", "auto")
        use_neural = self.neural is not None and mode in ("auto", "neural")
        if use_neural:
            prog, raw, rows, _ms = self.neural.plan(s["question"], table, s.get("context"))
            info = {"mode": "neural", "model": self.neural.model_id, "rows_shown": rows}
        else:
            prog = heuristic_plan(s["question"], table, table.lang)
            raw, info = serialize(prog), {"mode": "heuristic"}
        trace.append(TraceStep(step="propose", tool=info["mode"], input={"question": s["question"], "table_id": table.id, **info},
                               output={"raw": raw, "parsed": prog.model_dump() if prog else None},
                               ms=(time.perf_counter() - t0) * 1000, status="ok" if prog else "error"))
        return {"program": prog, "raw_output": raw, "attempts": s.get("attempts", 0) + 1, "planner_info": info}

    def verify(self, s: AgentState) -> AgentState:
        t0 = time.perf_counter()
        res = resolve(s["question"], s.get("table"), s.get("program"), context=s.get("context"),
                      passage_id=s.get("context_passage_id") or "context")
        trace = s["trace"] + res.trace
        trace.append(TraceStep(step="verify", output={"status": res.status, "reason": res.verdict.reason,
                                                       "checks": [c.model_dump() for c in res.verdict.checks]},
                               ms=(time.perf_counter() - t0) * 1000))
        return {"resolution": res, "trace": trace}

    def finalize(self, s: AgentState) -> AgentState:
        res: Resolution = s["resolution"]
        info = s.get("planner_info", {"mode": "heuristic"})
        result = AnswerResult(
            question=s["question"], corpus=s["corpus"], doc_id=s["doc"].id if s.get("doc") else None,
            table_id=s["table"].id if s.get("table") else None, status=res.status, answer=res.answer,
            program=s.get("program"), evidence_cells=res.cells, evidence_spans=res.spans, calculation=res.calculation,
            verdict=res.verdict, planner=PlannerInfo(mode=info["mode"], model_id=info.get("model"), raw_output=s.get("raw_output")),
            trace=s["trace"], elapsed_ms=(time.perf_counter() - s["t_start"]) * 1000,
        )
        return {"result": result}

    # ---- edges -------------------------------------------------------------------------
    @staticmethod
    def after_verify(s: AgentState) -> str:
        res: Resolution = s["resolution"]
        prog = s.get("program")
        # one bounded retry with the heuristic planner when the neural proposal was unusable
        if (res.status == "abstained" and res.verdict.reason in ("invalid_program", "verification_failed")
                and s.get("attempts", 0) < MAX_PROPOSALS and s.get("planner_info", {}).get("mode") == "neural"
                and (prog is None or prog.op != "abstain")):
            return "retry"
        return "done"

    def propose_fallback(self, s: AgentState) -> AgentState:
        t0 = time.perf_counter()
        table = s["table"]
        prog = heuristic_plan(s["question"], table, table.lang)
        s["trace"].append(TraceStep(step="propose", tool="heuristic", input={"question": s["question"], "table_id": table.id, "fallback": True},
                                    output={"raw": serialize(prog), "parsed": prog.model_dump()}, ms=(time.perf_counter() - t0) * 1000))
        return {"program": prog, "raw_output": serialize(prog), "attempts": s["attempts"] + 1,
                "planner_info": {**s.get("planner_info", {}), "mode": "neural", "fallback": "heuristic"}}

    def _build(self):
        g = StateGraph(AgentState)
        g.add_node("retrieve", self.retrieve)
        g.add_node("propose", self.propose)
        g.add_node("verify", self.verify)
        g.add_node("propose_fallback", self.propose_fallback)
        g.add_node("finalize", self.finalize)
        g.set_entry_point("retrieve")
        g.add_edge("retrieve", "propose")
        g.add_edge("propose", "verify")
        g.add_conditional_edges("verify", self.after_verify, {"retry": "propose_fallback", "done": "finalize"})
        g.add_edge("propose_fallback", "verify")
        g.add_edge("finalize", END)
        return g.compile()

    # ---- entry ---------------------------------------------------------------------------
    def run(self, question: str, corpus: Corpus, doc_id: str | None = None, table_id: str | None = None,
            planner_mode: str = "auto") -> AnswerResult:
        state: AgentState = {"question": question, "corpus": corpus, "doc_id": doc_id, "table_id": table_id,
                             "planner_mode": planner_mode, "trace": [], "t_start": time.perf_counter()}
        out = self.graph.invoke(state)
        return out["result"]

    def mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()
