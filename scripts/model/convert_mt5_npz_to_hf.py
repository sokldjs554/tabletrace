"""Convert a dumped Mesh-TensorFlow mT5 checkpoint (.npz from dump_tf_checkpoint.py)
into a Hugging Face `MT5ForConditionalGeneration` directory and verify it.

Why not `transformers`' own converter: transformers>=5 dropped TensorFlow support and
the original `convert_t5_original_tf_checkpoint_to_pytorch.py`. The name mapping below
follows the same rules that script used (kernels/scales transposed, embeddings not).

Usage:
  python convert_mt5_npz_to_hf.py <npz> <spiece.model> <out_dir> [--check]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch
from tokenizers import processors
from transformers import MT5Config, MT5ForConditionalGeneration, PreTrainedTokenizerFast


def build_config(meta: dict) -> MT5Config:
    vocab, d_model = meta["shared/embedding"]["shape"]
    n_enc = len({k.split("/")[1] for k in meta if k.startswith("encoder/block_")})
    n_dec = len({k.split("/")[1] for k in meta if k.startswith("decoder/block_")})
    d_ff = meta["encoder/block_000/layer_001/DenseReluDense/wi_0/kernel"]["shape"][1]
    inner = meta["encoder/block_000/layer_000/SelfAttention/q"]["shape"][1]
    heads, buckets = meta["encoder/block_000/layer_000/SelfAttention/relative_attention_bias"]["shape"]
    cfg = MT5Config(
        vocab_size=vocab, d_model=d_model, d_kv=inner // heads, d_ff=d_ff,
        num_layers=n_enc, num_decoder_layers=n_dec, num_heads=heads,
        relative_attention_num_buckets=buckets, dropout_rate=0.1,
        feed_forward_proj="gated-gelu", tie_word_embeddings=False,
        pad_token_id=0, eos_token_id=1, decoder_start_token_id=0,
    )
    # transformers>=5 ignores the constructor kwarg for MT5; mT5 has an untied lm_head
    # (decoder/logits/kernel exists in the checkpoint), so force it after construction.
    cfg.tie_word_embeddings = False
    return cfg

def tf_name_to_hf(name: str) -> str:
    """Map e.g. encoder/block_003/layer_001/DenseReluDense/wi_0/kernel ->
    encoder.block.3.layer.1.DenseReluDense.wi_0.weight"""
    if name == "shared/embedding":
        return "shared.weight"
    if name == "decoder/logits/kernel":
        return "lm_head.weight"
    parts = name.split("/")
    out = []
    for p in parts:
        m = re.fullmatch(r"(block|layer)_(\d+)", p)
        if m:
            out += [m.group(1), str(int(m.group(2)))]
        elif p == "rms_norm":
            out.append("layer_norm")
        elif p in ("kernel", "scale"):
            out.append("weight")
        else:
            out.append(p)
    hf = ".".join(out)
    if not hf.endswith(".weight"):
        hf += ".weight"
    # top-level encoder/decoder rms_norm is `final_layer_norm` in HF
    hf = hf.replace("encoder.layer_norm.weight", "encoder.final_layer_norm.weight")
    hf = hf.replace("decoder.layer_norm.weight", "decoder.final_layer_norm.weight")
    return hf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("npz"); ap.add_argument("spiece"); ap.add_argument("out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--check-only", action="store_true", help="skip conversion; load <out> and run the checks")
    a = ap.parse_args()
    t0 = time.time()
    if a.check_only:
        model = MT5ForConditionalGeneration.from_pretrained(a.out)
        tok = PreTrainedTokenizerFast.from_pretrained(a.out)
        check(model, tok)
        return
    meta = json.load(open(a.npz + ".meta.json"))
    cfg = build_config(meta)
    print("config:", {k: getattr(cfg, k) for k in ["vocab_size", "d_model", "d_ff", "d_kv", "num_layers", "num_decoder_layers", "num_heads", "feed_forward_proj", "tie_word_embeddings"]})
    model = MT5ForConditionalGeneration(cfg)
    assert model.lm_head.weight.data_ptr() != model.shared.weight.data_ptr(), "lm_head must be untied for mT5"
    sd = model.state_dict()
    arrays = np.load(a.npz)
    new_sd, used = {}, set()
    for tf_name in meta:
        arr = arrays[tf_name.replace("/", "__")].astype(np.float32)
        hf_name = tf_name_to_hf(tf_name)
        if tf_name.split("/")[-1] != "embedding":
            arr = arr.T if arr.ndim == 2 else arr   # mesh-tf stores [in, out]; torch Linear is [out, in]
        if hf_name not in sd:
            sys.exit(f"unmapped tensor {tf_name} -> {hf_name}")
        if tuple(arr.shape) != tuple(sd[hf_name].shape):
            sys.exit(f"shape mismatch {tf_name}: tf {arr.shape} vs hf {tuple(sd[hf_name].shape)}")
        new_sd[hf_name] = torch.from_numpy(np.ascontiguousarray(arr))
        used.add(hf_name)
    # relative_attention_bias: HF stores Embedding(num_buckets, num_heads); mesh stored [heads, buckets]
    missing = [k for k in sd if k not in used]
    # HF shares the encoder/decoder embedding with `shared`; those keys alias the same tensor.
    alias = {"encoder.embed_tokens.weight", "decoder.embed_tokens.weight"}
    real_missing = [k for k in missing if k not in alias]
    if real_missing:
        sys.exit(f"missing tensors in checkpoint: {real_missing[:10]}")
    for k in alias:
        new_sd[k] = new_sd["shared.weight"]
    res = model.load_state_dict(new_sd, strict=True)
    print("load_state_dict:", res)
    # make sure the input embeddings are one shared tensor (transformers>=5 may keep copies)
    model.encoder.embed_tokens = model.shared
    model.decoder.embed_tokens = model.shared
    assert model.encoder.embed_tokens.weight.data_ptr() == model.shared.weight.data_ptr()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True)
    # save_pretrained re-emits tie_word_embeddings=True for MT5 in transformers 5; fix the file so
    # from_pretrained does not warn (weights are untied either way, both tensors are stored).
    cfg_path = out / "config.json"
    cfg_json = json.loads(cfg_path.read_text()); cfg_json["tie_word_embeddings"] = False
    cfg_path.write_text(json.dumps(cfg_json, indent=2, ensure_ascii=False))
    tok = build_tokenizer(a.spiece)
    print("tokenizer vocab size:", len(tok), "| model vocab:", cfg.vocab_size, "| <extra_id_0> ->", tok.convert_tokens_to_ids("<extra_id_0>"))
    tok.save_pretrained(out)
    (out / "CONVERSION.md").write_text(
        "Source: gs://t5-data/pretrained_models/mt5/small/model.ckpt-1000000 (Mesh TensorFlow, bfloat16)\n"
        "Vocab:  gs://t5-data/vocabs/mc4.250000.100extra/sentencepiece.model\n"
        f"Converted with scripts/model/dump_tf_checkpoint.py + convert_mt5_npz_to_hf.py on {time.strftime('%Y-%m-%d')}.\n"
        f"Parameters: {sum(p.numel() for p in model.parameters()):,}\n"
    )
    print(f"saved to {out} in {time.time()-t0:.1f}s; params {sum(p.numel() for p in model.parameters()):,}")
    if a.check:
        check(model, tok)

def build_tokenizer(spiece_path: str) -> PreTrainedTokenizerFast:
    """transformers>=5 no longer builds T5 tokenizers from a raw .model file, so build the
    Unigram tokenizer with the `tokenizers` library directly from the SentencePiece model.
    Ids match the checkpoint: <pad>=0, </s>=1, <unk>=2, <extra_id_0>=250099 ... <extra_id_99>=250000.
    The spm pieces for sentinels are spelled "▁<extra_id_k>"; they are renamed to "<extra_id_k>"
    and registered as special tokens so the ids are reused instead of appended."""
    import sentencepiece.sentencepiece_model_pb2 as pb2
    from tokenizers import Regex, Tokenizer, decoders, normalizers, pre_tokenizers
    from tokenizers.models import Unigram
    m = pb2.ModelProto(); m.ParseFromString(open(spiece_path, "rb").read())
    vocab = []
    for piece in m.pieces:
        p = piece.piece
        if p.startswith("▁<extra_id_") and p.endswith(">"):
            p = p[1:]
        vocab.append((p, piece.score))
    unk_id = m.trainer_spec.unk_id
    base = Tokenizer(Unigram(vocab, unk_id, byte_fallback=False))
    norm = [normalizers.Replace(Regex(" {2,}"), " ")]
    if m.normalizer_spec.precompiled_charsmap:
        norm.insert(0, normalizers.Precompiled(m.normalizer_spec.precompiled_charsmap))
    base.normalizer = normalizers.Sequence(norm)
    base.pre_tokenizer = pre_tokenizers.Metaspace(replacement="▁", prepend_scheme="always")
    base.decoder = decoders.Metaspace(replacement="▁", prepend_scheme="always")
    base.post_processor = processors.TemplateProcessing(
        single="$A </s>", pair="$A </s> $B </s>", special_tokens=[("</s>", 1)]
    )
    sentinels = [f"<extra_id_{i}>" for i in range(100)]
    tok = PreTrainedTokenizerFast(
        tokenizer_object=base, unk_token="<unk>", eos_token="</s>", pad_token="<pad>",
        additional_special_tokens=sentinels, model_max_length=1024,
    )
    assert len(tok) == len(vocab), (len(tok), len(vocab))
    assert tok.convert_tokens_to_ids("<extra_id_0>") == 250099
    return tok

def check(model, tok):
    """Sanity check: span-corruption denoising is the pretraining task, so the model should fill
    sentinel spans with plausible text, and loss on a span-corrupted input should be far below
    the ~12.4 nats of a uniform guess over 250k tokens."""
    model.eval()
    sentinel = tok.convert_tokens_to_ids("<extra_id_0>")
    print("sentinel id for <extra_id_0>:", sentinel)
    cases = [
        ("서울은 대한민국의 <extra_id_0> 이다.", "<extra_id_0> 수도 <extra_id_1>"),
        ("The capital of France is <extra_id_0>.", "<extra_id_0> Paris <extra_id_1>"),
        ("Water boils at <extra_id_0> degrees Celsius at 1 atm.", "<extra_id_0> 100 <extra_id_1>"),
    ]
    for src, tgt in cases:
        enc = tok(src, return_tensors="pt")
        lab = tok(tgt, return_tensors="pt").input_ids
        with torch.no_grad():
            loss = model(**enc, labels=lab).loss.item()
            gen = model.generate(**enc, max_new_tokens=8, num_beams=1, do_sample=False)
        print(f"  src={src!r}\n    loss(target={tgt!r})={loss:.2f} nats | greedy={tok.decode(gen[0], skip_special_tokens=False)!r}")

if __name__ == "__main__":
    main()
