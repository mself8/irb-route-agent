"""⑨ 판단불가 처리, ⑩ 결과 리포트. 판정 결과는 바꾸지 않고 글만 쓴다.

지금은 틀 문장이다. TODO: LLM으로 문장을 다듬되, 인용과 근거 검사는 그대로 통과해야 출력한다.
"""
from ..state import GraphState

# (나) 계획서에 정보가 없을 때 연구자에게 물을 문장과 선택지. 선택지가 없으면 글로 적는다
ASK = {
    "F05": ("가명정보를 누가 분석하나요? 데이터를 가진 기관이 직접 쓰면 '기관 내부', 외부 연구자가 제공기관의 분석실·내부망에서만 "
            "쓰면 '제3자 제공(통제 환경)', 그 밖은 '그 외'입니다.", ["기관 내부", "제3자 제공(통제 환경)", "그 외"]),
    "F07": ("정신질환·HIV·성매개감염병·희귀질환·학대·낙태 정보가 들어 있나요?", ["없음", "있음"]),
    "F08": ("미성년자 등 취약한 환경의 대상자가 포함되나요?", ["아니오", "예"]),
    "F10": ("의약품·의료기기 임상시험인가요?", ["아니오", "예"]),
    "F11": ("환자(정보주체)의 동의를 받나요?", ["없음", "서면동의", "동의면제 요청"]),
    "F14": ("배아·난자·정자·유전자 관련 연구인가요?", ["아니오", "예"]),
    # F16~F18: 팀 문서 「식별코드 사실 항목 보완」 6장의 세 질문
    "F16": ("분석 데이터에 이름·등록번호·연락처 같은 식별자가 남아 있습니까?", ["아니오", "예"]),
    "F17": ("대상자를 연구용 번호(예: DM-001)로 바꿔 관리합니까?", ["예", "아니오"]),
    "F18": ("번호와 실제 환자를 잇는 대응표는 누가 갖고 있습니까?", ["없음(폐기)", "연구책임자", "데이터팀·제3자"]),
    "irb_exists": ("소속기관에 IRB(기관생명윤리위원회)가 있나요?", ["있음", "없음", "모름"]),
    "institution_name": ("소속 기관 이름을 적어 주세요. 소속이 없으면 '없음'이라고 적어 주세요.", []),
}
INPUT_BY_RULE = {"J2": "irb_exists", "J8": "institution_name"}
REASON = {"①": "위원회 판단", "②": "평가어", "③": "기관 재량"}
ASKED = {"①": "위원회", "②": "위원회", "③": "기관 사무국"}
ASKED_BY_RULE = {"S7": "데이터 보유기관(개인정보처리자)"}  # prep 판단불가 #14: 익명 여부의 판단 주체


def abstain(state: GraphState) -> dict:
    """⑨ 판단불가 행을 (가) 사무국 질문과 (나) 연구자 입력 요청으로 바꾼다."""
    items = []
    for r in state["judgments"]:
        if r["result"] != "판단불가":
            continue
        cites = [r["rule_id"], *r["fact_refs"]]
        if r["abstain_reason"] == "나":
            key = INPUT_BY_RULE.get(r["rule_id"]) if not r["fact_refs"] else r["fact_refs"][0]
            ask, options = ASK.get(key, (r["requirement"], []))
            items.append({"rule_id": r["rule_id"], "kind": "나", "reason": f"(나) 계획서에 정보 없음 · {r['requirement']}",
                          "ask_input": ask, "options": options, "input_key": key, "cites": cites})
        else:
            b = r["basis"]
            asked = ASKED_BY_RULE.get(r["rule_id"], ASKED[r["abstain_reason"]])
            question = (f"{b['law']} {b['article']} 관련 문의입니다. 본 연구에서 「{r['requirement']}」에 대해 "
                        f"{asked}의 판단을 요청드립니다. (참고: {r['result_detail']})")
            items.append({"rule_id": r["rule_id"], "kind": "가",
                          "reason": f"{r['abstain_reason']} {REASON[r['abstain_reason']]} · {r['requirement']}",
                          "question": question, "cites": cites})
    return {"abstain": items}


def report(state: GraphState) -> dict:
    """⑩ 판정 결과를 쉬운 문장으로 쓴다. 판정 행에 없는 규칙을 근거로 단 문장은 버린다."""
    rows = {r["rule_id"]: r for r in state["judgments"]}
    result = lambda rule_id: rows.get(rule_id, {}).get("result")  # noqa: E731
    exempt = state["decision"].get("exempt")
    out = []

    def say(text: str, *refs: str) -> None:
        if all(ref in rows for ref in refs if not ref.startswith("F")):
            out.append({"text": text, "refs": list(refs)})

    if result("G1") == "충족":
        say("배아·유전자 연구라서 이 도구의 범위 밖입니다. 사무국에 문의해 주세요.", "G1")
    if result("T1") == "충족":
        say("의약품·의료기기 임상시험이라 식약처 임상시험계획 승인과 임상시험실시기관 심사위원회를 거칩니다.", "T1", "F10")
        say("임상시험은 공용위원회 심의 대상에서 제외됩니다.", "T6")
        say("생명윤리법 기관위원회 심의가 추가로 필요한지는 기관 규정으로 확인해야 합니다.", "U28")
    if result("S6") == "충족":
        say("인체유래물을 직접 분석하는 연구라서 인체유래물연구의 심의 기준을 따릅니다. 면제 여부는 위원회가 확인합니다.", "S6", "E5")
    if result("S7") == "판단불가":
        say("익명정보라면 생명윤리법상 심의 대상이 아닐 수 있습니다. 다만 더 이상 알아볼 수 없는지는 데이터 보유기관이 판단하므로, "
            "관할 IRB에 심의면제 확인을 받아야 합니다.", "S7", "F17")
    if result("D1") == "충족":
        say("가명처리된 데이터를 동의 없이 연구에 쓰므로 기관 DRB 검토 경로에 해당합니다. DRB는 가이드라인 권고라서 기관 규정을 확인해야 합니다.",
            "D1", "F03", "F18")
        say("개인정보 보호법에 따라 동의 없이 쓸 근거가 있으므로, 생명윤리법상 서면동의 면제 판단은 따로 필요하지 않습니다.", "D1", "F11")
        say("가명정보 연구도 DRB와 별도로 IRB 심의 또는 심의면제 확인을 받아야 합니다.", "D6")
    if result("J2") == "충족":
        say("소속 기관에 IRB가 있어 그 IRB에 신청합니다.", "J2")
    if result("J8") == "충족":
        say("소속 기관이 없는 연구자라서 공용기관생명윤리위원회에 신청합니다.", "J8")
    if "J6" in rows:
        say("소속 기관에 IRB가 없어 공용위원회나 인증받은 다른 기관 IRB와 위탁 협약을 맺어야 할 수 있습니다. 협약 가능 여부는 사무국에 확인해 주세요.", "J6")
    if exempt == "yes":
        say("심의면제 신청 후보입니다. 면제 여부는 관할 위원회가 확인합니다.", "E3", "R-09")
    elif exempt == "unknown":
        rule_id = next((x for x in ("E3", "E2", "E4", "E5") if x in rows), None)
        if rule_id:
            say("심의면제 가능 여부는 아직 정할 수 없습니다. 판단불가 항목에 답하거나 위원회 확인을 받아야 합니다.", rule_id)
    if result("E3") == "미충족":
        say("식별자를 수집·기록하므로 심의면제 후보가 아니며, 심의를 받아야 합니다.", "E3", "F16")
    if result("E4") == "미충족":
        say("취약한 환경의 대상자가 포함되어 심의면제를 받을 수 없습니다.", "E4", "F08")
    if state["route"]["route"] == "A" and state["route"]["fast_track"]:
        say("가이드라인 표준절차상 DRB 승인서가 있으면 7일 이내에 심의면제 확인서를 받을 수 있습니다. 기관마다 다를 수 있습니다.", "D7")
    return {"report": out}
