"""Does vLLM / SGLang list the model families this project needs? Reads the published wheels (nothing is installed).

  python scripts/serving/check_engine_support.py          # writes experiments/serving/engine_support.json

Why: the serving scripts in this folder are only useful if the engines can load the model. TableTrace's model is mT5
(a T5-family encoder-decoder with relative attention bias). The check inspects each engine's own model registry.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WANT = {"t5": r"\bT5(?:ForConditionalGeneration|EncoderModel|Model)\b|\bmt5\b|models/(?:t5|mt5)\b", "bart": r"Bart|MBart|Florence", "exaone": r"Exaone"}


def wheel(pkg: str, tmp: str) -> Path:
    subprocess.run([sys.executable, "-m", "pip", "download", pkg, "--no-deps", "-d", tmp, "-q"], check=True)
    return next(Path(tmp).glob("*.whl"))


def scan(pkg: str, registry_suffixes: tuple[str, ...]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        w = wheel(pkg, tmp)
        z = zipfile.ZipFile(w)
        names = z.namelist()
        files = [n for n in names if n.endswith(".py") and "/models/" in n]
        reg = {}
        for suffix in registry_suffixes:
            for n in names:
                if n.endswith(suffix):
                    reg[n] = z.read(n).decode("utf-8", "ignore")
        out: dict = {"wheel": w.name, "requires_torch": [m.strip() for m in z.read(next(n for n in names if n.endswith("METADATA"))).decode().splitlines() if m.startswith("Requires-Dist: torch")][:1]}
        for fam, pat in WANT.items():
            hits_files = sorted({n for n in files if re.search(pat, n, re.I)})[:6]
            hits_reg = sorted({line.strip()[:110] for text in reg.values() for line in text.splitlines() if re.search(pat, line)})[:8]
            out[fam] = {"model_files": hits_files, "registry_lines": hits_reg, "listed": bool(hits_files or hits_reg)}
        return out


def main() -> None:
    res = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "vllm": scan("vllm", ("model_executor/models/registry.py",)), "sglang": scan("sglang", ("srt/models/registry.py", "srt/configs/model_config.py"))}
    dest = ROOT / "experiments" / "serving"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "engine_support.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: {f: v[f]["listed"] for f in WANT} | {"wheel": v["wheel"]} for k, v in res.items() if k in ("vllm", "sglang")}, indent=1))


if __name__ == "__main__":
    main()
