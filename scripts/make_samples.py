"""데모 샘플 2건(data/samples/*.json)을 만든다. result는 규칙 엔진을 실제로 돌려서 채운다.

실행: python scripts/make_samples.py   (규칙이나 사실 목록이 바뀌면 다시 돌린다)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("LLM", "0")  # 샘플은 모델 없이 틀 문장으로 만든다 (재현 가능하게)

from agent.nodes import judge, write  # noqa: E402
from agent.state import FACT_LABELS  # noqa: E402

NOTE = "데모용 가상 계획서다. result는 scripts/make_samples.py가 규칙 엔진을 돌려 만든 값이다."
INSTITUTION = "가상대학교병원"  # data/lists/demo_institutions.csv에 있는 가상 기관
TARGET = "2026-12-01"
PII = [("홍길동", "[이름]"), ("010-1234-5678", "[전화번호]"), ("hong@example.ac.kr", "[이메일]")]
HEAD = ("연구 제목: 대장내시경 용종 크기와 재발의 관련성 후향적 의무기록 연구\n"
        "연구책임자: 홍길동 (소화기내과, 010-1234-5678, hong@example.ac.kr)\n"
        "수행기관: 가상대학교병원\n")
TAIL = ("대상자 수: 약 300명\n"
        "연구 기간: 2026년 12월 1일부터 2027년 11월 30일까지\n"
        "동의: 후향적 기록 연구로 동의면제를 요청한다.")
# 사실 키 → (값, 가린 계획서의 원문 구간). 구간이 None이면 계획서에 없는 사실이다.
COMMON = {
    "F01": ("기록 이용", "후향적 의무기록 연구"),
    "F04": (None, None), "F05": (None, None), "F06": (None, None), "F08": (None, None), "F09": (None, None),
    "F17": (None, None), "F18": (None, None),
    "F07": ([], "나이, 성별, 용종 크기, 재발 여부"),
    "F10": ("아니오", "후향적 의무기록 연구"),
    "F11": ("동의면제 요청", "동의면제를 요청한다"),
    "F12": (["가상대학교병원"], "수행기관: 가상대학교병원"),
    "F13": ("2026-12-01 ~ 2027-11-30", "2026년 12월 1일부터 2027년 11월 30일까지"),
    "F14": ("아니오", "후향적 의무기록 연구"),
    "F15": (300, "약 300명"),
}
SAMPLES = {
    "sample1_crf": {
        "title": "샘플 1 · 진료기록 직접 열람 (CRF)",
        "method": "연구 방법: 연구자가 2020년 1월부터 2024년 12월까지 대장내시경을 받은 환자의 진료기록을 직접 열람하여 "
                  "환자 등록번호, 나이, 성별, 용종 크기, 재발 여부를 증례기록서(CRF)에 옮겨 적는다.\n",
        "facts": {"F02": ("예", "진료기록을 직접 열람하여"),
                  "F03": ("원자료", "진료기록을 직접 열람하여"),
                  "F16": (["등록번호"], "환자 등록번호")},
    },
    "sample2_pseudo": {
        "title": "샘플 2 · 가명처리 데이터셋 제공",
        "method": "연구 방법: 가상대학교병원 데이터팀이 2020년 1월부터 2024년 12월까지 대장내시경을 받은 환자의 진료기록을 "
                  "가명처리한 데이터셋(나이, 성별, 용종 크기, 재발 여부)을 제공받아 분석한다. "
                  "대상자는 연구번호로 대체하며, 대응표는 데이터팀이 별도 보관하고 연구자는 접근하지 않는다. "
                  "다른 기관 데이터와 결합하거나 외부로 반출하지 않는다.\n",
        "facts": {"F02": ("아니오", "가명처리한 데이터셋"),
                  "F03": ("가명처리", "가명처리한 데이터셋"),
                  "F04": ("기관 데이터팀", "가상대학교병원 데이터팀이"),
                  "F06": ("아니오", "다른 기관 데이터와 결합하거나 외부로 반출하지 않는다"),
                  "F16": ([], "가명처리한 데이터셋(나이, 성별, 용종 크기, 재발 여부)"),
                  "F17": ("예", "대상자는 연구번호로 대체하며"),
                  "F18": ("데이터팀·제3자", "대응표는 데이터팀이 별도 보관하고 연구자는 접근하지 않는다")},
    },
    # 샘플 2에서 식별 관리 문장을 뺀 판본: ④에서 연구용 번호·대응표를 채우면 제출 전 보완(R-11·R-12) 경고가 뜬다 (팀 문서 7장 데모)
    "sample3_nokey": {
        "title": "샘플 3 · 가명처리 데이터셋, 대응표 서술 없음",
        "method": "연구 방법: 가상대학교병원 데이터팀이 2020년 1월부터 2024년 12월까지 대장내시경을 받은 환자의 진료기록을 "
                  "가명처리한 데이터셋(나이, 성별, 용종 크기, 재발 여부)을 제공받아 분석한다. "
                  "다른 기관 데이터와 결합하거나 외부로 반출하지 않는다.\n",
        "facts": {"F02": ("아니오", "가명처리한 데이터셋"),
                  "F03": ("가명처리", "가명처리한 데이터셋"),
                  "F04": ("기관 데이터팀", "가상대학교병원 데이터팀이"),
                  "F06": ("아니오", "다른 기관 데이터와 결합하거나 외부로 반출하지 않는다"),
                  "F16": ([], "가명처리한 데이터셋(나이, 성별, 용종 크기, 재발 여부)")},
    },
    # 샘플 3에서 S3의 "보완 문구 넣고 다시"를 누른 결과와 글자까지 같은 계획서: 예시 모드에서도 경고가 사라지는 장면을 보인다
    "sample3b_fixed": {
        "title": "샘플 3 · 보완 문구를 넣은 뒤",
        "method": "연구 방법: 가상대학교병원 데이터팀이 2020년 1월부터 2024년 12월까지 대장내시경을 받은 환자의 진료기록을 "
                  "가명처리한 데이터셋(나이, 성별, 용종 크기, 재발 여부)을 제공받아 분석한다. "
                  "다른 기관 데이터와 결합하거나 외부로 반출하지 않는다.\n",
        "extra": write.KEY_TEXT["데이터팀·제3자"],
        "facts": {"F02": ("아니오", "가명처리한 데이터셋"),
                  "F03": ("가명처리", "가명처리한 데이터셋"),
                  "F04": ("기관 데이터팀", "가상대학교병원 데이터팀이"),
                  "F06": ("아니오", "다른 기관 데이터와 결합하거나 외부로 반출하지 않는다"),
                  "F16": ([], "가명처리한 데이터셋(나이, 성별, 용종 크기, 재발 여부)"),
                  "F17": ("예", "연구번호와 실제 대상자를 연결하는 대응표"),
                  "F18": ("데이터팀·제3자", "[데이터팀]이 별도로 분리 보관하며, 연구자는 대응표에 접근하지 않는다")},
    },
}


def build_facts(masked: str, table: dict) -> list[dict]:
    facts = []
    for key, label in FACT_LABELS.items():
        value, span = table[key]
        fact = {"key": key, "label": label, "value": value, "span": span, "span_start": None, "span_end": None,
                "status": "found" if span else "not_found", "cross_check": "agree" if span else None}
        if span:
            start = masked.find(span)
            assert start >= 0, (key, span)
            fact["span_start"], fact["span_end"] = start, start + len(span)
        facts.append(fact)
    return facts


def run_engine(plan: str, masked: str, facts: list[dict]) -> dict:
    state = {"raw_text": plan, "masked_text": masked, "institution_name": INSTITUTION, "target_start_date": TARGET,
             "facts": facts, "confirmed_facts": facts, "extra_inputs": {}}
    for step in (judge.institution, judge.gates, judge.route, judge.docs_schedule, write.abstain, write.report):
        state = {**state, **step(state)}
    return {k: state[k] for k in ("institution", "judgments", "route", "documents", "schedule", "abstain", "report",
                                  "suggestions", "highlights", "masked_text")}


for sample_id, spec in SAMPLES.items():
    plan = HEAD + spec["method"] + TAIL + (f"\n{spec['extra']}" if spec.get("extra") else "")
    masked = plan
    for original, token in PII:
        masked = masked.replace(original, token)
    facts = build_facts(masked, {**COMMON, **spec["facts"]})
    out = {"id": sample_id, "title": spec["title"], "_note": NOTE, "institution_name": INSTITUTION, "plan_text": plan,
           "pending": {"masked_text": masked,
                       "mask_log": [{"type": "이름", "count": 1}, {"type": "전화번호", "count": 1}, {"type": "이메일", "count": 1}],
                       "facts": facts},
           "result": run_engine(plan, masked, facts)}
    path = ROOT / "data" / "samples" / f"{sample_id}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = out["result"]
    print(sample_id, "경로", r["route"]["route"], r["route"]["committees"], "| 판정", len(r["judgments"]),
          "| 판단불가", [(a["rule_id"], a["kind"]) for a in r["abstain"]],
          "| 보완", [(s["rule_id"], s["level"]) for s in r["suggestions"]], "| 표시", [h["span"] for h in r["highlights"]])
