"""Smoke test of scripts/train/exaone_lora_sft.py on a tiny random Llama + a tiny BPE tokenizer (CPU, fp32).

It checks the loop, the chat-template encoding, adapter saving and the merged export, not model quality. The real run
(EXAONE on a Colab / Kaggle GPU) is in notebooks/gpu_experiments.ipynb.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("peft")
pytest.importorskip("transformers")
pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[1]
CHAT = ("{% for m in messages %}<|{{ m['role'] }}|>{{ m['content'] }}\n{% endfor %}"
        "{% if add_generation_prompt %}<|assistant|>{% endif %}")


def _tiny_model(tmp: Path) -> Path:
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers
    from transformers import LlamaConfig, LlamaForCausalLM, PreTrainedTokenizerFast

    texts = []
    for f in ("data/chem/documents.jsonl", "data/chem/synthetic_train.jsonl"):
        with open(ROOT / f, encoding="utf-8") as fh:
            texts += [next(fh) for _ in range(40)]
    tk = Tokenizer(models.BPE(unk_token="<unk>"))
    tk.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tk.train_from_iterator(texts, trainers.BpeTrainer(vocab_size=600, special_tokens=["<pad>", "<unk>", "<eos>"],
                                                      initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    tok = PreTrainedTokenizerFast(tokenizer_object=tk, pad_token="<pad>", unk_token="<unk>", eos_token="<eos>")
    tok.chat_template = CHAT
    out = tmp / "tiny"
    tok.save_pretrained(out)
    cfg = LlamaConfig(vocab_size=len(tok), hidden_size=32, intermediate_size=64, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=4,
                      max_position_embeddings=2048, pad_token_id=tok.pad_token_id, eos_token_id=tok.eos_token_id)
    LlamaForCausalLM(cfg).save_pretrained(out)
    return out


def test_lora_sft_runs_and_merges(tmp_path):
    model_dir = _tiny_model(tmp_path)
    out = tmp_path / "lora"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/train/exaone_lora_sft.py"), "--model", str(model_dir), "--dtype", "fp32",
                        "--train", str(ROOT / "data/chem/synthetic_train.jsonl"), "--corpus", str(ROOT / "data/chem/documents.jsonl"),
                        "--out", str(out), "--epochs", "1", "--bs", "2", "--grad-accum", "2", "--limit", "16", "--lora-r", "4", "--merge",
                        "--max-len", "1536"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    info = json.loads((out / "train_info.json").read_text())
    assert info["steps"] >= 1 and all(x["loss"] == x["loss"] for x in info["loss_log"])      # finite losses
    assert (out / "adapter_config.json").exists() and (out / "merged" / "config.json").exists()
    assert list((out / "merged").glob("*.safetensors"))
