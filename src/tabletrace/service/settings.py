from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TABLETRACE_", env_file=".env", extra="ignore")

    planner: str = "auto"                     # auto | neural | heuristic
    model_dir: str = "models/mt5-small-tabletrace"
    quantize: bool = False
    quantize_scope: str = ""                  # "" = all Linear when `quantize` is true; or lm_head | no_lm_head | ffn | attn (model/quant.py)
    entity_check: bool = True                 # verifier: the question's subject must occur in the cited rows (TABLETRACE_ENTITY_CHECK=0 turns it off)
    threads: int = 0
    max_concurrent_jobs: int = 2
    job_timeout_s: float = 60.0
    queue_limit: int = 16
    max_question_chars: int = 300
    console_dir: str = "console"
    release: str = "dev"
