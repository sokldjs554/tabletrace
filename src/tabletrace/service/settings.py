from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TABLETRACE_", env_file=".env", extra="ignore")

    planner: str = "auto"                     # auto | neural | heuristic
    model_dir: str = "models/mt5-small-tabletrace"
    quantize: bool = False
    quantize_scope: str = ""                  # "" = all Linear when `quantize` is true; or lm_head | no_lm_head | ffn | attn (model/quant.py)
    engine_url: str = ""                      # OpenAI-compatible server (vLLM / SGLang); when set it replaces the in-process model
    engine_model: str = "planner"             # the --served-model-name of that server
    engine_tools: bool = False                # the engine model picks tools step by step (agent/toolcall.py) instead of writing one program
    engine_api_key: str = "EMPTY"
    entity_check: bool = True                 # verifier: the question's subject must occur in the cited rows (TABLETRACE_ENTITY_CHECK=0 turns it off)
    evidence_repair: bool = True              # verifier: re-point a lookup to the cell that holds the answer (TABLETRACE_EVIDENCE_REPAIR=0 withholds instead)
    threads: int = 0
    max_concurrent_jobs: int = 2
    job_timeout_s: float = 60.0
    queue_limit: int = 16
    max_question_chars: int = 300
    console_dir: str = "console"
    release: str = "dev"
    memory_path: str = ""                     # SQLite file for per-user long-term memory (chat/memory.py); empty = kept in process memory only
    grpc_port: int = 0                        # > 0: also serve the gRPC API (service/grpc_server.py) on this port, sharing the runtime
