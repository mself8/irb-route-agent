"""데모 샘플 2건(data/samples/*.json)을 만든다. result는 규칙 엔진을 실제로 돌려서 채운다.

실행: python scripts/make_samples.py   (규칙이나 사실 목록이 바뀌면 다시 돌린다)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.nodes import judge, write  # noqa: E402
from agent.state import FACT_LABELS  # noqa: E402

NOTE = "데모용 가상 계획서다. result는 scripts/make_samples.py가 규칙 엔진을 돌려 만든 값이다."
INSTITUTION = "가상대학교병원"  # data/lists/demo_institutions.csv에 있는 가상 기관
TARGET = "2026-12-01"
PII = [("홍길동", "[이름]"), ("010-1234-5678", "[전화번호]"), ("hong@example.ac.kr", "[이메일]")]
HEAD = ("연구 제목: 대장내시경 용종 크기와 재발의 관련성 후향적 관찰연구\n"
        "연구책임자: 홍길동 (소화기내과, 010-1234-5678, hong@example.ac.kr)\n"
        "수행기관: 가상대학교병원\n")
TAIL = ("대상자 수: 약 300명\n"
        "연구 기간: 2026년 12월 1일부터 2027년 11월 30일까지\n"
        "동의: 후향적 기록 연구로 동의면제를 요청한다.")
# 사실 키 → (값, 가린 계획서의 원문 구간). 구간이 None이면 계획서에 없는 사실이다.
COMMON = {
    "F01": ("기록 이용", "후향적 관찰연구"),
    "F04": (None, None), "F05": (None, None), "F06": (None, None), "F08": (None, None), "F09": (None, None),
    "F07": ([], "나이, 성별, 용종 크기, 재발 여부"),
    "F10": ("아니오", "후향적 관찰연구"),
    "F11": ("동의면제 요청", "동의면제를 요청한다"),
    "F12": (["가상대학교병원"], "수행기관: 가상대학교병원"),
    "F13": ("2026-12-01 ~ 2027-11-30", "2026년 12월 1일부터 2027년 11월 30일까지"),
    "F14": ("아니오", "후향적 관찰연구"),
    "F15": (300, "약 300명"),
}
SAMPLES = {
    "sample1_crf": {
        "title": "샘플 1 · 진료기록 직접 열람 (CRF)",
        "method": "연구 방법: 연구자가 2020년 1월부터 2024년 12월까지 대장내시경을 받은 환자의 진료기록을 직접 열람하여 "
                  "환자 등록번호, 나이, 성별, 용종 크기, 재발 여부를 증례기록서(CRF)에 옮겨 적는다.\n",
        "facts": {"F02": ("예", "진료기록을 직접 열람하여"),
                  "F03": ("원자료", "진료기록을 직접 열람하여"),
                  "F16": ("예", "환자 등록번호")},
    },
    "sample2_pseudo": {
        "title": "샘플 2 · 가명처리 데이터셋 제공",
        "method": "연구 방법: 가상대학교병원 데이터팀이 2020년 1월부터 2024년 12월까지 대장내시경을 받은 환자의 진료기록을 "
                  "가명처리한 데이터셋(나이, 성별, 용종 크기, 재발 여부)을 제공받아 분석한다.\n",
        "facts": {"F02": ("아니오", "가명처리한 데이터셋"),
                  "F03": ("가명처리", "가명처리한 데이터셋"),
                  "F04": ("기관 데이터팀", "가상대학교병원 데이터팀이"),
                  "F16": ("아니오", "가명처리한 데이터셋(나이, 성별, 용종 크기, 재발 여부)")},
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


def run_engine(plan: str, facts: list[dict]) -> dict:
    state = {"raw_text": plan, "institution_name": INSTITUTION, "target_start_date": TARGET,
             "confirmed_facts": facts, "extra_inputs": {}}
    for step in (judge.institution, judge.gates, judge.route, judge.docs_schedule, write.abstain, write.report):
        state = {**state, **step(state)}
    return {k: state[k] for k in ("institution", "judgments", "route", "documents", "schedule", "abstain", "report")}


for sample_id, spec in SAMPLES.items():
    plan = HEAD + spec["method"] + TAIL
    masked = plan
    for original, token in PII:
        masked = masked.replace(original, token)
    facts = build_facts(masked, {**COMMON, **spec["facts"]})
    out = {"id": sample_id, "title": spec["title"], "_note": NOTE, "institution_name": INSTITUTION, "plan_text": plan,
           "pending": {"masked_text": masked,
                       "mask_log": [{"type": "이름", "count": 1}, {"type": "전화번호", "count": 1}, {"type": "이메일", "count": 1}],
                       "facts": facts},
           "result": run_engine(plan, facts)}
    path = ROOT / "data" / "samples" / f"{sample_id}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = out["result"]
    print(sample_id, "경로", r["route"]["route"], r["route"]["committees"], "| 판정", len(r["judgments"]),
          "| 판단불가", [(a["rule_id"], a["kind"]) for a in r["abstain"]])
