"""⑨ 사무국 질문 다듬기(agent/phrasing.py) 단위 테스트. 모델 서버 없이 _call을 가짜 응답으로 바꿔 돈다."""
import pytest

from agent import phrasing

PLAN = "연구 방법: 데이터팀이 가명처리한 데이터셋을 제공받아 분석한다.\n동의: 후향적 기록 연구로 동의면제를 요청한다."
ITEM = {"rule_id": "C3", "kind": "가", "reason": "① 위원회 판단 · 서면동의 면제를 받으려 하는가",
        "question": "생명윤리법 제16조 ③ 관련 문의입니다. …", "cites": ["C3", "F11"],
        "basis": {"law": "생명윤리법", "article": "제16조 ③", "text": "기관위원회의 승인을 받아 연구대상자의 서면동의를 면제할 수 있다."}}
GOOD = ('생명윤리법 제16조 ③ 관련 문의입니다. 본 연구는 "후향적 기록 연구로 동의면제를 요청한다."로 계획되어 있습니다. '
        "서면동의 면제에 대해 위원회의 확인을 요청드립니다.")


@pytest.fixture
def answer(monkeypatch):
    def install(*texts):
        monkeypatch.setattr(phrasing, "_call", lambda payload, n: {"questions": [{"id": i, "text": t} for i, t in enumerate(texts)]})
    return install


def test_good_text_passes(answer):
    answer(GOOD)
    assert phrasing.polish([ITEM], PLAN, []) == [GOOD]


@pytest.mark.parametrize("bad", [
    GOOD.replace("동의면제를 요청한다", "동의를 면제받는다"),           # 계획서에 없는 인용
    GOOD.replace("생명윤리법 제16조 ③", "생명윤리법 제16조 제3항"),      # 조문을 basis와 다르게 씀
    GOOD.replace("요청드립니다.", "요청드립니다. 결과는 7일 안에 나옵니다."),  # 새 숫자
    GOOD.replace("확인을 요청드립니다", "면제 대상입니다"),              # 판정하는 말
    GOOD.replace("계획되어 있습니다", "계획되어 있음"),                  # 존댓말이 아님
    "생명윤리법 제16조 ③ 관련 문의입니다.",                            # 1문장
])
def test_rule_breaking_text_is_none(answer, bad):
    answer(bad)
    assert phrasing.polish([ITEM], PLAN, []) == [None]


def test_keeps_order_and_length(answer):
    answer(GOOD, "잘못된 문장")
    assert phrasing.polish([ITEM, ITEM], PLAN, []) == [GOOD, None]


def test_server_error_falls_back_to_template(monkeypatch):
    def boom(payload, n):
        raise ConnectionError("no server")
    monkeypatch.setattr(phrasing, "_call", boom)
    assert phrasing.polish([ITEM, ITEM], PLAN, []) == [None, None]


def test_no_items_no_call():
    assert phrasing.polish([], PLAN, []) == []
