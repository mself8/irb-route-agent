"""⑤~⑧ 규칙 엔진. 판정은 이 파일에서만 한다. LLM을 쓰지 않는다.

판정 조건은 이 파일, 요건 문구·근거·원문은 data/rules/rules.yaml이 정본이다.
순서는 prep 판정규칙표의 결정 순서를 따른다: 범위(G·T·S) → 가명 데이터(D) → IRB·위탁(J) → 심의면제(E) → 동의(C).
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
UNAFFILIATED = {"", "없음", "소속 없음", "개인"}
IRB_NAME = {"own": "소속 기관 IRB", "public": "공용기관생명윤리위원회", "contract": "공용기관생명윤리위원회 (위탁 협약 후)"}
IRB_RULES = {"own": ["J2"], "public": ["J8"], "contract": ["J2", "J6"]}
# 가명정보 처리 가이드라인(2026.03.) 인쇄 48쪽 위험도별 적정성 검토 방식
REVIEW = {"저위험": "담당자 검토", "중위험": "내부 심의(2인 이상)", "고위험": "적정성 검토위원회(3인 이상)"}


def _data_state(data, ids, code, key) -> str:
    """팀 문서 「식별코드 사실 항목 보완」의 네 가지 데이터 상태. 식별자·식별코드·대응표가 계획서의 데이터 형태보다 우선한다.

    identified 식별자가 남음 / coded 코드화, 연구자가 대응표 보유 / pseudo 가명정보(대응표 분리 보관)
    anonymous 코드·대응표 없음 / unknown 아직 모름
    """
    if ids:
        return "identified"
    if ids is False and _yes(code) and key == "데이터팀·제3자":
        return "pseudo"
    if ids is False and _yes(code) and key == "연구책임자":
        return "coded"
    if data == "익명" or (ids is False and (_no(code) or key == "없음(폐기)")):
        return "anonymous"
    if data == "가명처리":
        return "pseudo"
    return "unknown"


@lru_cache(maxsize=1)
def rules() -> dict[str, dict]:
    return {r["id"]: r for r in yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))}


def _row(rule_id: str, result: str, detail: str | None = None, reason: str | None = None, refs=()) -> dict:
    r = rules()[rule_id]
    return {"rule_id": rule_id, "team_id": r.get("team_id"), "requirement": r["requirement"], "result": result,
            "abstain_reason": reason, "result_detail": detail, "type": r["type"], "basis": r["basis"],
            "fact_refs": list(refs)}


def _facts(state: GraphState) -> dict:
    """확정 사실의 값. 계획서에 없던 사실은 None."""
    return {f["key"]: None if f.get("status") == "not_found" else f.get("value")
            for f in state.get("confirmed_facts", [])}


def _yes(v) -> bool:
    return v in ("예", "있음")


def _no(v) -> bool:
    return v in ("아니오", "없음")


def _has(v) -> bool | None:
    """목록형 사실(민감정보·취약 대상)이 있는지. 모르면 None."""
    if v is None:
        return None
    return v not in ([], "", "없음", "아니오")


def _norm(name: str) -> str:
    return re.sub(r"\s|\(학\)|학교법인|의료법인|재단법인", "", name or "")


def _lookup(name: str) -> dict | None:
    """data/lists/*.csv에서 기관을 찾는다. 열: 기관명,IRB_등록,IRB_인증,임상시험실시기관,출처,확인일"""
    for path in sorted(LISTS_DIR.glob("*.csv")):
        with path.open(encoding="utf-8") as fp:
            for row in csv.DictReader(fp):
                if _norm(row["기관명"]) == _norm(name):
                    return row
    return None


def institution(state: GraphState) -> dict:
    """⑤ 소속기관명을 공공 명단과 문자열로 대조한다. 명단에 없으면 연구자에게 묻는다(판단불가 나)."""
    name = (state.get("institution_name") or "").strip()
    if name in UNAFFILIATED:
        return {"institution": {"name": name or None, "affiliated": False}}
    row = _lookup(name)
    irb = _yes(row["IRB_등록"]) if row else None
    answer = state.get("extra_inputs", {}).get("irb_exists")
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
    d = {"scope": "in", "drb": False, "irb": None, "exempt": False}

    # 1. 범위: 배아·유전자는 범위 밖, 임상시험은 특별법 경로, 식별 불가능한 자료만 쓰면 비대상
    if _yes(f.get("F14")):
        rows.append(_row("G1", "충족", "범위 밖 → 사무국 문의", refs=["F14"]))
        return {"judgments": rows, "decision": {**d, "scope": "out"}}
    if _yes(f.get("F10")):
        rows.append(_row("T1", "충족", "식약처 임상시험계획 승인 + 실시기관 심사위원회", refs=["F10"]))
        rows.append(_row("T6", "충족", "공용위원회 심의 대상 아님", refs=["F10"]))
        return {"judgments": rows, "decision": {**d, "scope": "trial"}}
    data, kind = f.get("F03"), f.get("F01")
    ids, code, key = _has(f.get("F16")), f.get("F17"), f.get("F18")
    state_ = _data_state(data, ids, code, key)
    if state_ == "anonymous":
        rows.append(_row("S7", "판단불가", "익명정보면 생명윤리법 심의 대상이 아닐 수 있으나, 더 이상 알아볼 수 없는지는 위원회 판단"
                         " → 관할 IRB에 심의면제 확인", "②", ["F03", "F16", "F17", "F18"]))
    elif kind == "기록 이용" and state_ in ("identified", "coded", "pseudo"):
        rows.append(_row("S3", "충족", "식별 가능한 정보(가명정보 포함)를 이용하는 인간대상연구", refs=["F01", "F03"]))

    # 2. 가명 데이터 → DRB 사전 체크. DRB는 가이드라인 권고라 결론은 기관확인이다
    if state_ == "pseudo":
        if f.get("F11") == "서면동의":
            rows.append(_row("D2", "충족", "동의 기반 처리 → DRB 검토 경로 아님", refs=["F03", "F11"]))
        else:
            d["drb"] = True
            rows.append(_row("D1", "충족", "기관 DRB 검토 경로 (가이드라인 권고, 기관확인)", refs=["F03"]))
            env = f.get("F05")
            if env is None:
                rows.append(_row("R-05", "판단불가", "데이터 이용 환경 정보 없음", "나", ["F05"]))
            else:
                level = {"기관 내부": "저위험", "제3자 제공(통제 환경)": "중위험"}.get(env, "고위험")
                rows.append(_row("R-05", "충족", f"1차 판정 {level} ({env}) · 적정성 검토: {REVIEW[level]}", refs=["F05"]))
                rows.append(_row("R-06", "판단불가", "기관 지침으로 위험도를 조정할 수 있음", "③"))
            if _yes(f.get("F06")):
                rows.append(_row("D3", "충족", "결합전문기관에서 결합", refs=["F06"]))
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
    if not inst.get("affiliated", True):
        d["irb"] = "public"
        rows.append(_row("J8", "충족", "소속 없는 연구자 → 공용위원회", refs=["F12"]))
    elif inst.get("irb_exists") is None:
        d["irb"] = "unknown"
        rows.append(_row("J2", "판단불가", "소속기관의 IRB 보유 여부를 명단에서 찾지 못함", "나"))
    elif inst["irb_exists"]:
        d["irb"] = "own"
        rows.append(_row("J2", "충족", f"{inst.get('name')} IRB에 신청", refs=["F12"]))
    else:
        d["irb"] = "contract"
        rows.append(_row("J2", "미충족", "소속 기관위원회 없음", refs=["F12"]))
        rows.append(_row("J6", "판단불가", "위원회가 없으면 인증 미취득 기관으로 보아 위탁 협약 가능 (해석 보류, 사무국 확인)", "③"))
    if len(f.get("F12") or []) >= 2:
        rows.append(_row("J10", "판단불가", "공동연구: 한 기관위원회 선정 또는 공용위원회 이용은 수행기관 합의 사항", "③", ["F12"]))

    # 4. 심의면제 후보. 데이터 상태로 가르고, 모르는 것은 연구자에게 먼저 묻는다(판단불가 나). 확정은 관할 위원회
    if kind == "기록 이용":
        if ids:
            rows.append(_row("E3", "미충족", "식별자를 수집·기록함 → 심의 대상", refs=["F16"]))
        elif ids is None:
            rows.append(_row("E3", "판단불가", "식별자 수집·기록 여부 정보 없음", "나", ["F16"]))
        elif code is None and state_ != "anonymous":
            rows.append(_row("E3", "판단불가", "연구용 식별코드 사용 여부 정보 없음", "나", ["F17"]))
        elif _yes(code) and key is None:
            rows.append(_row("E3", "판단불가", "대응표 보관 주체 정보 없음", "나", ["F18"]))
        elif state_ == "coded":
            rows.append(_row("E3", "판단불가", "연구자가 대응표를 보유해 식별할 수 있음 → 면제 여부는 위원회 판단", "①",
                             ["F16", "F17", "F18"]))
        else:  # 대응표를 연구자가 볼 수 없거나(가명), 코드·대응표가 없음(익명)
            d["exempt"] = True
            rows.append(_row("E3", "충족", "기존 자료 이용 · 식별자 없음 · 연구자 재식별 불가 → 심의면제 신청 후보",
                             refs=["F01", "F16", "F17", "F18"]))
    elif kind == "설문·면담" and ids is False and _has(f.get("F07")) is False:
        vulnerable = _has(f.get("F08"))
        if vulnerable is None:
            rows.append(_row("E4", "판단불가", "취약한 대상 포함 여부 정보 없음", "나", ["F08"]))
        elif vulnerable:
            rows.append(_row("E4", "미충족", "취약한 대상 포함 → 심의면제 불가", refs=["F08"]))
        else:
            d["exempt"] = True
            rows.append(_row("E2", "충족", "대상자 비특정 · 민감정보 미수집 → 심의면제 신청 후보", refs=["F01", "F16", "F07"]))
    if d["exempt"]:
        rows.append(_row("R-09", "판단불가", "면제 여부는 관할 위원회가 확인", "①"))
        rows.append(_row("R-10", "판단불가", "위험이 미미한지는 위원회가 판단", "②"))

    # 5. 동의
    if f.get("F11") == "동의면제 요청":
        rows.append(_row("C3", "판단불가", "서면동의 면제는 기관위원회 승인 사항 (위험이 극히 낮은지 등)", "①", ["F11"]))
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
    if d["irb"] == "unknown":
        return {"route": _route("미정", ["소속기관 IRB 보유 여부 확인 필요"], ["J2"])}
    irb = IRB_NAME[d["irb"]] + (" · 심의면제 신청 후보" if d["exempt"] else " · 심의")
    exempt = [r["rule_id"] for r in rows if r["rule_id"] in ("E2", "E3") and r["result"] == "충족"]
    if d["drb"]:
        committees = ["기관 DRB (가이드라인 권고 · 기관확인)", irb]
        return {"route": _route("A", committees, ["D1", "D6", *IRB_RULES[d["irb"]], *exempt], fast=d["exempt"])}
    return {"route": _route("C" if d["irb"] == "own" else "B", [irb], [*IRB_RULES[d["irb"]], *exempt])}


def docs_schedule(state: GraphState) -> dict:
    """⑧ 경로별 서류와, 목표 개시일에서 거꾸로 계산한 일정. 공개된 수치만 쓴다."""
    d, route_ = state["decision"], state["route"]
    fired = {r["rule_id"] for r in state["judgments"] if r["result"] != "미충족"}
    docs = []
    if route_["route"] == "임상시험":
        docs.append({"doc": "임상시험계획 승인 신청서 (식약처)", "level": "법정", "basis": "T1"})
    if "D1" in fired:
        docs.append({"doc": "DRB 심의 신청서", "level": "기관", "source": "기관 DRB 서식 (기관확인)"})
    if d["exempt"]:
        attach = " (DRB 승인서 첨부)" if d["drb"] else ""
        docs.append({"doc": f"심의면제 신청서{attach}", "level": "기관", "source": "관할 IRB 서식"})
    elif route_["route"] in ("A", "B", "C"):
        docs.append({"doc": "심의 신청서 · 연구계획서", "level": "기관", "source": "관할 IRB 서식"})
    if d["irb"] == "contract":
        docs.append({"doc": "기관생명윤리위원회 업무위탁 협약서 (시행규칙 별지 제3호서식)", "level": "법정", "basis": "J6"})
    if "D3" in fired:
        docs.append({"doc": "가명정보 결합 신청서 (결합전문기관)", "level": "법정", "basis": "D3"})
    if "C3" in fired:
        docs.append({"doc": "서면동의 면제 사유서", "level": "기관", "source": "관할 IRB 서식", "basis": "C3"})
    return {"documents": docs, "schedule": _schedule(state)}


def _schedule(state: GraphState) -> dict:
    d = state["decision"]
    needs_fix = any(r["result"] == "미충족" and rules()[r["rule_id"]].get("checkpoint") for r in state["judgments"])
    default = 1 if needs_fix else 0
    target = state.get("target_start_date")
    if d["drb"] and d["exempt"] and target:
        latest = (date.fromisoformat(target) - timedelta(days=7)).isoformat()
        return {"scenarios": [{"revisions": 0, "submit_by": latest}, {"revisions": 1}, {"revisions": 2}],
                "default": default,
                "missing": ["DRB 심의 소요: 공개 수치 없음 (기관확인)",
                            "심의면제 확인서: DRB 승인서가 있으면 7일 이내 발급 가능 (가이드라인 2025.12 표준절차, 기관마다 다름)",
                            "보완 1·2회: 공개 수치 없음"]}
    return {"scenarios": [{"revisions": n} for n in (0, 1, 2)], "default": default,
            "missing": ["관할 위원회 회의일·접수 마감: 공개 일정 데이터 없음"]}
