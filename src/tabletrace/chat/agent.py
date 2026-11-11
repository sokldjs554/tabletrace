"""The conversational agent: memory in front of the single-question pipeline.

    message -> intent (question | memory request) -> which table (given | named by the user | in focus | search)
            -> complete the follow-up from the previous turn -> AgentRuntime.run -> reply text -> remember the turn

Answers still come only from the verified pipeline; memory decides which table and which full question to ask it.
What memory contributed is returned with every reply (`memory.notes`) and recorded as the first trace step.
"""
from __future__ import annotations

from dataclasses import asdict

from tabletrace.agent.graph import AgentRuntime
from tabletrace.chat.memory import SessionStore, Turn, UserMemory
from tabletrace.chat.resolve import intent as detect_intent
from tabletrace.chat.resolve import is_follow_up, josa, pinned_table_reference, quoted, rewrite
from tabletrace.corpus.store import CorpusStore
from tabletrace.schema import AnswerResult, TraceStep

REASONS = {"not_in_document": "문서에 근거가 없습니다", "ambiguous_question": "질문이 모호합니다", "unit_mismatch": "단위나 기간이 맞지 않습니다",
           "verification_failed": "모델 제안이 검증을 통과하지 못했습니다", "retrieval_low": "관련 표를 찾지 못했습니다",
           "invalid_program": "모델 출력을 해석할 수 없습니다", "timeout": "시간이 초과됐습니다"}
NEED_USER = "기억 기능은 사용자 ID가 있어야 쓸 수 있습니다(user_id)."


class ChatAgent:
    def __init__(self, runtime: AgentRuntime, store: CorpusStore, users: UserMemory | None = None, sessions: SessionStore | None = None) -> None:
        self.rt, self.store = runtime, store
        self.users = users or UserMemory()
        self.sessions = sessions or SessionStore()

    # ---- reply text --------------------------------------------------------------------------
    def _text(self, res: AnswerResult, style: str) -> str:
        if res.status != "answered":
            reason = res.verdict.reason if res.verdict else None
            return f"답변을 보류했습니다. {REASONS.get(reason, reason or '')}".strip()
        if style != "evidence" or not res.evidence_cells:
            return res.answer or ""
        table = self.store.tables.get(res.table_id or "")
        cells = ", ".join(f"r{c.row}c{c.col}" + (f"(열: {table.header[c.col]})" if table and c.col < table.n_cols else "") for c in res.evidence_cells)
        return f"{res.answer} · 근거 셀 {cells}"

    # ---- one message -------------------------------------------------------------------------
    def handle(self, message: str, session_id: str | None = None, user_id: str | None = None, corpus: str | None = None,
               doc_id: str | None = None, table_id: str | None = None, planner: str = "auto") -> dict:
        if user_id:
            self.users.check_user(user_id)
        prefs = self.users.prefs(user_id) if user_id else {}
        existing = self.sessions.get(session_id)
        session = self.sessions.open(session_id, user_id, corpus or (existing.corpus if existing else None) or prefs.get("default_corpus") or "ko_tables")
        if corpus and corpus != session.corpus:        # the user moved to the other corpus: the old focus no longer applies
            session.corpus = corpus
        kind, args = detect_intent(message)
        turn = Turn(index=len(session.turns), message=message, intent=kind)
        result: AnswerResult | None = None
        focus_doc, focus_table = session.focus

        if kind != "ask":
            if not user_id and kind != "recall":
                turn.text = NEED_USER
            elif kind == "pin":
                target_doc, target_table = (doc_id, table_id) if table_id else (focus_doc, focus_table)
                if not target_table or target_table not in self.store.tables:
                    turn.text = "기억할 표가 없습니다. 먼저 표를 고르거나 표에 대해 질문해 주세요."
                else:
                    self.users.pin(user_id, args["name"], target_doc or self.store.tables[target_table].doc_id, target_table)
                    turn.text = f"\"{self.store.tables[target_table].title}\" 표를 {josa(quoted(args['name']), '으로', '로')} 기억했습니다."
                    turn.doc_id, turn.table_id = target_doc, target_table
            elif kind == "unpin":
                turn.text = f"\"{args['name']}\" 표를 기억에서 지웠습니다." if self.users.unpin(user_id, args["name"]) else f"\"{args['name']}\"(이)라는 이름으로 기억한 표가 없습니다."
            elif kind == "list_pins":
                pins = self.users.pins(user_id)
                turn.text = ("기억한 표: " + ", ".join(f"\"{p['name']}\"({self.store.tables[p['table_id']].title})" for p in pins if p["table_id"] in self.store.tables)) if pins else "기억한 표가 없습니다."
            elif kind == "set_pref":
                self.users.set_pref(user_id, args["key"], args["value"])
                turn.text = "앞으로 답과 함께 근거 셀을 알려 드리겠습니다." if args["value"] == "evidence" else "앞으로 답만 짧게 알려 드리겠습니다."
            elif kind == "forget":
                removed = self.users.forget(user_id)
                turn.text = f"기억을 지웠습니다(표 {removed['pins']}개, 설정 {removed['prefs']}개, 질문 기록 {removed['history']}건)."
            elif kind == "recall":
                here = [t.question for t in session.turns if t.intent == "ask" and t.question][-3:]
                earlier = [h["question"] for h in self.users.recent(user_id, 3, exclude_session=session.session_id)] if user_id else []
                parts = ([f"이 대화: {' / '.join(here)}"] if here else []) + ([f"이전 대화: {' / '.join(earlier)}"] if earlier else [])
                turn.text = " · ".join(parts) if parts else "기록된 질문이 없습니다."
        else:
            question, notes = message.strip(), []
            use_doc, use_table = doc_id, table_id
            ref = pinned_table_reference(message) if user_id else None
            pin = self.users.find_pin(user_id, ref[0]) if ref else None
            if pin and pin["table_id"] in self.store.tables and not table_id:
                use_doc, use_table, question = pin["doc_id"], pin["table_id"], ref[1]
                notes.append(f"기억해 둔 표 {josa(quoted(pin['name']), '을', '를')} 사용했습니다.")
            elif not use_table and focus_table and focus_table in self.store.tables and self.store.tables[focus_table].doc_id in self.store.docs:
                keep = is_follow_up(message)
                if not keep:                             # a full new question: stay only if search still finds the table in focus
                    idx = self.rt.indexes.get(session.corpus)
                    keep = idx is not None and any(h.id == focus_table for h in idx.search_tables(message, k=5))
                if keep and (not doc_id or doc_id == focus_doc):
                    use_doc, use_table = focus_doc, focus_table
                    notes.append("이전 턴의 표를 이어서 사용했습니다.")
                else:
                    notes.append("새 질문으로 보고 표를 다시 찾았습니다.")
            table = self.store.tables.get(use_table or "")
            rw = rewrite(question, session.last_question(), table)
            question, notes = rw.question, notes + rw.notes
            result = self.rt.run(question, session.corpus, doc_id=use_doc, table_id=use_table, planner_mode=planner)
            result.trace.insert(0, TraceStep(step="memory", tool="session", input={"message": message, "turn": turn.index},
                                             output={"question": question, "rewrite": rw.kind, "notes": notes, "table_id": use_table}))
            turn.question, turn.notes = question, notes
            turn.doc_id, turn.table_id = result.doc_id, result.table_id
            turn.status, turn.answer, turn.op = result.status, result.answer, (result.program.op if result.program else None)
            turn.evidence = [[c.row, c.col] for c in result.evidence_cells]
            turn.text = self._text(result, prefs.get("answer_style", "short"))
            if user_id:
                self.users.log(user_id, session.session_id, question, result.answer, result.table_id)
        session.add(turn)
        doc, tab = session.focus
        return {"session_id": session.session_id, "turn": turn.index, "intent": kind, "message": message, "question": turn.question,
                "text": turn.text, "memory": {"notes": turn.notes, "focus": {"doc_id": doc, "table_id": tab}, "user": user_id},
                "result": result.model_dump() if result else None, "turn_record": asdict(turn)}
