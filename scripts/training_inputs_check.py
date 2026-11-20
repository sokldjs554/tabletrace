"""Are the training examples of a stored run the same at two commits? (docs/REPORT.md §31.3)

The three trainings of section P (2026-11-20) all scored higher on the Korean test than the eight before them. Between
those runs the repository changed, among other things the units stored with four Korean tables (issue 40/41 fix,
5058e59). This builds the fine-tuning examples (prompt and target text) with the command of a stored run at an earlier
commit and at the current checkout, and compares them. It needs the EXAONE tokenizer (downloaded from the Hub) and
git; the earlier commit is checked out into a temporary worktree.

  python scripts/training_inputs_check.py      # -> experiments/eval/training_inputs_check.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEFORE = "5058e59^"                                   # the commit before the fix of issues 40 and 41
RUN = "experiments/exaone_lora_ownloop2/train_info.json"
TOKENIZER = "LGAI-EXAONE/EXAONE-4.0-1.2B"
CHILD = r"""
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root / "src"))
from transformers import AutoTokenizer
from tabletrace.model.serialize import set_table_format
from tabletrace.training.data import build_examples, load_docs, read_records
args = json.loads(sys.argv[2])
tok = AutoTokenizer.from_pretrained(sys.argv[3])
docs = load_docs(*[root / c for c in args["corpus"]]); set_table_format(args["table_format"])
exs = build_examples(read_records([root / p for p in args["train"]]), docs, tok, args["max_in"], drop_truncated_gold=True)
text = "\n\x00".join(e.input_text + "\x01" + e.target_text for e in exs)
print(json.dumps({"examples": len(exs), "sha256": hashlib.sha256(text.encode()).hexdigest()}))
"""


def build(root: Path, args: dict) -> dict:
    r = subprocess.run([sys.executable, "-I", "-c", CHILD, str(root), json.dumps(args), TOKENIZER], capture_output=True, text=True, cwd=tempfile.gettempdir())
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> None:
    args = json.loads((ROOT / RUN).read_text(encoding="utf-8"))["args"]
    before = subprocess.run(["git", "rev-parse", "--short", BEFORE], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "before"
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(wt), BEFORE], cwd=ROOT, check=True)
        try:
            old = build(wt, args)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT, check=True)
    now = build(ROOT, args)
    out = {"run": RUN, "train": args["train"], "corpus": args["corpus"], "max_in": args["max_in"], "tokenizer": TOKENIZER,
           "before": {"commit": before, **old}, "now": now, "same": old == now}
    dest = ROOT / "experiments" / "eval" / "training_inputs_check.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{before}: {old['examples']} examples {old['sha256'][:12]} | now: {now['examples']} {now['sha256'][:12]} | same: {out['same']}")
    print("wrote", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
