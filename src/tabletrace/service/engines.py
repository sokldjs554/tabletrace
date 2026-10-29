"""Serving-engine client: talk to a vLLM or SGLang server through their OpenAI-compatible API.

Why this exists: the CPU container cannot run vLLM/SGLang (both need a GPU build), so the agent's
neural planner has two interchangeable backends:
  * `NeuralPlanner`   — in-process Transformers model (what this project actually ran), and
  * `EnginePlanner`   — HTTP client for `vllm serve` / `sglang.launch_server` (prepared, tested
                        against a mock server in tests/test_engines.py, not run on a GPU here).
Both return the same (Program | None, raw, rows, ms) tuple so graph.py does not care which is used.
mT5 is an encoder-decoder; vLLM/SGLang serve decoder-only models, so the engine path targets an
instruction-tuned causal LM (e.g. EXAONE) with the same program grammar in the prompt.
"""
from __future__ import annotations

import time

import httpx

from tabletrace.agent.program import ProgramParseError, parse
from tabletrace.model.serialize import build_input
from tabletrace.schema import Program, Table

SYSTEM_PROMPT = (
    "You answer questions about a table. Reply with exactly one line in this grammar and nothing else:\n"
    "op: <lookup|text|diff|sum|avg|ratio|pct_change|abstain> ; cells: <r{i}c{j}, ...|-> ; answer: <text|-> [; reason: <not_in_document|ambiguous_question|unit_mismatch>]\n"
    "Use cell ids exactly as shown (r = data row index from 0, c = column index from 0). "
    "If the document does not contain the answer, reply with op: abstain."
)


class EnginePlanner:
    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY", timeout_s: float = 30.0, max_tokens: int = 64) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_id = f"engine:{model}"
        self.quantized = False
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"})
        self.max_tokens = max_tokens

    def health(self) -> dict:
        r = self.client.get("/v1/models")
        r.raise_for_status()
        return r.json()

    def complete(self, prompt: str) -> str:
        body = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                "max_tokens": self.max_tokens, "temperature": 0.0}
        r = self.client.post("/v1/chat/completions", json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def plan(self, question: str, table: Table, context: str | None = None) -> tuple[Program | None, str, int, float]:
        text = build_input(question, table, context)
        t0 = time.perf_counter()
        raw = self.complete(text)
        ms = (time.perf_counter() - t0) * 1000
        try:
            prog = parse(raw, table.id)
        except ProgramParseError:
            prog = None
        return prog, raw, table.n_rows, ms
