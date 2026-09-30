"""규칙 엔진(⑤~⑩)의 갈래별 판정. 샘플 2의 사실을 바꿔 가며 경로가 맞게 갈리는지 본다."""
import pytest

from agent import samples
from agent.nodes import judge, write


def run(overrides: dict, institution: str = "가상대학교병원", extra: dict | None = None, target: str = "2026-12-01",
        unwritten: tuple = ()) -> dict:
    """샘플 2의 사실을 바꿔 ⑤~⑩을 돌린다. unwritten은 연구자가 채웠지만 계획서에는 없는 사실이다."""
    sample = samples.load("sample2_pseudo")
    facts = [dict(f) for f in sample["pending"]["facts"]]
    for f in facts:
        if f["key"] in overrides:
            f["value"] = overrides[f["key"]]
            f["status"] = "not_found" if f["value"] is None else "found"
    extracted = [{**f, "status": "not_found"} if f["key"] in unwritten else f for f in facts]
    state = {"institution_name": institution, "target_start_date": target, "today": "2026-09-30",
             "masked_text": sample["pending"]["masked_text"], "facts": extracted,
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
    conflict = run({"F17": "아니오", "F18": "연구책임자"})       # 대응표가 있으면 코드도 있다고 보고 되묻지 않는다
    assert conflict["decision"]["exempt"] == "unknown" and "F17" not in asks(conflict)
    loop = run({"F17": "아니오", "F18": None})                  # 가명처리인데 코드 없음 → 대응표를 묻는다(같은 질문 반복 없음)
    assert "F18" in asks(loop) and "F17" not in asks(loop) and "D1" in ids(loop, "충족")
    viewed = run({"F03": "원자료", "F02": "예", "F17": None, "F18": None})
    assert "F17" in asks(viewed) and viewed["decision"]["exempt"] == "unknown"
    viewed_key = run({"F03": "원자료", "F02": "예", "F17": None, "F18": "연구책임자"})
    assert next(r for r in viewed_key["judgments"] if r["rule_id"] == "E3")["abstain_reason"] == "①"


def test_values_typed_on_screen_are_normalized():
    assert run({"F16": ["없음"]})["route"]["route"] == "A"      # 목록 칸에 "없음"을 쳐도 식별자가 아니다
    assert run({"F12": "가상대학교병원"}, "")["route"]["route"] == "A"  # 문자열 수행기관
    assert "R-05" in ids(run({"F05": "기관 내부 폐쇄망"}), "판단불가")    # 선택지 밖 값은 다시 묻는다


def test_consent_waiver_is_left_to_committee_on_every_route():
    # 가명정보 특례로 쓰는 경우 동의면제 판단이 필요한지는 가이드라인 안에서도 엇갈린다 (prep 케이스 5, 이슈 #9)
    assert "C3" in ids(run({}), "판단불가")
    assert "C3" in ids(run(IDENTIFIED), "판단불가")


def test_unknown_premises_do_not_produce_dates_or_drop_drb():
    no_ids = run({"F16": None})                                 # 식별자를 몰라도 가명처리면 DRB 경로는 남는다
    assert no_ids["route"]["route"] == "A" and "D1" in ids(no_ids, "충족") and "F16" in asks(no_ids)
    no_consent = run({"F11": None})                             # 동의 여부를 모르면 경로 미정, 날짜 없음
    assert no_consent["route"]["route"] == "미정" and not no_consent["route"]["fast_track"]
    assert all(s.get("submit_by") is None for s in no_consent["schedule"]["scenarios"])
    no_trial = run({**IDENTIFIED, "F10": None}, "없음")         # 임상시험 여부를 모르면 날짜를 내지 않는다
    assert all(s.get("submit_by") is None for s in no_trial["schedule"]["scenarios"])
    no_kind = run({"F01": None})
    assert "F01" in asks(no_kind) and no_kind["decision"]["exempt"] == "unknown"


def test_biospecimen_research_uses_its_own_exemption_rule():
    state = run({"F09": "예"})
    assert "S6" in ids(state, "충족") and "E5" in ids(state, "판단불가") and "E3" not in ids(state)
    assert state["decision"]["exempt"] == "unknown"
    state = run({**IDENTIFIED, "F09": "예"})                   # 개인정보를 적으면 사실로 면제 불가
    assert "E5" in ids(state, "미충족") and state["decision"]["exempt"] == "no"


def test_survey_exemption_is_left_to_committee():
    state = run({"F01": "설문·면담", "F03": "원자료", "F17": "아니오", "F08": "아니요"})
    assert "E2" in ids(state, "판단불가") and "S7" not in ids(state)  # 대면 설문은 익명이어도 인간대상연구
    state = run({"F01": "설문·면담", "F03": "원자료", "F16": [], "F07": [], "F08": ["미성년자"]})
    assert "E4" in ids(state, "미충족") and state["decision"]["exempt"] == "no"
    state = run({"F01": "설문·면담", "F03": "원자료", "F17": "아니오", "F07": ["정신질환"], "F08": []})
    assert "E2" in ids(state, "미충족") and state["decision"]["exempt"] == "no"


def test_unknown_affiliation_asks_institution():
    state = run({**IDENTIFIED, "F12": None}, "")
    assert state["route"]["route"] == "미정" and "institution_name" in asks(state)
    state = run({**IDENTIFIED, "F12": None}, "", {"institution_name": "없음"})
    assert state["route"]["route"] == "B"


def test_unknown_irb_asks_then_rejudges():
    state = run(IDENTIFIED, "없는병원")
    assert asks(state)[0] == "irb_exists" and state["schedule"]["scenarios"][0].get("submit_by") is None
    state = run(IDENTIFIED, "없는병원", {"irb_exists": "없음"})
    assert state["route"]["route"] == "B" and "J6" in ids(state, "충족") and "J3" in ids(state, "판단불가")
    assert all(s.get("submit_by") is None for s in state["schedule"]["scenarios"])  # 협약 소요 비공개


def test_public_irb_backward_schedule_matches_prep_answer():
    # prep 케이스 1(개인연구자 → 공용위원회, 목표 12-01) 정답: 보완 0회 11-12 · 1회 10-29 · 2회 10-13
    state = run(IDENTIFIED, "없음")
    dates = [s.get("submit_by") for s in state["schedule"]["scenarios"]]
    assert dates == ["2026-11-12", "2026-10-29", "2026-10-13"]
    past = run(IDENTIFIED, "없음", target="2026-10-20")         # 이미 지난 마감은 날짜 대신 "마감 경과"
    assert past["schedule"]["scenarios"][1].get("submit_by") is None
    assert "마감 경과" in past["schedule"]["scenarios"][1]["step"]
    exempt = run(ANONYMOUS, "없음")                              # 공용위원회 심의면제는 수시 접수
    assert all(s.get("submit_by") is None for s in exempt["schedule"]["scenarios"])
    assert run({})["schedule"]["scenarios"][0]["submit_by"] == "2026-11-23"  # DRB 빠른 길도 개시일 전날 기준


def test_sensitive_info_makes_one_revision_default():
    state = run({"F07": ["희귀질환"]})
    assert "D4" in ids(state, "미충족") and state["schedule"]["default"] == 1


def test_report_cites_only_judged_rules():
    state = run({})
    judged = ids(state)
    assert state["report"]
    for sentence in state["report"]:
        assert all(ref in judged for ref in sentence["refs"] if not ref.startswith("F"))


def test_fourth_review_fixes():
    discarded = run({"F03": "원자료", "F18": "없음(폐기)"})       # 원자료의 대응표 폐기 → 익명, DRB 아님 (익명·가명 배타)
    assert "S7" in ids(discarded) and "D1" not in ids(discarded) and discarded["route"]["route"] == "C"
    kept = run({"F18": "없음(폐기)", "F06": "예"})              # 가명처리 데이터의 대응표 폐기는 가명정보 안전조치 → DRB 유지
    assert "D1" in ids(kept, "충족") and "D3" in ids(kept, "충족") and "S7" not in ids(kept)
    for institution, extra in (("없는병원", {"irb_exists": "없음"}), ("없음", {})):
        state = run({}, institution, extra)                     # DRB 빠른 길 날짜는 자체 IRB일 때만
        assert state["schedule"]["scenarios"][0].get("submit_by") is None
    assert run({"F06": "예"})["schedule"]["scenarios"][0].get("submit_by") is None  # 결합은 소요 비공개
    no_consent = run({"F11": "없음"})                          # 동의 없이 가명정보를 써도 동의면제 판단은 위원회 몫
    assert "C3" in ids(no_consent, "판단불가") and not any("사유서" in d["doc"] for d in no_consent["documents"])
    assert not run({"F10": None})["route"]["fast_track"]        # 전제를 모르면 빠른 길 없음
    bio = run({**IDENTIFIED, "F09": "예"})
    assert not any("위원회가 확인" in s["text"] for s in bio["report"])
    contract = run(IDENTIFIED, "없는병원", {"irb_exists": "없음"})  # 위탁 협약 여부는 연구자에게 묻는다
    assert "contract" in asks(contract)
    contract = run(IDENTIFIED, "없는병원", {"irb_exists": "없음", "contract": "아니오"})
    assert "J3" in ids(contract, "미충족") and "U1" in ids(contract, "판단불가")
    assert any(a["rule_id"] == "U1" and "공용위원회 사무국" in a["question"] for a in contract["abstain"])


def test_fifth_review_fixes():
    unsure = run(IDENTIFIED, "없는병원", {"irb_exists": "없음", "contract": "모름"})  # 모름 → 같은 질문 반복 대신 사무국 확인
    assert "contract" not in asks(unsure) and any(a["rule_id"] == "J3" and a["kind"] == "가" for a in unsure["abstain"])
    done = run(IDENTIFIED, "없는병원", {"irb_exists": "없음", "contract": "예"})    # 협약함 → 협약한 위원회, 협약서·계산 불가 없음
    assert done["route"]["committees"][0] == judge.IRB_NAME["contracted_any"] + " · 심의"  # 상대를 말하지 않았으면 단정하지 않는다
    assert not any("협약서" in d["doc"] for d in done["documents"])
    assert next(r for r in done["judgments"] if r["rule_id"] == "J3")["type"] == "사실형"
    assert run({})["route"]["fast_track"]                        # 샘플 2: 자체 IRB · 결합 없음 → 빠른 길
    for overrides, institution in (({}, "없음"), ({"F06": "예"}, "가상대학교병원"), ({"F06": None}, "가상대학교병원")):
        assert not run(overrides, institution)["route"]["fast_track"]  # 공용위원회·결합·결합 미상이면 빠른 길 아님
    docs = [d["doc"] for d in run({"F10": None})["documents"]]   # 전제를 몰라도 DRB 신청서는 두고, 승인서 첨부만 뺀다
    assert "DRB 심의 신청서" in docs and not any("승인서 첨부" in d for d in docs)
    r09 = next(r for r in run({})["judgments"] if r["rule_id"] == "R-09")
    assert "대상에 해당" not in r09["requirement"]              # 다듬기 판정어 검사에 걸리지 않는 문구


def test_sixth_review_fixes():
    unsure = run(IDENTIFIED, "없는병원", {"irb_exists": "모름"})      # 모름 → 반복 질문 대신 사무국 확인
    assert "irb_exists" not in asks(unsure) and any(a["rule_id"] == "J2" and a["kind"] == "가" for a in unsure["abstain"])
    public = run({}, "없음")                                          # 공용위원회면 DRB 승인서 첨부 표시 없음
    assert not any("승인서 첨부" in d["doc"] for d in public["documents"])
    joint = run({**IDENTIFIED, "F12": ["가상대학교병원", "다른병원"]})  # 공동연구 → 공동 수행기관 IRB 표시
    assert any(c.startswith("공동 수행기관 IRB") for c in joint["route"]["committees"]) and "J10" in joint["route"]["trace"]
    via_public = run(IDENTIFIED, "없는병원", {"irb_exists": "없음", "contract": "예(공용위원회)"})
    assert [s.get("submit_by") for s in via_public["schedule"]["scenarios"]] == ["2026-11-12", "2026-10-29", "2026-10-13"]


def test_seventh_review_fixes():
    other = run(IDENTIFIED, "없는병원", {"irb_exists": "없음", "contract": "예(다른 기관 IRB)"})
    assert other["route"]["committees"][0] == "협약한 다른 기관 IRB · 심의"
    joint = run({"F12": ["가상대학교병원", "다른병원"]})          # 공동연구: 빠른 길 아님, 서류·일정·리포트에도 공동 IRB
    assert joint["route"]["route"] == "A" and not joint["route"]["fast_track"]
    assert joint["route"]["order"] == [1, 2, 2]                   # 공동 수행기관 IRB는 소속 IRB와 같은 차례
    assert any("공동 수행기관 IRB" in d["doc"] for d in joint["documents"])
    assert any("공동 수행기관 IRB" in m for m in joint["schedule"]["missing"])
    assert any("J10" in s["refs"] for s in joint["report"]) and not any("7일" in s["text"] for s in joint["report"])


def test_submission_fixes():
    clean = run({})                                                # 샘플 2: 식별 관리가 적혀 있어 보완 필요 없음, 빠른 길 유지
    assert {"R-11", "R-12"} <= ids(clean, "충족") and clean["route"]["fast_track"] and clean["schedule"]["default"] == 0
    assert not [s for s in clean["suggestions"] if s["level"] == "보완 필요"]
    told = run({}, unwritten=("F17", "F18"))                       # 연구자가 채웠지만 계획서에 없으면 경고 + 보완 문구
    assert {"R-11", "R-12"} <= ids(told, "미충족") and told["route"]["route"] == "A"
    fix = {s["rule_id"]: s for s in told["suggestions"]}
    assert fix["R-11"]["level"] == fix["R-12"]["level"] == "보완 필요" and "대응표" in fix["R-12"]["add_text"]
    assert "신규심의로 전환할 수 있습니다" in fix["R-11"]["warning"] and told["schedule"]["default"] == 1  # R-12 → 보완 1회
    assert any("R-11" in m for m in told["schedule"]["missing"])
    assert any(h["key"] == "F03" and "R-11" in h["note"] for h in told["highlights"])  # 서술이 없으면 데이터 형태 문장에 표시
    guessed = samples.load("sample3_nokey")["pending"]           # 추출 모델이 대응표를 추정으로 채워도(원문에 없음) 경고가 뜬다
    facts = [{**f, **({"value": "예", "status": "conflict"} if f["key"] == "F17" else {}),
              **({"value": "데이터팀·제3자", "status": "conflict"} if f["key"] == "F18" else {})} for f in guessed["facts"]]
    state = {"institution_name": "가상대학교병원", "target_start_date": "2026-12-01", "today": "2026-09-30",
             "masked_text": guessed["masked_text"], "facts": facts, "confirmed_facts": facts, "extra_inputs": {}}
    for step in (judge.institution, judge.gates):
        state = {**state, **step(state)}
    assert {"R-11", "R-12"} <= ids(state, "미충족")
    pi = run({"F18": "연구책임자"})                                  # 가명정보인데 연구자가 대응표 보유 → R-12
    assert "연구책임자" in next(s for s in pi["suggestions"] if s["rule_id"] == "R-12")["warning"]
    assert "R-13" in ids(run({"F06": "예"}), "미충족")               # 결합인데 결합전문기관 서술 없음
    crf = run(IDENTIFIED)                                          # 식별자 기록 → 노란색 표시 + 가명 방식 대안(엔진 재판정)
    assert crf["route"]["route"] == "C" and any(h["key"] == "F16" and h["note"].startswith("E3") for h in crf["highlights"])
    e3 = next(s for s in crf["suggestions"] if s["rule_id"] == "E3")
    assert e3["level"] == "안내" and "경로 A" in e3["warning"]
    for s in [*told["suggestions"], *crf["suggestions"]]:          # 경고는 가능성으로만 쓴다 (팀 문서 6.6)
        assert not any(w in s["warning"] for w in ("승인됩니다", "통과", "반려됩니다"))


def test_eighth_review_fixes():
    pi = run({"F18": "연구책임자"})                              # 연구자가 대응표를 가지면 사실과 반대인 문장을 주지 않는다
    assert next(s for s in pi["suggestions"] if s["rule_id"] == "R-12")["add_text"] is None
    rare = run({"F07": ["희귀질환"]})                             # 민감정보면 '동의 없이 처리' 문장을 권하지 않고 동의 원칙을 알린다
    fix = {s["rule_id"]: s for s in rare["suggestions"]}
    assert "본인 동의" in fix["D4"]["warning"] and "동의 없이 가명정보를 처리" not in (fix["C3"]["add_text"] or "")
    crf = run({**IDENTIFIED, "F07": ["희귀질환"]})               # 대안 설계에서도 남는 미충족을 숨기지 않는다
    e3 = next(s for s in crf["suggestions"] if s["rule_id"] == "E3")["warning"]
    assert "D4 미충족이 남습니다" in e3 and "R-11" not in e3
    answered = run({**IDENTIFIED, "F16": "예"})                  # (나) 답 '예'는 괄호 목록에 넣지 않는다
    assert "식별자(예)" not in next(s for s in answered["suggestions"] if s["rule_id"] == "E3")["warning"]
    edited = run({})                                            # S2에서 고친 값은 계획서에 적힌 것으로 보지 않는다
    edited = {**edited, "edited_by_user": ["F18"]}
    edited = {**edited, **judge.gates(edited)}
    assert {"R-11", "R-12"} <= ids(edited, "미충족")
    assert "R-13" in ids(run({"F06": "예"}), "미충족")
    marks = run({}, unwritten=("F17", "F18"))["highlights"]      # 겹치는 표시 구간은 하나로 합친다
    assert all(a["span_end"] <= b["span_start"] for a, b in zip(marks, marks[1:]))



def test_institution_layer():
    uos = run({}, "서울시립대학교")               # 기관 프로필: 제출처·기관 서식·정규심의 일정·기관 규칙
    assert uos["venue"]["id"] == "uos" and not uos["route"]["fast_track"]  # 면제도 정규심의 안건 → 7일 빠른 길 없음
    assert uos["schedule"]["scenarios"][0]["submit_by"] == "2026-10-26"    # 11-06 회의 + 결과 14일 < 12-01 개시
    assert any("별지서식 9-3" in d["doc"] for d in uos["documents"])     # 심의면제 후보 → 면제용 서식 9-3
    assert any("별지서식 9-1" in d["doc"] for d in run(IDENTIFIED, "서울시립대학교")["documents"])  # 정규심의 → 9-1
    assert {"I-UOS-1", "I-UOS-2", "I-UOS-P"} <= {s["rule_id"] for s in uos["suggestions"] if s["scope"] == "기관"}
    assert "I-UOS-2" not in {s["rule_id"] for s in run(IDENTIFIED, "서울시립대학교")["suggestions"]}  # 허가 공문은 면제 문맥만
    assert run({}, "서울시립대학교", target="2026-12-28")["schedule"]["scenarios"][0]["submit_by"] == "2026-11-23"  # 연말도 계산
    cmc = run({"F12": ["서울성모병원"]}, "서울성모병원")  # 명단에 없는 별칭도 기관 프로필이 있으면 IRB가 있는 기관
    assert cmc["venue"]["id"] == "cmc" and cmc["institution"]["irb_exists"] is True
    assert not cmc["route"]["fast_track"]                              # IRB·DRB 순서를 공개하지 않은 기관은 7일 빠른 길을 켜지 않는다
    assert "I-CMC-1" not in {s["rule_id"] for s in cmc["suggestions"]}  # IRB 전 DRB 승인은 반출 연구 항목
    export = run({"F12": ["서울성모병원"], "F06": "예"}, "서울성모병원")
    assert "I-CMC-1" in {s["rule_id"] for s in export["suggestions"]}
    public = run({}, "없음")
    assert public["venue"]["id"] == "public" and "제37호" in public["venue"]["plan_form"]
    survey = run({**IDENTIFIED, "F01": "설문·면담"}, "없음")            # 공용위원회 서식은 연구 유형마다 다르다
    assert "제33호" in survey["venue"]["plan_form"] and any("서면동의 면제 사유서" in d["doc"] for d in survey["documents"])
    smc = run({"F12": ["삼성서울병원"]}, "삼성서울병원")               # 삼성서울병원은 IRB 승인 → 데이터 수집 → DRB
    assert smc["route"]["route"] == "A" and smc["route"]["committees"][0].startswith("소속 기관 IRB")
    assert not smc["route"]["fast_track"]
    plain = run({})                                                    # 프로필이 없는 기관은 예전처럼 공통 서류
    assert plain["venue"] is None and any(d["source"] == "관할 IRB 서식" for d in plain["documents"])
    rows = judge.compare_table()                                       # 서식 표준화 비교표: 서류 12 + 계획서 항목 13
    assert len(rows) == 25 and {"공용위원회", "서울시립대", "서울성모병원", "질병관리청"} <= set(rows[0])
    assert "—" not in {v for r in rows for v in r.values()}            # 빈칸은 '안내문에 없음'으로 쓴다


def test_data_holder_differs():
    """소속 기관과 데이터를 가진 기관이 다르면 IRB는 소속 쪽, DRB는 데이터 보유 기관이고, 7일 빠른 길은 없다 (prep 이슈 #10)."""
    away = run({}, "질병관리청")                                  # 샘플 2의 데이터는 가상대학교병원 데이터팀이 준다
    assert away["route"]["route"] == "A" and not away["route"]["fast_track"]
    assert away["route"]["committees"][0].startswith("데이터 보유 기관 DRB · 가상대학교병원")
    assert any(d["doc"] == "DRB 심의 신청서 (가상대학교병원)" for d in away["documents"])
    assert any("데이터를 가진 기관(가상대학교병원)" in s["text"] for s in away["report"])
    home = run({})                                                # 같은 기관(프로필 없는 가상 기관)이면 가이드라인 표준절차의 빠른 길
    assert home["route"]["fast_track"] and home["route"]["committees"][0].startswith("기관 DRB")
    alone = run({}, "없음")                                       # 소속 없는 연구자도 DRB는 데이터를 가진 기관
    assert alone["route"]["committees"][0].startswith("데이터 보유 기관 DRB · 가상대학교병원")


def test_drb_order_follows_data_holder():
    """DRB 순서는 DRB를 둔 기관(데이터 보유 기관)의 안내를 따른다 (10차 리뷰)."""
    a = run({"F12": ["서울성모병원"]}, "삼성서울병원")            # 삼성 소속 + 성모 데이터 → 성모 DRB(순서 비공개), DRB 먼저
    assert a["route"]["committees"][0].startswith("데이터 보유 기관 DRB · 서울성모병원") and "삼성서울병원 안내" not in str(a["route"])
    b = run({"F12": ["삼성서울병원"]}, "서울성모병원")            # 성모 소속 + 삼성 데이터 → 삼성 안내대로 IRB 먼저
    assert b["route"]["committees"][0].startswith("소속 기관 IRB") and "삼성서울병원 안내" in b["route"]["committees"][1]
    smc = run({"F12": ["삼성서울병원"]}, "삼성서울병원")           # DRB가 IRB 뒤인 기관은 DRB 승인서를 IRB 이후에 낸다
    assert {d["to"] for d in smc["documents"] if "DRB" in d["doc"] and "승인" in d["doc"]} <= {"IRB 이후"}
    assert all(d.get("to") for d in smc["documents"])                  # 모든 서류에 어디에 내는지가 붙는다
    assert {d["to"] for d in run({"F06": "예"})["documents"]} >= {"DRB", "IRB", "결합전문기관"}


def test_unimplemented_checks_do_not_warn():
    """검사 함수가 아직 없는 기관 규칙(check)은 계획서가 규정을 지켜도 뜨는 헛경고를 내지 않는다."""
    cuk = run({"F12": ["가톨릭대"]}, "가톨릭대")
    fired = {s["rule_id"] for s in cuk["suggestions"] if s.get("scope") == "기관"}
    assert not {"I-CUK-1", "I-CUK-3", "I-CUK-4", "I-CUK-5"} & fired   # 과거형·문체·만 나이·심의 전 시작: 검사 전이라 내지 않음
    assert "I-CUK-2" in fired                                          # 산출근거는 서술 여부(told)로 확인: 샘플 2에 없음



def test_institution_criteria_rows():
    """제출처 기관의 규정이 판정표의 '기관 기준' 행이 되고, 계획서 글 검사가 위반 문장을 찾는다 (가톨릭대 유의사항)."""
    base = samples.load("sample2_pseudo")
    clean = run({"F12": ["가톨릭대"]}, "가톨릭대")
    rows = {r["rule_id"]: r for r in clean["judgments"] if r["type"] == "기관 기준"}
    assert rows["I-CUK-1"]["result"] == rows["I-CUK-3"]["result"] == rows["I-CUK-4"]["result"] == "충족"
    assert rows["I-CUK-2"]["result"] == "미충족"                        # 샘플 2엔 대상자 수 산출근거가 없다
    assert not [r for r in run({})["judgments"] if r["type"] == "기관 기준"]  # 프로필 없는 기관은 기관 기준 행이 없다
    trap = base["pending"]["masked_text"].replace(
        "제공받아 분석한다.", "제공받아 분석하였다. 연구대상자는 19세 이상 성인으로 합니다.")
    facts = [dict(f, value=["가톨릭대"]) if f["key"] == "F12" else
             dict(f, value="2026-10-15 ~ 2027-10-14") if f["key"] == "F13" else dict(f)
             for f in base["pending"]["facts"]]
    state = {"institution_name": "가톨릭대", "target_start_date": "2026-10-15", "today": "2026-09-30", "masked_text": trap,
             "facts": facts, "confirmed_facts": facts, "extra_inputs": {}}
    for step in (judge.institution, judge.gates, judge.route, judge.docs_schedule, write.abstain, write.report):
        state = {**state, **step(state)}
    bad = {r["rule_id"] for r in state["judgments"] if r["type"] == "기관 기준" and r["result"] == "미충족"}
    assert {"I-CUK-1", "I-CUK-3", "I-CUK-4", "I-CUK-5"} <= bad          # 과거형·경어체·만 나이 없음·심의 전 시작
    marked = " ".join(h["span"] for h in state["highlights"])
    assert "분석하였다" in marked and "19세 이상" in marked
    other = run({"F12": ["삼성서울병원"]}, "삼성서울병원")               # 기관을 바꾸면 판정 기준도 바뀐다
    assert not [r for r in other["judgments"] if r["rule_id"].startswith("I-CUK")]
