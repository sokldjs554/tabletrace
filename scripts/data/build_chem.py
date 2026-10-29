"""Build the English chemistry document corpus from OpenStax *Chemistry 2e* CNXML sources.

Input : data/raw/openstax-chemistry/{collections/chemistry-2e.collection.xml, modules/*/index.cnxml}
        (OpenStax / Rice University, CC BY-NC-SA 4.0)
Output: data/chem/documents.jsonl   one Document per module that contains at least one usable table:
                                    paragraphs (section-tagged) + tables (header/rows/units)
        data/chem/split.json        document-level split: train / dev / test module ids
        data/chem/build_report.json counts and exclusions

MathML inside cells is flattened to plain text (mi/mn/mo/mtext concatenated, msub -> "H2O",
msup -> "10^-6"). Tables with multi-level headers or row/col spans are excluded (recorded).
"""
from __future__ import annotations

import json
import random
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "openstax-chemistry"
OUT = ROOT / "data" / "chem"
NS = {"c": "http://cnx.rice.edu/cnxml", "md": "http://cnx.rice.edu/mdml", "m": "http://www.w3.org/1998/Math/MathML",
      "col": "http://cnx.rice.edu/collxml"}
C = "{http://cnx.rice.edu/cnxml}"
M = "{http://www.w3.org/1998/Math/MathML}"


def math_text(el: ET.Element) -> str:
    tag = el.tag.replace(M, "")
    kids = list(el)
    if tag in ("mi", "mn", "mo", "mtext", "ms"):
        return (el.text or "").strip()
    if tag == "msub" and len(kids) == 2:
        return math_text(kids[0]) + math_text(kids[1])
    if tag == "msup" and len(kids) == 2:
        return math_text(kids[0]) + "^" + math_text(kids[1])
    if tag == "msubsup" and len(kids) == 3:
        return math_text(kids[0]) + math_text(kids[1]) + "^" + math_text(kids[2])
    if tag == "mfrac" and len(kids) == 2:
        return math_text(kids[0]) + "/" + math_text(kids[1])
    if tag == "mspace":
        return " "
    return "".join(math_text(k) for k in kids)


def flat_text(el: ET.Element) -> str:
    """Text of a CNXML element with inline markup flattened; math converted; blocks skipped."""
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for k in el:
        t = k.tag
        if t.startswith(M):
            parts.append(" " + math_text(k) + " ")
        elif t in (C + "sub", C + "sup"):
            parts.append(flat_text(k))
        elif t in (C + "newline",):
            parts.append(" ")
        elif t in (C + "table", C + "figure", C + "list", C + "note", C + "example", C + "exercise", C + "equation"):
            pass
        else:
            parts.append(flat_text(k))
        if k.tail:
            parts.append(k.tail)
    s = "".join(parts)
    s = s.replace("−", "−")
    return re.sub(r"\s+", " ", s).strip()


def parse_table(t: ET.Element, idx: int, doc_id: str, title: str, exclusions: Counter) -> dict | None:
    tgroup = t.find("c:tgroup", NS)
    if tgroup is None:
        exclusions["no_tgroup"] += 1
        return None
    thead, tbody = tgroup.find("c:thead", NS), tgroup.find("c:tbody", NS)
    if tbody is None:
        exclusions["no_tbody"] += 1
        return None
    head_rows = thead.findall("c:row", NS) if thead is not None else []
    body_rows = tbody.findall("c:row", NS)
    if not head_rows:
        # no <thead>: treat the first body row as the header (common in OpenStax appendix tables)
        if len(body_rows) < 3:
            exclusions["no_header_row"] += 1
            return None
        head_rows, body_rows = body_rows[:1], body_rows[1:]
        exclusions["header_from_first_body_row"] += 1
    # OpenStax tables often put a spanning title row above the real header row: keep it as caption
    title_rows = []
    for hr in head_rows[:-1]:
        es = hr.findall("c:entry", NS)
        if len(es) == 1 and (es[0].get("namest") or True):
            title_rows.append(flat_text(es[0]))
        else:
            exclusions["multilevel_header"] += 1
            return None
    entries = head_rows[-1].findall("c:entry", NS)
    if any(e.get("namest") or e.get("morerows") for e in entries):
        exclusions["header_span"] += 1
        return None
    header = [flat_text(e) for e in entries]
    rows = []
    for r in body_rows:
        es = r.findall("c:entry", NS)
        if any(e.get("namest") or e.get("morerows") for e in es):
            exclusions["body_span"] += 1
            return None
        rows.append([flat_text(e) for e in es])
    ncol = len(header)
    if ncol < 2 or any(len(r) != ncol for r in rows) or len(rows) < 2:
        exclusions["ragged_or_small"] += 1
        return None
    if len(rows) > 40:
        exclusions["too_many_rows"] += 1
        return None
    if sum(len(c) for r in rows for c in r) > 2500:
        exclusions["too_long"] += 1
        return None
    from tabletrace.tools.numbers import header_unit

    cap = t.find("c:caption", NS)
    tt = t.find("c:title", NS)
    caption = " ".join(x for x in [flat_text(tt) if tt is not None else "", flat_text(cap) if cap is not None else "", *title_rows] if x) or None
    tid = f"chem_{doc_id.split('_')[1]}_t{idx}"
    return {"id": tid, "doc_id": doc_id, "title": caption or title, "caption": caption, "header": header, "rows": rows,
            "units": {i: u for i, h in enumerate(header) if (u := header_unit(h))}, "lang": "en",
            "source_url": None, "note": t.get("summary")}


def parse_module(mid: str, exclusions: Counter) -> dict | None:
    path = RAW / "modules" / mid / "index.cnxml"
    root = ET.parse(path).getroot()
    title = flat_text(root.find("c:title", NS))
    content = root.find("c:content", NS)
    if content is None:
        return None
    doc_id = f"doc_{mid}"
    passages, tables = [], []
    section_stack: list[str] = []

    def walk(el: ET.Element, section: str | None) -> None:
        for k in el:
            if k.tag == C + "section":
                st = k.find("c:title", NS)
                walk(k, flat_text(st) if st is not None else section)
            elif k.tag == C + "para":
                txt = flat_text(k)
                if len(txt) >= 40:
                    passages.append({"id": f"{doc_id}_p{len(passages)}", "doc_id": doc_id, "order": len(passages),
                                     "text": txt, "section": section})
                walk(k, section)  # tables nested inside paragraphs
            elif k.tag == C + "table":
                tb = parse_table(k, len(tables), doc_id, title, exclusions)
                if tb:
                    tb["section"] = section
                    tables.append(tb)
            elif k.tag in (C + "figure", C + "glossary", C + "exercise", C + "problem", C + "solution"):
                if k.tag == C + "figure":
                    continue
                walk(k, section)
            else:
                walk(k, section)

    walk(content, None)
    # drop end-of-chapter material (exercises/glossary) which is not document text
    if not tables:
        return None
    return {"id": doc_id, "corpus": "chem_docs", "lang": "en", "title": title, "passages": passages, "tables": tables,
            "source": {"name": "OpenStax Chemistry 2e (Rice University)",
                       "url": f"https://openstax.org/books/chemistry-2e (module {mid})",
                       "license": "CC BY-NC-SA 4.0", "note": "CNXML source from github.com/openstax/osbooks-chemistry-bundle"}}


def main() -> None:
    coll = ET.parse(RAW / "collections" / "chemistry-2e.collection.xml").getroot()
    order = [m.get("document") for m in coll.iter("{http://cnx.rice.edu/collxml}module")]
    exclusions: Counter = Counter()
    docs = []
    for mid in order:
        d = parse_module(mid, exclusions)
        if d:
            docs.append(d)
    rnd = random.Random(7)
    ids = [d["id"] for d in docs]
    rnd.shuffle(ids)
    n_test, n_dev = max(8, len(ids) // 5), max(4, len(ids) // 10)
    split = {"test": sorted(ids[:n_test]), "dev": sorted(ids[n_test:n_test + n_dev]), "train": sorted(ids[n_test + n_dev:])}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "documents.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    json.dump(split, open(OUT / "split.json", "w"), indent=1)
    report = {"modules_in_book": len(order), "documents_with_tables": len(docs),
              "tables": sum(len(d["tables"]) for d in docs), "passages": sum(len(d["passages"]) for d in docs),
              "table_exclusions": dict(exclusions), "split_sizes": {k: len(v) for k, v in split.items()}}
    json.dump(report, open(OUT / "build_report.json", "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
