"""Recover the results of the owner's second GPU run from what the notebook printed.

The run (Kaggle, 2x T4, 2026-11-14, notebook 2 sections A to H) finished and packed 90 result entries, but the session
was replaced before the archive was downloaded and the files were lost (docs/dev/issues-log.md 60). The notebook kept
its cell outputs. Every evaluation prints its meta and metrics as JSON, the training scripts print their logs, so the
numbers can be read back. What cannot be read back: the per-question predictions.

  python scripts/recover_gpu2_from_notebook.py        # -> experiments/gpu2_2026-11-14/recovered.json

Input: experiments/gpu2_2026-11-14/notebook_with_outputs.ipynb (the file as downloaded from Kaggle, unchanged).
Keys of the output hold no dots (the documents cite them as dotted paths): "ref_7.8b_awq" becomes "ref_7p8b_awq".
"""
from __future__ import annotations

import ast
import contextlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments" / "gpu2_2026-11-14"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SECTIONS = {"## A.": "A", "## A2.": "A2", "## B.": "B", "## C.": "C", "## D.": "D", "## E.": "E", "## F.": "F", "## G.": "G", "## H.": "H", "## I.": "I"}
TRAIN_TAGS = {"B": ["pool7000"], "C": ["ddp1", "ddp2"], "D": ["rlstart"], "F": ["colid_s1", "colid_s2", "full_colid"], "G": ["kochem"]}


def key_of(name: str) -> str:
    return name.replace(".", "p")


def stdout_of(cell: dict) -> str:
    return ANSI.sub("", "".join("".join(o.get("text", "")) for o in cell.get("outputs", []) if o.get("output_type") == "stream"))


def parse_output(text: str) -> dict:
    """-> evaluations (meta, metrics, by_category) in print order, other JSON lines, Python-dict lines, note lines."""
    dec = json.JSONDecoder()
    lines = text.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    out = {"evals": [], "json": [], "dicts": [], "notes": []}
    k = 0
    while k < len(lines):
        ln = lines[k]
        s = ln.strip()
        if ln == "{" and k + 1 < len(lines) and lines[k + 1].startswith(' "meta"'):
            obj, end = dec.raw_decode(text, offsets[k])
            nxt = text[end:].lstrip("\n").split("\n", 1)[0]
            by_cat = None
            if nxt.startswith('{"') and nxt.count('"verified_em"') >= 1 and '"meta"' not in nxt:
                try:
                    by_cat = json.loads(nxt)
                except json.JSONDecodeError:
                    by_cat = None
            out["evals"].append({"meta": obj["meta"], "metrics": obj["metrics"], "by_category": by_cat})
            while k < len(lines) and offsets[k] < end:
                k += 1
            if by_cat is not None:
                k += 1
            continue
        if s.startswith('{"') and s.endswith("}"):
            with contextlib.suppress(json.JSONDecodeError):
                out["json"].append(json.loads(s))
        elif s.startswith("{'") and s.endswith("}"):
            with contextlib.suppress(ValueError, SyntaxError):
                out["dicts"].append(ast.literal_eval(s))
        elif s.startswith("DEV {"):
            with contextlib.suppress(ValueError, SyntaxError):
                out["dicts"].append({"dev": ast.literal_eval(s[4:])})
        elif s:
            out["notes"].append(s)
        k += 1
    return out


def two_proportion_p(k1: int, k2: int, n: int) -> float:
    """Unpaired two-sided z-test for two proportions over n questions each. The two models answered the SAME questions,
    but which ones each got right is lost, so the paired test this project normally uses cannot be done."""
    p1, p2 = k1 / n, k2 / n
    p = (k1 + k2) / (2 * n)
    se = math.sqrt(p * (1 - p) * 2 / n)
    if se == 0:
        return 1.0
    z = abs(p1 - p2) / se
    return round(math.erfc(z / math.sqrt(2)), 4)


def main() -> None:
    nb = json.loads((RUN / "notebook_with_outputs.ipynb").read_text(encoding="utf-8"))
    section = None
    parsed: dict[str, dict] = {}
    for cell in nb["cells"]:
        src = "".join(cell.get("source", ""))
        if cell["cell_type"] == "markdown":
            section = next((v for k, v in SECTIONS.items() if src.startswith(k)), section)
            continue
        if section is None:
            continue
        got = parse_output(stdout_of(cell))
        p = parsed.setdefault(section, {"evals": [], "json": [], "dicts": [], "notes": []})
        for k in p:
            p[k] += got[k]

    # ---- evaluations: a first pass (subject check off) is followed by its re-verification (subject check on)
    evals: dict[str, dict] = {}
    for sec, p in parsed.items():
        last_model = None
        seq = p["evals"]
        for j, e in enumerate(seq):
            meta = e["meta"]
            if meta.get("replay_from"):
                name = meta["replay_from"].split("/")[-1]
                evals.setdefault(key_of(name), {"name": name, "section": sec, "v1": None, "ec": None})["ec"] = e
                last_model = re.sub(r"_(ko_test|ko_custom|chem_\w+|unseen_dev\w*)$", "", name)
                continue
            nxt = seq[j + 1]["meta"].get("replay_from") if j + 1 < len(seq) else None
            if nxt and seq[j + 1]["meta"]["data"] == meta["data"]:
                name = nxt.split("/")[-1]
            else:                                   # its re-verification failed (sampled tool-calling runs): name it after the model before it
                n = (meta.get("sample") or {}).get("n")
                name = f"{last_model}_unseen_dev{n or ''}"
            evals.setdefault(key_of(name), {"name": name, "section": sec, "v1": None, "ec": None})["v1"] = e

    # ---- training runs
    training: dict[str, dict] = {}
    for sec, tags in TRAIN_TAGS.items():
        p = parsed.get(sec, {"notes": [], "dicts": []})
        infos = [re.match(r"학습 ([\d.]+) 분 \| (\d+) 예제 \| (\d+) step \| GPU 프로세스 (\d+)", n) for n in p["notes"]]
        infos = [m for m in infos if m]
        logs, cur = [], []
        for d in p["dicts"]:
            if "of" not in d:
                continue
            if cur and (d["step"] <= cur[-1]["step"] or d["of"] != cur[-1]["of"]):
                logs.append(cur)
                cur = []
            cur.append(d)
        if cur:
            logs.append(cur)
        for i, tag in enumerate(tags):
            if i >= len(infos):
                continue
            m = infos[i]
            log = next((lg for lg in logs if lg[0]["of"] == int(m.group(3))), [])
            if log in logs:
                logs.remove(log)
            training[tag] = {"minutes": float(m.group(1)), "examples": int(m.group(2)), "steps": int(m.group(3)), "gpu_processes": int(m.group(4)),
                             "final_loss": log[-1]["loss"] if log else None, "loss_log": log}

    ddp = None
    for n in parsed.get("C", {}).get("notes", []):
        m = re.match(r"1장 (\d+)초 \((\d+) step\) \| 2장 (\d+)초 \((\d+) step\) \| 속도 ([\d.]+)배", n)
        if m:
            ddp = {"one_gpu_s": int(m.group(1)), "one_gpu_steps": int(m.group(2)), "two_gpu_s": int(m.group(3)), "two_gpu_steps": int(m.group(4)), "speedup": float(m.group(5))}

    # ---- reinforcement learning (the reward and the loss are the owner's code)
    d = parsed.get("D", {"dicts": [], "notes": []})
    steps = [x for x in d["dicts"] if "step" in x and "reward_mean" in x]
    devs = [x["dev"] for x in d["dicts"] if "dev" in x]
    summary = next((re.match(r"갱신 (\d+) / (\d+) \| 고른 걸음 (\d+)", n) for n in d["notes"] if n.startswith("갱신 ")), None)
    phases = {}
    for a, b in ((0, 50), (50, 100), (100, 150), (150, 200)):
        seg = steps[a:b]
        if not seg:
            continue
        phases[f"s{a + 1}_{b}"] = {"reward_mean": round(sum(s["reward_mean"] for s in seg) / len(seg), 4),
                                   "groups_all_equal": round(sum(s["groups_all_equal"] for s in seg) / len(seg), 4),
                                   "updates": sum(bool(s["update_applied"]) for s in seg),
                                   **{k: sum(s[k] for s in seg) for k in ("correct", "repaired", "withheld", "wrong", "unparsable")}}
    grpo = {"updates_applied": int(summary.group(1)) if summary else None, "steps": int(summary.group(2)) if summary else len(steps),
            "kept_step": int(summary.group(3)) if summary else None, "minutes": steps[-1]["minutes"] if steps else None,
            "samples_per_step": sum(steps[0][k] for k in ("correct", "repaired", "withheld", "wrong", "unparsable")) if steps else None,
            "dev_history": devs, "dev_by_step": {f"s{h['step']}": h for h in devs}, "phases": phases, "train_log": steps}

    bench = {}
    for b in parsed.get("E", {}).get("json", []):
        if "throughput_req_per_s" in b:
            bench[f"c{b['concurrency']}"] = b
    q_tag = next((e["name"] for e in evals.values() if e["name"].startswith("exaone_q_fp16_")), "")
    bench = {"model": re.sub(r"^exaone_q_fp16_|_vllm_ko_\w+$", "", q_tag), "fp16": bench}

    def em(k, which="ec"):
        return evals[k][which]["metrics"]

    def delta(a, b, metric, which="ec"):
        return round(em(a, which)[metric] - em(b, which)[metric], 4)

    derived = {}
    if "exaone_grpo_vllm_ko_test" in evals and "exaone_rlstart_vllm_ko_test" in evals:
        g, s0 = "exaone_grpo_vllm_ko_test", "exaone_rlstart_vllm_ko_test"
        n = em(g)["n"]
        k_g, k_s = round(em(g)["verified_em"] * n), round(em(s0)["verified_em"] * n)
        derived["grpo_vs_start"] = {
            "verified_em_ec_delta": delta(g, s0, "verified_em"), "verified_em_v1_delta": delta(g, s0, "verified_em", "v1"),
            "raw_answer_delta": delta(g, s0, "raw_answer_em_answerable"), "cells_exact_raw_delta": delta(g, s0, "evidence_cells_exact_raw"),
            "repaired_delta": delta(g, s0, "evidence_repaired_rate"), "false_abstain_delta": delta(g, s0, "false_abstain_rate"),
            "correct_start": k_s, "correct_grpo": k_g, "correct_delta": k_g - k_s, "unpaired_p": two_proportion_p(k_s, k_g, n)}
    if "exaone_pool7000_overlap672_vllm_unseen_dev" in evals:
        o, f, f2 = "exaone_pool7000_overlap672_vllm_unseen_dev", "exaone_pool7000_first672_vllm_unseen_dev", "exaone_pool7000_first1500_vllm_unseen_dev"
        derived["large_tables"] = {"overlap_minus_first_ec": delta(o, f, "verified_em"), "overlap_minus_first_v1": delta(o, f, "verified_em", "v1"),
                                   "first1500_minus_first672_ec": delta(f2, f, "verified_em"), "first1500_minus_overlap672_ec": delta(f2, o, "verified_em"),
                                   "latency_ratio_1500_to_672": round(em(f2)["mean_ms_per_example"] / em(f)["mean_ms_per_example"], 2)}
    if "exaone_colid_s1_vllm_ko_test" in evals:
        reps = [em(f"exaone_colid_s{s}_vllm_ko_test")["evidence_repaired_rate"] for s in (1, 2)]
        exact = [em(f"exaone_colid_s{s}_vllm_ko_test")["evidence_cells_exact_raw"] for s in (1, 2)]
        derived["colid_300"] = {"repaired_mean": round(sum(reps) / 2, 4), "cells_exact_raw_mean": round(sum(exact) / 2, 4),
                                "plain_repaired": em("exaone_rlstart_vllm_ko_test")["evidence_repaired_rate"],
                                "plain_cells_exact_raw": em("exaone_rlstart_vllm_ko_test")["evidence_cells_exact_raw"]}
    if "tools_32b_awq_ko_test" in evals and "ref_32b_awq_ko_test" in evals:
        derived["size_32b"] = {"program_minus_tools_ec": delta("ref_32b_awq_ko_test", "tools_32b_awq_ko_test", "verified_em"),
                               "tools_32b_minus_1p2b_ec": delta("tools_32b_awq_ko_test", "tools_1p2b_ko_test", "verified_em")}

    # ---- against the first notebook's stored results (another session: not paired, not even the same day)
    def stored(name):
        f = ROOT / "experiments" / "eval" / name / "metrics.json"
        return json.loads(f.read_text(encoding="utf-8"))["metrics"] if f.exists() else None

    full_v1, plain300_v1 = stored("exaone_full_vllm_ko_test"), stored("exaone_vllm_ko_test")
    if full_v1:
        cross = {}
        for tag, k in (("pool7000", "exaone_pool7000_vllm_ko_test"), ("full_colid", "exaone_full_colid_vllm_ko_test"), ("kochem", "exaone_kochem_vllm_ko_test")):
            if k in evals:
                n = em(k, "v1")["n"]
                a, b = round(em(k, "v1")["verified_em"] * n), round(full_v1["verified_em"] * n)
                cross[tag] = {"verified_em_v1_delta": round(em(k, "v1")["verified_em"] - full_v1["verified_em"], 4), "correct": a, "correct_full": b,
                              "unpaired_p": two_proportion_p(b, a, n)}
        derived["vs_first_notebook_full"] = cross
    if plain300_v1 and "exaone_rlstart_vllm_ko_test" in evals:
        derived["same_setting_two_sessions"] = {          # 300 examples, plain format, seed 0: trained and scored again in this run
            "verified_em_v1_delta": round(em("exaone_rlstart_vllm_ko_test", "v1")["verified_em"] - plain300_v1["verified_em"], 4),
            "repaired_delta": round(em("exaone_rlstart_vllm_ko_test", "v1")["evidence_repaired_rate"] - plain300_v1["evidence_repaired_rate"], 4)}
    if "exaone_q_fp16_pool7000_vllm_ko_test" in evals and "exaone_pool7000_vllm_ko_test" in evals:
        n = em("exaone_pool7000_vllm_ko_test", "v1")["n"]
        derived["same_model_served_twice"] = {"questions_different_at_most": abs(round(em("exaone_q_fp16_pool7000_vllm_ko_test", "v1")["verified_em"] * n)
                                                                              - round(em("exaone_pool7000_vllm_ko_test", "v1")["verified_em"] * n))}
    if grpo["dev_history"]:
        first, last = grpo["dev_history"][0], grpo["dev_history"][-1]
        best = max(grpo["dev_history"], key=lambda h: (h["mean_reward"], -h["step"]))
        derived["grpo_dev"] = {"best_step": best["step"], "best_reward": best["mean_reward"], "first_reward": first["mean_reward"], "last_reward": last["mean_reward"],
                               "withheld_first": first["withheld"], "withheld_last": last["withheld"], "correct_first": first["correct"], "correct_last": last["correct"],
                               "unparsable_every_check": first["unparsable"] if len({h["unparsable"] for h in grpo["dev_history"]}) == 1 else None, "n": first["n"]}

    failed = [
        {"what": "ref_1.2b (untuned 1.2B, few-shot)", "why": "already evaluated in an earlier session of the same day; the cell skipped it, so nothing was printed in this output"},
        {"what": "ref_7.8b_awq on the Korean test set", "why": "the evaluation stopped on a tool error: one answer was longer than the cell-search tool accepted (fixed: tests/test_eval_robustness.py). Its 30-question set finished"},
        {"what": "re-verification (subject check) of the two sampled tool-calling runs on large tables", "why": "the replay looked up every question of the data set in the sampled predictions (KeyError; fixed in the same test file). The first pass is recovered"},
        {"what": "4-bit serving with bitsandbytes (section E)", "why": "this vLLM version has no such quantization method; the server did not start. The fp16 side is recovered"},
        {"what": "per-question predictions of every evaluation", "why": "they were only in the lost files, so paired tests and per-question analyses are not possible for this run"},
    ]
    stamps = sorted(e[w]["meta"]["finished"] for e in evals.values() for w in ("v1", "ec") if e[w])
    out = {
        "provenance": {"source": "cell outputs of the notebook as downloaded from Kaggle", "file": "experiments/gpu2_2026-11-14/notebook_with_outputs.ipynb",
                       "hardware": "Kaggle, 2x Tesla T4", "first_result": stamps[0] if stamps else None, "last_result": stamps[-1] if stamps else None,
                       "evaluations": sum(bool(e["v1"]) + bool(e["ec"]) for e in evals.values()),
                       "note": "numbers are what the scripts printed at the time; the result files themselves were lost with the session"},
        "evals": evals, "training": training, "ddp": ddp, "grpo": grpo, "bench": bench, "derived": derived, "failed": failed,
    }
    (RUN / "recovered.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("evaluations:", out["provenance"]["evaluations"], "| names:", len(evals), "| training runs:", sorted(training), "| GRPO steps:", len(steps), "| dev checks:", len(devs))
    for k, e in evals.items():
        v1 = e["v1"]["metrics"]["verified_em"] if e["v1"] else None
        ec = e["ec"]["metrics"]["verified_em"] if e["ec"] else None
        print(f"  {k:48s} n={(e['v1'] or e['ec'])['metrics']['n']:5d} v1={v1} ec={ec}")
    print(json.dumps(derived, ensure_ascii=False))


if __name__ == "__main__":
    main()
