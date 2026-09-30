"""발표용 지표를 한 번에 뽑는다. 프롬프트를 다듬는 데 쓴 샘플 2건(data/samples)은 넣지 않는다.

대상: data/cases/*.json (T3 확인 전 초안). 모델 서버가 떠 있는 곳에서 돌린다.
  python eval/metrics.py [N=5]

지표
1. 경로 일치율  (가) 규칙 엔진만: 정답 사실을 넣어 판정 / (나) 전체: 추출한 사실을 고치지 않고 그대로 확정해 판정
2. 경로 근거 재현율: 정답 경로를 정하는 규칙(expected.rule_ids)이 경로 trace에 있는 비율
3. 판단불가: 기권율(판단불가 행 / 판정 행), 필수 판단불가 재현율(expected.abstain), 부당 기권 수(expected.decided를 판단불가로 냄)
4. 인용 정확도: 모델이 낸 근거 구간 중 계획서와 글자 그대로 맞는 비율(검사 전 원출력). 검사를 통과한 것만 화면에 나간다
5. 사실 추출 정확도: 채점 대상 사실(expected.unscored_facts 제외)의 값 일치율
6. N회 반복 일치율: 같은 계획서를 N번 돌렸을 때 경로와 사실이 모두 같은 비율
7. 관할 일치율(CRIS): data/cases/cris/*.json의 실제 연구에서 에이전트가 고른 위원회 종류와 CRIS의 승인 위원회를 비교.
   통과 여부는 재지 않는다. CRIS만 다시 돌리기: python eval/metrics.py --cris-only
결과: eval/results/metrics.json, eval/results/metrics_table.md (슬라이드용 표)
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ["FAKE"] = "0"  # 실제 그래프
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent import api, llm  # noqa: E402
from agent.nodes import read as read_node  # noqa: E402

TARGET = "2026-12-01"


def same(a, b) -> bool:
    return sorted(a) == sorted(b) if isinstance(a, list) and isinstance(b, list) else a == b


def fact_equal(key: str, got, want) -> bool:
    """규칙 엔진이 그 사실을 쓰는 방식으로 비교한다. 식별자(F16)·취약 대상(F08)은 있고 없음만, 수행기관(F12)은 개수만 판정에 쓴다."""
    if key in ("F08", "F16"):
        return (None if got is None else bool(got)) == (None if want is None else bool(want))
    if key == "F12":
        return (None if got is None else len(got)) == (None if want is None else len(want))
    return same(got, want)


def run_with_facts(case: dict) -> dict:
    """② ③을 정답으로 바꿔 끼우고 ⑤~⑩은 실제 그래프로 돈다 (규칙 엔진만의 정확도)."""
    pending = case["pending"]

    class Fixed:
        @staticmethod
        def mask(text):
            return pending["masked_text"], pending["mask_log"]

        @staticmethod
        def extract(masked_text):
            return pending["facts"]

    original = read_node._impl
    read_node._impl = lambda name: Fixed if name in ("pii", "llm") else original(name)
    try:
        p = api.start(case["plan_text"], case["institution_name"], TARGET)
        return api.confirm(p.run_id, [f.model_dump() for f in p.facts]).model_dump()
    finally:
        read_node._impl = original


def run_end_to_end(case: dict) -> tuple[dict, list[dict], float]:
    """실제 ② 마스킹·③ 추출 → 추출 사실을 그대로 확정 → 판정."""
    t = time.time()
    p = api.start(case["plan_text"], case["institution_name"], TARGET)
    facts = [f.model_dump() for f in p.facts]
    return api.confirm(p.run_id, facts).model_dump(), facts, time.time() - t


def judged(result: dict) -> dict:
    return {r["rule_id"]: r["result"] for r in result["judgments"]}


def score(case: dict, result: dict) -> dict:
    exp, rows = case["expected"], judged(result)
    abstained = {k for k, v in rows.items() if v == "판단불가"}
    return {"route_ok": result["route"]["route"] == exp["route"],
            "route": result["route"]["route"],
            "trace_recall": (sum(r in result["route"]["trace"] for r in exp["rule_ids"]) / len(exp["rule_ids"])
                             if exp["rule_ids"] else 1.0),
            "abstain_rate": len(abstained) / max(len(rows), 1),
            "abstain_recall": (len(abstained & set(exp["abstain"])) / len(exp["abstain"])) if exp["abstain"] else None,
            "wrong_abstain": sorted(abstained & set(exp.get("decided", [])))}


def citation_accuracy(masked_text: str) -> tuple[int, int]:
    """모델 원출력에서 found인 근거 구간 중 계획서와 글자 그대로 맞는 수 / 전체 수."""
    raw = llm._call(llm._prompt(list(llm.FACT_LABELS)), masked_text)
    spans = [v.get("span", "") for v in raw.values() if v.get("found")]
    return sum(llm.locate(s, masked_text) is not None for s in spans), len(spans)


def irb_choice(result: dict) -> str:
    """에이전트가 고른 위원회 종류: own(소속 기관 IRB) / public(공용위원회) / contract(위탁 협약) / unknown(미정) / out."""
    route = result["route"]["route"]
    if route in ("A", "C", "임상시험"):
        return "own"
    if route == "B":
        return "public" if "J8" in result["route"]["trace"] else "contract"
    return "unknown" if route == "미정" else "out"


def cris_eval() -> list[dict]:
    """CRIS 실제 연구: 에이전트가 고른 위원회 종류와 CRIS에 적힌 승인 위원회를 비교한다 (통과 여부는 재지 않는다)."""
    rows = []
    for p in sorted((ROOT / "data" / "cases" / "cris").glob("*.json")):
        case = json.loads(p.read_text(encoding="utf-8"))
        result, _, secs = run_end_to_end(case)
        choice, relation = irb_choice(result), case["actual"]["relation"]
        rows.append({"case": case["id"], "registration": case["registration"], "institution": case["institution_name"],
                     "actual": case["actual"]["committees"], "relation": relation, "route": result["route"]["route"],
                     "committees": result["route"]["committees"], "choice": choice,
                     "match": choice == "own" if relation == "same" else None, "seconds": round(secs, 1)})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    return rows


def main(n: int, cris_only: bool = False) -> None:
    if cris_only:
        return summarize([], n, cris_eval())
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "cases").glob("*.json"))]
    rows = []
    for case in cases:
        scored_keys = [k for k in llm.FACT_LABELS if k not in case["expected"].get("unscored_facts", [])]
        want = {f["key"]: f["value"] for f in case["pending"]["facts"]}
        engine = score(case, run_with_facts(case))
        runs = [run_end_to_end(case) for _ in range(n)]
        e2e = [score(case, r) for r, _, _ in runs]
        facts = [{f["key"]: f for f in fs} for _, fs, _ in runs]
        fact_acc = [sum(fact_equal(k, fr[k]["value"], want[k]) for k in scored_keys) / len(scored_keys) for fr in facts]
        stable_route = all(s["route"] == e2e[0]["route"] for s in e2e)
        stable_facts = all(all(same(fr[k]["value"], facts[0][k]["value"]) for k in llm.FACT_LABELS) for fr in facts)
        ok, total = citation_accuracy(case["pending"]["masked_text"])
        row = {"case": case["id"], "expected_route": case["expected"]["route"],
               "engine": engine,
               "e2e_route_ok_rate": sum(s["route_ok"] for s in e2e) / n,
               "e2e_routes": [s["route"] for s in e2e],
               "e2e_abstain_rate": sum(s["abstain_rate"] for s in e2e) / n,
               "e2e_wrong_abstain": sorted({w for s in e2e for w in s["wrong_abstain"]}),
               "fact_accuracy": sum(fact_acc) / n,
               "wrong_facts": sorted({k for fr in facts for k in scored_keys if not fact_equal(k, fr[k]["value"], want[k])}),
               "e2e_fact_values": [{k: fr[k]["value"] for k in llm.FACT_LABELS} for fr in facts],
               "stable_route": stable_route, "stable_facts": stable_facts,
               "citation_ok": ok, "citation_total": total,
               "seconds": round(sum(s for _, _, s in runs) / n, 1)}
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "e2e_fact_values"}, ensure_ascii=False), flush=True)
    summarize(rows, n, cris_eval())


def summarize(rows: list[dict], n: int, cris: list[dict]) -> None:
    out = ROOT / "eval" / "results"
    out.mkdir(exist_ok=True)
    if not rows:  # CRIS만 다시 돌린 경우: 앞선 결과에 CRIS만 덮어쓴다
        prev = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
        rows, n = prev["cases"], prev["summary"]["runs"]
    k = len(rows)
    rate = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    recalls = [r["engine"]["abstain_recall"] for r in rows if r["engine"]["abstain_recall"] is not None]
    s = {
        "cases": k, "runs": n,
        "route_engine": rate([r["engine"]["route_ok"] for r in rows]),
        "route_e2e": rate([r["e2e_route_ok_rate"] for r in rows]),
        "trace_recall_engine": rate([r["engine"]["trace_recall"] for r in rows]),
        "abstain_rate_engine": rate([r["engine"]["abstain_rate"] for r in rows]),
        "abstain_recall_engine": rate(recalls),
        "wrong_abstain_engine": sum(len(r["engine"]["wrong_abstain"]) for r in rows),
        "fact_accuracy": rate([r["fact_accuracy"] for r in rows]),
        "citation_accuracy_raw": sum(r["citation_ok"] for r in rows) / max(sum(r["citation_total"] for r in rows), 1),
        "stable_route": rate([r["stable_route"] for r in rows]),
        "stable_facts": rate([r["stable_facts"] for r in rows]),
        "seconds": rate([r["seconds"] for r in rows]),
        "cris_cases": len(cris),
        "cris_same": sum(c["relation"] == "same" for c in cris),
        "cris_match": sum(bool(c["match"]) for c in cris),
        "cris_other_asked": sum(c["relation"] == "different" and c["choice"] == "unknown" for c in cris),
        "cris_other": sum(c["relation"] == "different" for c in cris),
    }
    (out / "metrics.json").write_text(json.dumps({"model": llm.MODEL, "summary": s, "cases": rows, "cris": cris},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    pct = lambda v: "-" if v is None else f"{v * 100:.0f}%"  # noqa: E731
    table = "\n".join([
        f"# 지표 (가상 계획서 {k}건 · T3 확인 전 초안 · 프롬프트 조정에 쓴 샘플 2건 제외 · 반복 {n}회)",
        "",
        "| 지표 | 값 | 뜻 |",
        "|---|---|---|",
        f"| 경로 일치율 (규칙 엔진) | {pct(s['route_engine'])} | 정답 사실을 넣었을 때 경로가 맞은 비율 |",
        f"| 경로 일치율 (전체) | {pct(s['route_e2e'])} | 추출한 사실을 고치지 않고 확정했을 때 |",
        f"| 필수 판단불가 재현율 | {pct(s['abstain_recall_engine'])} | 넘겨야 할 항목을 넘긴 비율 |",
        f"| 부당 기권 | {s['wrong_abstain_engine']}건 | 정해진 답이 있는데 판단불가로 넘긴 수 |",
        f"| 기권율 | {pct(s['abstain_rate_engine'])} | 판단불가 행 / 전체 판정 행 |",
        f"| 사실 추출 정확도 | {pct(s['fact_accuracy'])} | 채점 대상 사실의 값 일치율 |",
        f"| 인용 정확도 (모델 원출력) | {pct(s['citation_accuracy_raw'])} | 원문과 글자 그대로 맞은 인용. 틀린 인용은 화면에 나가지 않음 |",
        f"| {n}회 반복 일치율 (경로) | {pct(s['stable_route'])} | 같은 계획서를 {n}번 돌려 경로가 모두 같은 비율 |",
        f"| 건당 처리 시간 | {s['seconds']:.0f}초 | 마스킹·추출·판정·질문 작성 |",
        f"| 관할 일치 (CRIS 실제 연구) | {s['cris_match']}/{s['cris_same']}건 | 소속 기관 IRB가 승인한 연구에서 같은 위원회를 고른 수 |",
        f"| 다른 기관 IRB 승인 연구 | {s['cris_other_asked']}/{s['cris_other']}건 확인 요청 | 명단에 없는 관계는 추정하지 않고 연구자에게 물음 |",
    ])
    (out / "metrics_table.md").write_text(table + "\n", encoding="utf-8")
    print(table)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(int(args[0]) if args else 5, cris_only="--cris-only" in sys.argv)
