"""규칙 엔진(⑤~⑩)의 갈래별 판정. 샘플 2의 사실을 바꿔 가며 경로가 맞게 갈리는지 본다."""
import pytest

from agent import samples
from agent.nodes import judge, write


def run(overrides: dict, institution: str = "가상대학교병원", extra: dict | None = None) -> dict:
    facts = [dict(f) for f in samples.load("sample2_pseudo")["pending"]["facts"]]
    for f in facts:
        if f["key"] in overrides:
            f["value"] = overrides[f["key"]]
            f["status"] = "not_found" if f["value"] is None else "found"
    state = {"institution_name": institution, "target_start_date": "2026-12-01",
             "confirmed_facts": facts, "extra_inputs": extra or {}}
    for step in (judge.institution, judge.gates, judge.route, judge.docs_schedule, write.abstain, write.report):
        state = {**state, **step(state)}
    return state


def ids(state: dict, result: str | None = None) -> set[str]:
    return {r["rule_id"] for r in state["judgments"] if result is None or r["result"] == result}


IDENTIFIED = {"F03": "원자료", "F02": "예", "F16": ["등록번호"], "F17": None, "F18": None}
ANONYMOUS = {"F03": "원자료", "F17": "아니오", "F18": None}


@pytest.mark.parametrize("overrides, institution, route", [
    ({}, "가상대학교병원", "A"),                                     # 가명정보(대응표 분리) → DRB → 면제 후보
    (IDENTIFIED, "가상대학교병원", "C"),                              # 식별자 기록 → 자체 IRB 심의
    ({"F03": "원자료", "F18": "연구책임자"}, "가상대학교병원", "C"),    # 코드화 + 연구자 대응표 → 자체 IRB, 면제는 위원회 판단
    (ANONYMOUS, "가상대학교병원", "C"),                               # 익명 → DRB 없이 자체 IRB 면제 후보
    ({"F03": "익명", "F17": None, "F18": None}, "가상대학교병원", "C"),
    (IDENTIFIED, "", "B"),                                           # 소속 없음 → 공용위원회
    (IDENTIFIED, "없는병원", "미정"),                                 # 명단에 없음 → IRB 보유 여부를 묻는다
    ({"F10": "예"}, "가상대학교병원", "임상시험"),
    ({"F14": "예"}, "가상대학교병원", "범위 밖"),
])
def test_route(overrides, institution, route):
    assert run(overrides, institution)["route"]["route"] == route


def test_exemption_is_only_a_candidate():
    state = run(ANONYMOUS)
    assert "E3" in ids(state, "충족")
    assert {"R-09", "R-10", "S7"} <= ids(state, "판단불가")  # 면제·익명 여부 확정은 위원회 몫
    assert "D1" not in ids(state)                             # 익명정보는 DRB 대상이 아니다
    assert state["route"]["committees"] == ["소속 기관 IRB · 심의면제 신청 후보"]


def test_coded_with_researcher_key_goes_to_committee():
    state = run({"F03": "원자료", "F18": "연구책임자"})
    e3 = next(r for r in state["judgments"] if r["rule_id"] == "E3")
    assert e3["result"] == "판단불가" and e3["abstain_reason"] == "①"
    assert not state["decision"]["exempt"] and "D1" not in ids(state)


def test_missing_code_facts_ask_researcher_first():
    state = run({"F17": None, "F18": None})
    asks = [a["input_key"] for a in state["abstain"] if a["kind"] == "나"]
    assert "F17" in asks
    state = run({"F18": None})
    asks = [a["input_key"] for a in state["abstain"] if a["kind"] == "나"]
    assert "F18" in asks


def test_unknown_irb_asks_then_rejudges():
    state = run(IDENTIFIED, "없는병원")
    asks = [a for a in state["abstain"] if a["kind"] == "나"]
    assert asks and asks[0]["input_key"] == "irb_exists"
    state = run(IDENTIFIED, "없는병원", {"irb_exists": "없음"})
    assert state["route"]["route"] == "B" and "J6" in ids(state, "판단불가")


def test_vulnerable_subjects_block_survey_exemption():
    state = run({"F01": "설문·면담", "F03": "원자료", "F16": [], "F07": [], "F08": ["미성년자"]})
    assert "E4" in ids(state, "미충족") and not state["decision"]["exempt"]


def test_sensitive_info_makes_one_revision_default():
    state = run({"F07": ["희귀질환"]})
    assert "D4" in ids(state, "미충족") and state["schedule"]["default"] == 1


def test_report_cites_only_judged_rules():
    state = run({})
    judged = ids(state)
    assert state["report"]
    for sentence in state["report"]:
        assert all(ref in judged for ref in sentence["refs"] if not ref.startswith("F"))
