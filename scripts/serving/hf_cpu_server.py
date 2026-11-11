"""A minimal OpenAI-compatible chat server around a local Hugging Face causal LM, for machines without a GPU.

vLLM and SGLang need a GPU. This server exposes the same two endpoints the project uses (`GET /v1/models`,
`POST /v1/chat/completions`) so that the engine planner, the tool-calling planner and the evaluation runner can talk
to a model on CPU. It is for small measurements, not for serving: one request at a time, greedy decoding.

    python scripts/serving/hf_cpu_server.py --model models/exaone-4.0-1.2b --port 8011
    python -m tabletrace.eval.run --planner engine --engine-url http://127.0.0.1:8011 --tool-calling --concurrency 1 ...

Tool schemas are passed to the model's own chat template (`tools=`); the reply is returned as text, and the client
reads <tool_call>{...}</tool_call> blocks from it. `logprobs: true` returns the log-probability of every generated token.
"""
from __future__ import annotations

import argparse
import json
import threading
import time


def build_app(model_dir: str, served_name: str = "planner", threads: int = 0, dtype: str = "float32", max_input_tokens: int = 8192):
    import torch
    from fastapi import FastAPI, HTTPException
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if threads:
        torch.set_num_threads(threads)
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForCausalLM.from_pretrained(model_dir, torch_dtype=getattr(torch, dtype)).eval()
    stop_ids = {i for i in (tok.eos_token_id, tok.convert_tokens_to_ids("[|endofturn|]")) if isinstance(i, int) and i >= 0 and i != tok.unk_token_id}
    lock = threading.Lock()                       # one generation at a time: the CPU is the bottleneck, not the queue
    app = FastAPI(title="hf-cpu-server")
    stats = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0}

    def normalise(messages: list[dict]) -> list[dict]:
        """OpenAI sends tool-call arguments as a JSON string; chat templates expect an object."""
        out = []
        for m in messages:
            m = dict(m)
            calls = []
            for c in m.get("tool_calls") or []:
                fn = dict(c.get("function") or c)
                if isinstance(fn.get("arguments"), str):
                    try:
                        fn["arguments"] = json.loads(fn["arguments"])
                    except json.JSONDecodeError:
                        fn["arguments"] = {}
                calls.append({"type": "function", "function": fn})
            if calls:
                m["tool_calls"] = calls
            out.append(m)
        return out

    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": [{"id": served_name, "object": "model", "root": model_dir}]}

    @app.get("/stats")
    def get_stats():
        return stats

    @app.post("/v1/chat/completions")
    def chat(body: dict):
        kwargs = {"tools": body["tools"]} if body.get("tools") else {}
        try:
            ids = tok.apply_chat_template(normalise(body["messages"]), add_generation_prompt=True, return_tensors="pt", tokenize=True, **kwargs)
        except Exception as e:                    # a template that rejects the conversation is the caller's error
            raise HTTPException(400, f"chat template: {e}") from None
        ids = ids["input_ids"] if hasattr(ids, "keys") else ids
        if ids.shape[1] > max_input_tokens:
            raise HTTPException(400, f"prompt has {ids.shape[1]} tokens, limit {max_input_tokens}")
        t0 = time.perf_counter()
        with lock, torch.no_grad():
            out = model.generate(ids, max_new_tokens=int(body.get("max_tokens") or 256), do_sample=False, pad_token_id=tok.pad_token_id or tok.eos_token_id,
                                 eos_token_id=sorted(stop_ids) or None, output_scores=bool(body.get("logprobs")), return_dict_in_generate=True)
        new = out.sequences[0, ids.shape[1]:].tolist()
        while new and new[-1] in stop_ids:
            new.pop()
        text = tok.decode(new, skip_special_tokens=False).strip()
        text = text.split("</think>")[-1].strip() if "</think>" in text else text      # EXAONE 4.0 writes an (empty) reasoning block first
        choice = {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        if body.get("logprobs"):
            scores = model.compute_transition_scores(out.sequences, out.scores, normalize_logits=True)[0].tolist()
            choice["logprobs"] = {"content": [{"token": tok.decode([t]), "logprob": lp} for t, lp in zip(new, scores[: len(new)], strict=True)]}
        dt = time.perf_counter() - t0
        stats["requests"] += 1
        stats["prompt_tokens"] += int(ids.shape[1])
        stats["completion_tokens"] += len(new)
        stats["seconds"] += dt
        return {"id": f"cpu-{stats['requests']}", "object": "chat.completion", "model": served_name, "choices": [choice],
                "usage": {"prompt_tokens": int(ids.shape[1]), "completion_tokens": len(new)}, "seconds": round(dt, 2)}

    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8011)
    ap.add_argument("--served-model-name", default="planner")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--dtype", default="float32", choices=["float32", "bfloat16"])
    a = ap.parse_args()
    uvicorn.run(build_app(a.model, a.served_model_name, a.threads, a.dtype), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
