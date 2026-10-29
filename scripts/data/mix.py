"""Mix JSONL files with per-file sample caps: mix.py OUT file1:N file2:M ... (deterministic shuffle)."""
import random
import sys
from pathlib import Path

out, specs = sys.argv[1], sys.argv[2:]
rnd = random.Random(0)
rows = []
for spec in specs:
    path, n = spec.rsplit(":", 1)
    with open(path, encoding="utf-8") as f:
        items = [line for line in f if line.strip()]
    rnd.shuffle(items)
    rows += items[: int(n)]
    print(f"{path}: took {min(int(n), len(items))} of {len(items)}")
rnd.shuffle(rows)
Path(out).write_text("".join(rows), encoding="utf-8")
print(f"{out}: {len(rows)} records")
