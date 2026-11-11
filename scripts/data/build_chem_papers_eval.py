"""Hand-written questions on the chemistry-paper tables (data/chem_papers/documents.jsonl).

The questions below were written by reading each table (by the AI coding tool, not by a chemist, and not reviewed by a
second person). Only the question, the operation and the gold cells are written by hand. The answer is filled in here
from the table (lookup) or from the project's calculator (diff, sum, avg, ratio, pct_change), so a typo in a cell
reference shows up as a wrong-looking answer instead of passing silently, and `check` fails when a referenced cell
does not exist. Abstention questions ask for something the table does not have: a row that is absent, or a cell the
paper left empty ("-").

    python scripts/data/build_chem_papers_eval.py        # -> data/chem_papers/custom_eval.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tabletrace.schema import CellRef, Table  # noqa: E402
from tabletrace.tools.calculator import compute  # noqa: E402

OUT = ROOT / "data" / "chem_papers"
L, A = "lookup", "abstain"
# (table id suffix, op, gold cells as (row, col), question)
QUESTIONS = [
    ("2609_05086_t0", L, [(10, 2)], "In the laminar-jet-absorption (LJA) measurements, what diffusion coefficient of CO2 in 1-butanol was obtained at 303.32 K and 12.02 bar?"),
    ("2609_05086_t0", L, [(16, 1)], "At what pressure was the LJA measurement at 322.95 K that gave a diffusion coefficient of 2.93 ± 0.18 taken?"),
    ("2609_05086_t0", A, [], "What diffusion coefficient of CO2 in 1-butanol did the LJA experiments give at 343 K?"),
    ("2609_05086_t0", "diff", [(18, 0), (0, 0)], "How many kelvin lie between the LJA measurement at 332.67 K and the one at 283.63 K?"),
    ("2609_05086_t1", L, [(2, 1)], "What is the PFG-NMR diffusion coefficient of CO2 infinitely diluted in 1-butanol at 313.15 K?"),
    ("2609_05086_t2", L, [(1, 2)], "What is the value of parameter B in the correlation fitted to the LJA data?"),
    ("2609_05086_t2", "diff", [(1, 1), (0, 1)], "By how much does correlation parameter A from the LJA data exceed the one from PFG-NMR?"),
    ("2609_05086_t2", "ratio", [(1, 2), (0, 2)], "What is the ratio of parameter B for LJA to parameter B for PFG-NMR?"),
    ("2609_05086_t3", L, [(1, 1)], "What segment number m is used for 1-butanol?"),
    ("2609_05086_t3", "diff", [(1, 2), (0, 2)], "How much larger is the segment diameter σ of 1-BuOH than that of CO2?"),
    ("2609_05086_t3", A, [], "What dipole moment D is listed for CO2 in the pure component parameters?"),
    ("2609_02762_t0", L, [(2, 1)], "What is the solute-solvent well depth ε_ow for solute SA3?"),
    ("2609_02762_t0", L, [(8, 5)], "Which value of h_oo is reported for solute SN5?"),
    ("2609_02762_t0", "diff", [(0, 4), (1, 4)], "How much larger is k_o for SA1 than for SA2?"),
    ("2609_02762_t0", A, [], "What is ε_ow for solute SA6?"),
    ("2609_02762_t1", L, [(1, 1)], "What Henry's law constant K_o does DST predict for SA2?"),
    ("2609_02762_t1", "ratio", [(0, 1), (2, 1)], "How many times larger is the predicted Henry's law constant of SA1 than that of SA3?"),
    ("2609_05671_t0", L, [(6, 2)], "What is the donor number (DN) of dimethyl sulfoxide?"),
    ("2609_05671_t0", L, [(3, 1)], "What is the PubChem CID of tetrahydrofuran?"),
    ("2609_05671_t0", "diff", [(7, 4), (5, 4)], "How much larger is the molar mass of N,N-diethylacetamide than that of dimethylacetamide?"),
    ("2609_05671_t0", "avg", [(2, 3), (3, 3)], "What is the average acceptor number (AN) of 1,2-dimethoxyethane and tetrahydrofuran?"),
    ("2609_05671_t0", A, [], "What is the donor number of acetonitrile?"),
    ("2609_05671_t1", L, [(4, 3)], "What density does the MD simulation give for N-methyl-2-pyrrolidone?"),
    ("2609_05671_t1", L, [(6, 1)], "Which charge scaling was used for dimethyl sulfoxide in the MD benchmark?"),
    ("2609_05671_t1", "diff", [(0, 2), (0, 3)], "By how much does the experimental density of dichloromethane exceed its MD density?"),
    ("2609_06162_t0", L, [(14, 4)], "What is the MAD of the LHnz functional on the SIE4x4 benchmark?"),
    ("2609_06162_t0", L, [(44, 2)], "What MAD does B86bPBE0 give for WATER27?"),
    ("2609_06162_t0", L, [(43, 3)], "What is the MAD of LHz for the S66 benchmark?"),
    ("2609_06162_t0", "diff", [(54, 1), (54, 4)], "How much lower is the WTMAD-2 of LHnz than that of 10-DFA?"),
    ("2609_06162_t0", "pct_change", [(24, 2), (24, 1)], "What is the percentage change in the MB16-43 MAD when going from 10-DFA to B86bPBE0?"),
    ("2609_06162_t0", A, [], "What is the MAD of LHz on the MB08-165 benchmark?"),
    ("2609_07106_t0", L, [(4, 2)], "What is the lattice parameter a of CuRh2Se4 at 100 K?"),
    ("2609_07106_t0", L, [(3, 1)], "What space group is reported for CuRh2S4?"),
    ("2609_07106_t0", L, [(14, 2)], "What is the goodness of fit (GOF) of the CuRh2Se4 refinement?"),
    ("2609_07106_t0", "diff", [(10, 2), (10, 1)], "How many more unique observed reflections were collected for CuRh2Se4 than for CuRh2S4?"),
    ("2609_07106_t0", A, [], "What is the lattice parameter a of CuIr2Se4 at 100 K?"),
    ("2609_09293_t0", L, [(2, 3)], "What is the free energy in kcal/mol of the second transition state (TS2) of PETase acylation?"),
    ("2609_09293_t0", L, [(4, 6)], "What is the 95% confidence interval in kJ/mol for intermediate basin 2 (I2)?"),
    ("2609_09293_t0", "diff", [(2, 3), (0, 3)], "How much higher in free energy (kcal/mol) is TS2 than TS1?"),
    ("2609_09293_t0", A, [], "What is the free energy of a fifth transition state (TS5) of PETase?"),
    ("2609_13018_t0", L, [(0, 4)], "What is the MAE of plain CCSD(T) over all A24 systems?"),
    ("2609_13018_t0", L, [(5, 3)], "What is the xTC-DCSD MAE for the hydrogen-bonded systems?"),
    ("2609_13018_t0", "diff", [(9, 2), (11, 2)], "For the dispersion-bound systems, how much lower is the xTC CCSD MAE than the plain CCSD MAE?"),
    ("2609_16558_t0", L, [(5, 2)], "What is the SQD energy of the T4 structure with 10 active orbitals?"),
    ("2609_16558_t1", L, [(2, 4)], "What peak memory was needed for the 30-orbital active space?"),
    ("2609_16558_t1", "ratio", [(2, 1), (1, 1)], "How many times longer did SQD take with 30 active orbitals than with 25?"),
    ("2609_16558_t1", "sum", [(0, 3), (1, 3), (2, 3)], "What is the total TCC(T) wall-clock time over the 20-, 25- and 30-orbital calculations?"),
    ("2609_18654_t0", L, [(0, 2)], "What is the VPT2 zero-point energy of water?"),
    ("2609_18654_t0", "diff", [(3, 1), (3, 3)], "By how much does the harmonic ν3 eigenenergy of water exceed the bQFF value?"),
    ("2609_18654_t1", L, [(6, 5)], "What is the experimental value of mode ν6 of CHFClBr?"),
    ("2609_18654_t1", A, [], "What is the experimental zero-point energy of CHFClBr?"),
    ("2609_19045_t0", L, [(5, 5)], "What is the full CCSD energy of the three-layer LiH stack at d = 3.0 Å?"),
    ("2609_19045_t0", L, [(0, 4)], "What is the Scheme 2 error at a layer separation of 2.5 Å?"),
    ("2609_19045_t0", "diff", [(10, 2), (10, 4)], "How much smaller is the Scheme 2 error than the Scheme 1 error at d = 3.5 Å?"),
    ("2609_16851_t0", L, [(0, 3)], "What is A^zz/(2π) for hydrogens 6 and 13 of pentacene?"),
    ("2609_16851_t0", A, [], "What is A^xx/(2π) for the carbon-13 nuclei of pentacene?"),
    ("2609_20891_t0", L, [(4, 1)], "What is the mean rank of BoTorch UCB across the 14 tasks?"),
    ("2609_20891_t0", L, [(0, 2)], "How many task wins does HEBO have?"),
    ("2609_20891_t0", "diff", [(9, 1), (0, 1)], "How much lower is the mean rank of HEBO than that of Random Search?"),
    ("2609_20891_t1", L, [(1, 3)], "How many labeled observations does the OPV formulation task have?"),
    ("2609_20891_t1", L, [(10, 5)], "What is the mean R^2 for the Li-ion electrolyte conductivity task?"),
    ("2609_20891_t1", A, [], "What is the mean R^2 for a perovskite stability task?"),
]


def main() -> None:
    tables = {t["id"]: Table.model_validate(t) for line in open(OUT / "documents.jsonl", encoding="utf-8") for t in json.loads(line)["tables"]}
    rows = []
    for i, (suffix, op, cells, question) in enumerate(QUESTIONS, start=1):
        table = tables[f"cp_{suffix}"]
        rec = {"qid": f"chem_paper_{i:02d}", "category": "abstain" if op == A else ("cell" if op == L else "calc"), "question": question,
               "answer": None, "doc_id": table.doc_id, "table_id": table.id, "op": op, "gold_cells": [list(c) for c in cells],
               "source": "custom_papers", "needs_text": False}
        if op == L:
            (r, c), = cells
            rec["answer"] = table.cell(r, c)
            if not rec["answer"] or rec["answer"] == "-":
                raise SystemExit(f"{rec['qid']}: the gold cell is empty")
        elif op == A:
            rec["reason"] = "not_in_document"
        else:
            calc = compute(table, op, [CellRef(table_id=table.id, row=r, col=c) for r, c in cells])
            rec["answer"] = calc.formatted
            if calc.unit:
                rec["alt_answers"] = [calc.formatted.rsplit(" " + calc.unit, 1)[0]]
        rows.append(rec)
    with open(OUT / "custom_eval.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(len(rows), dict(Counter(r["op"] for r in rows)), "tables", len({r["table_id"] for r in rows}))
    for r in rows:
        if r["category"] == "calc":
            print(" ", r["qid"], r["op"], r["answer"], "|", r["question"][:70])


if __name__ == "__main__":
    main()
