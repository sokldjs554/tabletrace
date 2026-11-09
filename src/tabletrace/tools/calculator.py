import ast
import math
import operator

from tabletrace.schema import CalcInput, Calculation
from tabletrace.tools.numbers import format_number, parse_number


class CalcError(ValueError):
    pass


def evaluate_expression(expr: str) -> float:
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    unary = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return binary[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary:
            return unary[type(node.op)](evaluate(node.operand))
        raise CalcError("unsupported expression")

    try:
        result = evaluate(ast.parse(expr, mode="eval").body)
        if not math.isfinite(result):
            raise CalcError("result must be finite")
        return float(result)
    except (SyntaxError, ArithmeticError, ValueError, RecursionError) as exc:
        raise CalcError("invalid expression") from exc


def compute(table, op: str, cells: list) -> Calculation:
    for cell in cells:
        if cell.table_id != table.id:
            raise CalcError(f"cell belongs to table {cell.table_id}")

    inputs = []
    for cell in cells:
        try:
            raw = table.cell(cell.row, cell.col)
        except (IndexError, KeyError, TypeError) as exc:
            raise CalcError("invalid cell") from exc
        parsed = parse_number(raw, table.units.get(cell.col))
        if parsed is None:
            raise CalcError("not a single number")
        inputs.append(CalcInput(cell=cell, raw=raw, value=parsed.value, unit=parsed.unit))

    if op != "count" and inputs and any(item.unit != inputs[0].unit for item in inputs[1:]):
        raise CalcError("unit mismatch")
    if op not in {"diff", "sum", "avg", "ratio", "count", "pct_change"}:
        raise CalcError("unknown operation")
    if (op in {"diff", "ratio", "pct_change"} and len(inputs) != 2) or (op in {"sum", "avg"} and len(inputs) < 2) or (op == "count" and not inputs):
        raise CalcError("invalid number of cells")

    values = [repr(item.value) for item in inputs]
    if op == "diff":
        expression = f"{values[0]} - {values[1]}"
    elif op == "ratio":
        expression = f"{values[0]} / {values[1]}"
    elif op == "pct_change":
        expression = f"({values[0]} - {values[1]}) / {values[1]} * 100"
    elif op == "count":
        expression = str(len(inputs))
    else:
        expression = " + ".join(values)
        if op == "avg":
            expression = f"({expression}) / {len(values)}"
    result = evaluate_expression(expression)
    unit = "%" if op == "pct_change" else None if op in {"ratio", "count"} else inputs[0].unit
    formatted = format_number(result) + (f" {unit}" if unit is not None else "")
    return Calculation(op=op, expression=expression, inputs=inputs, result=result, unit=unit, formatted=formatted)
