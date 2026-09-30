"""③ 사실 추출 평가: 정답이 있는 계획서마다 extract()를 N번 돌려 정확도와 반복 일치율을 낸다.

- 정답: data/samples/*.json, data/cases/*.json의 pending.facts (입력은 pending.masked_text).
- 정확도: 정답과 값이 같은 사실의 비율 (없음=None끼리도 정답, 목록은 순서 무시).
- 반복 일치율: N번 모두 값과 상태가 똑같은 사실의 비율. 모델은 temperature 0.
- 실행: 모델 서버가 떠 있는 곳에서 python eval/extract_eval.py [N=5]. 결과는 eval/results/extract_eval.json에도 쓴다.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent import llm  # noqa: E402


def same(a, b) -> bool:
    return sorted(a) == sorted(b) if isinstance(a, list) and isinstance(b, list) else a == b


def main(n: int) -> None:
    files = sorted((ROOT / "data" / "samples").glob("*.json")) + sorted((ROOT / "data" / "cases").glob("*.json"))
    report = []
    for f in files:
        case = json.loads(f.read_text(encoding="utf-8"))
        want = {x["key"]: x["value"] for x in case["pending"]["facts"]}
        runs, secs = [], []
        for _ in range(n):
            t = time.time()
            runs.append({x["key"]: x for x in llm.extract(case["pending"]["masked_text"])})
            secs.append(time.time() - t)
        keys = list(want)
        acc = [sum(same(r[k]["value"], want[k]) for k in keys) / len(keys) for r in runs]
        stable = sum(all(same(r[k]["value"], runs[0][k]["value"]) and r[k]["status"] == runs[0][k]["status"]
                         for r in runs) for k in keys)
        wrong = sorted({k for r in runs for k in keys if not same(r[k]["value"], want[k])})
        conflicts = sum(r[k]["status"] == "conflict" for r in runs for k in keys) / n
        row = {"case": f.stem, "facts": len(keys), "runs": n, "accuracy_mean": round(sum(acc) / n, 3),
               "accuracy_min": round(min(acc), 3), "agreement": round(stable / len(keys), 3),
               "conflicts_per_run": conflicts, "wrong_keys": wrong, "seconds_mean": round(sum(secs) / n, 1)}
        report.append(row)
        print(json.dumps(row, ensure_ascii=False))
    out = ROOT / "eval" / "results" / "extract_eval.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"model": llm.MODEL, "cases": report}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
