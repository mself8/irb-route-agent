"""정답 독립 확인: 합성 20 + 함정 20을 무작위로 뽑아, 만든 쪽이 아닌 에이전트가 원문만 보고 단 정답과 비교한다.

  python eval/independent.py blind     # → eval/results/independent_blind.json (정답을 뺀 문제지)
  python eval/independent.py score     # independent_labels.json(독립 정답)과 비교 → independent40.json · independent40_table.md
독립 정답을 다는 에이전트는 규칙 파일(data/rules, src/agent, data/institutions/profiles)을 보지 않고
법령 원문(prep/laws/10_원문_*)과 기관 공개 안내 조사 기록(data/institutions/notes)만 본다.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "eval" / "results"
SEED = 20260930
# 규칙마다 묻는 주제 (정답이 아니라 무엇을 보라는지만)
TOPIC = {
    "E3": "기존 자료·문서를 쓰는 연구의 심의면제 요건 (식별정보를 기록하는가)",
    "E2": "설문·면담 연구의 심의면제 요건 (대상자 특정·민감정보)", "E4": "심의면제에서 빠지는 취약한 대상자",
    "E5": "인체유래물연구의 심의면제 요건", "R-11": "심의면제를 신청할 때 식별 관리(식별자·연구용 번호·대응표) 서술",
    "R-12": "가명정보의 추가정보(대응표) 분리 보관", "R-13": "다른 기관 데이터 결합 절차",
    "D1": "가명정보를 동의 없이 쓰는지 (DRB 검토 경로)", "D2": "정보주체 동의를 받아 처리하는지",
    "D3": "서로 다른 기관의 가명정보 결합", "D4": "본인 동의가 원칙인 민감정보",
    "T1": "의약품·의료기기 임상시험 해당 여부", "G1": "배아·유전자 연구 (이 도구의 범위 밖)", "S6": "인체유래물연구 해당 여부",
    "S7": "익명정보만 쓰는지", "J2": "소속 기관의 IRB 설치·등록", "J3": "다른 위원회·공용위원회와의 위탁 협약",
    "J4": "위탁 협약 가능 기관 (종사 연구자 수)", "J5": "위탁 협약 가능 기관 (최근 3년 심의 건수)",
    "J8": "소속 없는 연구자의 위원회", "J10": "공동연구의 위원회 선정", "C3": "서면동의 면제", "R-05": "가명정보 처리 환경의 위험도",
    "U1": "위원회 설치·협약 전 공용위원회 이용",
}
CHECK_TOPIC = {"past_tense": "계획서 서술 시점 (이미 한 연구처럼 썼는가)", "period_before_review": "연구 기간 시작일과 심의 일정",
               "sample_size_rationale": "예상 대상자 수와 산출 근거", "recruit_doc": "공개 모집과 모집 문건",
               "english_title": "영문 연구 제목", "mixed_style": "계획서 문체 (평서체·경어체)", "age_without_man": "나이 표기 (만 나이)",
               "crf_identifiers": "증례기록서·연구 자료에 적는 식별정보"}
TOLD_TOPIC = {"I-CMC-3": "외부 반출 시 가명화 절차·반출 방법·수령기관 보안환경", "I-CMC-8": "선정기준의 연령",
              "I-CMC-9": "가명화·익명화 담당과 운영 방식", "I-CMC-10": "의무기록 자료의 보관·폐기 계획",
              "I-CUK-14": "불편감을 느낀 대상자의 상담 연계·비용", "I-CUK-15": "보상용 연락처의 폐기",
              "I-PUB-8": "기수집 개인정보 2차 사용 이유", "I-SNUH-3": "외부 반출 시 반출 기관·데이터·전달방법",
              "I-SNUH-7": "연구 기간을 승인 기준으로 적는지", "I-SNUH-9": "재식별 금지", "I-SNUH-10": "윤리성 확보 방안(준수 법령)",
              "I-SNUH-11": "연구 기록 보관 기간", "I-UOS-2": "받은 데이터로 심의면제를 신청할 때 보관 기관의 허가 공문"}
NOTES = {"I-CMC": "cmc", "I-CUK": "cuk", "I-PUB": "public", "I-SNUH": "snuh", "I-UOS": "uos", "I-KHMC": "khmc", "I-SMC": "smc",
         "I-KDCA": "kdca", "I-KUMC": "kumc", "I-YUHS": "yuhs", "I-AMC": "amc"}


def topic(c: dict) -> str:
    rule = c["rule"]
    if rule.startswith("I-"):
        note = NOTES.get(rule.rsplit("-", 1)[0], "")
        what = TOLD_TOPIC.get(rule) or CHECK_TOPIC.get(c["check"], "")
        return f"{c['institution']} IRB 공개 안내의 '{what}' (조사 기록 data/institutions/notes/{note}.md)"
    return TOPIC.get(rule, rule)


def pick() -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)
    traps = [c for c in json.loads((ROOT / "eval/traps/traps300.json").read_text(encoding="utf-8"))["cases"] if c["kind"] == "trap"]
    synth = json.loads((ROOT / "eval/synth/synth300.json").read_text(encoding="utf-8"))["cases"]
    return rng.sample(traps, 20), rng.sample(synth, 20)


def blind() -> None:
    traps, synth = pick()
    items = [{"id": c["id"], "set": "trap", "institution": c["institution"], "plan": c["plan"], "topic": topic(c)} for c in traps]
    items += [{"id": c["id"], "set": "synth", "institution": c["institution"], "target_start_date": c.get("target_start_date"),
               "plan": c["plan"]} for c in synth]
    (RES / "independent_blind.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"문제지 {len(items)}건 → eval/results/independent_blind.json")


def score() -> None:
    traps, synth = pick()
    labels = {x["id"]: x for x in json.loads((RES / "independent_labels.json").read_text(encoding="utf-8"))["items"]}
    same = lambda a, b: a == b or {a, b} <= {"미충족", "경고"}  # noqa: E731
    rows = []
    for c in traps:
        x = labels.get(c["id"], {})
        ours = c["expect"][c["rule"]]
        rows.append({"id": c["id"], "set": "trap", "rule": c["rule"], "ours": ours, "theirs": x.get("state"),
                     "agree": same(ours, x.get("state")), "route_ours": c["route_expected"], "route_theirs": x.get("route"),
                     "agree_route": c["route_expected"] == x.get("route"), "basis_ours": c["source"], "basis_theirs": x.get("basis"),
                     "summary": x.get("summary", ""), "plan": c["plan"]})
    for c in synth:
        x = labels.get(c["id"], {})
        rows.append({"id": c["id"], "set": "synth", "route_ours": c["route_expected"], "route_theirs": x.get("route"),
                     "agree_route": c["route_expected"] == x.get("route"), "committee_ours": c.get("committee_expected"),
                     "committee_theirs": x.get("committee"), "agree_committee": c.get("committee_expected") == x.get("committee"),
                     "basis_ours": " → ".join(c.get("decision_trace", [])), "basis_theirs": x.get("basis"),
                     "summary": x.get("summary", ""), "plan": c["plan"]})
    t, s = [r for r in rows if r["set"] == "trap"], [r for r in rows if r["set"] == "synth"]
    out = {"synth": {"n": len(s), "agree_route": sum(r["agree_route"] for r in s), "agree_committee": sum(r["agree_committee"] for r in s)},
           "traps": {"n": len(t), "agree_expect": sum(r["agree"] for r in t), "agree_route": sum(r["agree_route"] for r in t)},
           "items": rows}
    (RES / "independent40.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 정답 독립 확인 40건 (평가용 합성 데이터 · 팀원 확인용)", "",
             f"합성 20건 경로 일치 {out['synth']['agree_route']}/20 · 위원회 종류 일치 {out['synth']['agree_committee']}/20. "
             f"함정 20건 기대 결과 일치 {out['traps']['agree_expect']}/20 · 경로 일치 {out['traps']['agree_route']}/20.", "",
             "팀원 확인: 마지막 칸에 O(우리 정답이 맞음)·X(틀림)·?(모르겠음)를 적어 주세요.", "",
             "| 번호 | 계획서 요약 | 우리 정답 | 독립 정답 | 근거 조문 | 확인 |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        ours = f"{r.get('rule', '')} {r.get('ours', '')} · 경로 {r['route_ours']}".strip() if r["set"] == "trap" else \
            f"경로 {r['route_ours']} · {r['committee_ours']}"
        theirs = f"{r.get('theirs', '')} · 경로 {r['route_theirs']}" if r["set"] == "trap" else f"경로 {r['route_theirs']} · {r['committee_theirs']}"
        mark = "" if r.get("agree", True) and r["agree_route"] and r.get("agree_committee", True) else " ⚠"
        lines.append(f"| {i} ({r['id']}) | {r['summary'] or r['plan'].splitlines()[0]} | {ours} | {theirs}{mark} | {r['basis_ours']} | |")
    (RES / "independent40_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    {"blind": blind, "score": score}[sys.argv[1]]()
