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


def confidence_from(token_logprobs: list[float]) -> dict | None:
    """Summaries of one generated sequence. `mean_logprob` does not depend on length; `min_logprob` is the least certain token."""
    if not token_logprobs:
        return None
    total = float(sum(token_logprobs))
    return {"tokens": len(token_logprobs), "sum_logprob": round(total, 5), "mean_logprob": round(total / len(token_logprobs), 5),
            "min_logprob": round(float(min(token_logprobs)), 5)}


class EnginePlanner:
    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY", timeout_s: float = 30.0, max_tokens: int = 64,
                 shots: list[tuple[str, str]] | None = None) -> None:
        """`shots`: (input, program) pairs shown as earlier turns of the chat. A model that was not tuned on the program
        grammar (a larger EXAONE used as a reference) needs them; the tuned planner is always called without."""
        self.shots = shots or []
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
        return self.complete_scored(prompt, logprobs=False)[0]

    def complete_scored(self, prompt: str, logprobs: bool = True) -> tuple[str, dict | None]:
        """-> (text, confidence). The confidence is built from the log-probabilities of the generated tokens, which
        OpenAI-compatible servers (vLLM, SGLang) return with `logprobs: true`; None when the server sends none."""
        demos = [m for x, y in self.shots for m in ({"role": "user", "content": x}, {"role": "assistant", "content": y})]
        body = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *demos, {"role": "user", "content": prompt}],
                "max_tokens": self.max_tokens, "temperature": 0.0}
        if logprobs:
            body["logprobs"] = True
        r = self.client.post("/v1/chat/completions", json=body)
        r.raise_for_status()
        choice = r.json()["choices"][0]
        content = (choice.get("logprobs") or {}).get("content") or []
        return choice["message"]["content"], confidence_from([t["logprob"] for t in content if t.get("logprob") is not None])

    def plan(self, question: str, table: Table, context: str | None = None) -> tuple[Program | None, str, int, float]:
        return self.plan_scored(question, table, context, logprobs=False)[:4]

    def plan_scored(self, question: str, table: Table, context: str | None = None, logprobs: bool = True) -> tuple[Program | None, str, int, float, dict | None]:
        text = build_input(question, table, context)
        t0 = time.perf_counter()
        raw, conf = self.complete_scored(text, logprobs=logprobs)
        ms = (time.perf_counter() - t0) * 1000
        try:
            prog = parse(raw, table.id)
        except ProgramParseError:
            prog = None
        return prog, raw, table.n_rows, ms, conf
