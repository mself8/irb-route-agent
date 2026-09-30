"""⑨ 판단불가 처리, ⑩ 결과 리포트. 판정 결과는 바꾸지 않고 글만 쓴다.

지금은 틀 문장이다. TODO: LLM으로 문장을 다듬되, 인용과 근거 검사는 그대로 통과해야 출력한다.
"""
from ..state import GraphState
from . import judge
from .read import _impl

# (나) 계획서에 정보가 없을 때 연구자에게 물을 문장과 선택지. 선택지가 없으면 글로 적는다
ASK = {
    "F01": ("연구 유형이 무엇인가요?", ["기록 이용", "설문·면담", "관찰", "중재", "인체유래물"]),
    "F06": ("다른 기관의 데이터와 결합하거나 외부로 반출하나요?", ["아니오", "예"]),
    "F09": ("혈액·조직 같은 인체유래물을 쓰나요?", ["아니오", "예"]),
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
    "contract": ("소속 기관이 공용위원회나 다른 기관 IRB와 위탁 협약을 맺었나요?",
                 ["예(공용위원회)", "예(다른 기관 IRB)", "아니오", "모름"]),
    "institution_name": ("소속 기관 이름을 적어 주세요. 소속이 없으면 '없음'이라고 적어 주세요.", []),
}
INPUT_BY_RULE = {"J2": "irb_exists", "J8": "institution_name", "J3": "contract"}
REASON = {"①": "위원회 판단", "②": "평가어", "③": "기관 재량·기관확인"}
ASKED = {"①": "위원회", "②": "위원회", "③": "기관 사무국"}
ASKED_BY_RULE = {"S7": "데이터 보유기관(개인정보처리자)", "U1": "공용위원회 사무국"}  # prep 판단불가 #14: 익명 여부의 판단 주체

# 제출 전 보완 문구 (팀 문서 「식별코드 누락 시 행정 처리 위험과 해결 방안」 6.3). [ ]는 연구자가 사실에 맞게 채운다.
# 경고는 가능성으로만 쓰고 사무국 판단을 예측하지 않는다. 법 문구는 prep 원문(09-29 대조)을 따른다.
ID_TEXT = ("본 연구는 성명, 주민등록번호, 병원 등록번호, 연락처 등 개인식별정보를 수집·기록하지 않는다. "
           "연구대상자는 [데이터팀]이 부여한 연구번호로 대체하여 관리한다.")
KEY_TEXT = {"데이터팀·제3자": "연구번호와 실제 대상자를 연결하는 대응표는 [데이터팀]이 별도로 분리 보관하며, 연구자는 대응표에 접근하지 않는다. "
                           "대응표 접근 권한은 [담당 부서]로 제한한다.",
            "없음(폐기)": "연구번호와 실제 대상자를 연결하는 대응표는 연구번호를 부여한 뒤 파기한다."}
NO_CODE_TEXT = "본 연구는 성명, 주민등록번호, 병원 등록번호, 연락처 등 개인식별정보를 수집·기록하지 않으며, 연구번호와 대응표를 만들지 않는다."
LINK_TEXT = ("다른 기관 자료와의 결합은 개인정보 보호법 제28조의3에 따라 [결합전문기관]이 수행한다. "
             "결합된 정보를 결합전문기관 밖으로 반출할 때는 가명정보 또는 익명정보로 처리한 뒤 전문기관의 장의 승인을 받는다.")
SENSITIVE_TEXT = "민감정보([종류])는 [접근 권한자]만 접근하고, [분석 장소]에서만 분석하며 외부로 반출하지 않는다."
PSEUDO_TEXT = "본 연구는 개인정보 보호법 제28조의2에 따라 과학적 연구를 위하여 정보주체의 동의 없이 가명정보를 처리한다."
WAIVER_TEXT = ("[이유]로 연구대상자의 동의를 받는 것이 연구 진행과정에서 현실적으로 불가능하거나 연구의 타당성에 심각한 영향을 미치며, "
               "연구대상자의 동의 거부를 추정할 만한 사유가 없고 동의를 면제하여도 연구대상자에게 미치는 위험이 극히 낮으므로 "
               "서면동의 면제를 요청한다(생명윤리법 제16조 제3항).")
# 식별 데이터를 가명 데이터로 바꿨을 때(샘플 2의 방식) 규칙 엔진이 어떻게 판정하는지 보여 준다
PSEUDO_DESIGN = {"F02": "아니오", "F03": "가명처리", "F16": [], "F17": "예", "F18": "데이터팀·제3자"}


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
                          "question": question, "cites": cites, "_basis": r["basis"]})
    return {"abstain": _polish(items, state)}


def _polish(items: list[dict], state: GraphState) -> list[dict]:
    """(가) 질문을 AI로 다듬는다(agent/phrasing.py가 있을 때). 검사를 통과하지 못한 문장은 틀 문장을 그대로 쓴다."""
    impl = _impl("phrasing")
    asked = [i for i in items if i["kind"] == "가"]
    if impl and asked:
        texts = impl.polish([{**i, "basis": i["_basis"]} for i in asked],
                            state.get("masked_text", ""), state.get("confirmed_facts", []))
        for item, text in zip(asked, texts):
            if text:
                item["question"] = text
            if hasattr(impl, "references"):
                item["references"] = impl.references({**item, "basis": item["_basis"]})
    for item in items:
        item.pop("_basis", None)
    return items


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
        tail = "" if result("E5") == "미충족" else " 면제 여부는 위원회가 확인합니다."
        say("인체유래물을 직접 분석하는 연구라서 인체유래물연구의 심의 기준을 따릅니다." + tail, "S6", "E5")
    if result("S7") == "판단불가" and result("S6") != "충족":
        say("익명정보라면 생명윤리법상 심의 대상이 아닐 수 있습니다. 다만 더 이상 알아볼 수 없는지는 데이터 보유기관이 판단하므로, "
            "관할 IRB에 심의면제 확인을 받아야 합니다.", "S7", "F17")
    if result("D1") == "충족":
        say("가명처리된 데이터를 동의 없이 연구에 쓰므로 기관 DRB 검토 경로에 해당합니다. DRB는 가이드라인 권고라서 기관 규정을 확인해야 합니다.",
            "D1", "F03", "F18")
        say("가명정보 연구도 DRB와 별도로 IRB 심의 또는 심의면제 확인을 받아야 합니다.", "D6")
    if result("J2") == "충족":
        say("소속 기관에 IRB가 있어 그 IRB에 신청합니다.", "J2")
    if result("J8") == "충족":
        say("소속 기관이 없는 연구자라서 공용기관생명윤리위원회에 신청합니다.", "J8")
    if result("J6") == "충족" and result("J3") == "충족":
        say("소속 기관에 IRB가 없지만 위탁 협약을 맺었으므로, 협약한 위원회에 신청합니다.", "J6", "J3")
    elif result("J6") == "충족":
        say("소속 기관에 IRB가 없어 공용위원회나 인증받은 다른 기관 IRB와 위탁 협약을 맺고 심의를 받습니다.", "J6", "J3")
    if exempt == "yes":
        say("심의면제 신청 후보입니다. 면제 여부는 관할 위원회가 확인합니다.", "E3", "R-09")
    elif exempt == "unknown":
        rule_id = next((x for x in ("E3", "E2", "E4", "E5") if x in rows), None)
        if rule_id:
            say("심의면제 가능 여부는 아직 정할 수 없습니다. 판단불가 항목에 답하거나 위원회 확인을 받아야 합니다.", rule_id)
    if result("E3") == "미충족":
        say("식별자를 수집·기록하므로 심의면제 후보가 아니며, 심의를 받아야 합니다.", "E3", "F16")
    if result("E2") == "미충족":
        say("식별자나 건강 등 민감정보를 수집하므로 심의면제 후보가 아니며, 심의를 받아야 합니다.", "E2")
    if result("E5") == "미충족":
        say("개인정보를 수집·기록하는 인체유래물연구라서 심의면제를 받을 수 없습니다.", "E5", "F16")
    if result("E4") == "미충족":
        say("취약한 환경의 대상자가 포함되어 심의면제를 받을 수 없습니다.", "E4", "F08")
    if result("J10") == "판단불가":
        say("여러 기관이 함께 하는 연구라서 기본은 기관마다 IRB 심의를 받습니다. 한 기관 위원회를 정하거나 공용위원회를 쓰려면 "
            "수행기관끼리 합의해야 합니다.", "J10", "F12")
    if state["route"]["route"] == "A" and state["route"]["fast_track"]:
        say("가이드라인 표준절차상 DRB 승인서가 있으면 7일 이내에 심의면제 확인서를 받을 수 있습니다. 기관마다 다를 수 있습니다.", "D7")
    suggestions = suggest(state)
    return {"report": out, "suggestions": suggestions, "highlights": highlights(state, suggestions)}


def suggest(state: GraphState) -> list[dict]:
    """제출 전 보완: 미충족 규칙과 계획서에 없는 서술을 경고와 계획서에 넣을 문장으로 바꾼다. 판정은 바꾸지 않는다."""
    rows = {r["rule_id"]: r for r in state["judgments"]}
    f = judge._facts(state)
    result = lambda rule_id: rows.get(rule_id, {}).get("result")  # noqa: E731
    out = []

    def add(rule_id: str, level: str, warning: str, add_text: str | None = None) -> None:
        b = rows[rule_id]["basis"]
        out.append({"rule_id": rule_id, "level": level, "warning": warning, "add_text": add_text,
                    "basis": f"{b['law']} {b['article']}"})

    if result("R-11") == "미충족":
        gap = ", ".join(judge.ID_LABEL[k] for k in rows["R-11"]["fact_refs"])
        text = NO_CODE_TEXT if f.get("F17") == "아니오" else f"{ID_TEXT} {KEY_TEXT.get(f.get('F18'), KEY_TEXT['데이터팀·제3자'])}"
        add("R-11", "보완 필요", f"계획서에 {gap} 서술이 없습니다. 이대로 심의면제를 신청하면 사무국이 신규심의로 전환할 수 있습니다.", text)
    if result("R-12") == "미충족":
        warning = ("가명정보를 쓰는데 대응표를 연구책임자가 갖고 있습니다." if f.get("F18") == "연구책임자"
                   else "대응표 분리 보관과 접근 통제가 계획서에 없습니다.")
        text = KEY_TEXT["없음(폐기)"] if f.get("F18") == "없음(폐기)" else KEY_TEXT["데이터팀·제3자"]
        add("R-12", "보완 필요", warning + " DRB에서 안전조치 보완을 요구받을 수 있습니다.", text)
    if result("R-13") == "미충족":
        add("R-13", "보완 필요", "다른 기관 데이터와 결합하려면 결합전문기관을 거쳐야 하는데, 그 절차가 계획서에 없습니다.", LINK_TEXT)
    if result("D4") == "미충족":
        add("D4", "확인 필요", f"민감정보({', '.join(f.get('F07') or [])})가 들어 있습니다. DRB가 처리 근거와 보호조치를 확인할 수 있습니다.",
            SENSITIVE_TEXT)
    if "C3" in rows:
        texts = [PSEUDO_TEXT] if state["decision"].get("drb") is True else []
        texts += [WAIVER_TEXT] if f.get("F11") == "동의면제 요청" else []
        add("C3", "확인 필요", "동의 없이 진행하는 근거를 계획서에 적어 두세요. 서면동의 면제는 기관위원회가 승인합니다.", " ".join(texts) or None)
    if result("E3") == "미충족":
        alt = _what_if(state, PSEUDO_DESIGN)
        steps = " → ".join(c.split(" (")[0] for c in alt["committees"])
        add("E3", "안내", f"식별자({', '.join(f.get('F16') or [])})를 기록해서 심의면제 대상이 아닙니다. 데이터팀이 식별자를 지운 가명 데이터를 "
            f"받는 방식으로 바꾸면, 규칙 엔진으로 다시 판정한 결과 경로 {alt['route']}({steps})입니다. 면제 여부는 위원회가 확인하며, "
            "연구에 식별자가 꼭 필요하면 지금 경로를 따릅니다.", f"{ID_TEXT} {KEY_TEXT['데이터팀·제3자']}")
    return out


def _what_if(state: GraphState, changes: dict) -> dict:
    """사실 몇 개를 바꿔 규칙 엔진(⑥⑦)을 다시 돌린 경로. 연구자에게 대안을 보여 줄 때만 쓴다."""
    facts = [{**x, "value": changes[x["key"]], "status": "found"} if x["key"] in changes else x for x in state["confirmed_facts"]]
    s = {**state, "confirmed_facts": facts}
    s = {**s, **judge.gates(s)}
    return judge.route(s)["route"]


def highlights(state: GraphState, suggestions: list[dict]) -> list[dict]:
    """계획서에서 노란색으로 칠할 곳: 보완 제안과 심의면제 미충족의 근거 사실 구간. 서술이 없으면 데이터 형태 문장에 단다."""
    text = state.get("masked_text", "")
    facts = {x["key"]: x for x in state.get("facts") or state.get("confirmed_facts", [])}
    rows = {r["rule_id"]: r for r in state["judgments"]}
    marks: dict[tuple, list[str]] = {}

    def mark(key: str, note: str) -> bool:
        span = (facts.get(key) or {}).get("span")
        if not span or facts[key].get("status") == "not_found":
            return False
        start = facts[key].get("span_start")
        if start is None or text[start:start + len(span)] != span:
            start = text.find(span)
        if start < 0:
            return False
        marks.setdefault((start, start + len(span), key, span), []).append(note)
        return True

    targets = [s["rule_id"] for s in suggestions]
    targets += [r for r in ("E2", "E4", "E5") if rows.get(r, {}).get("result") == "미충족"]
    for rule_id in targets:
        r = rows[rule_id]
        note = f"{rule_id} {r['result_detail']}"
        if not any([mark(k, note) for k in r["fact_refs"]]):
            any(mark(k, f"{rule_id} 여기에 서술 추가: {r['result_detail']}") for k in ("F03", "F01"))
    return [{"key": k, "span": span, "span_start": a, "span_end": b, "note": " / ".join(notes)}
            for (a, b, k, span), notes in sorted(marks.items())]
