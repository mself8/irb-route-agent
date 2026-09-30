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


@pytest.mark.parametrize("overrides, institution, route", [
    ({}, "가상대학교병원", "A"),                                           # 가명 데이터 → DRB → 면제 후보
    ({"F03": "원자료", "F02": "예", "F16": "예"}, "가상대학교병원", "C"),    # 식별정보 기록 → 자체 IRB 심의
    ({"F03": "원자료", "F16": "아니오"}, "가상대학교병원", "C"),             # 식별정보 미기록 → 자체 IRB 면제 후보
    ({"F03": "원자료", "F16": "예"}, "", "B"),                              # 소속 없음 → 공용위원회
    ({"F03": "원자료", "F16": "예"}, "없는병원", "미정"),                    # 명단에 없음 → IRB 보유 여부를 묻는다
    ({"F10": "예"}, "가상대학교병원", "임상시험"),
    ({"F14": "예"}, "가상대학교병원", "범위 밖"),
    ({"F03": "익명"}, "가상대학교병원", "비대상"),
])
def test_route(overrides, institution, route):
    assert run(overrides, institution)["route"]["route"] == route


def test_exemption_is_only_a_candidate():
    state = run({"F03": "원자료", "F16": "아니오"})
    assert "E3" in ids(state, "충족")
    assert {"R-09", "R-10"} <= ids(state, "판단불가")  # 면제 확정은 위원회 몫
    assert state["route"]["committees"] == ["소속 기관 IRB · 심의면제 신청 후보"]


def test_unknown_irb_asks_then_rejudges():
    state = run({"F03": "원자료", "F16": "예"}, "없는병원")
    asks = [a for a in state["abstain"] if a["kind"] == "나"]
    assert asks and asks[0]["input_key"] == "irb_exists"
    state = run({"F03": "원자료", "F16": "예"}, "없는병원", {"irb_exists": "없음"})
    assert state["route"]["route"] == "B" and "J6" in ids(state, "판단불가")


def test_vulnerable_subjects_block_survey_exemption():
    state = run({"F01": "설문·면담", "F03": "원자료", "F16": "아니오", "F07": [], "F08": ["미성년자"]})
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
