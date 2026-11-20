import re

from tabletrace.agent.program import make, make_abstain
from tabletrace.retrieval.tokenize import tokenize
from tabletrace.schema import CellRef, Program, Table
from tabletrace.tools.cells import column_overlap_scores, normalize_text, row_overlap_scores
from tabletrace.tools.numbers import parse_number

_INTENTS = (
    ("ratio", r"비율|몇 배|배인|ratio|times (larger|greater|higher|more)|fold|by what factor"),
    ("pct_change", r"몇 ?%|퍼센트|percent(age)? change|증가율|감소율|성장률"),
    ("avg", r"평균|average|mean"),
    ("diff", r"차이|차는|더 많|더 적|더 (길|크|높|낮|짧|무거|가벼)|몇 .{0,6}더|빼면|감소|증가(량|폭)|difference|more than|fewer|less than|increase|decrease|change in|how much (higher|lower|larger|smaller|greater|bigger|longer|heavier)"),
    ("sum", r"합계|합은|합이|총합|모두 합|더하면|총 |total|sum of|combined|altogether|in total"),
)


def _calc_intent(question: str) -> str | None:
    lower = question.lower()
    for operation, pattern in _INTENTS:
        if re.search(pattern, lower):
            return operation
    return None


def _named_column(table: Table, tokens: list[str]) -> int | None:
    scores = column_overlap_scores(table, tokens)
    for col, header in enumerate(table.header):
        name = normalize_text(header)
        if len(name) >= 2 and any(name in token and token != name for token in tokens):
            scores[col] += 1
    best = max(range(len(scores)), key=scores.__getitem__, default=None)
    return best if best is not None and scores[best] > 0 else None


def _quantity_column(table: Table, preferred: int | None) -> int | None:
    minimum = max(2, int(len(table.rows) * 0.6))
    last_numeric = None
    for col in range(len(table.header)):
        unit = table.units.get(col)
        count = sum(parse_number(row[col], unit) is not None for row in table.rows if col < len(row))
        if count >= minimum:
            if col == preferred:
                return col
            last_numeric = col
    return last_numeric


def _row_scores(table: Table, tokens: list[str], question_text: str, excluded: int | None) -> list[float]:
    scores = row_overlap_scores(table, tokens, exclude_col=excluded)
    for index, row in enumerate(table.rows):
        for col, cell in enumerate(row):
            if col != excluded:
                phrase = normalize_text(cell)
                if len(phrase) >= 2 and phrase in question_text:
                    scores[index] += 2
    return scores


def _first_mention(row: list[str], question_text: str) -> int:
    positions = []
    for cell in row:
        phrase = normalize_text(cell)
        if len(phrase) >= 2:
            start = question_text.find(phrase)
            if start >= 0:
                positions.append(start)
    return min(positions, default=10**6)


def plan(question: str, table: Table, lang: str) -> Program:
    tokens = set(tokenize(question, lang))
    tokens.update(normalize_text(word) for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9\.\-]+", question))
    tokens.discard("")
    if not tokens:
        return make_abstain("ambiguous_question")

    row_words = [word for word in tokens if len(word) >= 2 or word.isdigit()]
    question_text = normalize_text(question)
    named = _named_column(table, list(tokens))
    operation = _calc_intent(question)
    if operation:
        target = _quantity_column(table, named)
        if target is not None:
            scores = _row_scores(table, row_words, question_text, target)
            matches = [i for i, score in enumerate(scores) if score > 0]
            matches.sort(key=scores.__getitem__, reverse=True)
            operands = matches[:3] if operation == "sum" else matches[:2]
            if len(operands) >= 2:
                operands.sort(key=lambda i: _first_mention(table.rows[i], question_text))
                return make(operation, [CellRef(table_id=table.id, row=i, col=target) for i in operands], None)

    scores = _row_scores(table, row_words, question_text, named)
    highest = max(scores, default=0)
    if highest <= 0:
        return make_abstain("not_in_document")
    if scores.count(highest) > 1:
        return make_abstain("ambiguous_question")
    row = scores.index(highest)
    if named is None:
        remaining = []
        for col, cell in enumerate(table.rows[row]):
            value = normalize_text(cell)
            if not any(word in value for word in row_words):
                remaining.append(col)
        if len(remaining) != 1:
            return make_abstain("ambiguous_question")
        named = remaining[0]

    ref = CellRef(table_id=table.id, row=row, col=named)
    return make("lookup", [ref], table.cell(row, named))
