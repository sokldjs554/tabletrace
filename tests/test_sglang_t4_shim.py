"""The SGLang Turing shim (scripts/serving/sglang_t4_shim.py) is exercised against a stub of
sglang.srt.layers.utils.multi_platform, because the real package (and a GPU) are not available here."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "scripts" / "serving" / "sglang_t4_shim.py"

STUB = '''
class MultiPlatformOp:
    def __init__(self):
        self._forward_method = self.dispatch_forward()
    def forward(self, *a, **k):
        return self._forward_method(*a, **k)
    def forward_native(self, x):
        return ("native", x)
    def forward_cuda(self, x):
        raise RuntimeError("no kernel image is available for execution on the device")
    def dispatch_forward(self):
        return self.forward_cuda   # the real one does this whenever CUDA is present

class RMSNorm(MultiPlatformOp):
    pass
'''


def _stub_tree(tmp_path: Path) -> Path:
    pkg = tmp_path / "sglang" / "srt" / "layers" / "utils"
    pkg.mkdir(parents=True, exist_ok=True)
    for d in (tmp_path / "sglang", tmp_path / "sglang" / "srt", tmp_path / "sglang" / "srt" / "layers", pkg):
        (d / "__init__.py").write_text("")
    (pkg / "multi_platform.py").write_text(STUB)
    return tmp_path


def _run(code: str, tmp_path: Path, env: dict) -> str:
    e = dict(os.environ, PYTHONPATH=f"{_stub_tree(tmp_path)}{os.pathsep}{SHIM.parent}", **env)
    if "SGLANG_T4_SHIM_FORCE" not in env:
        e.pop("SGLANG_T4_SHIM_FORCE", None)
    return subprocess.run([sys.executable, "-c", code], env=e, capture_output=True, text=True, check=True).stdout.strip()


CODE = """
import sglang_t4_shim
from sglang.srt.layers.utils.multi_platform import RMSNorm, MultiPlatformOp
try:
    print(RMSNorm().forward(1), getattr(MultiPlatformOp, "_t4_shim", False))
except RuntimeError as e:
    print("cuda", e)
"""


def test_shim_routes_to_native_when_forced(tmp_path):
    out = _run(CODE, tmp_path, {"SGLANG_T4_SHIM": "1", "SGLANG_T4_SHIM_FORCE": "1"})
    assert out == "('native', 1) True"


def test_shim_is_inert_without_env(tmp_path):
    out = _run(CODE, tmp_path, {"SGLANG_T4_SHIM": "0"})
    assert out.startswith("cuda no kernel image")


def test_shim_does_not_patch_capable_devices(tmp_path):
    # SGLANG_T4_SHIM=1 but no CUDA device here and no FORCE: the hook is installed, the patch is not applied.
    out = _run(CODE, tmp_path, {"SGLANG_T4_SHIM": "1"})
    assert out.startswith("cuda no kernel image")


def test_install_writes_module_and_pth(tmp_path):
    site = tmp_path / "site-packages"
    subprocess.run([sys.executable, str(SHIM), "--install", "--site", str(site)], check=True, capture_output=True)
    assert (site / "sglang_t4_shim.py").read_text() == SHIM.read_text()
    assert (site / "sglang_t4_shim.pth").read_text().strip() == "import sglang_t4_shim"


def test_patch_function_is_idempotent(tmp_path):
    tree = str(_stub_tree(tmp_path))
    sys.path.insert(0, tree)
    sys.path.insert(0, str(SHIM.parent))
    try:
        os.environ["SGLANG_T4_SHIM_FORCE"] = "1"
        shim = importlib.import_module("sglang_t4_shim")
        mod = importlib.import_module("sglang.srt.layers.utils.multi_platform")
        assert shim.patch(mod) is True
        assert shim.patch(mod) is False          # second call is a no-op
        assert mod.RMSNorm().forward(2) == ("native", 2)
        assert mod.MultiPlatformOp._t4_shim_original_dispatch is not None
    finally:
        os.environ.pop("SGLANG_T4_SHIM_FORCE", None)
        for k in [k for k in sys.modules if k == "sglang" or k.startswith("sglang.") or k == "sglang_t4_shim"]:
            sys.modules.pop(k, None)
        sys.path.remove(tree)
        sys.path.remove(str(SHIM.parent))
