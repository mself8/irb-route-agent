"""발표용 모델 비교 표: 같은 시험지(함정·합성 층화 각 100건)를 추출 모델만 바꿔 끝까지 돌린 결과를, 네 모델 모두에게 똑같이 매기는 표준 지표로 나란히 놓는다.

  python eval/model_table.py [--results DIR]            # 기본 4개 모델 (결과 파일이 없는 모델은 '—')
  python eval/model_table.py --model "이름=tag" ...     # 모델 이름=tag (tag 없는 파일이 Qwen3.8)
입력: DIR/{traps,synth}300_stage2<tag>.json (eval/model_compare_run.py·trap_eval.py --sealed … --stage 2 --tag <tag>),
      DIR/model_speed<tag>.json (eval/model_speed.py: 한가한 서버에서 실제형 샘플 3건을 한 건씩 추출), 1단계 결과
결과: eval/results/model_table.md · model_table.json
AUC는 확률 점수를 내는 분류기의 지표라, 예/아니오만 내는 이 시스템에는 균형 정확도(판정이 하나뿐인 분류기의 AUC와 같은 값)를 쓴다.
"""
import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import standard_metrics as sm  # noqa: E402

RESULTS = ROOT / "eval" / "results"
DEFAULT = ["Qwen3.8-27B-FP8=", "EXAONE-4.0-32B-FP8=_exaone4_32b", "Gemma-3-27B-it-FP8=_gemma3_27b",
           "Mistral-Small-3.2-24B-FP8=_mistral_small24b"]


def mcc(b: dict) -> float | None:
    tp, fp, fn, tn = b["tp"], b["fp"], b["fn"], b["tn"]
    d = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / d if d else None


def rate(p: dict | None) -> float | None:
    return p["k"] / p["n"] if p and p.get("n") else None


def kappa(run1: dict, run2: dict) -> float | None:
    """판정 상태(규칙마다)의 코헨 카파: 2단계 vs 1단계(정답 사실)."""
    ref = {c["id"]: c.get("states") or {} for c in run1["cases"]}
    rows = [(sm.judgment(ref[c["id"]].get(r, [])), sm.judgment((c.get("states") or {}).get(r, [])))
            for c in run2["cases"] if c["id"] in ref for r in sorted(set(ref[c["id"]]) | set(c.get("states") or {}))]
    if not rows:
        return None
    n = len(rows)
    po = sum(a == b for a, b in rows) / n
    ca, cb = Counter(a for a, _ in rows), Counter(b for _, b in rows)
    pe = sum(ca[x] * cb[x] for x in ca) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else None


def evaluate(t2: dict | None, s2: dict | None, t1: dict, s1: dict, checks: dict) -> dict:
    """모델 하나의 지표. 없는 입력은 None."""
    out: dict = {}
    if s2:
        r = sm.routes(sm.route_pairs(s2))
        out |= {"route_synth_acc": rate(r["accuracy"]), "route_synth_f1": r["macro_f1"]}
        fw = sm.false_warnings(s1, s2)
        out["false_alarm_plans"] = rate(fw["cases"])
    if t2:
        r = sm.routes(sm.route_pairs(t2))
        out |= {"route_trap_acc": rate(r["accuracy"]), "route_trap_f1": r["macro_f1"]}
        b = sm.binary(sm.pairs(t2, checks))
        out |= {"det_precision": rate(b["precision"]), "det_recall": rate(b["recall"]), "det_f1": b["f1"], "det_mcc": mcc(b),
                "det_bacc": (rate(b["recall"]) + rate(b["specificity"])) / 2 if b["recall"]["n"] and b["specificity"]["n"] else None}
    items = sm.stage_facts(t2) + sm.stage_facts(s2) if t2 and s2 else []  # 200건이 다 있어야 모델끼리 같은 시험지다
    if items:
        f = sm.facts(items)
        p, r = rate(f["found_precision"]), rate(f["found_recall"])
        out |= {"fact_acc": rate(f["accuracy"]), "fact_macro_f1": f["macro_f1"], "fact_set_f1": f["set"]["f1"],
                "fact_presence_f1": 2 * p * r / (p + r) if p and r else None}
    both = sm.route_pairs(t2) + sm.route_pairs(s2) if t2 and s2 else []
    if both:
        r = sm.routes(both)
        out |= {"route_acc": rate(r["accuracy"]), "route_f1": r["macro_f1"]}
    runs = [(t1, t2), (s1, s2)]
    joined = [(a, b) for a, b in runs if b]
    if joined:
        r1 = {"cases": [c for a, _ in joined for c in a["cases"]]}
        r2 = {"cases": [c for _, b in joined for c in b["cases"]]}
        ag = sm.agreement(r1, r2)
        out |= {"judge_acc": rate(ag["accuracy"]), "judge_kappa": kappa(r1, r2), "abstain": rate(ag["abstain"]),
                "selective_acc": rate(ag["selective"])}
    secs = [c.get("seconds") for r in (t2, s2) if r for c in r["cases"] if c.get("seconds")]
    out["latency"] = statistics.median(secs) if secs else None
    return out


def upper(t1: dict, s1: dict, t2ids: dict | None, s2ids: dict | None, checks: dict) -> dict:
    """정답 사실(1단계)을 같은 건으로 줄인 엔진 상한. 추출·판정 지표는 해당 없음."""
    out: dict = {}
    if s2ids:
        r = sm.routes(sm.route_pairs(sm.subset(s1, s2ids)))
        out |= {"route_synth_acc": rate(r["accuracy"]), "route_synth_f1": r["macro_f1"]}  # 헛경고는 이 값이 기준이라 칸을 비운다
    if t2ids:
        sub = sm.subset(t1, t2ids)
        r = sm.routes(sm.route_pairs(sub))
        b = sm.binary(sm.pairs(sub, checks))
        out |= {"route_trap_acc": rate(r["accuracy"]), "route_trap_f1": r["macro_f1"], "det_precision": rate(b["precision"]),
                "det_recall": rate(b["recall"]), "det_f1": b["f1"], "det_mcc": mcc(b),
                "det_bacc": (rate(b["recall"]) + rate(b["specificity"])) / 2}
    return out


ROWS = [  # (묶음, 지표 키, 표시 이름, 형식, 높을수록 좋음) — 네 모델 모두에게 똑같이 매기는 표준 지표만
    ("사실 추출 (200건 × 18항목)", "fact_acc", "Accuracy", "pct", True),
    ("사실 추출 (200건 × 18항목)", "fact_macro_f1", "Macro-F1", "f", True),
    ("경로 판정 (200건, 6분류)", "route_acc", "Accuracy", "pct", True),
    ("경로 판정 (200건, 6분류)", "route_f1", "Macro-F1", "f", True),
    ("규칙 위반 탐지 (함정 100건)", "det_precision", "Precision", "pct", True),
    ("규칙 위반 탐지 (함정 100건)", "det_recall", "Recall", "pct", True),
    ("규칙 위반 탐지 (함정 100건)", "det_f1", "F1", "f", True),
    ("속도", "speed", "추출 초/건", "s1", False),
]
NOTES = ["- 같은 시험지 200건(함정 100 · 합성 100, 평가용 합성 데이터)에서 추출 모델만 바꿨다. 사람 확인 없이 추출값 그대로 판정했다.",
         "- Macro-F1: 부류마다 F1을 구해 평균(드문 부류도 같은 무게). 규칙 위반 탐지는 (계획서, 규칙) 쌍 단위다.",
         "- AUC는 확률 점수를 내는 분류기의 지표라 예/아니오만 내는 이 시스템에는 매기지 않았다.",
         "- 추출 초/건: 다른 요청이 없는 서버에서 실제형 샘플 3건을 한 건씩 추출한 평균(교차 확인 2회 호출 포함).",
         "- 모두 vLLM 0.25.1, GPU 2장(TP=2), FP8. 비교 모델은 느려서 오류로 빠지지 않게 호출 제한을 180초로 늘렸다(Qwen3.8은 60초에서 오류 0건)."]


def fmt(v, kind: str) -> str:
    if v is None:
        return "—"
    return {"pct": f"{100 * v:.1f}%", "f": f"{v:.3f}", "s": f"{v:.0f}", "s1": f"{v:.1f}"}[kind]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", help="표시 이름=tag (여러 번)")
    ap.add_argument("--results", type=Path, default=RESULTS, help="2단계·속도 결과 폴더 (기본: 이 레포의 eval/results)")
    a = ap.parse_args()
    specs, src = [m.split("=", 1) for m in (a.model or DEFAULT)], a.results
    t1, s1 = sm.load(RESULTS / "traps300_stage1.json"), sm.load(RESULTS / "synth300_stage1.json")
    checks = {c["rule"]: c["check"] for c in t1["cases"] if c.get("check")}
    models, found = {}, []
    for name, tag in specs:
        t2, s2 = sm.load(src / f"traps300_stage2{tag}.json"), sm.load(src / f"synth300_stage2{tag}.json")
        models[name] = evaluate(t2, s2, t1, s1, checks)
        speed = sm.load(src / f"model_speed{tag}.json")
        models[name]["speed"] = statistics.mean(speed["seconds"]) if speed and speed.get("seconds") else None
        found.append((name, t2 is not None, s2 is not None))
    base_t2, base_s2 = sm.load(RESULTS / "traps300_stage2.json"), sm.load(RESULTS / "synth300_stage2.json")
    ref = upper(t1, s1, base_t2, base_s2, checks)
    names = list(models)
    lines = ["# 모델 비교 — 평가용 합성 데이터(Claude Code로 생성) · 엔진 동결본 206ba17 · 같은 시험지 200건", "",
             "굵은 값이 네 모델 중 가장 좋은 값이다.", "",
             "| 묶음 | 지표 | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for group, key, label, kind, higher in ROWS:
        vals = [models[n].get(key) for n in names]
        model_vals = [v for v in vals if v is not None]
        best = (max(model_vals) if higher else min(model_vals)) if len(model_vals) > 1 else None
        cells = [f"**{fmt(v, kind)}**" if best is not None and v == best else fmt(v, kind) for v in vals]
        lines.append(f"| {group} | {label} | " + " | ".join(cells) + " |")
    lines += ["", *NOTES, f"- 참고: 추출이 완벽하면(정답 사실) 함정 100건 경로 Accuracy {fmt(ref.get('route_trap_acc'), 'pct')}, "
              f"위반 탐지 F1 {fmt(ref.get('det_f1'), 'f')}이다.", ""]
    gone = [f"{n} ({'함정' if not t else ''}{' · ' if not t and not s else ''}{'합성' if not s else ''} 결과 없음)"
            for n, t, s in found if not (t and s)]
    if gone:
        lines += ["- 아직 없는 결과: " + " / ".join(gone), ""]
    (RESULTS / "model_table.md").write_text("\n".join(lines), encoding="utf-8")
    (RESULTS / "model_table.json").write_text(json.dumps(models, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines[:6 + len(ROWS)]))


if __name__ == "__main__":
    main()
