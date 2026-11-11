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
    tcfg = json.loads((out / "merged" / "tokenizer_config.json").read_text())
    assert not isinstance(tcfg.get("extra_special_tokens"), list) and tcfg.get("tokenizer_class") != "TokenizersBackend"


def test_lora_sft_accepts_the_column_id_table_format(tmp_path):
    """--table-format colid trains end to end and is recorded with the run (the serving side must use the same format)."""
    model_dir = _tiny_model(tmp_path)
    out = tmp_path / "lora_colid"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/train/exaone_lora_sft.py"), "--model", str(model_dir), "--dtype", "fp32",
                        "--train", str(ROOT / "data/chem/synthetic_train.jsonl"), "--corpus", str(ROOT / "data/chem/documents.jsonl"),
                        "--out", str(out), "--epochs", "1", "--bs", "2", "--grad-accum", "2", "--limit", "8", "--lora-r", "4",
                        "--max-len", "1536", "--table-format", "colid"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    info = json.loads((out / "train_info.json").read_text())
    assert info["args"]["table_format"] == "colid" and info["steps"] >= 1
    assert all(x["loss"] == x["loss"] for x in info["loss_log"])


def test_lora_sft_on_two_processes_and_with_extra_data(tmp_path):
    """torchrun with two CPU processes: each trains on half of the data, gradients are averaged, rank 0 saves once.
    --extra-train adds a random sample from another file on top of --limit."""
    model_dir = _tiny_model(tmp_path)
    out = tmp_path / "lora_ddp"
    r = subprocess.run([sys.executable, "-m", "torch.distributed.run", "--nproc_per_node", "2", str(ROOT / "scripts/train/exaone_lora_sft.py"),
                        "--model", str(model_dir), "--dtype", "fp32", "--train", str(ROOT / "data/chem/synthetic_train.jsonl"),
                        "--corpus", str(ROOT / "data/chem/documents.jsonl"), "--out", str(out), "--epochs", "1", "--bs", "2", "--grad-accum", "2",
                        "--limit", "8", "--extra-train", str(ROOT / "data/chem/synthetic_train.jsonl"), "--extra-n", "8", "--seed", "3",
                        "--lora-r", "4", "--max-len", "1536"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    info = json.loads((out / "train_info.json").read_text())
    assert info["world_size"] == 2 and info["n_examples"] == 16 and info["steps"] == 2          # 16 examples / 2 processes / (2 x 2)
    assert all(x["loss"] == x["loss"] for x in info["loss_log"]) and (out / "adapter_config.json").exists()


def test_lora_sft_with_the_owner_written_loop(tmp_path):
    """--loop owner: masking, schedule and loop from tabletrace.training.lm_loop (skipped until the owner writes it)."""
    import importlib.util

    if importlib.util.find_spec("tabletrace.training.lm_loop") is None:
        pytest.skip("tabletrace/training/lm_loop.py is not written yet (owner training task, docs/rewrite/06_training_code.md)")
    model_dir = _tiny_model(tmp_path)
    out = tmp_path / "lora_owner"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/train/exaone_lora_sft.py"), "--model", str(model_dir), "--dtype", "fp32",
                        "--train", str(ROOT / "data/chem/synthetic_train.jsonl"), "--corpus", str(ROOT / "data/chem/documents.jsonl"),
                        "--out", str(out), "--epochs", "2", "--bs", "2", "--grad-accum", "2", "--limit", "16", "--lora-r", "4",
                        "--max-len", "1536", "--loop", "owner", "--warmup-steps", "2", "--lr", "1e-3"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    info = json.loads((out / "train_info.json").read_text())
    assert info["loop"].startswith("tabletrace.training.lm_loop") and info["steps"] == 8        # 16 examples / (2 x 2) x 2 epochs
    assert [x["step"] for x in info["loss_log"]] == list(range(1, 9))
    assert all(x["loss"] == x["loss"] for x in info["loss_log"])                                 # finite
    assert info["loss_log"][0]["lr"] == pytest.approx(0.5e-3) and info["loss_log"][-1]["lr"] < info["loss_log"][2]["lr"]
    assert (out / "adapter_config.json").exists()


def test_owner_loop_is_asked_for_by_name_when_missing(tmp_path):
    import importlib.util

    if importlib.util.find_spec("tabletrace.training.lm_loop") is not None:
        pytest.skip("lm_loop exists")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/train/exaone_lora_sft.py"), "--model", "none", "--train", "x", "--corpus", "x",
                        "--out", str(tmp_path / "o"), "--loop", "owner"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "docs/rewrite/06_training_code.md" in r.stderr


def test_tokenizer_config_is_made_portable(tmp_path):
    """transformers 5 saves extra_special_tokens as a list and names the class TokenizersBackend; SGLang's 4.57 cannot read that."""
    sys.path.insert(0, str(ROOT / "scripts" / "serving"))
    from fix_tokenizer_config import portable_tokenizer_config

    cfg = {"extra_special_tokens": ["[|system|]", "[|user|]"], "additional_special_tokens": ["[|user|]"], "tokenizer_class": "TokenizersBackend", "model_max_length": 4096}
    (tmp_path / "tokenizer_config.json").write_text(json.dumps(cfg))
    assert portable_tokenizer_config(tmp_path) is True
    out = json.loads((tmp_path / "tokenizer_config.json").read_text())
    assert "extra_special_tokens" not in out and out["additional_special_tokens"] == ["[|user|]", "[|system|]"]
    assert out["tokenizer_class"] == "PreTrainedTokenizerFast" and out["model_max_length"] == 4096
    assert portable_tokenizer_config(tmp_path) is False          # idempotent
    assert portable_tokenizer_config(tmp_path / "missing") is False


def test_model_config_rope_keys_are_restored_for_transformers_4(tmp_path):
    """transformers 5 writes RoPE settings only under rope_parameters (rope_theta/rope_scaling null). 4.57's Exaone4Config then
    falls back to rope_theta=10000 and no scaling: the model loads and talks fluently but ignores the context (owner's SGLang run)."""
    sys.path.insert(0, str(ROOT / "scripts" / "serving"))
    from fix_tokenizer_config import portable_model_config, portable_model_dir

    cfg = {"model_type": "exaone4", "rope_theta": None, "rope_scaling": None, "dtype": "float16", "torch_dtype": None,
           "rope_parameters": {"rope_theta": 1000000.0, "rope_type": "llama3", "factor": 16.0, "low_freq_factor": 1.0, "high_freq_factor": 4.0, "original_max_position_embeddings": 8192}}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    assert portable_model_config(tmp_path) is True
    out = json.loads((tmp_path / "config.json").read_text())
    assert out["rope_theta"] == 1000000.0 and out["torch_dtype"] == "float16"
    assert out["rope_scaling"] == {"rope_type": "llama3", "factor": 16.0, "low_freq_factor": 1.0, "high_freq_factor": 4.0, "original_max_position_embeddings": 8192}
    assert out["rope_parameters"] == cfg["rope_parameters"]            # 5.x keeps reading this one
    assert portable_model_config(tmp_path) is False                     # idempotent
    # default rope type: only rope_theta is restored, rope_scaling stays unset
    (tmp_path / "config.json").write_text(json.dumps({"rope_parameters": {"rope_theta": 500000.0, "rope_type": "default"}}))
    assert portable_model_config(tmp_path) is True
    out = json.loads((tmp_path / "config.json").read_text())
    assert out["rope_theta"] == 500000.0 and "rope_scaling" not in out
    assert portable_model_dir(tmp_path / "missing") is False
