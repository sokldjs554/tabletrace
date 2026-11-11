"""Conversational agent: intents, follow-up completion from session memory, per-user long-term memory, API."""
import pytest
from fastapi.testclient import TestClient

from tabletrace.chat.agent import ChatAgent
from tabletrace.chat.memory import SessionStore, Turn, UserMemory
from tabletrace.chat.resolve import intent, is_follow_up, pinned_table_reference, rewrite
from tabletrace.service.app import build_runtime, create_app
from tabletrace.service.settings import Settings

BOX = "ko_29fbd6328d"          # 2018년 한국영화 박스 오피스 (one of the hand-made evaluation tables)
FIRST = "2018년 박스오피스에서 안시성의 관객수는 몇 명입니까?"


@pytest.fixture(scope="module")
def backend():
    store, runtime = build_runtime(Settings(planner="heuristic"))
    return store, runtime


@pytest.fixture
def chat(backend):
    store, runtime = backend
    return ChatAgent(runtime, store)


@pytest.mark.parametrize("message, expected", [
    ("이 표를 '박스오피스'로 기억해줘", ("pin", {"name": "박스오피스"})),
    ("지금 표를 내 영화표라고 저장해", ("pin", {"name": "내 영화표"})),
    ("remember this table as box office", ("pin", {"name": "box office"})),
    ("'박스오피스' 표를 지워줘", ("unpin", {"name": "박스오피스"})),
    ("내가 기억한 표 보여줘", ("list_pins", {})),
    ("내 기억 전부 지워줘", ("forget", {})),
    ("지난번에 뭐 물어봤지?", ("recall", {})),
    ("앞으로 근거와 함께 알려줘", ("set_pref", {"key": "answer_style", "value": "evidence"})),
    ("답은 짧게 해줘", ("set_pref", {"key": "answer_style", "value": "short"})),
    (FIRST, ("ask", {})),
    ("그럼 독전은?", ("ask", {})),
])
def test_intent(message, expected):
    assert intent(message) == expected


def test_pinned_table_reference():
    assert pinned_table_reference("'박스오피스' 표에서 독전의 관객수는?") == ("박스오피스", "독전의 관객수는?")
    assert pinned_table_reference("독전의 관객수는?") is None


def _prev(backend, question=FIRST, row=6, col=4, answer="5,436,789"):
    return Turn(index=0, message=question, intent="ask", question=question, table_id=BOX, status="answered", answer=answer, evidence=[[row, col]])


def test_rewrite_row_switch_column_switch_and_reference(backend):
    table = backend[0].tables[BOX]
    prev = _prev(backend)
    r = rewrite("그럼 독전은?", prev, table)
    assert (r.kind, r.question) == ("row_switch", "2018년 박스오피스에서 독전의 관객수는 몇 명입니까?")
    r = rewrite("매출액은요?", prev, table)
    assert (r.kind, r.question) == ("column_switch", "안시성의 매출액은 무엇입니까?")
    r = rewrite("그 영화의 개봉일은 언제입니까?", prev, table)
    assert (r.kind, r.question) == ("reference", "안시성의 개봉일은 언제입니까?")
    assert all(r.notes for r in (rewrite("그럼 독전은?", prev, table), rewrite("매출액은요?", prev, table)))


def test_rewrite_leaves_full_questions_and_other_tables_alone(backend):
    table = backend[0].tables[BOX]
    prev = _prev(backend)
    full = "신과함께: 인과 연의 매출액은 얼마입니까?"
    assert rewrite(full, prev, table).kind == "unchanged" and rewrite(full, prev, table).question == full
    assert rewrite("그럼 독전은?", None, table).kind == "unchanged"                  # nothing to lean on
    other = next(t for tid, t in backend[0].tables.items() if tid != BOX)
    assert rewrite("그럼 독전은?", prev, other).kind == "unchanged"                 # the previous turn was about another table
    two_cells = Turn(index=0, message="q", intent="ask", question="q", table_id=BOX, evidence=[[0, 4], [1, 4]])
    assert rewrite("그럼 독전은?", two_cells, table).kind == "unchanged"            # calculations are not completed
    assert not is_follow_up(full) and is_follow_up("그럼 독전은?") and is_follow_up("그 영화의 개봉일은 언제입니까?")


def test_rewrite_never_invents_an_entity(backend):
    r = rewrite("그럼 없는영화는?", _prev(backend), backend[0].tables[BOX])
    assert r.kind == "row_switch" and "없는영화" in r.question and any("찾지 못했습니다" in n for n in r.notes)


def test_conversation_carries_the_table_and_completes_follow_ups(chat):
    a = chat.handle(FIRST, table_id=BOX)
    sid = a["session_id"]
    assert a["text"] == "5,436,789" and a["memory"]["notes"] == [] and a["result"]["trace"][0]["step"] == "memory"
    b = chat.handle("그럼 독전은?", session_id=sid)
    assert b["question"] == "2018년 박스오피스에서 독전의 관객수는 몇 명입니까?" and b["text"] == "5,063,620"
    assert b["memory"]["focus"]["table_id"] == BOX and len(b["memory"]["notes"]) == 2
    assert b["result"]["trace"][0]["output"]["rewrite"] == "row_switch"
    c = chat.handle("매출액은?", session_id=sid)
    assert c["question"] == "독전의 매출액은 무엇입니까?" and c["text"] == "43,483,690,913"
    d = chat.handle("그 영화의 개봉일은 언제입니까?", session_id=sid)
    assert d["text"] == "5월 22일"
    e = chat.handle("그럼 없는영화는?", session_id=sid)                      # not in the table: the pipeline withholds
    assert e["result"]["status"] == "abstained" and e["text"].startswith("답변을 보류했습니다")
    assert [t["intent"] for t in chat.sessions.get(sid).view()["turns"]] == ["ask"] * 5


def test_without_memory_the_follow_up_alone_is_not_answerable(backend):
    _, runtime = backend
    res = runtime.run("그럼 독전은?", "ko_tables", table_id=BOX)
    assert res.status == "abstained" or res.answer != "5,063,620"


def test_personal_memory_pins_preferences_and_forgetting(chat):
    sid = chat.handle(FIRST, table_id=BOX, user_id="u1")["session_id"]
    assert "기억했습니다" in chat.handle("이 표를 '박스오피스'로 기억해줘", session_id=sid, user_id="u1")["text"]
    assert chat.handle("근거와 함께 알려줘", session_id=sid, user_id="u1")["intent"] == "set_pref"
    # a new conversation: the pinned table is found by name and the preference still applies
    fresh = chat.handle("'박스오피스' 표에서 독전의 관객수는 몇 명입니까?", user_id="u1")
    assert fresh["session_id"] != sid and fresh["memory"]["focus"]["table_id"] == BOX
    assert fresh["text"].startswith("5,063,620 · 근거 셀 r9c4") and any("기억해 둔 표" in n for n in fresh["memory"]["notes"])
    assert "박스오피스" in chat.handle("내가 기억한 표 보여줘", user_id="u1")["text"]
    recall = chat.handle("지난번에 뭐 물어봤지?", session_id=fresh["session_id"], user_id="u1")["text"]
    assert "이전 대화" in recall and "안시성" in recall
    assert chat.users.view("u1")["prefs"] == {"answer_style": "evidence"}
    removed = chat.handle("내 기억 지워줘", user_id="u1")["text"]
    assert "표 1개" in removed and chat.users.view("u1") == {"user_id": "u1", "pins": [], "prefs": {}, "recent": []}


def test_memory_requests_need_a_user_and_other_users_see_nothing(chat):
    sid = chat.handle(FIRST, table_id=BOX)["session_id"]
    assert "사용자 ID" in chat.handle("이 표를 '박스'로 기억해줘", session_id=sid)["text"]
    chat.handle("이 표를 '박스'로 기억해줘", session_id=sid, user_id="alice")
    assert chat.users.pins("alice") and chat.users.pins("bob") == []
    assert chat.handle("'박스' 표에서 독전의 관객수는 몇 명입니까?", user_id="bob")["memory"]["notes"] == []     # bob has no such table
    chat.users.forget("alice")


def test_user_memory_persists_in_a_file_and_validates(tmp_path):
    path = str(tmp_path / "memory.sqlite")
    UserMemory(path).pin("u1", "표1", "doc", BOX)
    UserMemory(path).set_pref("u1", "answer_style", "evidence")
    again = UserMemory(path)                                    # a new process would open the same file
    assert again.pins("u1") == [{"name": "표1", "doc_id": "doc", "table_id": BOX}] and again.prefs("u1") == {"answer_style": "evidence"}
    with pytest.raises(ValueError):
        again.set_pref("u1", "answer_style", "poem")
    with pytest.raises(ValueError):
        again.pins("u1; DROP TABLE pins")
    assert again.forget("u1") == {"pins": 1, "prefs": 1, "history": 0}


def test_session_store_is_bounded():
    store = SessionStore(max_sessions=2, idle_s=3600)
    a, b = store.open(None, None, "ko_tables"), store.open(None, None, "ko_tables")
    a.touched -= 10
    c = store.open(None, None, "ko_tables")
    assert store.get(a.session_id) is None and store.get(b.session_id) is b and store.get(c.session_id) is c
    stale = SessionStore(max_sessions=5, idle_s=1)
    s = stale.open(None, None, "ko_tables")
    s.touched -= 5
    stale.open(None, None, "ko_tables")
    assert stale.get(s.session_id) is None


def test_chat_api(tmp_path):
    settings = Settings(planner="heuristic", memory_path=str(tmp_path / "m.sqlite"))
    with TestClient(create_app(settings)) as client:
        a = client.post("/v1/chat", json={"message": FIRST, "table_id": BOX, "user_id": "u9"}).json()
        b = client.post("/v1/chat", json={"message": "그럼 독전은?", "session_id": a["session_id"], "user_id": "u9"}).json()
        assert (a["text"], b["text"]) == ("5,436,789", "5,063,620") and b["turn"] == 1
        session = client.get(f"/v1/chat/{a['session_id']}").json()
        assert len(session["turns"]) == 2 and session["focus"]["table_id"] == BOX
        assert len(client.get("/v1/users/u9/memory").json()["recent"]) == 2
        assert client.delete("/v1/users/u9/memory").json()["removed"]["history"] == 2
        assert client.get("/v1/chat/unknown").status_code == 404
        assert client.post("/v1/chat", json={"message": "x", "table_id": "missing"}).status_code == 404
        assert client.post("/v1/chat", json={"message": "x", "session_id": "../etc"}).status_code == 422
        assert client.post("/v1/chat", json={"message": "x", "user_id": "a b"}).status_code == 422
        assert client.get("/v1/users/a%20b/memory").status_code == 422


def test_particles_follow_the_last_syllable():
    from tabletrace.chat.resolve import josa
    assert josa("매출액", "은", "는") == "매출액은" and josa("차로수", "은", "는") == "차로수는"
    assert josa("서울", "으로", "로") == "서울로" and josa("부산", "으로", "로") == "부산으로" and josa("대구", "으로", "로") == "대구로"
    assert josa("2018", "을", "를") == "2018을" and josa("2019", "을", "를") == "2019를" and josa("7", "으로", "로") == "7로"
    assert josa('"독전"', "을", "를") == '"독전"을'                      # closing quotes and brackets are skipped
    assert josa("GDP", "은", "는") == "GDP은(는)" and josa("km", "으로", "로") == "km(으)로"   # no Korean reading: show both
