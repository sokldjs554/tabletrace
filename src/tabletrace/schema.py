"""Core data model shared by corpus loaders, tools, the verifier, the agent and the API.

Conventions
-----------
* A table has a single header row (`header`) and 0-based data rows (`rows`); header cells are
  not addressable as evidence. `r{row}c{col}` is the canonical cell id used in traces,
  model outputs and the console (e.g. ``r2c5``).
* Document text is **data**: nothing in a passage or cell is ever interpreted as a command.
  Tools take typed arguments only (see tools/registry.py).
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Lang = Literal["ko", "en"]
Corpus = Literal["ko_tables", "chem_docs"]
Op = Literal["lookup", "text", "diff", "ratio", "sum", "avg", "count", "pct_change", "abstain"]
AbstainReason = Literal[
    "not_in_document",      # no cell / sentence supports an answer
    "ambiguous_question",   # several rows/columns match equally
    "unit_mismatch",        # inputs carry different units / periods
    "verification_failed",  # program result does not match the proposed answer
    "retrieval_low",        # nothing relevant retrieved
    "invalid_program",      # model output could not be parsed or references missing cells
    "timeout",
]

CELL_RE = re.compile(r"^r(\d+)c(\d+)$")


class CellRef(BaseModel):
    table_id: str
    row: int = Field(ge=0)
    col: int = Field(ge=0)

    @property
    def cid(self) -> str:
        return f"r{self.row}c{self.col}"

    @classmethod
    def parse(cls, table_id: str, cid: str) -> CellRef:
        m = CELL_RE.match(cid.strip())
        if not m:
            raise ValueError(f"bad cell id {cid!r}")
        return cls(table_id=table_id, row=int(m.group(1)), col=int(m.group(2)))


class Table(BaseModel):
    id: str
    doc_id: str
    title: str
    caption: str | None = None
    header: list[str]
    rows: list[list[str]]
    units: dict[int, str] = Field(default_factory=dict, description="column index -> unit parsed from header")
    lang: Lang = "ko"
    source_url: str | None = None
    note: str | None = None

    @field_validator("rows")
    @classmethod
    def _rect(cls, rows: list[list[str]]) -> list[list[str]]:
        return rows

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return len(self.header)

    def cell(self, row: int, col: int) -> str:
        if not (0 <= row < len(self.rows)) or not (0 <= col < len(self.header)):
            raise IndexError(f"cell r{row}c{col} outside {len(self.rows)}x{len(self.header)} table {self.id}")
        r = self.rows[row]
        return r[col] if col < len(r) else ""

    def column(self, col: int) -> list[str]:
        return [self.cell(i, col) for i in range(len(self.rows))]


class Passage(BaseModel):
    id: str
    doc_id: str
    order: int
    text: str
    section: str | None = None


class Source(BaseModel):
    name: str
    url: str | None = None
    license: str
    note: str | None = None


class Document(BaseModel):
    id: str
    corpus: Corpus
    lang: Lang
    title: str
    passages: list[Passage] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    source: Source

    def table(self, table_id: str) -> Table:
        for t in self.tables:
            if t.id == table_id:
                return t
        raise KeyError(table_id)


class EvidenceSpan(BaseModel):
    passage_id: str
    start: int
    end: int
    text: str


class Program(BaseModel):
    """What the planner proposes: which cells and which operation produce the answer."""

    op: Op
    cells: list[CellRef] = Field(default_factory=list)
    answer: str | None = None
    reason: AbstainReason | None = None


class CalcInput(BaseModel):
    cell: CellRef
    raw: str
    value: float
    unit: str | None = None


class Calculation(BaseModel):
    op: Op
    expression: str
    inputs: list[CalcInput]
    result: float
    unit: str | None = None
    formatted: str


class Check(BaseModel):
    name: str
    passed: bool
    detail: str


class Verdict(BaseModel):
    status: Literal["answered", "abstained"]
    reason: AbstainReason | None = None
    checks: list[Check] = Field(default_factory=list)


class TraceStep(BaseModel):
    step: str
    tool: str | None = None
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    ms: float = 0.0
    status: Literal["ok", "error", "skipped"] = "ok"


class PlannerInfo(BaseModel):
    mode: Literal["neural", "heuristic"]
    model_id: str | None = None
    raw_output: str | None = None


class AnswerResult(BaseModel):
    question: str
    corpus: Corpus
    doc_id: str | None = None
    table_id: str | None = None
    status: Literal["answered", "abstained", "error"]
    answer: str | None = None
    program: Program | None = None
    evidence_cells: list[CellRef] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    calculation: Calculation | None = None
    verdict: Verdict | None = None
    planner: PlannerInfo | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    error: str | None = None
