"""③ 사실 추출(agent/llm.py) 단위 테스트. 모델 서버 없이 _call을 가짜 응답으로 바꿔 돈다."""
import pytest

from agent import llm
from agent.state import FACT_LABELS, Fact

TEXT = "연구 방법: 데이터팀이 가명처리한 데이터셋을 제공받아\n원내 분석실에서 분석한다."


def _resp(**facts) -> dict:
    """지정하지 않은 항목은 found=false."""
    out = {k: {"found": False, "value": None, "span": ""} for k in FACT_LABELS}
    out.update(facts)
    return out


@pytest.fixture
def fake(monkeypatch):
    """fake(first, second): 항목 순서대로 묻는 첫 호출과 뒤집어 묻는 두 번째 호출의 응답을 정한다."""
    def install(first: dict, second: dict):
        def _call(system, masked_text):
            return first if system.index("- F01") < system.index("- F02") else second
        monkeypatch.setattr(llm, "_call", _call)
    return install


def test_shape_and_order(fake):
    fake(_resp(), _resp())
    facts = llm.extract(TEXT)
    assert [f["key"] for f in facts] == list(FACT_LABELS)
    for f in facts:
        Fact(**f)  # state.Fact 모양
        assert f["status"] == "not_found" and f["value"] is None and f["span"] is None


def test_agree_found_with_offsets(fake):
    hit = {"found": True, "value": "가명처리", "span": "가명처리한 데이터셋"}
    fake(_resp(F03=hit), _resp(F03=hit))
    f = llm.extract(TEXT)[2]
    assert (f["status"], f["cross_check"], f["value"]) == ("found", "agree", "가명처리")
    assert TEXT[f["span_start"]:f["span_end"]] == f["span"] == "가명처리한 데이터셋"


def test_span_not_in_text_is_dropped(fake):
    made_up = {"found": True, "value": "가명처리", "span": "익명화한 자료를 받는다"}
    fake(_resp(F03=made_up), _resp(F03=made_up))
    f = llm.extract(TEXT)[2]
    assert (f["status"], f["value"], f["span"]) == ("not_found", None, None)


def test_span_whitespace_difference_is_recovered_verbatim(fake):
    hit = {"found": True, "value": "기관 내부", "span": "제공받아 원내 분석실에서"}  # 원문은 줄바꿈
    fake(_resp(F05=hit), _resp(F05=hit))
    f = llm.extract(TEXT)[4]
    assert f["status"] == "found"
    assert f["span"] == "제공받아\n원내 분석실에서" == TEXT[f["span_start"]:f["span_end"]]


def test_disagreeing_calls_are_conflict(fake):
    a = {"found": True, "value": "가명처리", "span": "가명처리한 데이터셋"}
    b = {"found": True, "value": "원자료", "span": "데이터셋"}
    fake(_resp(F03=a), _resp(F03=b))
    f = llm.extract(TEXT)[2]
    assert (f["status"], f["cross_check"], f["value"]) == ("conflict", "disagree", "가명처리")


def test_found_on_one_side_only_is_conflict(fake):
    hit = {"found": True, "value": "기관 데이터팀", "span": "데이터팀이"}
    fake(_resp(), _resp(F04=hit))
    f = llm.extract(TEXT)[3]
    assert (f["status"], f["cross_check"], f["value"]) == ("conflict", "disagree", "기관 데이터팀")


def test_list_order_does_not_matter(fake):
    fake(_resp(F12={"found": True, "value": ["가", "나"], "span": "데이터팀"}),
         _resp(F12={"found": True, "value": ["나", "가"], "span": "데이터팀"}))
    f = llm.extract(TEXT)[11]
    assert (f["status"], f["cross_check"]) == ("found", "agree")
