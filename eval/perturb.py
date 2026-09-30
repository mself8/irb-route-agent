"""누락 주입 검증: 정답이 있는 계획서에서 근거 문장을 지운 변형본을 만들어, 빠진 사실을 지어내지 않고 비워 두는지 잰다.

멘토링(09-30 21:28) 제안: "랜덤으로 누락시키면 셀프 데이터 대량 생산", "잘 걸러내는 게 중요".
통과 예측이 아니라 "빠진 것을 잡아내는가"를 잰다.

- 재료: data/samples 2건 + data/cases 10건 (정답 사실과 근거 구간이 있는 계획서).
- 변형: 근거 구간이 든 줄을 하나씩 지운 변형 + 무작위로 2~3줄을 함께 지운 변형(계획서마다 5개, 시드 고정).
  지운 줄에 근거가 있던 사실은 정답이 not_found, 나머지는 원래 정답 그대로다. 채점 제외 사실(unscored)은 세지 않는다.
- 기대 결과: 지운 사실을 not_found로 바꾼 정답 사실을 규칙 엔진에 넣어 나온 경로와 (나) 질문.
- 실제 결과: 변형본을 실제 ② 마스킹 → ③ 추출 → (추출 사실 그대로 확정) → 규칙 엔진에 넣은 경로와 (나) 질문.
- 마스킹 누락 검사: 가짜 이름·전화번호·이메일·주민번호 줄을 넣고 가린 결과에 원래 글자가 남는지 본다 (모델 없음).
실행: 모델 서버가 떠 있는 곳에서 python eval/perturb.py → eval/results/perturbation.json, perturbation.md
"""
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ["FAKE"] = "0"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent import api, llm, pii  # noqa: E402
from agent.nodes import read as read_node  # noqa: E402

SEED, MULTI, WORKERS, TARGET = 930, 5, 6, "2026-12-01"
PII_LINES = [  # (넣을 줄, 가려져야 할 글자들) — 전부 가짜
    ("담당 연구원: 김민수 (010-9876-5432, minsu.kim@example.org)", ["김민수", "010-9876-5432", "minsu.kim@example.org"]),
    ("연구 문의처: 02-555-1234 / 이메일 research_office@test.co.kr", ["02-555-1234", "research_office@test.co.kr"]),
    ("공동연구자: 박지영 교수 (주민번호 800101-2234567는 행정용으로만 보관)", ["박지영", "800101-2234567"]),
]


def load_cases() -> list[dict]:
    files = sorted((ROOT / "data" / "samples").glob("*.json")) + sorted((ROOT / "data" / "cases").glob("*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


def evidence_lines(case: dict) -> dict[int, set[str]]:
    """줄 번호 → 그 줄에 근거 구간이 있는 채점 대상 사실. 마스킹은 줄 안에서만 바꾸므로 줄 번호는 원문과 같다."""
    masked = case["pending"]["masked_text"]
    unscored = set(case.get("expected", {}).get("unscored_facts", []))
    by_line: dict[int, set[str]] = {}
    for f in case["pending"]["facts"]:
        if f["status"] != "found" or f["span_start"] is None or f["key"] in unscored:
            continue
        for i in range(masked[:f["span_start"]].count("\n"), masked[:f["span_end"]].count("\n") + 1):
            by_line.setdefault(i, set()).add(f["key"])
    return by_line


def variants(cases: list[dict]) -> list[dict]:
    rng, out = random.Random(SEED), []
    for c in cases:
        assert c["plan_text"].count("\n") == c["pending"]["masked_text"].count("\n"), c["id"]
        by_line = evidence_lines(c)
        drops = [[i] for i in sorted(by_line)]
        if len(by_line) >= 3:
            drops += [sorted(rng.sample(sorted(by_line), rng.choice([2, 3]))) for _ in range(MULTI)]
        for drop in drops:
            lines = c["plan_text"].split("\n")
            removed = set().union(*(by_line[i] for i in drop))
            out.append({"case": c, "drop": drop, "removed": sorted(removed),
                        "plan": "\n".join(line for i, line in enumerate(lines) if i not in drop)})
    return out


def expected_facts(case: dict, removed: set[str]) -> list[dict]:
    facts = []
    for f in case["pending"]["facts"]:
        f = dict(f, span_start=None, span_end=None)  # 줄을 지우면 위치가 바뀐다. 판정은 값만 쓴다
        if f["key"] in removed:
            f.update(value=None, span=None, status="not_found", cross_check=None)
        facts.append(f)
    return facts


def judge(plan: str, masked: str, log: list, facts: list[dict], institution: str) -> dict:
    """② ③ 결과를 주어진 값으로 바꿔 끼우고 규칙 엔진(⑤~⑩)만 돈다. LLM=0이라 ⑨ 문장 다듬기도 건너뛴다."""
    class Fixed:
        mask = staticmethod(lambda text: (masked, log))
        extract = staticmethod(lambda masked_text: facts)

    original, os.environ["LLM"] = read_node._impl, "0"
    read_node._impl = lambda name: Fixed if name in ("pii", "llm") else None
    try:
        p = api.start(plan, institution, TARGET)
        return api.confirm(p.run_id, [f.model_dump() for f in p.facts]).model_dump()
    finally:
        read_node._impl, os.environ["LLM"] = original, "1"


def asked(result: dict) -> list[str]:
    return sorted(str(a.get("input_key")) for a in result["abstain"] if a["kind"] == "나")


def main() -> None:
    cases, t0 = load_cases(), time.time()
    vs = variants(cases)
    for v in vs:
        v["masked"], v["log"] = pii.mask(v["plan"])
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:  # ③ 추출만 모델을 쓴다
        extracted = list(pool.map(lambda v: llm.extract(v["masked"]), vs))
    rows = []
    for v, got in zip(vs, extracted):
        c, removed = v["case"], set(v["removed"])
        got_by = {f["key"]: f for f in got}
        want = expected_facts(c, removed)
        exp = judge(v["plan"], v["masked"], v["log"], want, c["institution_name"])
        act = judge(v["plan"], v["masked"], v["log"], got, c["institution_name"])
        kept = [f["key"] for f in c["pending"]["facts"] if f["status"] == "found" and f["key"] not in removed
                and f["key"] not in c.get("expected", {}).get("unscored_facts", [])]
        rows.append({"case": c["id"], "drop": v["drop"], "removed": v["removed"],
                     "removed_status": {k: got_by[k]["status"] for k in removed},
                     "removed_value": {k: got_by[k]["value"] for k in removed},
                     "kept_n": len(kept),
                     "kept_alarm": {k: got_by[k]["status"] for k in kept if got_by[k]["status"] != "found"},
                     "route_expected": exp["route"]["route"], "route_actual": act["route"]["route"],
                     "asked_expected": asked(exp), "asked_actual": asked(act)})
    report(rows, cases, time.time() - t0)


def pii_check(cases: list[dict]) -> tuple[int, int, list[str]]:
    leaks, total = [], 0
    for c in cases:
        for line, secrets in PII_LINES:
            masked, _ = pii.mask(c["plan_text"] + "\n" + line)
            for s in secrets:
                total += 1
                if s in masked:
                    leaks.append(f"{c['id']}: {s}")
    return total - len(leaks), total, leaks


def report(rows: list[dict], cases: list[dict], secs: float) -> None:
    removed = [(k, s) for r in rows for k, s in r["removed_status"].items()]
    alarms = [s for r in rows for s in r["kept_alarm"].values()]
    kept_n = sum(r["kept_n"] for r in rows)
    n, rm = len(rows), max(len(removed), 1)
    nf = sum(s == "not_found" for _, s in removed)
    cf = sum(s == "conflict" for _, s in removed)
    route_ok = sum(r["route_expected"] == r["route_actual"] for r in rows)
    asked_ok = sum(r["asked_expected"] == r["asked_actual"] for r in rows)
    both_ok = sum(r["route_expected"] == r["route_actual"] and r["asked_expected"] == r["asked_actual"] for r in rows)
    per_key: dict[str, list[str]] = {}
    for k, s in removed:
        per_key.setdefault(k, []).append(s)
    ok, total_pii, leaks = pii_check(cases)
    summary = {"variants": n, "removed_facts": len(removed), "detected_not_found": nf, "flagged_conflict": cf,
               "kept_facts": kept_n, "false_alarm_not_found": alarms.count("not_found"),
               "false_alarm_conflict": alarms.count("conflict"), "route_match": route_ok, "asked_match": asked_ok,
               "both_match": both_ok, "pii_ok": ok, "pii_total": total_pii, "seconds": round(secs)}
    out = ROOT / "eval" / "results"
    out.mkdir(exist_ok=True)
    (out / "perturbation.json").write_text(json.dumps({"model": llm.MODEL, "seed": SEED, "summary": summary, "variants": rows,
                                                       "pii_leaks": leaks}, ensure_ascii=False, indent=2), encoding="utf-8")
    pct = lambda a, b: f"{a / b * 100:.0f}%" if b else "-"  # noqa: E731
    weak = sorted(per_key.items(), key=lambda kv: sum(s == "not_found" for s in kv[1]) / len(kv[1]))
    lines = [
        f"# 누락 주입 검증 (변형본 {n}건 · 계획서 {len(cases)}건에서 만듦 · 시드 {SEED})",
        "",
        "근거 문장을 지운 변형본에서, 빠진 사실을 지어내지 않고 비워 두는지 잰다. 통과 예측이 아니다.",
        "",
        "| 지표 | 값 | 뜻 |",
        "|---|---|---|",
        f"| 누락 탐지율 | {pct(nf, rm)} ({nf}/{len(removed)}) | 지운 사실을 '계획서에 없음'으로 비워 둔 비율 |",
        f"| 확인 필요 표시 | {pct(cf, rm)} ({cf}/{len(removed)}) | 지운 사실을 두 번째 추출과 달라 '확인 필요'로 넘긴 비율 |",
        f"| 채워 넣음 | {pct(len(removed) - nf - cf, rm)} | 지운 사실에 값을 채움(남은 문장에서 추론했거나 지어냄) |",
        f"| 오경보율 | {pct(len(alarms), kept_n)} ({len(alarms)}/{kept_n}) | 지우지 않은 사실을 없음·확인 필요로 둔 비율 |",
        f"| 최종 판정 일치율 | {pct(both_ok, n)} ({both_ok}/{n}) | 경로와 (나) 질문이 모두 기대 결과와 같은 비율 |",
        f"| 경로만 일치 | {pct(route_ok, n)} | |",
        f"| (나) 질문만 일치 | {pct(asked_ok, n)} | 빠진 정보를 연구자에게 묻는 목록 |",
        f"| 마스킹 | {ok}/{total_pii} 가림 | 가짜 이름·전화번호·이메일·주민번호 줄을 넣었을 때 |",
        "",
        "## 사실별 누락 탐지율 (낮은 순)",
        "",
        "| 사실 | 탐지 | 확인 필요 | 채움 | 지운 횟수 |",
        "|---|---|---|---|---|",
        *[f"| {k} {llm.FACT_LABELS[k]} | {pct(v.count('not_found'), len(v))} | {pct(v.count('conflict'), len(v))} | "
          f"{pct(len(v) - v.count('not_found') - v.count('conflict'), len(v))} | {len(v)} |" for k, v in weak],
        "",
        "## 한계",
        "",
        "- 변형본은 우리 샘플 2건과 T3 확인 전 테스트 계획서 10건에서 만들었다. 실제 계획서의 문체·길이 분포와 다르다.",
        "- 문장 삭제만 봤다. 표현 바꾸기, 모순된 문장, 오탈자는 보지 않았다.",
        "- '채워 넣음'에는 남은 문장에서 정당하게 추론한 경우도 섞여 있다(예: 제목의 '후향적'에서 임상시험 아님을 추론).",
        "  사례는 perturbation.json의 removed_value로 확인할 수 있다.",
        "- 마스킹 검사는 우리가 만든 세 가지 형식만 넣었다. 실제 문서의 모든 개인정보 형식을 대표하지 않는다.",
        f"- 소요 {round(secs / 60)}분, 추출 동시 {WORKERS}건.",
    ]
    (out / "perturbation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
