from tabletrace.agent.program import ProgramParseError, parse
from tabletrace.eval.metrics import answer_match
from tabletrace.schema import Table
from tabletrace.verify.verifier import resolve

_SCORES = {"correct": 1.0, "repaired": 0.3, "withheld": 0.0, "wrong": -0.5, "unparsable": -1.0}


def evidence_reward(
    raw: str,
    question: str,
    table: Table,
    gold_answer: str | None,
    context: str | None = None,
    entity_check: bool = False,
) -> tuple[float, dict]:
    try:
        program = parse(raw, table.id)
    except (ProgramParseError, ValueError, TypeError, AttributeError):
        return _SCORES["unparsable"], {"level": "unparsable", "parse_ok": False, "op": None}

    try:
        strict = resolve(question, table, program, context=context, entity_check=entity_check, repair=False)
        relaxed = resolve(question, table, program, context=context, entity_check=entity_check, repair=True)
        if gold_answer is None:
            if program.op == "abstain":
                level = "correct"
            elif strict.status == "answered" or relaxed.status == "answered":
                level = "wrong"
            else:
                level = "withheld"
        elif strict.status == "answered":
            level = "correct" if answer_match(strict.answer, gold_answer) else "wrong"
        elif relaxed.status == "answered":
            level = "repaired" if answer_match(relaxed.answer, gold_answer) else "wrong"
        else:
            level = "withheld"
    except Exception:
        level = "withheld"
        return _SCORES[level], {"level": level, "parse_ok": True, "op": program.op, "error": "verification_error"}
    return _SCORES[level], {"level": level, "parse_ok": True, "op": program.op}
