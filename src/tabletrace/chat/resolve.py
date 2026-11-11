"""Turn a chat message into something the single-question pipeline can answer.

Two jobs, both rule-based and deterministic (no model call), so that every completion can be explained in the reply:

  intent()   is the message a question, or a request about memory ("이 표를 '박스오피스'로 기억해줘", "내 기억 지워줘")?
  rewrite()  complete a follow-up from the previous turn. Three patterns are handled:
               row switch     "그럼 신과함께는?"      -> the previous question with its row entity replaced
               column switch  "그럼 매출액은?"        -> the previous question with its column name replaced
               reference      "그 영화의 개봉일은?"    -> "그 영화" replaced by the previous row entity
             Anything else is passed on unchanged, on the table already in focus.

The previous turn's evidence cell tells which row and column the last answer came from; that is the memory this
module reads. It never invents entities: a replacement is made only with text found in the table or in the message.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from tabletrace.chat.memory import Turn
from tabletrace.schema import Table
from tabletrace.tools.cells import normalize_text

Q = r"['\"‘’“”「」『』]"
PIN = [re.compile(rf"(?:이|현재|지금|이번)\s*표(?:를|는)?\s*{Q}?(?P<name>[^'\"‘’“”「」『』]{{1,40}}?){Q}?\s*(?:이라고|라고|으로|로)\s*(?:기억|저장|고정)"),
       re.compile(rf"(?:remember|save|pin)\s+(?:this|the current)\s+table\s+as\s+{Q}?(?P<name>[^'\"]{{1,40}}?){Q}?\s*[.!]?$", re.I)]
UNPIN = [re.compile(rf"{Q}?(?P<name>[^'\"‘’“”「」『』]{{1,40}}?){Q}?\s*표(?:를|는)?\s*(?:기억에서\s*)?(?:지워|삭제|잊어)"),
         re.compile(rf"(?:forget|unpin)\s+(?:the\s+)?table\s+{Q}?(?P<name>[^'\"]{{1,40}}?){Q}?\s*[.!]?$", re.I)]
LIST_PINS = [re.compile(r"(?:내가?|기억(?:한|시킨|해\s*둔)|저장(?:한|해\s*둔)|고정(?:한|해\s*둔)?)\s*표.{0,12}(?:목록|보여|뭐|무엇|알려|있)"),
             re.compile(r"(?:my|list|show).{0,12}(?:pinned|saved|remembered)\s+tables", re.I)]
FORGET = [re.compile(r"(?:내\s*)?(?:기억|메모리|기록)(?:을|를|은|는)?\s*(?:전부|모두|다)?\s*(?:지워|삭제|잊어)"),
          re.compile(r"forget\s+(?:everything|all|my\s+(?:memory|data))", re.I)]
RECALL = [re.compile(r"(?:지난번|저번|이전에?|전에|아까|예전에?).{0,14}(?:뭐|무엇|무슨|어떤).{0,10}(?:물어|질문|물었)"),
          re.compile(r"what did i ask", re.I)]
PREF_SHORT = [re.compile(r"(?:답|답변|대답)(?:은|을|만)?\s*(?:짧게|간단히|간단하게|답만)"), re.compile(r"(?:short|brief)\s+answers?", re.I)]
PREF_EVIDENCE = [re.compile(r"근거(?:\s*셀)?(?:와|를|도|랑)?\s*(?:함께|같이|포함|붙여|보여)"), re.compile(r"(?:with|show|include)\s+(?:the\s+)?evidence", re.I)]
USE_PIN = [re.compile(rf"^{Q}?(?P<name>[^'\"‘’“”「」『』]{{1,40}}?){Q}?\s*표에서\s*(?P<rest>.+)$"),
           re.compile(rf"^in\s+(?:the\s+)?{Q}?(?P<name>[^'\"]{{1,40}}?){Q}?\s+table[,:]?\s*(?P<rest>.+)$", re.I)]

CONNECTIVE = re.compile(r"^\s*(?:그럼|그러면|그렇다면|그리고|그\s*중(?:에서?)?|그\s*밖에|또|이번엔|이번에는|반대로|거기서|then|and|so|what about|how about)\s*[,，]?\s*", re.I)
TOPIC_END = re.compile(r"\s*(?:(?:은|는|이|가|도)\s*(?:요|어때|어떤가요|어떻습니까|어떻게\s*되나요)?|\s*(?:요|어때))?\s*[?？.!]*\s*$")
INTERROGATIVE = re.compile(r"몇|얼마|언제|누구|누가|무엇|뭐|무슨|어디|어느|어떤|어떻게|왜|what|when|who|whom|how|which|where|why", re.I)
REFERENCE = re.compile(r"(?:그|해당|같은|위)\s*(?:영화|작품|팀|선수|사람|인물|배우|나라|국가|회사|기업|곳|해|날|도로|구간|물질|항목|행|것)|그것|거기|그곳|\b(?:it|that one|the same (?:one|row))\b", re.I)


_DIGIT_FINAL = {"0": 21, "1": 8, "3": 16, "6": 1, "7": 8, "8": 8}   # final consonant of the Korean reading (영 일 삼 육 칠 팔); 2 4 5 9 end open


def josa(word: str, closed: str, opened: str) -> str:
    """`word` plus the particle that fits its last syllable: josa("매출액", "은", "는") -> "매출액은", josa("차로수", "은", "는") -> "차로수는".
    For (으)로 a final ㄹ counts as open ("서울로"). When the last character has no Korean reading here (Latin, symbols) both forms are shown."""
    last = next((ch for ch in reversed(word) if ch.isalnum()), "")
    if "가" <= last <= "힣":
        final = (ord(last) - 0xAC00) % 28
    elif last in "0123456789":
        final = _DIGIT_FINAL.get(last, 0)
    else:
        return f"{word}{closed}({opened})" if len(closed) == 1 else f"{word}({closed[:-len(opened)]}){opened}"
    if closed == "으로" and final == 8:
        final = 0
    return word + (closed if final else opened)


def quoted(text: str) -> str:
    return f'"{text}"'


@dataclass
class Rewrite:
    question: str
    kind: str = "unchanged"            # unchanged | row_switch | column_switch | reference
    notes: list[str] = field(default_factory=list)


def _first(patterns, text):
    for p in patterns:
        m = p.search(text)
        if m:
            return m
    return None


def intent(message: str) -> tuple[str, dict]:
    """(intent, arguments). Intents: pin, unpin, list_pins, forget, recall, set_pref, ask."""
    text = message.strip()
    if m := _first(PIN, text):
        return "pin", {"name": m.group("name").strip()}
    if _first(LIST_PINS, text):
        return "list_pins", {}
    if _first(FORGET, text):
        return "forget", {}
    if m := _first(UNPIN, text):
        return "unpin", {"name": m.group("name").strip()}
    if _first(RECALL, text):
        return "recall", {}
    if _first(PREF_EVIDENCE, text):
        return "set_pref", {"key": "answer_style", "value": "evidence"}
    if _first(PREF_SHORT, text):
        return "set_pref", {"key": "answer_style", "value": "short"}
    return "ask", {}


def pinned_table_reference(message: str) -> tuple[str, str] | None:
    """("name", rest of the question) when the message starts with "'name' 표에서 ..."."""
    m = _first(USE_PIN, message.strip())
    return (m.group("name").strip(), m.group("rest").strip()) if m else None


def _surface(question: str, cell_text: str) -> str | None:
    """The stretch of `question` that is this cell's text (case-insensitive, whitespace-insensitive), or None."""
    words = cell_text.split()
    if not words or len(normalize_text(cell_text)) < 2:
        return None
    m = re.search(r"\s*".join(re.escape(w) for w in words), question, re.I)
    return m.group(0) if m else None


def _header_name(header: str) -> str:
    """Column name without a trailing unit: "관객수 (명)" -> "관객수"."""
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*$", "", header).strip() or header.strip()


def _mention(message: str) -> str:
    return TOPIC_END.sub("", CONNECTIVE.sub("", message)).strip(" '\"‘’“”「」『』")


def is_follow_up(message: str) -> bool:
    """A message that leans on the previous turn: starts with a connective, refers back, or is a bare topic."""
    return bool(CONNECTIVE.match(message) or REFERENCE.search(message) or not INTERROGATIVE.search(message))


def rewrite(message: str, previous: Turn | None, table: Table | None) -> Rewrite:
    """Complete `message` from the previous question on the same table. Returns it unchanged when no rule applies."""
    if previous is None or table is None or previous.table_id != table.id or len(previous.evidence) != 1:
        return Rewrite(message.strip())
    row, col = previous.evidence[0]
    if not (0 <= row < table.n_rows and 0 <= col < table.n_cols):
        return Rewrite(message.strip())
    prev_q = previous.question
    # which row entity and which column name did the previous question mention?
    labels = [s for c in range(table.n_cols) if c != col and (s := _surface(prev_q, table.cell(row, c)))]
    row_label = max(labels, key=len) if labels else None
    header = _surface(prev_q, _header_name(table.header[col]))

    # 1. reference: "그 영화의 개봉일은?"
    if m := REFERENCE.search(message):
        referent = row_label or (previous.answer or "").strip()
        if referent:
            return Rewrite(message[: m.start()] + referent + message[m.end():], "reference",
                           [f"\"{m.group(0)}\"를 이전 답의 행 {josa(quoted(referent), '으로', '로')} 바꿨습니다."])

    # 2. ellipsis: a bare topic such as "그럼 신과함께는?" or "매출액은?"
    mention = _mention(message)
    if mention and not INTERROGATIVE.search(mention) and len(mention) <= 40:
        want = normalize_text(mention)
        headers = [_header_name(h) for i, h in enumerate(table.header)
                   if i != col and want and (want == normalize_text(_header_name(h)) or (len(want) >= 2 and want in normalize_text(h)))]
        if headers and row_label:         # ask for the new column of the same row; the old predicate ("몇 명") may not fit it
            return Rewrite(f"{row_label}의 {josa(headers[0], '은', '는')} 무엇입니까?", "column_switch",
                           [f"이전 답의 행 \"{row_label}\"에서 열을 {josa(quoted(headers[0]), '으로', '로')} 바꿨습니다."])
        if headers and header:
            return Rewrite(prev_q.replace(header, headers[0], 1), "column_switch",
                           [f"이전 질문에서 열 {josa(quoted(header), '을', '를')} {josa(quoted(headers[0]), '으로', '로')} 바꿨습니다."])
        if row_label:
            in_table = any(want and want in normalize_text(v) for r in table.rows for v in r)
            note = f"이전 질문에서 {josa(quoted(row_label), '을', '를')} {josa(quoted(mention), '으로', '로')} 바꿨습니다."
            return Rewrite(prev_q.replace(row_label, mention, 1), "row_switch", [note] if in_table else [note, f"{josa(quoted(mention), '은', '는')} 이 표에서 찾지 못했습니다."])
    return Rewrite(message.strip())
