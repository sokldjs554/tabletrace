"""Language-aware tokenization for lexical retrieval.

Korean: Kiwi morphological analysis keeps content morphemes (nouns, verbs, adjectives, numbers,
foreign words) and drops particles/endings, so "러시아가 획득한 메달은" matches a cell "러시아".
English: lowercase alphanumerics with a light suffix strip; chemical formulas are kept intact.
"""
from __future__ import annotations

import re
from functools import lru_cache

_KO_KEEP = {"NNG", "NNP", "NNB", "NR", "NP", "SN", "SL", "SH", "VV", "VA", "XR", "MAG", "MM", "VV-R", "VA-R"}
_EN_RE = re.compile(r"[a-z0-9][a-z0-9\-\.\/%°]*[a-z0-9%°]|[a-z0-9]")
_EN_STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "and", "or", "is", "are", "was", "were", "for",
            "what", "which", "how", "many", "much", "does", "do", "did", "with", "by", "from", "that", "this",
            "it", "its", "as", "be", "than", "value", "table"}
_KO_STOP = {"무엇", "누구", "언제", "어디", "몇", "얼마", "것", "수", "때", "등", "및", "중", "경우", "대한", "위", "뭐", "어떤", "어느"}


@lru_cache(maxsize=1)
def _kiwi():
    from kiwipiepy import Kiwi

    return Kiwi()


def tokenize_ko(text: str) -> list[str]:
    toks = []
    for t in _kiwi().tokenize(text or ""):
        if t.tag in _KO_KEEP and t.form not in _KO_STOP and len(t.form) > 0:
            toks.append(t.form.lower())
    return toks


def tokenize_en(text: str) -> list[str]:
    toks = []
    for m in _EN_RE.finditer((text or "").lower()):
        w = m.group(0)
        if w in _EN_STOP or (len(w) < 2 and not w.isdigit()):
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        toks.append(w)
    return toks


def tokenize(text: str, lang: str) -> list[str]:
    return tokenize_ko(text) if lang == "ko" else tokenize_en(text)
