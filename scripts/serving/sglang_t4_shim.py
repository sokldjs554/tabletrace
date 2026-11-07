"""Run SGLang 0.5.x on a Turing GPU (Tesla T4, compute capability 7.5).

Why this exists: the prebuilt `sgl_kernel` wheel carries no sm75 code, so the first fused op (RMSNorm) dies with
"no kernel image is available for execution on the device" (experiments/serving/sglang_t4_failure.md). Every op
the dense EXAONE path touches (RMSNorm, RotaryEmbedding, SiluAndMul, ...) is a `MultiPlatformOp` that also has a
pure-PyTorch `forward_native`; `MultiPlatformOp.dispatch_forward` just always picks `forward_cuda` when CUDA is
present. This shim makes it pick `forward_native` when the GPU's compute capability is below 8.0. Attention stays
on the `triton` backend (its kernels have an "older architectures" branch) and sampling on the `pytorch` backend,
neither of which calls sgl_kernel.

It is a workaround, not SGLang's supported path: the fused CUDA kernels are replaced by unfused PyTorch ops, so
the server is slower than SGLang on an Ampere GPU. It has not been run by the author of this repository (no GPU
here); it was written against the sglang 0.5.9 wheel source.

Install into the virtualenv that runs the server. A `.pth` file imports this module in every interpreter of that
venv (the scheduler subprocesses included), and the hook only activates when SGLANG_T4_SHIM=1 is set:

    <venv>/bin/python scripts/serving/sglang_t4_shim.py --install
    SGLANG_T4_SHIM=1 ATTN_BACKEND=triton SAMPLING_BACKEND=pytorch bash scripts/serving/sglang.sh

SGLANG_T4_SHIM_FORCE=1 applies the patch regardless of the device (tests).
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import os
import shutil
import sys
import sysconfig
from pathlib import Path

TARGET = "sglang.srt.layers.utils.multi_platform"
ENV = "SGLANG_T4_SHIM"
PTH_NAME = "sglang_t4_shim.pth"


def needs_native() -> bool:
    if os.environ.get(ENV + "_FORCE") == "1":
        return True
    try:
        import torch

        return bool(torch.cuda.is_available()) and torch.cuda.get_device_capability(0)[0] < 8
    except Exception:
        return False


def patch(module) -> bool:
    """Make MultiPlatformOp dispatch to forward_native. Returns True when the patch was applied."""
    cls = getattr(module, "MultiPlatformOp", None)
    if cls is None or getattr(cls, "_t4_shim", False) or not needs_native():
        return False

    def dispatch_forward(self):
        return self.forward_native

    cls._t4_shim_original_dispatch = cls.dispatch_forward
    cls.dispatch_forward = dispatch_forward
    cls._t4_shim = True
    print("[sglang_t4_shim] compute capability < 8.0: MultiPlatformOp.dispatch_forward -> forward_native", file=sys.stderr)
    return True


class _Loader(importlib.abc.Loader):
    def __init__(self, inner):
        self.inner = inner

    def create_module(self, spec):
        return self.inner.create_module(spec)

    def exec_module(self, module):
        self.inner.exec_module(module)
        patch(module)


class _Finder(importlib.abc.MetaPathFinder):
    """Wraps the loader of the one target module so it is patched right after it executes, before any layer uses it."""

    def find_spec(self, name, path, target=None):
        if name != TARGET:
            return None
        sys.meta_path.remove(self)
        try:
            spec = importlib.util.find_spec(name)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _Loader(spec.loader)
        return spec


def install_hook() -> None:
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
    if TARGET in sys.modules:
        patch(sys.modules[TARGET])


def install_into_site(site: Path | None = None) -> tuple[Path, Path]:
    """Copy this file into the interpreter's site-packages and add a .pth that imports it at startup."""
    site = site or Path(sysconfig.get_paths()["purelib"])
    site.mkdir(parents=True, exist_ok=True)
    dst = site / "sglang_t4_shim.py"
    shutil.copyfile(Path(__file__).resolve(), dst)
    pth = site / PTH_NAME
    pth.write_text("import sglang_t4_shim\n", encoding="utf-8")
    return dst, pth


def main(argv: list[str]) -> int:
    if "--install" in argv:
        site = None
        if "--site" in argv:
            site = Path(argv[argv.index("--site") + 1])
        dst, pth = install_into_site(site)
        print(f"installed {dst} and {pth}; run the server with {ENV}=1")
        return 0
    if "--check" in argv:
        try:
            import torch

            cap = torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None
        except Exception as e:  # torch missing in this interpreter
            cap = f"torch unavailable: {e}"
        print(f"device capability: {cap}; shim would apply: {needs_native()}; {ENV}={os.environ.get(ENV)}")
        return 0
    print(__doc__)
    return 2


if os.environ.get(ENV) == "1":
    install_hook()

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
