"""설명용 근거 검색(agent/retrieve.py) 테스트. data/laws의 실제 원문으로 돈다."""
from agent import retrieve

KEYS = {"문서명", "조항", "원문", "url", "확인일", "점수"}


def test_shape_and_k():
    hits = retrieve.search("가명정보 결합 전문기관 반출", k=3)
    assert 1 <= len(hits) <= 3 and all(set(h) == KEYS for h in hits)


def test_same_query_same_result():
    assert retrieve.search("심의면제 위험이 미미한 경우") == retrieve.search("심의면제 위험이 미미한 경우")


def test_finds_the_right_article():
    assert retrieve.search("가명정보 결합 전문기관 반출", 1)[0]["조항"].startswith("제28조의3")
    assert retrieve.search("위탁 협약 인증을 받지 못한 기관", 1)[0]["조항"].startswith("제5조")
    top = retrieve.search("가명정보 위험도 내부 활용 제3자 제공 통제 가능 환경", 1)[0]
    assert top["문서명"].startswith("가명정보 처리 가이드라인") and "기본 위험도" in top["조항"]


def test_only_current_source_text():
    chunks = retrieve._index()[0]
    assert chunks and all(c["원문"] for c in chunks)
    assert not any("개정 연혁" in c["조항"] or "확인불가" in c["조항"] for c in chunks)
