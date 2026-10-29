"""A small BM25 (Okapi) index. Kept dependency-free so the service image stays small."""
from __future__ import annotations

import math
from collections import Counter, defaultdict


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.doc_ids: list[str] = []
        self.doc_len: list[int] = []
        self.tf: list[Counter[str]] = []
        self.df: Counter[str] = Counter()
        self.postings: dict[str, list[int]] = defaultdict(list)
        self.avgdl = 0.0

    def add(self, doc_id: str, tokens: list[str]) -> None:
        idx = len(self.doc_ids)
        self.doc_ids.append(doc_id)
        self.doc_len.append(len(tokens))
        c = Counter(tokens)
        self.tf.append(c)
        for t in c:
            self.df[t] += 1
            self.postings[t].append(idx)
        self.avgdl = sum(self.doc_len) / len(self.doc_len)

    def __len__(self) -> int:
        return len(self.doc_ids)

    def idf(self, term: str) -> float:
        n, df = len(self.doc_ids), self.df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, tokens: list[str], k: int = 10) -> list[tuple[str, float]]:
        if not self.doc_ids or not tokens:
            return []
        scores: dict[int, float] = defaultdict(float)
        q = Counter(tokens)
        for term in q:
            if term not in self.postings:
                continue
            idf = self.idf(term)
            for idx in self.postings[term]:
                f = self.tf[idx][term]
                dl = self.doc_len[idx]
                scores[idx] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:k]
        return [(self.doc_ids[i], s) for i, s in ranked]
