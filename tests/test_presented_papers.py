"""2026-11-16, the owner's decision: the documents the owner presents and answers for name only the papers the owner
has read. The AI tool's literature notes stay in the repository as a labelled record (they are why no document claims a
new method), but their paper names must not drift back into the README, the one-page summary or the handoff."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI_READ = ("TrustTable", "RSAT", "Reasoning-Table", "ViTaB", "CReSt", "Table-R1", "TableGPT", "TabLaP", "Tabular-TX", "SearchFireSafety", "TableVQA")
OWNER_READ = ("리즈닝 피드백 기반 학습", "루브릭 전략 비교")


def test_presented_documents_name_only_the_papers_the_owner_read():
    for rel in ("README.md", "docs/ONE_PAGE.md", "docs/HANDOFF.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert [name for name in AI_READ if name in text] == [], rel
    one_page = (ROOT / "docs/ONE_PAGE.md").read_text(encoding="utf-8")
    assert "## 읽은 논문" in one_page and all(title in one_page for title in ("리즈닝 피드백 기반 학습", "루브릭 전략 비교"))
    handoff = (ROOT / "docs/HANDOFF.md").read_text(encoding="utf-8")
    assert "**논문은 직접 읽은 것만 이름을 댄다**" in handoff and all(title in handoff for title in OWNER_READ)


def test_the_ai_literature_notes_are_kept_and_labelled():
    notes = (ROOT / "docs/research/papers.md").read_text(encoding="utf-8")
    assert notes.splitlines()[2].startswith("> **이 파일은 대부분 AI 도구가 원문을 읽고 적은 조사 기록이다.**")
    report = (ROOT / "docs/REPORT.md").read_text(encoding="utf-8")
    for heading in ("### 19.4 ", "### 20.11 "):
        sec = report[report.index(heading):][:600]
        assert "AI 도구가" in sec and "2026-11-16 결정" in sec, heading
    for rel in ("README.md", "docs/ONE_PAGE.md"):              # no novelty claim, with or without names
        assert "새로운 방법이라고 주장하지 않" in (ROOT / rel).read_text(encoding="utf-8"), rel
