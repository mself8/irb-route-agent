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


def asks(state: dict) -> list[str]:
    return [a["input_key"] for a in state["abstain"] if a["kind"] == "나"]


IDENTIFIED = {"F03": "원자료", "F02": "예", "F16": ["등록번호"], "F17": None, "F18": None}
ANONYMOUS = {"F03": "원자료", "F17": "아니오", "F18": None}


@pytest.mark.parametrize("overrides, institution, route", [
    ({}, "가상대학교병원", "A"),                                     # 가명정보(대응표 분리) → DRB → 면제 후보
    (IDENTIFIED, "가상대학교병원", "C"),                              # 식별자 기록 → 자체 IRB 심의
    ({"F03": "원자료", "F18": "연구책임자"}, "가상대학교병원", "C"),    # 코드화 + 연구자 대응표 → 면제는 위원회 판단
    (ANONYMOUS, "가상대학교병원", "C"),                               # 익명 → DRB 없이 자체 IRB 면제 후보
    ({"F03": "익명", "F17": None, "F18": None}, "가상대학교병원", "C"),
    (IDENTIFIED, "없음", "B"),                                       # 소속 없음 → 공용위원회
    (IDENTIFIED, "", "C"),                                           # 기관명이 비면 수행기관(F12)으로 찾는다
    (IDENTIFIED, "없는병원", "미정"),                                 # 명단에 없음 → IRB 보유 여부를 묻는다
    ({"F10": "예"}, "가상대학교병원", "임상시험"),
    ({"F14": "예"}, "가상대학교병원", "범위 밖"),
])
def test_route(overrides, institution, route):
    assert run(overrides, institution)["route"]["route"] == route


def test_exemption_is_only_a_candidate():
    state = run(ANONYMOUS)
    assert "E3" in ids(state, "충족")
    assert {"R-09", "R-10", "S7"} <= ids(state, "판단불가")  # 면제·익명 여부 확정은 위원회·데이터 보유기관 몫
    assert "D1" not in ids(state)                             # 익명정보는 DRB 대상이 아니다
    assert state["route"]["committees"] == ["소속 기관 IRB · 심의면제 신청 후보"]


def test_coded_with_researcher_key_goes_to_committee():
    state = run({"F03": "원자료", "F18": "연구책임자"})
    e3 = next(r for r in state["judgments"] if r["rule_id"] == "E3")
    assert e3["result"] == "판단불가" and e3["abstain_reason"] == "①"
    assert state["decision"]["exempt"] == "unknown" and "D1" not in ids(state)
    assert state["route"]["committees"] == ["소속 기관 IRB · 심의 또는 심의면제 (확인 필요)"]


def test_missing_or_conflicting_code_facts_ask_researcher_first():
    assert "F17" in asks(run({"F17": None, "F18": None}))
    assert "F18" in asks(run({"F18": None}))
    assert "F16" in asks(run({"F16": "모름"}))                  # "모름"은 식별자가 아니라 모르는 값
    conflict = run({"F17": "아니오", "F18": "연구책임자"})       # 코드가 없는데 대응표가 있다는 모순
    assert conflict["decision"]["exempt"] != "yes" and "F17" in asks(conflict)


def test_values_typed_on_screen_are_normalized():
    assert run({"F16": ["없음"]})["route"]["route"] == "A"      # 목록 칸에 "없음"을 쳐도 식별자가 아니다
    assert run({"F12": "가상대학교병원"}, "")["route"]["route"] == "A"  # 문자열 수행기관
    assert "R-05" in ids(run({"F05": "기관 내부 폐쇄망"}), "판단불가")    # 선택지 밖 값은 다시 묻는다


def test_pseudonymous_route_needs_no_consent_waiver():
    state = run({})
    assert "C3" not in ids(state)  # 가명정보 특례로 쓰면 동의면제 판단 불필요 (가이드라인 부록3)
    assert not any("동의 면제" in d["doc"] for d in state["documents"])
    assert "C3" in ids(run(IDENTIFIED), "판단불가")


def test_biospecimen_research_uses_its_own_exemption_rule():
    state = run({"F09": "예"})
    assert "S6" in ids(state, "충족") and "E5" in ids(state, "판단불가") and "E3" not in ids(state)
    assert state["decision"]["exempt"] == "unknown"


def test_survey_exemption_is_left_to_committee():
    state = run({"F01": "설문·면담", "F03": "원자료", "F17": "아니오", "F08": "아니요"})
    assert "E2" in ids(state, "판단불가") and "S7" not in ids(state)  # 대면 설문은 익명이어도 인간대상연구
    state = run({"F01": "설문·면담", "F03": "원자료", "F16": [], "F07": [], "F08": ["미성년자"]})
    assert "E4" in ids(state, "미충족") and state["decision"]["exempt"] == "no"


def test_unknown_affiliation_asks_institution():
    state = run({**IDENTIFIED, "F12": None}, "")
    assert state["route"]["route"] == "미정" and "institution_name" in asks(state)
    state = run({**IDENTIFIED, "F12": None}, "", {"institution_name": "없음"})
    assert state["route"]["route"] == "B"


def test_unknown_irb_asks_then_rejudges():
    state = run(IDENTIFIED, "없는병원")
    assert asks(state)[0] == "irb_exists" and state["schedule"]["scenarios"][0].get("submit_by") is None
    state = run(IDENTIFIED, "없는병원", {"irb_exists": "없음"})
    assert state["route"]["route"] == "B" and "J6" in ids(state, "판단불가")


def test_public_irb_backward_schedule_matches_prep_answer():
    # prep 케이스 1(개인연구자 → 공용위원회, 목표 12-01) 정답: 보완 0회 11-12 · 1회 10-29 · 2회 10-13
    state = run(IDENTIFIED, "없음")
    dates = [s.get("submit_by") for s in state["schedule"]["scenarios"]]
    assert dates == ["2026-11-12", "2026-10-29", "2026-10-13"]


def test_sensitive_info_makes_one_revision_default():
    state = run({"F07": ["희귀질환"]})
    assert "D4" in ids(state, "미충족") and state["schedule"]["default"] == 1


def test_report_cites_only_judged_rules():
    state = run({})
    judged = ids(state)
    assert state["report"]
    for sentence in state["report"]:
        assert all(ref in judged for ref in sentence["refs"] if not ref.startswith("F"))
