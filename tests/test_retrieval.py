from tabletrace.retrieval.bm25 import BM25
from tabletrace.retrieval.index import CorpusIndex
from tabletrace.retrieval.tokenize import tokenize_en, tokenize_ko
from tabletrace.schema import Document, Passage, Source


def test_tokenize_ko_keeps_content_morphemes():
    toks = tokenize_ko("2008년 올림픽 메달 집계에서 러시아가 획득한 메달은 몇 개입니까?")
    assert "러시아" in toks and "메달" in toks and "2008" in toks
    assert "가" not in toks and "은" not in toks


def test_tokenize_en():
    toks = tokenize_en("What is the critical pressure (kPa) of CO2 at 31.1 °C?")
    assert "critical" in toks and "co2" in toks and "kpa" in toks and "the" not in toks


def test_bm25_ranks_matching_doc_first():
    idx = BM25()
    idx.add("a", ["러시아", "메달", "집계"])
    idx.add("b", ["서울", "타워", "층수"])
    idx.add("c", ["메달", "순위"])
    hits = idx.search(["러시아", "메달"], k=3)
    assert hits[0][0] == "a" and len(hits) == 2


def test_corpus_index(medal_table, chem_table):
    d1 = Document(id="d_medal", corpus="ko_tables", lang="ko", title="2008 올림픽", tables=[medal_table],
                  passages=[Passage(id="p1", doc_id="d_medal", order=0, text="개막식은 2008년 8월 8일 베이징에서 열렸다.")],
                  source=Source(name="t", license="x"))
    idx = CorpusIndex([d1], "ko")
    assert idx.search_tables("러시아 메달", k=1)[0].id == "t_medal"
    assert idx.search_passages("개막식 날짜", k=1)[0].id == "p1"
    assert idx.search_tables("없는 내용 zzz", k=1) == []
