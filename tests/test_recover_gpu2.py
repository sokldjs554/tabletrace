"""The second GPU run's result files were lost; its numbers are read back from the stored notebook output
(scripts/recover_gpu2_from_notebook.py). The recovered file must be exactly what the script produces from the notebook,
and it must say what could not be recovered."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments" / "gpu2_2026-11-14"


def test_recovered_file_is_reproduced_from_the_notebook(tmp_path):
    stored = (RUN / "recovered.json").read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/recover_gpu2_from_notebook.py")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    assert (RUN / "recovered.json").read_text(encoding="utf-8") == stored


def test_recovered_file_holds_what_the_run_printed_and_lists_what_is_missing():
    d = json.loads((RUN / "recovered.json").read_text(encoding="utf-8"))
    assert d["provenance"]["evaluations"] == 60 and len(d["evals"]) == 31
    assert all("." not in k for k in d["evals"])                              # documents cite these keys as dotted paths
    grpo, start = d["evals"]["exaone_grpo_vllm_ko_test"], d["evals"]["exaone_rlstart_vllm_ko_test"]
    assert grpo["ec"]["metrics"]["n"] == start["ec"]["metrics"]["n"] == 699
    assert d["grpo"]["steps"] == 200 == len(d["grpo"]["train_log"]) and d["grpo"]["kept_step"] == 25 and len(d["grpo"]["dev_history"]) == 9
    assert d["derived"]["grpo_vs_start"]["correct_delta"] == d["derived"]["grpo_vs_start"]["correct_grpo"] - d["derived"]["grpo_vs_start"]["correct_start"]
    assert d["ddp"]["speedup"] == round(d["ddp"]["one_gpu_s"] / d["ddp"]["two_gpu_s"], 2)
    assert set(d["training"]) == {"pool7000", "ddp1", "ddp2", "rlstart", "colid_s1", "colid_s2", "full_colid", "kochem"}
    for name in ("tools_1p2b_unseen_dev500", "tools_32b_awq_unseen_dev500"):   # their re-verification failed: only the first pass exists
        assert d["evals"][name]["v1"] and d["evals"][name]["ec"] is None
    assert "ref_1p2b_ko_test" not in d["evals"] and "ref_7p8b_awq_ko_test" not in d["evals"]
    assert len(d["failed"]) == 5 and any("predictions" in f["what"] for f in d["failed"])
