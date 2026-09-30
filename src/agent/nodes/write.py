"""⑨ 판단불가 처리, ⑩ 결과 리포트. 판정 결과는 바꾸지 않고 글만 쓴다.

지금은 틀 문장이다. TODO: LLM으로 문장을 다듬되, 인용과 근거 검사는 그대로 통과해야 출력한다.
"""
from ..state import GraphState

# (나) 계획서에 정보가 없을 때 연구자에게 물을 문장과 선택지
ASK = {
    "F05": ("데이터를 어디에서 분석하나요?", ["기관 내부", "제3자 제공(통제 환경)", "그 외"]),
    "F07": ("정신질환·HIV·성매개감염병·희귀질환·학대·낙태 정보가 들어 있나요?", ["없음", "있음"]),
    "F08": ("미성년자 등 취약한 환경의 대상자가 포함되나요?", ["아니오", "예"]),
    "F16": ("이름·등록번호 같은 식별정보를 수집하거나 기록하나요?", ["아니오", "예"]),
    "irb_exists": ("소속기관에 IRB(기관생명윤리위원회)가 있나요?", ["있음", "없음", "모름"]),
}
INPUT_BY_RULE = {"J2": "irb_exists"}
REASON = {"①": "위원회 판단", "②": "평가어", "③": "기관 재량"}
ASKED = {"①": "위원회", "②": "위원회", "③": "기관 사무국"}


def abstain(state: GraphState) -> dict:
    """⑨ 판단불가 행을 (가) 사무국 질문과 (나) 연구자 입력 요청으로 바꾼다."""
    items = []
    for r in state["judgments"]:
        if r["result"] != "판단불가":
            continue
        cites = [r["rule_id"], *r["fact_refs"]]
        if r["abstain_reason"] == "나":
            key = r["fact_refs"][0] if r["fact_refs"] else INPUT_BY_RULE.get(r["rule_id"])
            ask, options = ASK.get(key, (r["requirement"], []))
            items.append({"rule_id": r["rule_id"], "kind": "나", "reason": f"(나) 계획서에 정보 없음 · {r['requirement']}",
                          "ask_input": ask, "options": options, "input_key": key, "cites": cites})
        else:
            b = r["basis"]
            question = (f"{b['law']} {b['article']} 관련 문의입니다. 본 연구에서 「{r['requirement']}」에 대해 "
                        f"{ASKED[r['abstain_reason']]}의 판단을 요청드립니다. (참고: {r['result_detail']})")
            items.append({"rule_id": r["rule_id"], "kind": "가",
                          "reason": f"{r['abstain_reason']} {REASON[r['abstain_reason']]} · {r['requirement']}",
                          "question": question, "cites": cites})
    return {"abstain": items}


def report(state: GraphState) -> dict:
    """⑩ 판정 결과를 쉬운 문장으로 쓴다. 판정 행에 없는 규칙을 근거로 단 문장은 버린다."""
    rows = {r["rule_id"]: r for r in state["judgments"]}
    result = lambda rule_id: rows.get(rule_id, {}).get("result")  # noqa: E731
    out = []

    def say(text: str, *refs: str) -> None:
        if all(ref in rows for ref in refs if not ref.startswith("F")):
            out.append({"text": text, "refs": list(refs)})

    if result("G1") == "충족":
        say("배아·유전자 연구라서 이 도구의 범위 밖입니다. 사무국에 문의해 주세요.", "G1")
    if result("T1") == "충족":
        say("의약품·의료기기 임상시험이라 식약처 임상시험계획 승인과 임상시험실시기관 심사위원회를 거칩니다.", "T1", "F10")
        say("임상시험은 공용위원회 심의 대상에서 제외됩니다.", "T6")
    if result("S7") == "충족":
        say("식별할 수 없는 자료만 쓰므로 생명윤리법상 기관위원회 심의 대상이 아닙니다. 기관 규정은 따로 확인해 주세요.", "S7", "F03")
    if result("D1") == "충족":
        say("가명처리된 데이터를 동의 없이 연구에 쓰므로 기관 DRB 검토 경로에 해당합니다. DRB는 가이드라인 권고라서 기관 규정을 확인해야 합니다.", "D1", "F03")
        say("가명정보 연구도 DRB와 별도로 IRB 심의 또는 심의면제 확인을 받아야 합니다.", "D6")
    if result("J2") == "충족":
        say("소속 기관에 IRB가 있어 그 IRB에 신청합니다.", "J2")
    if result("J8") == "충족":
        say("소속 기관이 없는 연구자라서 공용기관생명윤리위원회에 신청합니다.", "J8")
    if "J6" in rows:
        say("소속 기관에 IRB가 없어 공용위원회 등과 위탁 협약을 맺어야 할 수 있습니다. 협약 가능 여부는 사무국에 확인해 주세요.", "J6")
    exempt = next((x for x in ("E3", "E2") if result(x) == "충족"), None)
    if exempt:
        say("심의면제 신청 후보입니다. 면제 여부는 관할 위원회가 확인합니다.", exempt, "R-09")
    if result("E3") == "미충족":
        say("식별정보를 기록하므로 심의면제 후보가 아니며, 심의를 받아야 합니다.", "E3", "F16")
    if state["route"]["route"] == "A" and state["route"]["fast_track"]:
        say("가이드라인 표준절차상 DRB 승인서가 있으면 7일 이내에 심의면제 확인서를 받을 수 있습니다. 기관마다 다를 수 있습니다.", "D7")
    return {"report": out}
