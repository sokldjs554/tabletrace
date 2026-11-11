"""Neural planner: the fine-tuned mT5 proposes a Program for (question, table, context)."""
from __future__ import annotations

import time
from pathlib import Path

from tabletrace.agent.program import ProgramParseError, parse
from tabletrace.model.serialize import build_input, choose_context_and_rows
from tabletrace.schema import Program, Table


class NeuralPlanner:
    def __init__(self, model_dir: str | Path, max_in: int = 512, max_out: int = 64, threads: int | None = None,
                 quantize: bool | str = False) -> None:
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
            from tabletrace.model.quant import quantize_model

            scope = quantize if isinstance(quantize, str) else "all"
            self.model = quantize_model(self.model, scope)
            self.quantized = True
        self.max_in, self.max_out = max_in, max_out
        tag = ""
        if quantize:
            tag = ":int8" if quantize is True or quantize == "all" else f":int8-{quantize}"
        self.model_id = Path(model_dir).name + tag

    def inputs_for(self, question: str, table: Table, context: str | None) -> tuple[str, int]:
        context, n = choose_context_and_rows(self.tok, question, table, context, self.max_in)
        return build_input(question, table, context, max_rows=n), n

    def generate(self, texts: list[str], **gen_kwargs) -> list[str]:
        import torch

        enc = self.tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=self.max_in)
        with torch.no_grad():
            out = self.model.generate(**enc, max_new_tokens=self.max_out, do_sample=False, num_beams=1, **gen_kwargs)
        return self.tok.batch_decode(out, skip_special_tokens=True)

    def generate_scored(self, texts: list[str]) -> tuple[list[str], list[dict | None]]:
        """Greedy decoding plus the log-probability of every generated token (the model's own confidence)."""
        import torch

        from tabletrace.service.engines import confidence_from

        enc = self.tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=self.max_in)
        with torch.no_grad():
            out = self.model.generate(**enc, max_new_tokens=self.max_out, do_sample=False, num_beams=1, output_scores=True, return_dict_in_generate=True)
        scores = self.model.compute_transition_scores(out.sequences, out.scores, normalize_logits=True)
        generated = out.sequences[:, 1:]                       # without the decoder start token
        confs = []
        for row, ids in zip(scores.tolist(), generated.tolist(), strict=True):
            keep = []
            for lp, tid in zip(row, ids, strict=True):
                if tid == self.tok.pad_token_id:
                    break
                keep.append(lp)                                # the end-of-sequence token is part of what the model chose
            confs.append(confidence_from(keep))
        return self.tok.batch_decode(out.sequences, skip_special_tokens=True), confs

    def plan_batch_scored(self, items: list[tuple[str, Table, str | None]], batch_size: int = 8) -> list[tuple[Program | None, str, int, float, dict | None]]:
        """plan_batch with a fifth field: the confidence summary of the generated program."""
        results = []
        for i in range(0, len(items), batch_size):
            chunk = items[i:i + batch_size]
            pairs = [self.inputs_for(q, t, c) for q, t, c in chunk]
            t0 = time.perf_counter()
            raws, confs = self.generate_scored([txt for txt, _ in pairs])
            ms = (time.perf_counter() - t0) * 1000 / len(chunk)
            for (_q, t, _c), raw, (_txt, n), conf in zip(chunk, raws, pairs, confs, strict=True):
                try:
                    prog = parse(raw, t.id)
                except ProgramParseError:
                    prog = None
                results.append((prog, raw, n, ms, conf))
        return results

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
