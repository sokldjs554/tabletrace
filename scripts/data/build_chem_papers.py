"""Tables from openly licensed chemistry papers (arXiv, CC BY 4.0) as a second English chemistry corpus.

The first chemistry corpus is a textbook (OpenStax). Paper tables are harder: unit rows under the header, symbols
written as mathematics, uncertainties inside cells. This script turns the tables listed in
data/chem_papers/sources.json into the project's document format.

    python scripts/data/build_chem_papers.py --html-dir <folder with <arxiv id>.html files>

The HTML files are the arXiv HTML pages (https://arxiv.org/html/<id>), not stored in the repository; fetch them at
most one every three seconds. Output: data/chem_papers/documents.jsonl (+ build_report.json). Every document carries
the paper's title, authors, arXiv id and licence. Changes made to the tables: mathematics is written as plain text
from its TeX source, a unit row is merged into the header, footnote markers are dropped.
"""
from __future__ import annotations

import argparse
import html as H
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tabletrace.tools.numbers import header_unit  # noqa: E402

OUT = ROOT / "data" / "chem_papers"
GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "kappa": "κ",
         "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ",
         "omega": "ω", "Delta": "Δ", "Gamma": "Γ", "Omega": "Ω", "Sigma": "Σ", "Phi": "Φ", "Lambda": "Λ", "Theta": "Θ"}
SYMBOLS = {"pm": "±", "times": "×", "cdot": "·", "leq": "≤", "geq": "≥", "le": "≤", "ge": "≥", "approx": "≈", "sim": "~", "rightarrow": "→", "to": "→",
           "AA": "Å", "mathring{A}": "Å", "circ": "°", "infty": "∞", "%": "%", "#": "#", "&": "&", "_": "_", "ell": "l", "langle": "<", "rangle": ">"}


def tex_to_text(tex: str) -> str:
    """Plain text for the TeX of a table cell: CO_{2} -> CO2, 10^{-9} -> 10^-9, \\pm -> ±, k_{B} -> k_B."""
    s = re.sub(r"\\(?:mathrm|mathbf|mathit|mathsf|mathcal|mathbb|text|textrm|textbf|textit|operatorname|bm|boldsymbol|rm|it|bf|displaystyle|left|right)(?![A-Za-z])", "", tex)
    s = re.sub(r"\\(?:bar|overline)\s*\{([^{}]*)\}", "\\1\u0304", s)                  # keep the bar: x̄ and x are different columns
    s = re.sub(r"\\(?:hat|tilde|vec|dot)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:frac|dfrac|tfrac)\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", s)
    s = re.sub(r"\\[,;:!> ]|\\quad|\\qquad", " ", s)
    s = re.sub(r"\\([A-Za-z]+|[%#&_])", lambda m: GREEK.get(m.group(1), SYMBOLS.get(m.group(1), m.group(1))), s)
    for _ in range(4):                                       # innermost groups first; \x01 marks a finished superscript
        s = re.sub(r"_\{([^{}]*)\}|_([A-Za-z0-9])", lambda m: (lambda x: x if x.strip().isdigit() else "_" + x.strip())(m.group(1) if m.group(1) is not None else m.group(2)), s)
        s = re.sub(r"\^\{([^{}]*)\}|\^([A-Za-z0-9+\-−°])", lambda m: "\x01" + (m.group(1) if m.group(1) is not None else m.group(2)).strip() + " ", s)
    s = s.replace("\x01", "^").replace("{", "").replace("}", "").replace("−", "-").replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip()


def clean_cell(cell_html: str) -> str:
    c = re.sub(r'<math[^>]*alttext="([^"]*)"[^>]*>.*?</math>', lambda m: " " + tex_to_text(H.unescape(m.group(1))) + " ", cell_html, flags=re.S)
    c = re.sub(r"<sup[^>]*>(.*?)</sup>", lambda m: "" if re.fullmatch(r"\s*(<[^>]+>)*[a-z*†‡§]?(</[^>]+>)*\s*", m.group(1)) else "^" + m.group(1), c, flags=re.S)   # footnote marks go, exponents stay
    c = re.sub(r"<sub[^>]*>(.*?)</sub>", r"\1", c, flags=re.S)
    c = re.sub(r"<br[^>]*>", " ", c)
    c = re.sub(r"<[^>]+>", "", c)
    c = H.unescape(c).replace("\u200b", "").replace("−", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", c).strip()


def page_tables(page: str) -> list[dict]:
    """Every tabular of the page with its caption, in document order."""
    out = []
    for fig in re.finditer(r'<figure[^>]*class="[^"]*ltx_table[^"]*"[^>]*>(.*?)</figure>', page, re.S):
        cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", fig.group(1), re.S)
        caption = clean_cell(cap.group(1)) if cap else ""
        for t in re.findall(r"<table[^>]*ltx_tabular[^>]*>(.*?)</table>", fig.group(1), re.S):
            rows = [[clean_cell(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)] for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)]
            out.append({"caption": caption, "rows": [r for r in rows if any(x for x in r)], "merged_cells": "colspan" in t or "rowspan" in t})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html-dir", required=True)
    a = ap.parse_args()
    spec = json.loads((OUT / "sources.json").read_text(encoding="utf-8"))
    docs, report = [], {"papers": 0, "tables": 0, "skipped": []}
    for paper in spec["papers"]:
        tables_html = page_tables((Path(a.html_dir) / f"{paper['arxiv_id']}.html").read_text(encoding="utf-8", errors="ignore"))
        pid = "cp_" + paper["arxiv_id"].replace(".", "_")
        tables = []
        for k, pick in enumerate(paper["tables"]):
            t = tables_html[pick["index"]]
            rows = t["rows"]
            if t["merged_cells"] or len({len(r) for r in rows}) != 1:
                report["skipped"].append({"paper": paper["arxiv_id"], "index": pick["index"], "why": "merged cells or ragged rows"})
                continue
            header, body = rows[0], rows[1:]
            if pick.get("unit_row"):                         # second row holds the units: fold it into the header
                header = [f"{h} ({u})" if u and u != "-" else h for h, u in zip(header, body[0], strict=True)]
                body = body[1:]
            header = [h or pick.get("first_header", "item") if j == 0 else h for j, h in enumerate(header)]
            if any(not h for h in header):
                report["skipped"].append({"paper": paper["arxiv_id"], "index": pick["index"], "why": "empty header cell"})
                continue
            tables.append({"id": f"{pid}_t{k}", "doc_id": pid, "title": paper["title"], "caption": t["caption"], "header": header, "rows": body,
                           "units": {str(j): u for j, h in enumerate(header) if (u := header_unit(h))} if pick.get("units", True) else {}, "lang": "en",
                           "source_url": f"https://arxiv.org/abs/{paper['arxiv_id']}"})
        if not tables:
            continue
        passages = [{"id": f"{pid}_p{i}", "doc_id": pid, "order": i, "text": t["caption"]} for i, t in enumerate(tables) if t["caption"]]
        docs.append({"id": pid, "corpus": "chem_docs", "lang": "en", "title": paper["title"], "passages": passages, "tables": tables,
                     "source": {"name": f"{', '.join(paper['authors'][:3])}{' et al.' if len(paper['authors']) > 3 else ''}, arXiv:{paper['arxiv_id']}",
                                "url": f"https://arxiv.org/abs/{paper['arxiv_id']}", "license": "CC BY 4.0",
                                "note": "tables extracted from the arXiv HTML version; mathematics rewritten as plain text, unit rows merged into headers"}})
        report["papers"] += 1
        report["tables"] += len(tables)
    with open(OUT / "documents.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    (OUT / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# Sources of the chemistry-paper tables", "",
             "Every table in `documents.jsonl` comes from the arXiv HTML version of one of the papers below. All are distributed by their",
             "authors under the Creative Commons Attribution 4.0 licence (https://creativecommons.org/licenses/by/4.0/), as stated on each",
             "abstract page on 2026-11-11.", "",
             "Changes made: tables were extracted from the HTML; mathematics is written as plain text from its TeX source; a unit row under",
             "the header is merged into the header; footnote markers are dropped; an empty first header cell is given a name. Cell values",
             "are otherwise unchanged. The questions in `custom_eval.jsonl` are not part of the papers.", "",
             "| arXiv | Title | Authors | Tables used |", "|---|---|---|---|"]
    by_id = {d["id"]: d for d in docs}
    for paper in spec["papers"]:
        d = by_id.get("cp_" + paper["arxiv_id"].replace(".", "_"))
        if d:
            lines.append(f"| [{paper['arxiv_id']}](https://arxiv.org/abs/{paper['arxiv_id']}) | {paper['title']} | {'; '.join(paper['authors'])} | "
                         f"{'; '.join(t['caption'].split(':')[0] for t in d['tables'])} |")
    (OUT / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
