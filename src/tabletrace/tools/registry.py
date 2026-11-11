"""Typed tool registry: the agent can only call these functions with validated arguments.

Trust boundary: the planner (neural or heuristic) emits a *program* (op + cell ids). The program
is parsed with a strict grammar, cell ids are range-checked against the selected table, and the
operation is dispatched here. Free text from documents, tables or model output never reaches
`eval`, a shell, or any tool as code.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from tabletrace.schema import CellRef, Table, TraceStep
from tabletrace.tools.calculator import CalcError, compute
from tabletrace.tools.cells import find_cells, lookup_cell


class LookupArgs(BaseModel):
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class FindArgs(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    exact: bool = True


class RowArgs(BaseModel):
    row: int = Field(ge=0)


class ColumnArgs(BaseModel):
    col: int = Field(ge=0)
    limit: int = Field(default=40, ge=1, le=200)


class CalcArgs(BaseModel):
    op: str
    cells: list[str] = Field(min_length=1, max_length=12)


class ToolError(Exception):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[type[BaseModel], Callable[..., Any]]] = {}
        self.register("cell_lookup", LookupArgs, self._lookup)
        self.register("cell_find", FindArgs, self._find)
        self.register("calculate", CalcArgs, self._calc)
        self.register("row_read", RowArgs, self._row)
        self.register("column_read", ColumnArgs, self._column)

    def register(self, name: str, args_model: type[BaseModel], fn: Callable[..., Any]) -> None:
        self._tools[name] = (args_model, fn)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, name: str, table: Table, args: dict, trace: list[TraceStep] | None = None) -> Any:
        if name not in self._tools:
            raise ToolError(f"unknown tool {name!r}")
        model, fn = self._tools[name]
        t0 = time.perf_counter()
        try:
            parsed = model.model_validate(args)
        except ValidationError as e:
            if trace is not None:
                trace.append(TraceStep(step="tool", tool=name, input=args, output={"error": str(e)}, status="error"))
            raise ToolError(f"invalid arguments for {name}: {e.errors()[0]['msg']}") from None
        try:
            out = fn(table, parsed)
        except (CalcError, IndexError, ValueError) as e:
            if trace is not None:
                trace.append(TraceStep(step="tool", tool=name, input=parsed.model_dump(), output={"error": str(e)},
                                       ms=(time.perf_counter() - t0) * 1000, status="error"))
            raise ToolError(str(e)) from None
        if trace is not None:
            shown = out.model_dump() if isinstance(out, BaseModel) else out
            if isinstance(shown, list):
                shown = {"cells": [c.cid for c in shown]}
            trace.append(TraceStep(step="tool", tool=name, input=parsed.model_dump(), output=shown,
                                   ms=(time.perf_counter() - t0) * 1000))
        return out

    @staticmethod
    def _lookup(table: Table, a: LookupArgs) -> dict:
        return lookup_cell(table, a.row, a.col)

    @staticmethod
    def _find(table: Table, a: FindArgs) -> list[CellRef]:
        return find_cells(table, a.text, exact=a.exact)

    @staticmethod
    def _row(table: Table, a: RowArgs) -> dict:
        """All cells of one row with their ids (for a model that inspects a table step by step)."""
        if a.row >= table.n_rows:
            raise IndexError(f"row {a.row} outside a table of {table.n_rows} rows")
        return {"row": a.row, "cells": {f"r{a.row}c{j}": table.cell(a.row, j) for j in range(table.n_cols)}}

    @staticmethod
    def _column(table: Table, a: ColumnArgs) -> dict:
        if a.col >= table.n_cols:
            raise IndexError(f"column {a.col} outside a table of {table.n_cols} columns")
        shown = min(table.n_rows, a.limit)
        return {"col": a.col, "header": table.header[a.col], "cells": {f"r{i}c{a.col}": table.cell(i, a.col) for i in range(shown)},
                "rows_not_shown": table.n_rows - shown}

    @staticmethod
    def _calc(table: Table, a: CalcArgs):
        cells = [CellRef.parse(table.id, c) for c in a.cells]
        return compute(table, a.op, cells)


REGISTRY = ToolRegistry()
