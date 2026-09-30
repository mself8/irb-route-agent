"""⑤~⑧ 규칙 엔진. 판정은 이 파일에서만 한다. LLM을 쓰지 않는다.

판정 조건은 이 파일, 요건 문구·근거·원문은 data/rules/rules.yaml이 정본이다.
순서는 prep 판정규칙표의 결정 순서를 따른다: 범위(G·T·S) → 가명 데이터(D) → IRB·위탁(J) → 심의면제(E) → 동의(C).
모르는 사실은 추정하지 않고 판단불가(나)로 연구자에게 묻는다. 사실로 정해지는 것은 기권하지 않는다.
"""
import csv
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from ..state import GraphState

ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = ROOT / "data" / "rules" / "rules.yaml"
LISTS_DIR = ROOT / "data" / "lists"
PUBLIC_SCHEDULE = ROOT / "data" / "schedules" / "public_irb_2026.csv"
UNAFFILIATED = {"없음", "소속 없음", "개인"}
IRB_NAME = {"own": "소속 기관 IRB", "public": "공용기관생명윤리위원회",
            "contract": "공용위원회 또는 인증받은 다른 기관 IRB (위탁 협약 필요)"}
IRB_RULES = {"own": ["J2"], "public": ["J8"], "contract": ["J2", "J6"]}
EXEMPT_SUFFIX = {"yes": " · 심의면제 신청 후보", "no": " · 심의", "unknown": " · 심의 또는 심의면제 (확인 필요)"}
# 가명정보 처리 가이드라인(2026.03.) 인쇄 48쪽 위험도별 적정성 검토 방식
REVIEW = {"저위험": "담당자 검토", "중위험": "내부 심의(2인 이상)", "고위험": "적정성 검토위원회(3인 이상)"}

# 사실 값 정리: 화면에서 손으로 고친 값이나 표현이 달라도 규칙이 같은 뜻으로 읽게 한다
NONE_WORDS = {"", "없음", "아니오", "아니요", "해당 없음", "없다"}
UNKNOWN_WORDS = {"모름", "모르겠음", "미정", "확인 필요"}
LIST_FACTS = {"F07", "F08", "F12", "F16"}
YES_NO = {"F02", "F06", "F09", "F10", "F14", "F17"}
YES_NO_WORDS = {"예": "예", "네": "예", "있음": "예", "아니오": "아니오", "아니요": "아니오", "없음": "아니오"}
CHOICES = {
    "F01": {"중재", "관찰", "설문·면담", "기록 이용", "인체유래물"},
    "F03": {"원자료", "가명처리", "익명"},
    "F04": {"연구자", "기관 데이터팀", "외부 기관"},
    "F05": {"기관 내부", "제3자 제공(통제 환경)", "그 외"},
    "F11": {"서면동의", "동의면제 요청", "없음"},
    "F18": {"없음(폐기)", "연구책임자", "데이터팀·제3자"},
}


@lru_cache(maxsize=1)
def rules() -> dict[str, dict]:
    return {r["id"]: r for r in yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))}


def _row(rule_id: str, result: str, detail: str | None = None, reason: str | None = None, refs=()) -> dict:
    r = rules()[rule_id]
    return {"rule_id": rule_id, "team_id": r.get("team_id"), "requirement": r["requirement"], "result": result,
            "abstain_reason": reason, "result_detail": detail, "type": r["type"], "basis": r["basis"],
            "fact_refs": list(refs)}


def _clean(key: str, v):
    """허용값 밖의 값과 "모름"은 None(모름)으로 두어 연구자에게 다시 묻게 한다."""
    if v is None or (isinstance(v, str) and v.strip() in UNKNOWN_WORDS):
        return None
    if key in LIST_FACTS:
        items = [str(i).strip() for i in (v if isinstance(v, list) else str(v).split(","))]
        if any(i in UNKNOWN_WORDS for i in items):
            return None
        return [i for i in items if i and i not in NONE_WORDS]
    if isinstance(v, str):
        v = v.strip()
    if key in YES_NO:
        return YES_NO_WORDS.get(v)
    if key in CHOICES:
        return v if v in CHOICES[key] else None
    return v


def _facts(state: GraphState) -> dict:
    """확정 사실의 값. 계획서에 없던 사실은 None."""
    return {f["key"]: None if f.get("status") == "not_found" else _clean(f["key"], f.get("value"))
            for f in state.get("confirmed_facts", [])}


def _yes(v) -> bool:
    return v == "예"


def _has(v) -> bool | None:
    """목록형 사실(식별자·민감정보·취약 대상)이 있는지. 모르면 None."""
    if v is None:
        return None
    return bool(v) if isinstance(v, list) else v not in NONE_WORDS


def _norm(name: str) -> str:
    return re.sub(r"\s|\(학\)|학교법인|의료법인|재단법인", "", name or "")


def _lookup(name: str) -> dict | None:
    """data/lists/*.csv에서 기관을 찾는다. 열: 기관명,IRB_등록,IRB_인증,임상시험실시기관,출처,확인일"""
    for path in sorted(LISTS_DIR.glob("*.csv")):
        with path.open(encoding="utf-8-sig") as fp:
            for row in csv.DictReader(fp):
                if _norm(row["기관명"]) == _norm(name):
                    return row
    return None


def institution(state: GraphState) -> dict:
    """⑤ 소속기관명을 공공 명단과 문자열로 대조한다.

    기관명이 비었으면 사실 F12(수행기관)의 첫 기관으로 찾고, 그래도 없으면 연구자에게 묻는다(판단불가 나).
    """
    extra = state.get("extra_inputs", {})
    f12 = _facts(state).get("F12") or []
    name = (extra.get("institution_name") or state.get("institution_name") or (f12[0] if f12 else "")).strip()
    if name in UNAFFILIATED:
        return {"institution": {"name": None, "affiliated": False}}
    if not name:
        return {"institution": {"name": None, "affiliated": None}}
    row = _lookup(name)
    irb = _yes(row["IRB_등록"]) if row else None
    answer = extra.get("irb_exists")
    if answer in ("있음", "없음"):
        irb = answer == "있음"
    return {"institution": {
        "name": name,
        "affiliated": True,
        "irb_exists": irb,
        "irb_certified": _yes(row["IRB_인증"]) if row else None,
        "clinical_trial_site": _yes(row["임상시험실시기관"]) if row else None,
        "source": [row["출처"]] if row else (["연구자 입력"] if answer in ("있음", "없음") else []),
        "checked_at": row["확인일"] if row else None,
    }}


def gates(state: GraphState) -> dict:
    """⑥ 관문을 순서대로 지난다: 범위 → 가명 데이터 → IRB·위탁 → 심의면제 → 동의."""
    f = _facts(state)
    inst = state["institution"]
    rows = []
    # drb: True / "unknown"(동의 여부 모름) / False, exempt: yes / no / unknown
    # pending: 경로를 가르는 전제(범위·임상시험·동의)를 아직 몰라서 일정을 계산하지 않는다
    d = {"scope": "in", "drb": False, "irb": None, "exempt": "no", "pending": False}

    # 1. 범위: 배아·유전자는 범위 밖, 임상시험은 특별법 경로
    if _yes(f.get("F14")):
        rows.append(_row("G1", "충족", "범위 밖 → 사무국 문의", refs=["F14"]))
        return {"judgments": rows, "decision": {**d, "scope": "out"}}
    if f.get("F14") is None:
        d["pending"] = True
        rows.append(_row("G1", "판단불가", "배아·유전자 연구인지 정보 없음", "나", ["F14"]))
    if _yes(f.get("F10")):
        rows.append(_row("T1", "충족", "의약품이면 약사법 제34조, 의료기기면 의료기기법 제10조: 식약처 승인 + 실시기관 심사위원회",
                         refs=["F10"]))
        rows.append(_row("T6", "충족", "공용위원회 심의 대상 아님", refs=["F10"]))
        rows.append(_row("U28", "판단불가", "생명윤리법 기관위원회 심의가 추가로 필요한지는 기관 SOP로 확인", "③"))
        return {"judgments": rows, "decision": {**d, "scope": "trial"}}
    if f.get("F10") is None:
        d["pending"] = True
        rows.append(_row("T1", "판단불가", "의약품·의료기기 임상시험인지 정보 없음", "나", ["F10"]))

    data, kind = f.get("F03"), f.get("F01")
    ids, code, key = _has(f.get("F16")), f.get("F17"), f.get("F18")
    if key in ("연구책임자", "데이터팀·제3자") and code == "아니오":
        code = "예"  # 대응표가 있다면 식별코드도 있다 (같은 질문을 되풀이하지 않게 대응표 쪽을 믿는다)
    viewed = _yes(f.get("F02"))
    biospecimen = _yes(f.get("F09")) or kind == "인체유래물"
    anonymous = ids is False and not viewed and (
        data == "익명" or key == "없음(폐기)" or (code == "아니오" and data != "가명처리"))
    pseudo = not ids and (data == "가명처리" or key == "데이터팀·제3자")
    data_refs = ["F03", "F16", "F17", "F18"]

    if kind is None:
        rows.append(_row("S3", "판단불가", "연구 유형 정보 없음", "나", ["F01"]))
    if biospecimen:
        rows.append(_row("S6", "충족", "인체유래물연구 (심의면제 기준은 시행규칙 제33조)", refs=["F09"]))
    elif f.get("F09") is None and kind not in ("기록 이용", "설문·면담"):  # 기록·설문 연구는 검체를 쓸 수 없어 묻지 않는다
        rows.append(_row("S6", "판단불가", "인체유래물을 쓰는지 정보 없음", "나", ["F09"]))
    if kind == "기록 이용" and not biospecimen:
        if anonymous:
            rows.append(_row("S7", "판단불가", "익명정보면 생명윤리법 심의 대상이 아닐 수 있으나, 더 이상 알아볼 수 없는지는 "
                             "데이터 보유기관(개인정보처리자)이 판단 → 관할 IRB에 심의면제 확인", "②", data_refs))
        elif ids or viewed or data in ("원자료", "가명처리") or key:
            rows.append(_row("S3", "충족", "식별 가능한 정보(가명정보 포함)를 이용하는 인간대상연구", refs=["F01", *data_refs]))

    # 2. 가명 데이터 → DRB 사전 체크. DRB는 가이드라인 권고라 결론은 기관확인이다. 식별자 사실과 따로 판정한다
    if pseudo:
        consent = f.get("F11")
        if consent == "서면동의":
            rows.append(_row("D2", "충족", "동의 기반 처리 → DRB 검토 경로 아님", refs=["F03", "F11"]))
        else:
            if consent is None:
                d["drb"], d["pending"] = "unknown", True
                rows.append(_row("D1", "판단불가", "정보주체 동의 여부 정보 없음 (동의 없이 쓰면 DRB 경로)", "나", ["F11"]))
            else:
                d["drb"] = True
                rows.append(_row("D1", "충족", "동의 없이 이용 → 기관 DRB 검토 경로 (가이드라인 권고, 기관확인)",
                                 refs=["F03", "F11", "F18"]))
            env = f.get("F05")
            if env is None:
                rows.append(_row("R-05", "판단불가", "누가 어디서 분석하는지 정보 없음", "나", ["F05"]))
            else:
                level = {"기관 내부": "저위험", "제3자 제공(통제 환경)": "중위험", "그 외": "고위험"}[env]
                rows.append(_row("R-05", "충족", f"1차 판정 {level} ({env}) · 적정성 검토: {REVIEW[level]} "
                                 "(개인정보위 지침 기준, DRB와의 관계는 기관확인)", refs=["F05"]))
                rows.append(_row("R-06", "판단불가", "기관 지침으로 위험도를 조정할 수 있음", "③"))
            if _yes(f.get("F06")):
                rows.append(_row("D3", "충족", "결합전문기관에서 결합", refs=["F06"]))
            elif f.get("F06") is None:
                rows.append(_row("D3", "판단불가", "다른 기관 데이터와 결합하는지 정보 없음", "나", ["F06"]))
            sensitive = _has(f.get("F07"))
            if sensitive is None:
                rows.append(_row("D4", "판단불가", "민감정보 포함 여부 정보 없음", "나", ["F07"]))
            elif sensitive:
                rows.append(_row("D4", "미충족", "민감정보 포함: 본인 동의 원칙, 보호조치 계획 필요 (기관확인)", refs=["F07"]))
            else:
                rows.append(_row("D4", "충족", "해당 민감정보 없음", refs=["F07"]))
            rows.append(_row("D6", "충족", "DRB와 별도로 IRB 심의 또는 심의면제 확인 필요", refs=["F03"]))
            rows.append(_row("D7", "판단불가", "표준절차는 DRB 승인 → IRB 심의면제 신청, 순서는 기관마다 다름", "③"))

    # 3. IRB·위탁: 어느 위원회에 내는가
    if inst.get("affiliated") is None:
        d["irb"] = "unknown"
        rows.append(_row("J8", "판단불가", "소속 기관 정보 없음", "나"))
    elif not inst["affiliated"]:
        d["irb"] = "public"
        rows.append(_row("J8", "충족", "소속 없는 연구자 → 공용위원회"))
    elif inst.get("irb_exists") is None:
        d["irb"] = "unknown"
        rows.append(_row("J2", "판단불가", "소속기관의 IRB 보유 여부를 명단에서 찾지 못함", "나"))
    elif inst["irb_exists"]:
        d["irb"] = "own"
        rows.append(_row("J2", "충족", f"{inst.get('name')} IRB에 신청", refs=["F12"]))
    else:
        d["irb"] = "contract"
        rows.append(_row("J2", "미충족", "소속 기관위원회 없음", refs=["F12"]))
        rows.append(_row("J6", "충족", "위원회를 두지 않아 인증을 받지 못한 기관 → 위탁 협약 가능 기관"))
        rows.append(_row("J3", "판단불가", "이미 협약했는지, 상대(공용위원회 또는 인증받은 다른 기관 IRB)는 누구인지 사무국 확인", "③"))
    if len(f.get("F12") or []) >= 2:
        rows.append(_row("J10", "판단불가", "공동연구: 한 기관위원회 선정 또는 공용위원회 이용은 수행기관 합의 사항", "③", ["F12"]))

    # 4. 심의면제 후보. 사실로 정해지면 판정하고, 모르면 연구자에게 묻고, 위원회 몫이면 넘긴다
    if biospecimen:
        if ids:
            rows.append(_row("E5", "미충족", "개인정보를 수집·기록함 → 인체유래물연구 심의면제 불가", refs=["F16"]))
        elif ids is None:
            d["exempt"] = "unknown"
            rows.append(_row("E5", "판단불가", "식별자 수집·기록 여부 정보 없음", "나", ["F16"]))
        else:
            d["exempt"] = "unknown"
            rows.append(_row("E5", "판단불가", "인체유래물연구의 심의면제 요건(시행규칙 제33조)은 위원회 확인", "①", ["F09", "F16"]))
    elif kind == "기록 이용":
        d["exempt"] = "unknown"
        if ids:
            d["exempt"] = "no"
            rows.append(_row("E3", "미충족", "식별자를 수집·기록함 → 심의 대상", refs=["F16"]))
        elif ids is None:
            rows.append(_row("E3", "판단불가", "식별자 수집·기록 여부 정보 없음", "나", ["F16"]))
        elif key == "연구책임자":
            rows.append(_row("E3", "판단불가", "연구자가 대응표를 보유해 식별할 수 있음 → 면제 여부는 위원회 판단", "①",
                             ["F16", "F17", "F18"]))
        elif key in ("데이터팀·제3자", "없음(폐기)") or (code == "아니오" and data != "가명처리"):
            d["exempt"] = "yes"
            rows.append(_row("E3", "충족", "기존 자료 이용 · 식별자 미기록 · 연구자 재식별 불가 → 심의면제 신청 후보",
                             refs=["F01", "F16", "F17", "F18"]))
        elif code == "아니오":
            rows.append(_row("E3", "판단불가", "가명처리라면 대응표가 있을 수 있음 → 누가 보관하는지 확인", "나", ["F18"]))
        elif code is None:
            rows.append(_row("E3", "판단불가", "연구용 식별코드 사용 여부 정보 없음", "나", ["F17"]))
        else:
            rows.append(_row("E3", "판단불가", "대응표 보관 주체 정보 없음", "나", ["F18"]))
    elif kind == "설문·면담":
        if ids:
            rows.append(_row("E2", "미충족", "식별자를 수집·기록함 → 심의면제 불가", refs=["F16"]))
        elif ids is None:
            d["exempt"] = "unknown"
            rows.append(_row("E2", "판단불가", "식별자 수집·기록 여부 정보 없음", "나", ["F16"]))
        elif _has(f.get("F07")):
            rows.append(_row("E2", "미충족", "민감정보(개인정보 보호법 제23조)를 수집함 → 심의면제 불가", refs=["F07"]))
        else:
            vulnerable = _has(f.get("F08"))
            if vulnerable:
                rows.append(_row("E4", "미충족", "취약한 대상 포함 → 심의면제 불가", refs=["F08"]))
            elif vulnerable is None:
                d["exempt"] = "unknown"
                rows.append(_row("E4", "판단불가", "취약한 대상 포함 여부 정보 없음", "나", ["F08"]))
            else:
                d["exempt"] = "unknown"
                rows.append(_row("E2", "판단불가", "대상자가 특정되지 않고 건강 등 민감정보를 수집·기록하지 않는지는 위원회 확인",
                                 "①", ["F01", "F16", "F07"]))
    elif kind is None:
        d["exempt"] = "unknown"
    if d["exempt"] == "yes":
        rows.append(_row("R-09", "판단불가", "면제 여부는 관할 위원회가 확인", "①"))
        rows.append(_row("R-10", "판단불가", "위험이 미미한지는 위원회가 판단", "②"))

    # 5. 동의. 가명정보 특례로 쓰는 경우 동의면제 판단이 필요한지는 가이드라인 안에서도 엇갈린다 (prep 이슈 #9)
    if f.get("F11") == "동의면제 요청":
        detail = ("가명정보 특례로 동의 없이 쓰는 경우 생명윤리법 동의면제 판단이 필요한지는 가이드라인 안에서도 엇갈림 → 위원회 확인"
                  if d["drb"] else "서면동의 면제는 기관위원회 승인 사항 (위험이 극히 낮은지 등)")
        rows.append(_row("C3", "판단불가", detail, "①", ["F11"]))
    return {"judgments": rows, "decision": d}


def _route(label: str, committees: list[str], trace: list[str], fast: bool = False) -> dict:
    return {"route": label, "committees": committees, "order": list(range(1, len(committees) + 1)),
            "fast_track": fast, "trace": trace}


def route(state: GraphState) -> dict:
    """⑦ 판정 결과로 경로와 신청 순서를 정하고, 경로를 정한 규칙을 trace로 남긴다."""
    d, rows = state["decision"], state["judgments"]
    if d["scope"] == "out":
        return {"route": _route("범위 밖", ["사무국 문의"], ["G1"])}
    if d["scope"] == "trial":
        return {"route": _route("임상시험", ["식약처 임상시험계획 승인", "임상시험실시기관 심사위원회"], ["T1", "T6"])}
    drb = {True: ["기관 DRB (가이드라인 권고 · 기관확인)"], "unknown": ["기관 DRB (동의 없이 쓰는 경우 · 확인 필요)"]}.get(d["drb"], [])
    drb_rules = ["D1", "D6"] if d["drb"] else []
    if d["irb"] == "unknown" or d["drb"] == "unknown":
        who = [r["rule_id"] for r in rows if r["rule_id"] in ("J2", "J8")]
        irb = IRB_NAME.get(d["irb"], "소속 기관·IRB 보유 여부 확인 필요")
        return {"route": _route("미정", [*drb, irb], [*drb_rules, *who])}
    irb = IRB_NAME[d["irb"]] + EXEMPT_SUFFIX[d["exempt"]]
    exempt = [r["rule_id"] for r in rows if r["rule_id"] in ("E2", "E3", "E5")]
    trace = [*drb_rules, *IRB_RULES[d["irb"]], *exempt]
    if d["drb"]:
        return {"route": _route("A", [*drb, irb], trace, fast=d["exempt"] == "yes")}
    return {"route": _route("C" if d["irb"] == "own" else "B", [irb], trace)}


def docs_schedule(state: GraphState) -> dict:
    """⑧ 경로별 서류와, 목표 개시일에서 거꾸로 계산한 일정. 공개된 수치만 쓴다."""
    d, route_ = state["decision"], state["route"]
    fired = {r["rule_id"] for r in state["judgments"] if r["result"] != "미충족"}
    docs = []
    if route_["route"] == "임상시험":
        docs.append({"doc": "임상시험계획 승인 신청서 (식약처)", "level": "법정", "basis": "T1"})
    if d["drb"]:
        docs.append({"doc": "DRB 심의 신청서", "level": "기관", "source": "기관 DRB 서식 (기관확인)"})
    if route_["route"] in ("A", "B", "C"):
        attach = " (DRB 승인서 첨부)" if d["drb"] is True else ""
        doc = {"yes": f"심의면제 신청서{attach}", "no": "심의 신청서 · 연구계획서",
               "unknown": "심의 또는 심의면제 신청서 (위원회 확인 후 결정)"}[d["exempt"]]
        docs.append({"doc": doc, "level": "기관", "source": "관할 IRB 서식"})
    if d["irb"] == "contract":
        docs.append({"doc": "기관생명윤리위원회 업무위탁 협약서 (시행규칙 별지 제3호서식)", "level": "법정", "basis": "J6"})
    if "D3" in fired and _yes(_facts(state).get("F06")):
        docs.append({"doc": "가명정보 결합 신청서 (결합전문기관)", "level": "법정", "basis": "D3"})
    if "C3" in fired:
        docs.append({"doc": "서면동의 면제 사유서", "level": "기관", "source": "관할 IRB 서식", "basis": "C3"})
    return {"documents": docs, "schedule": _schedule(state)}


def _none(default: int, *why: str) -> dict:
    return {"scenarios": [{"revisions": n} for n in (0, 1, 2)], "default": default, "missing": list(why)}


def _schedule(state: GraphState) -> dict:
    d, route_ = state["decision"], state["route"]["route"]
    needs_fix = any(r["result"] == "미충족" and rules()[r["rule_id"]].get("checkpoint") for r in state["judgments"])
    default = 1 if needs_fix else 0
    target = state.get("target_start_date")
    if route_ == "임상시험":
        return _none(default, "식약처 승인·실시기관 심사위원회 일정: 공개 수치 없음")
    if route_ == "범위 밖":
        return _none(default, "범위 밖이라 일정을 계산하지 않음")
    if route_ not in ("A", "B", "C") or not target:
        return _none(default, "경로가 정해지지 않아 일정을 계산하지 않음")
    if d["pending"]:
        return _none(default, "임상시험·범위·동의 여부를 확인하기 전이라 일정을 계산하지 않음")
    target_day = date.fromisoformat(target)
    today = date.fromisoformat(state["today"]) if state.get("today") else date.today()
    if d["drb"] is True and d["exempt"] == "yes":
        latest = target_day - timedelta(days=8)  # 확인서가 개시일 전날까지 오도록 (공용위원회 역산과 같은 기준)
        first = ({"revisions": 0, "submit_by": latest.isoformat(), "step": "IRB 심의면제 신청 (DRB 승인서 첨부)"}
                 if latest >= today else {"revisions": 0, "step": "마감 경과"})
        return {"scenarios": [first, {"revisions": 1}, {"revisions": 2}], "default": default,
                "missing": ["DRB 심의 소요: 공개 수치 없음 (기관확인)",
                            "심의면제 확인서: DRB 승인서가 있으면 7일 이내 발급 가능 (가이드라인 2025.12 표준절차, 기관마다 다름)",
                            "보완 1·2회: 공개 수치 없음"]}
    if d["irb"] == "contract":
        return _none(default, "위탁 협약 소요: 공개 수치 없음 → 계산 불가 (협약을 마치면 상대 위원회 일정을 따름)")
    if d["irb"] == "public" and d["exempt"] == "yes":
        return _none(default, "공용위원회 심의면제: 마감 없이 수시 접수")
    if d["irb"] == "public" and PUBLIC_SCHEDULE.exists():
        return {"scenarios": _public_irb(target_day, today), "default": default,
                "missing": ["공용위원회 정규 회의만 사용 (특별위원회 관할 비공개)", "결과 통보: 회의일로부터 7일 이내 (SOP 제36조②)"]}
    return _none(default, "관할 위원회 회의일·접수 마감: 공개 일정 데이터 없음")


def _public_irb(target: date, today: date) -> list[dict]:
    """공용위원회 역산: 결과 통보 최대(회의+7일)가 개시일 전날까지 오는 가장 늦은 정규 회의에서 출발해,
    보완 1회마다 한 사이클(결과 통보 뒤 다음 회의 접수 마감에 맞출 수 있는 앞선 회의, 14일 이상 간격)씩 당긴다."""
    with PUBLIC_SCHEDULE.open(encoding="utf-8-sig") as fp:
        meetings = sorted((date.fromisoformat(r["회의일"]), r["접수마감"]) for r in csv.DictReader(fp) if r["구분"] == "정규")
    limit = target - timedelta(days=8)  # 회의+7일 < 개시일 (prep 케이스 1: 통보가 개시일 당일이면 탈락)
    if not meetings or limit > meetings[-1][0]:
        return [{"revisions": n, "step": "공개된 회의 일정(2026) 밖이라 계산 불가"} for n in (0, 1, 2)]
    scenarios = []
    for n in (0, 1, 2):
        pick = next(((m, due) for m, due in reversed(meetings) if m <= limit), None)
        if pick is None:
            scenarios.append({"revisions": n, "step": "해당 회의 없음"})
            continue
        if date.fromisoformat(pick[1]) < today:
            scenarios.append({"revisions": n, "step": f"마감 경과 ({pick[1]})"})
        else:
            scenarios.append({"revisions": n, "submit_by": pick[1], "step": f"공용위원회 접수 마감 ({pick[0].isoformat()} 회의)"})
        limit = pick[0] - timedelta(days=14)
    return scenarios
