# SGLang on a Colab T4: measured failure (2026-11-04)

Run by the project owner in Colab (notebook `notebooks/gpu_experiments.ipynb`, section 3), pasted back verbatim. Not run by the author of this repository.

| item | value | source |
|---|---|---|
| GPU | Tesla T4, 15,360 MiB, compute capability 7.5 (sm75) | `nvidia-smi` output of the run |
| driver / CUDA | 580.178.04 / 13.0 | same |
| server | `sglang==0.5.9` in a Python 3.12 virtualenv, `--attention-backend triton`, `--sampling-backend pytorch`, `--dtype half` | notebook cell, server_args in the log |
| model | EXAONE-4.0-1.2B after a 32-example LoRA smoke run, merged, fp16 | training log |

What happened, in order:

1. Install of `sglang==0.5.9` in a Python 3.12 venv: fine (3.13 failed, see `docs/experiments/gpu-runbook.md`).
2. Tokenizer load failed on `tokenizer_config.json` written by transformers 5.x (`AttributeError: 'list' object has no attribute 'keys'`). Fixed by `scripts/serving/fix_tokenizer_config.py`.
3. The server then loaded the model and failed in the first forward pass, during CUDA-graph capture, in `sgl_kernel.rmsnorm`:

```
File ".../sgl_kernel/elementwise.py", line 45, in rmsnorm
    torch.ops.sgl_kernel.rmsnorm.default(out, input, weight, eps, enable_pdl)
RuntimeError: RMSNorm failed with error code no kernel image is available for execution on the device
...
Exception: Capture cuda graph failed: RMSNorm failed with error code no kernel image is available for execution on the device
```

Reading: the prebuilt `sgl_kernel` binary contains no kernel for compute capability 7.5. `no kernel image is available` is CUDA's error for exactly that. SGLang's own startup check accepts sm75 ("SGLang only supports sm75 and above" in the 0.5.23 wheel), but its kernels are not built for it.

Not a workaround: `--disable-cuda-graph` only moves the same call into the first normal forward. In sglang 0.5.9, `MultiPlatformOp.dispatch_forward` returns `forward_cuda` whenever CUDA is present (`sglang/srt/layers/utils/multi_platform.py`), and `RMSNorm.forward_cuda` calls `sgl_kernel`; the package has no switch to the native PyTorch implementation on CUDA. Other layers (rotary embedding, activation, sampling) also use `sgl_kernel`.

Conclusion: **SGLang 0.5.9 does not run on a T4.** It needs an Ampere or newer GPU (sm80+: A100, L4, A10, H100). vLLM 0.32 lists float16 and a Triton attention backend for Turing, so the vLLM path is the one to run on Colab free / Kaggle T4. Status for SGLang in the posting table: executed and failed on this hardware; not tested on sm80+.

## Second run, 2026-11-07 (same hardware, same result)

Same kind of T4 (this time a Kaggle session with two T4s; the notebook's platform check reported Colab because Kaggle's image also has `/content`), same `sglang==0.5.9` venv, model folder reached by absolute path (the vLLM server in section 2 of the same notebook run served this folder fine). The model loaded, then CUDA-graph capture failed at the first `RMSNorm` of layer 0 (`exaone4.py` line 205, `q_norm`):

```
File ".../sgl_kernel/elementwise.py", line 45, in rmsnorm
    torch.ops.sgl_kernel.rmsnorm.default(out, input, weight, eps, enable_pdl)
RuntimeError: RMSNorm failed with error code no kernel image is available for execution on the device
Exception: Capture cuda graph failed: RMSNorm failed with error code no kernel image is available for execution on the device
```

Two runs, three days apart, identical failure point. The notebook now checks the compute capability before installing SGLang and stops with a message instead of spending the install time.

## Workaround prepared (2026-11-07), not yet run

The failing ops are all `MultiPlatformOp` subclasses whose `dispatch_forward` returns `forward_cuda` whenever CUDA is present, and each of them (RMSNorm, RotaryEmbedding, SiluAndMul) also carries a pure-PyTorch `forward_native` (checked in the sglang 0.5.9 wheel source: `sglang/srt/layers/utils/multi_platform.py`, `layernorm.py`, `rotary_embedding.py`, `activation.py`). The Triton attention kernels have an "older architectures" block-size branch (`triton_ops/extend_attention.py`), and `--sampling-backend pytorch` avoids sgl_kernel sampling. `scripts/serving/sglang_t4_shim.py` therefore patches `MultiPlatformOp.dispatch_forward` to return `forward_native` when the compute capability is below 8.0; a `.pth` file loads it in every interpreter of the venv (scheduler subprocesses included) and `SGLANG_T4_SHIM=1` switches it on. Unit-tested against a stub of the module (`tests/test_sglang_t4_shim.py`); whether the whole server then runs on a T4 is only known after the owner runs notebook section 3 again. Expected cost: unfused PyTorch ops instead of fused kernels, so slower than SGLang on sm80+.

