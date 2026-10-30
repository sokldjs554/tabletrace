"""Record the outcome of the test suite and the E2E reports as artifacts that docs/REPORT.md can cite.

  python scripts/summarize_checks.py          # runs `pytest -q` (all tests) and summarizes docs/images/e2e-*.json
Writes experiments/tests/summary.json and docs/images/e2e-summary.json.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True)
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|error|errors|deselected)", tail)}
    dest = ROOT / "experiments" / "tests"
    dest.mkdir(parents=True, exist_ok=True)
    files = sorted(p.name for p in (ROOT / "tests").glob("test_*.py"))
    (dest / "summary.json").write_text(json.dumps({"command": "pytest -q tests", "result_line": tail, "passed": counts.get("passed", 0), "failed": counts.get("failed", 0),
                                                  "skipped": counts.get("skipped", 0), "errors": counts.get("error", 0) + counts.get("errors", 0),
                                                  "test_files": len(files), "wall_s": round(time.time() - t0, 1), "exit_code": r.returncode,
                                                  "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1))
    e2e: dict = {}
    for mode in ("live", "static"):
        p = ROOT / "docs" / "images" / f"e2e-{mode}.json"
        if p.exists():
            checks = json.loads(p.read_text(encoding="utf-8"))["checks"]
            e2e[mode] = {"total": len(checks), "passed": sum(1 for c in checks if c["ok"]), "failed": [c["name"] for c in checks if not c["ok"]]}
    (ROOT / "docs" / "images" / "e2e-summary.json").write_text(json.dumps(e2e, ensure_ascii=False, indent=1))
    print(tail)
    print(json.dumps(e2e, ensure_ascii=False))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
