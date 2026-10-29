"""Neural planner: the fine-tuned mT5 proposes a Program for (question, table, context)."""
from __future__ import annotations

import time
from pathlib import Path

from tabletrace.agent.program import ProgramParseError, parse
from tabletrace.model.serialize import build_input, fit_rows
from tabletrace.schema import Program, Table


class NeuralPlanner:
    def __init__(self, model_dir: str | Path, max_in: int = 512, max_out: int = 64, threads: int | None = None,
                 quantize: bool = False) -> None:
        import torch
        from transformers import MT5ForConditionalGeneration, PreTrainedTokenizerFast

        if threads:
            torch.set_num_threads(threads)
        self.model_dir = str(model_dir)
        self.tok = PreTrainedTokenizerFast.from_pretrained(model_dir)
        self.model = MT5ForConditionalGeneration.from_pretrained(model_dir)
        self.model.eval()
        self.quantized = False
        if quantize:
            self.model = torch.ao.quantization.quantize_dynamic(self.model, {torch.nn.Linear}, dtype=torch.qint8)
            self.quantized = True
        self.max_in, self.max_out = max_in, max_out
        self.model_id = Path(model_dir).name + (":int8" if quantize else "")

    def inputs_for(self, question: str, table: Table, context: str | None) -> tuple[str, int]:
        n = fit_rows(self.tok, question, table, context, self.max_in)
        if n < 2 and context:
            context, n = None, fit_rows(self.tok, question, table, None, self.max_in)
        return build_input(question, table, context, max_rows=n), n

    def generate(self, texts: list[str], **gen_kwargs) -> list[str]:
        import torch

        enc = self.tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=self.max_in)
        with torch.no_grad():
            out = self.model.generate(**enc, max_new_tokens=self.max_out, do_sample=False, num_beams=1, **gen_kwargs)
        return self.tok.batch_decode(out, skip_special_tokens=True)

    def plan_batch(self, items: list[tuple[str, Table, str | None]], batch_size: int = 8) -> list[tuple[Program | None, str, int, float]]:
        """-> [(program or None if unparsable, raw text, rows shown, ms)]"""
        results: list[tuple[Program | None, str, int, float]] = []
        for i in range(0, len(items), batch_size):
            chunk = items[i:i + batch_size]
            texts, rows = [], []
            for q, t, c in chunk:
                txt, n = self.inputs_for(q, t, c)
                texts.append(txt)
                rows.append(n)
            t0 = time.perf_counter()
            raws = self.generate(texts)
            ms = (time.perf_counter() - t0) * 1000 / len(chunk)
            for (_q, t, _c), raw, n in zip(chunk, raws, rows, strict=True):
                try:
                    prog = parse(raw, t.id)
                except ProgramParseError:
                    prog = None
                results.append((prog, raw, n, ms))
        return results

    def plan(self, question: str, table: Table, context: str | None = None) -> tuple[Program | None, str, int, float]:
        return self.plan_batch([(question, table, context)])[0]
