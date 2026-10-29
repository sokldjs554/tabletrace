"""Restricted arithmetic over table cells.

Only the operations enumerated in `schema.Op` are available and every operand must be a cell
reference that parses as a single number (tools/numbers.py). Free-form expressions from the
model or from documents are never evaluated; `evaluate_expression` accepts a tiny grammar
(numbers, + - * / and parentheses) parsed with `ast` and executed by hand — no `eval`.
"""
from __future__ import annotations

import ast
import operator

from tabletrace.schema import CalcInput, Calculation, CellRef, Table
from tabletrace.tools.numbers import format_number, parse_number

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


class CalcError(ValueError):
    pass


def evaluate_expression(expr: str) -> float:
    """Evaluate '12.5 - 3' or '(60 - 40) / 40 * 100' safely. Anything else is rejected."""
    if len(expr) > 200:
        raise CalcError("expression too long")
    try:
        tree = ast.parse(expr.replace("−", "-"), mode="eval")
    except SyntaxError as e:
        raise CalcError(f"bad expression: {e.msg}") from None

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise CalcError("division by zero")
            return _BIN[type(node.op)](left, right)
        raise CalcError(f"disallowed syntax: {type(node).__name__}")

    return ev(tree)


def _inputs(table: Table, cells: list[CellRef]) -> list[CalcInput]:
    out = []
    for c in cells:
        if c.table_id != table.id:
            raise CalcError(f"cell {c.cid} belongs to table {c.table_id}, not {table.id}")
        raw = table.cell(c.row, c.col)
        p = parse_number(raw, default_unit=table.units.get(c.col))
        if p is None:
            raise CalcError(f"cell {c.cid} ({raw!r}) is not a single number")
        out.append(CalcInput(cell=c, raw=raw, value=p.value, unit=p.unit))
    return out


def compute(table: Table, op: str, cells: list[CellRef]) -> Calculation:
    """Run one restricted operation over cells of a table and return an auditable Calculation."""
    if op == "lookup":
        raise CalcError("lookup is not a calculation")
    inputs = _inputs(table, cells)
    units = {i.unit for i in inputs}
    unit = inputs[0].unit if len(units) == 1 else None
    vals = [i.value for i in inputs]
    if op == "diff":
        if len(vals) != 2:
            raise CalcError("diff needs exactly 2 cells")
        if len(units) != 1:
            raise CalcError(f"unit mismatch: {sorted(str(u) for u in units)}")
        expr = f"{vals[0]} - {vals[1]}"
    elif op == "sum":
        if len(vals) < 2:
            raise CalcError("sum needs at least 2 cells")
        if len(units) != 1:
            raise CalcError(f"unit mismatch: {sorted(str(u) for u in units)}")
        expr = " + ".join(str(v) for v in vals)
    elif op == "avg":
        if len(vals) < 2:
            raise CalcError("avg needs at least 2 cells")
        if len(units) != 1:
            raise CalcError(f"unit mismatch: {sorted(str(u) for u in units)}")
        expr = f"({' + '.join(str(v) for v in vals)}) / {len(vals)}"
    elif op == "ratio":
        if len(vals) != 2:
            raise CalcError("ratio needs exactly 2 cells")
        expr = f"{vals[0]} / {vals[1]}"
        unit = None if len(units) == 1 else f"{inputs[0].unit}/{inputs[1].unit}"
    elif op == "pct_change":
        if len(vals) != 2:
            raise CalcError("pct_change needs exactly 2 cells (new, old)")
        if len(units) != 1:
            raise CalcError(f"unit mismatch: {sorted(str(u) for u in units)}")
        expr = f"({vals[0]} - {vals[1]}) / {vals[1]} * 100"
        unit = "%"
    elif op == "count":
        expr = str(len(vals))
        unit = None
    else:
        raise CalcError(f"unknown op {op}")
    result = evaluate_expression(expr)
    formatted = format_number(result) + (f" {unit}" if unit else "")
    return Calculation(op=op, expression=expr, inputs=inputs, result=result, unit=unit, formatted=formatted)
