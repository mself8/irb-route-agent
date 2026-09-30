"""표준 지표 한 장: 합성 계획서 300·함정 300 실측 결과에 정밀도·재현율·F1·혼동행렬을 윌슨 95% 구간과 함께 매긴다.

LLM·네트워크 없이 몇 초 안에 돈다. 입력 파일이 없으면 그 절은 한 줄로 알리고 건너뛴다.
  python eval/standard_metrics.py [--stage1 P] [--stage2 P] [--synth1 P] [--synth2 P] [--independent P] [--out DIR]
입력 (기본은 eval/results/ 아래)
- traps300_stage1.json·traps300_stage2.json: 함정. synth300_stage1.json·synth300_stage2.json: 합성 계획서
  1단계 = 정답 사실을 넣고 규칙 엔진만, 2단계 = AI가 뽑은 사실을 고치지 않고 판정 (1단계에서 층화해 뽑은 일부)
- metrics.json: 사례 10건 × 5회 (정답 사실은 data/cases/<case>.json). perturbation.json: 이전 가림 측정
- independent40.json: 만든 쪽이 아닌 에이전트가 원문만 보고 따로 단 정답과의 일치 수
지표
1. 경로: 정확도·매크로 F1·혼동행렬. 합성은 위원회 종류 정확도와 연구 유형별 정확도도
2. 함정: (계획서, 규칙) 쌍의 이진 판별. 양성 = 뒤집은 규칙(expect), 음성 = 지킨 규칙(satisfies)
3. 멀쩡한 계획서 헛경고: 합성 2단계에서 같은 계획서의 1단계에 없던 미충족·경고가 뜬 것
4. 판정: 2단계 판정 행을 같은 계획서의 1단계 판정 행(정답 사실 = 기준)과 비교. 일치율·기권율·선택적 정확도
5. 사실 추출: 항목별 정확도(metrics.py의 fact_equal)·범주형 매크로 F1·목록형 집합 F1·있다/없다 판별
   합성은 출처(시나리오 생성·CRIS 원본 변형)별로도 나눈다. 실제에 가까운 문장이 추출을 얼마나 바꾸는지 보려고
6. 개인정보 가림: 심어 둔 가상 개인정보(pii_gold)를 지금 코드(agent.pii)로 다시 가려 정밀도·재현율
결과: eval/results/standard_metrics.md (발표용 한 장), standard_metrics.json (숫자)
"""
import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "eval")]
from agent import pii  # noqa: E402
from agent.state import FACT_LABELS  # noqa: E402
from metrics import fact_equal  # noqa: E402  규칙 엔진이 사실을 쓰는 방식으로 비교한다

FLAG = {"미충족", "경고"}
ROUTES = ["A", "B", "C", "임상시험", "범위 밖", "미정"]
TYPES = ["중재", "관찰", "설문·면담", "기록 이용", "인체유래물"]
FACTS = list(FACT_LABELS)
CATEGORICAL = ["F01", "F02", "F03", "F04", "F05", "F06", "F09", "F10", "F11", "F14", "F17", "F18"]
LISTS = ["F07", "F08", "F12", "F16"]
VARIANTS = ["정면", "말바꾸기", "부정문", "경계", "기관 맥락"]
CONTROLS = ["대조군", "지킨 변형"]  # 대조군 = 뼈대 그대로, 지킨 변형 = 규칙을 지키면서 문장만 바꾼 대조군 (variant가 있음)
ORIGINS = ["시나리오 생성", "CRIS 원본 변형"]
CHECKS = {"past_tense": "과거형", "mixed_style": "문체 섞임", "age_without_man": "만 나이", "sample_size_rationale": "대상자 수 근거",
          "period_before_review": "심의 전 시작", "recruit_doc": "모집 문건", "crf_identifiers": "CRF 식별자",
          "english_title": "영문 제목", "told": "알린 낱말"}
BIN_HEAD = ["| 구분 | 걸림/양성 | 헛경고/음성 | 재현율 | 정밀도 | F1 | 오경보율 | 특이도 |", "|---|---|---|---|---|---|---|---|"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """윌슨 95% 구간 (하한, 상한). n=0이면 None."""
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    mid, half = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, mid - half), min(1.0, mid + half)


def prop(k: int, n: int) -> dict:
    lo, hi = wilson(k, n) or (None, None)
    return {"k": k, "n": n, "p": k / n if n else None, "lo": lo, "hi": hi}


def show(d: dict | None, count: bool = False) -> str:
    """87% [81–91]. count면 뒤에 (k/n). n=0이면 —.
    0%·100%로 반올림되지만 실제로는 아닌 값은 소수 한 자리(0.4%·99.6%). 구간은 하한 내림·상한 올림 ([100–100]이 되지 않게)."""
    if not d or not d["n"]:
        return "—"
    v = 100 * d["p"]
    p = f"{v:.0f}"
    p = f"{min(max(v, 0.1), 99.9):.1f}" if p in ("0", "100") and 0 < d["k"] < d["n"] else p
    s = f"{p}% [{math.floor(100 * d['lo'] + 1e-9)}–{math.ceil(100 * d['hi'] - 1e-9)}]"
    return f"{s} ({d['k']}/{d['n']})" if count else s


def num(v) -> str:
    return "—" if v is None else f"{v:.2f}"


def f1(tp: int, fp: int, fn: int) -> float | None:
    return 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None


def mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def ordered(present, known: list) -> list:
    """알려진 순서대로, 모르는 값은 뒤에 가나다순."""
    present = set(present) - {None}
    return [k for k in known if k in present] + sorted(present - set(known))


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def subset(run: dict, other: dict) -> dict:
    """run에서 other에 있는 계획서만 (1단계를 2단계와 같은 건으로 줄일 때)."""
    ids = {c["id"] for c in other["cases"]}
    return {**run, "cases": [c for c in run["cases"] if c["id"] in ids]}


def missing(*named) -> list[str]:
    gone = [name for name, run in named if run is None]
    return [f"{' · '.join(gone)} 결과 없음", ""] if gone else []


# 함정 -------------------------------------------------------------------------------------------------------------------
def pairs(run: dict, checks: dict) -> list[dict]:
    """(계획서, 규칙) 쌍. 양성 = 함정이 뒤집은 규칙(expect), 음성 = 계획서가 지킨 규칙(satisfies).
    양성은 기대 상태가 나오면 걸림(미충족과 경고는 같게 센다). 음성은 alarm의 상태가 나오면 헛경고(alarm에 없는 규칙은 미충족·경고).
    기관 규칙의 검사 종류는 그 규칙 함정의 check를 쓰고, 없으면 알린 낱말(told)로 본다.
    대조군은 변형 이름과 상관없이 대조군(뼈대)과 지킨 변형 두 묶음으로만 나눈다."""
    alarm, out = run.get("alarm") or {}, []
    for c in run["cases"]:
        states = c.get("states") or {}
        trap = c["kind"] == "trap"
        todo = [(r, True, FLAG if s in FLAG else {s}) for r, s in (c.get("expect") or {}).items() if trap]
        todo += [(r, False, set(alarm.get(r, FLAG))) for r in c.get("satisfies") or []]
        for rule, positive, hit in todo:
            own = rule == c.get("rule")
            scope = (own and c.get("scope")) or ("기관" if rule.startswith("I-") else "법")
            check = ((own and c.get("check")) or checks.get(rule, "told")) if scope == "기관" else None
            variant = (c.get("variant") or "기타") if trap else CONTROLS[bool(c.get("variant"))]
            out.append({"case": c["id"], "rule": rule, "positive": positive, "flagged": bool(set(states.get(rule, [])) & hit),
                        "scope": scope, "check": check, "variant": variant})
    return out


def binary(ps: list[dict]) -> dict:
    """정밀도·F1은 양성과 음성이 함께 있는 묶음에서만 매긴다 (대조군만 있는 묶음의 정밀도 0%는 뜻이 없다)."""
    pos, neg = [p for p in ps if p["positive"]], [p for p in ps if not p["positive"]]
    tp, fp = sum(p["flagged"] for p in pos), sum(p["flagged"] for p in neg)
    fn, tn, both = len(pos) - tp, len(neg) - fp, bool(pos and neg)
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "recall": prop(tp, len(pos)), "precision": prop(tp, tp + fp) if both else prop(0, 0),
            "f1": f1(tp, fp, fn) if both else None, "fpr": prop(fp, len(neg)), "specificity": prop(tn, len(neg))}


def breakdown(ps: list[dict]) -> dict:
    """전체·법·기관·기관 검사 종류별·변형별."""
    out = {"전체": binary(ps)}
    for attr, known, name in (("scope", ["법", "기관"], str), ("check", list(CHECKS), lambda v: f"기관 · {CHECKS.get(v, v)}"),
                              ("variant", VARIANTS + CONTROLS, lambda v: v if v in CONTROLS else f"변형 · {v}")):
        for v in ordered({p[attr] for p in ps}, known):
            out[name(v)] = binary([p for p in ps if p[attr] == v])
    return out


def bin_row(name: str, b: dict) -> str:
    return (f"| {name} | {b['tp']}/{b['tp'] + b['fn']} | {b['fp']}/{b['fp'] + b['tn']} | {show(b['recall'])} | "
            f"{show(b['precision'])} | {num(b['f1'])} | {show(b['fpr'])} | {show(b['specificity'])} |")


def top_rules(ps: list[dict], positive: bool) -> list[tuple[str, int, int]]:
    """놓침(양성인데 안 걸림)이나 헛경고(음성인데 걸림)가 많은 규칙 8개: (규칙, 건수, 쌍 수)."""
    bad, total = Counter(), Counter()
    for p in ps:
        if p["positive"] == positive:
            total[p["rule"]] += 1
            bad[p["rule"]] += p["flagged"] != positive
    return sorted(((r, k, total[r]) for r, k in bad.items() if k), key=lambda x: (-x[1], -x[1] / x[2], x[0]))[:8]


def trap_section(t1: dict | None, t2: dict | None) -> tuple[list[str], dict]:
    lines, data = ["## 함정 탐지", ""], {}
    runs = {name: r for name, r in (("1단계", t1), ("2단계", t2)) if r}
    if not runs:
        return lines + ["함정 결과 없음", ""], data
    checks = {c["rule"]: c["check"] for r in runs.values() for c in r["cases"] if c["kind"] == "trap" and c.get("check")}
    ps = {name: pairs(r, checks) for name, r in runs.items()}
    data = {name: breakdown(p) for name, p in ps.items()}
    main = next(iter(runs))
    lines += ["양성 = 함정이 뒤집은 규칙(걸려야 맞음). 음성 = 계획서가 지킨 규칙(걸리면 헛경고). 단위는 (계획서, 규칙) 쌍이다.", "",
              f"{main} · 계획서 {len(runs[main]['cases'])}건", "", *BIN_HEAD, *(bin_row(k, v) for k, v in data[main].items()), ""]
    lines += missing(("함정 1단계", t1), ("함정 2단계", t2))
    if t1 and t2:
        same = data["1단계 · 2단계와 같은 건"] = breakdown(pairs(subset(t1, t2), checks))
        lines += [f"### 1단계 → 2단계 (2단계는 규칙 종류별로 층화해 뽑은 {len(t2['cases'])}건, 1단계도 같은 건만)", "",
                  "| 구분 | 재현율 1단계 | 재현율 2단계 | 오경보율 1단계 | 오경보율 2단계 | F1 1단계 | F1 2단계 |",
                  "|---|---|---|---|---|---|---|"]
        for k in ("전체", "법", "기관"):
            a, b = same.get(k) or binary([]), data["2단계"].get(k) or binary([])
            lines.append(f"| {k} | {show(a['recall'])} | {show(b['recall'])} | {show(a['fpr'])} | {show(b['fpr'])} | "
                         f"{num(a['f1'])} | {num(b['f1'])} |")
        lines.append("")
    cols = [(f"{name} {'놓침' if pos else '헛경고'}", top_rules(p, pos)) for name, p in ps.items() for pos in (True, False)]
    data["top"] = {name: top for name, top in cols}
    rows = max(len(top) for _, top in cols)
    lines += ["### 놓침·헛경고가 많은 규칙 (건수/쌍 수)", ""]
    lines += (["| 순위 | " + " | ".join(name for name, _ in cols) + " |", "|---" * (len(cols) + 1) + "|"]
              + [f"| {i + 1} | " + " | ".join(f"{t[i][0]} {t[i][1]}/{t[i][2]}" if i < len(t) else "없음" if not i else ""
                                               for _, t in cols) + " |" for i in range(rows)] if rows else ["놓침·헛경고 없음"])
    return lines + [""], data


# 멀쩡한 계획서 헛경고 ----------------------------------------------------------------------------------------------------------
def false_warnings(run1: dict, run2: dict) -> dict:
    """2단계에서 미충족·경고가 뜬 규칙 중 같은 계획서의 1단계(정답 사실)에서는 안 걸린 것. 계획서 단위로 센다."""
    ref = {c["id"]: c.get("states") or {} for c in run1["cases"]}
    counts, rules = [], Counter()
    for c in run2["cases"]:
        if c["id"] in ref:
            new = [r for r, s in (c.get("states") or {}).items() if FLAG & set(s) and not FLAG & set(ref[c["id"]].get(r, []))]
            counts.append(len(new))
            rules.update(new)
    return {"cases": prop(sum(k > 0 for k in counts), len(counts)), "total": sum(counts),
            "per_case": sum(counts) / len(counts) if counts else None, "top": rules.most_common(8)}


def warning_section(s1: dict | None, s2: dict | None) -> tuple[list[str], dict]:
    lines = ["## 멀쩡한 계획서 헛경고 (합성 2단계)", ""]
    if not (s1 and s2):
        return lines + missing(("합성 1단계", s1), ("합성 2단계", s2)), {}
    fw = false_warnings(s1, s2)
    return lines + ["정답 사실로는 안 걸린 규칙이 AI가 뽑은 사실로는 미충족·경고로 뜬 경우다.", "",
                    "| 지표 | 값 |", "|---|---|",
                    f"| 헛경고가 1건 이상인 계획서 | {show(fw['cases'], True)} |",
                    f"| 계획서당 헛경고 | {num(fw['per_case'])}건 ({fw['total']}건 / {fw['cases']['n']}건) |",
                    f"| 많이 낸 규칙 (계획서 수) | {' · '.join(f'{r} {k}' for r, k in fw['top']) or '없음'} |", ""], fw


NEGATION = {"A대신B": "'○○ 대신 연구번호를 쓴다'", "A기록안함": "'○○는 기록하지 않는다'", "미성년자제외": "'미성년자는 제외한다'",
            "민감정보없음명시": "'민감정보는 넣지 않는다'", "대응표연구자아님": "'대응표는 연구책임자가 아닌 데이터팀이'",
            "주민번호수집안함": "'주민등록번호와 이름은 받지 않는다'", "결합안함명시": "'결합은 없다'", "공동연구아님": "'공동연구가 아니다'",
            "약안씀": "'약이나 기기를 쓰지 않는다'", "유전자분석안함": "'유전자 분석은 하지 않는다'", "면제요청안함": "'면제는 요청하지 않는다'",
            "민감문항없음": "'건강 정보는 묻지 않는다'"}


def negation_section(t2: dict | None, alarm: dict) -> list[str]:
    """규칙을 부정문으로 지킨 대조군이 2단계(AI 추출)에서 헛걸리는가. 2단계 표본 + 표본 밖 보충 측정(traps300_stage2_negation.json)."""
    extra = load(RESULTS / "traps300_stage2_negation.json")
    cases = [c for r in (t2, extra) if r for c in r["cases"] if c.get("kind") == "control" and c.get("variant") in NEGATION]
    if not cases:
        return []
    lines = ["### 부정문으로 규칙을 지킨 대조군 (2단계, AI 추출)", "",
             "AI 추출의 F16 부정문 오류는 고치지 않고 그대로 쟀다.", "",
             "| 표현 | 건수 | 헛경고 | 뽑은 식별자(F16) |", "|---|---|---|---|"]
    for v, label in NEGATION.items():
        group = [c for c in cases if c.get("variant") == v]
        if not group:
            continue
        bad = sum(any(FLAG & set(c.get("states", {}).get(r) or []) if not alarm.get(r) else set(alarm[r]) & set(c.get("states", {}).get(r) or [])
                      for r in c.get("satisfies", [])) for c in group)
        ids = " · ".join(str((c.get("facts_got") or {}).get("F16")) for c in group)
        lines.append(f"| {label} | {len(group)} | {bad} | {ids} |")
    return lines + [""]


# 경로 -------------------------------------------------------------------------------------------------------------------
def route_pairs(run: dict) -> list[tuple[str, str]]:
    return [(c["route_expected"], c.get("route") or "없음") for c in run["cases"] if c.get("route_expected")]


def routes(ps: list[tuple[str, str]]) -> dict:
    """(정답, 에이전트) 경로 → 정확도·매크로 F1(나온 경로만)·혼동행렬."""
    labels = ordered({x for p in ps for x in p}, ROUTES)
    conf = Counter(ps)
    per = {a: f1(conf[a, a], sum(conf[o, a] for o in labels) - conf[a, a], sum(conf[a, o] for o in labels) - conf[a, a])
           for a in labels}
    return {"accuracy": prop(sum(conf[a, a] for a in labels), len(ps)), "macro_f1": mean(per.values()), "f1": per,
            "labels": labels, "confusion": [[conf[a, b] for b in labels] for a in labels]}


def committee(run: dict) -> dict | None:
    cs = [c for c in run["cases"] if c.get("committee_expected")]
    return prop(sum(c.get("committee") == c["committee_expected"] for c in cs), len(cs)) if cs else None


def by_type(run: dict) -> dict:
    """합성 계획서의 연구 유형(strata["연구 유형"], 옛 이름 type)별 경로 정확도."""
    g = defaultdict(list)
    for c in run["cases"]:
        if c.get("route_expected"):
            strata = c.get("strata") or {}
            g[strata.get("연구 유형") or strata.get("type") or "없음"].append(c.get("route") == c["route_expected"])
    return {t: prop(sum(g[t]), len(g[t])) for t in ordered(g, TYPES)}


def confusion(name: str, r: dict) -> list[str]:
    labels = r["labels"]
    return [f"#### {name}", "", "| 정답 \\ 에이전트 | " + " | ".join(labels) + " |", "|---" * (len(labels) + 1) + "|",
            *(f"| {a} | " + " | ".join(str(v) if v else "·" for v in row) + " |" for a, row in zip(labels, r["confusion"])), ""]


def route_section(t1, t2, s1, s2, m) -> tuple[list[str], dict, list[str]]:
    sets = []  # (이름, 실행 결과)
    for kind, r1, r2 in (("합성", s1, s2), ("함정", t1, t2)):
        sets += [(f"{kind} 1단계", r1)] if r1 else []
        sets += [(f"{kind} 1단계 · 2단계와 같은 건", subset(r1, r2))] if r1 and r2 else []
        sets += [(f"{kind} 2단계", r2)] if r2 else []
    data = {name: {**routes(route_pairs(r)), "committee": committee(r)} for name, r in sets}
    if m:
        data["사례 10건 × 5회"] = {**routes([(c["expected_route"], x) for c in m["cases"] for x in c["e2e_routes"]]), "committee": None}
    lines = ["## 경로", ""] + missing(("합성 1단계", s1), ("합성 2단계", s2), ("함정 1단계", t1), ("함정 2단계", t2),
                                      ("사례 10건 × 5회", m))
    if data:
        lines += ["| 데이터 | 건수 | 경로 정확도 | 매크로 F1 | 위원회 종류 정확도 |", "|---|---|---|---|---|"]
        lines += [f"| {k} | {v['accuracy']['n']} | {show(v['accuracy'])} | {num(v['macro_f1'])} | {show(v['committee'])} |"
                  for k, v in data.items()]
        lines.append("")
    if s1:
        wrong = Counter((a, b) for a, b in route_pairs(s1) if a != b)
        data["합성 1단계 불일치"] = [[a, b, k] for (a, b), k in wrong.most_common()]
        lines += ["합성 1단계 경로 불일치 (정답→엔진): " + (" · ".join(f"{a}→{b} {k}" for (a, b), k in wrong.most_common()) or "없음"), ""]
    synth =[(name, r) for name, r in (("1단계", s1), ("2단계", s2)) if r]
    if synth:
        types = {name: by_type(r) for name, r in synth}
        data["합성 연구 유형별"] = types
        lines += ["### 합성 · 연구 유형별 경로 정확도", "", "| 연구 유형 | " + " | ".join(n for n, _ in synth) + " |",
                  "|---" * (len(synth) + 1) + "|"]
        lines += [f"| {t} | " + " | ".join(show(types[n].get(t), True) for n, _ in synth) + " |"
                  for t in ordered({t for v in types.values() for t in v}, TYPES)]
        lines.append("")
    appendix = [x for k, v in data.items() if "labels" in v for x in confusion(k, v)]
    return lines, data, appendix


# 판정 -------------------------------------------------------------------------------------------------------------------
def judgment(states: list[str]) -> str:
    """판정 행의 상태. 경고는 보완 제안이라 뺀다. 없으면 '없음'."""
    return next((s for s in states if s != "경고"), "없음")


def agreement(run1: dict, run2: dict) -> dict:
    """2단계 판정을 같은 계획서의 1단계 판정(정답 사실 = 기준)과 규칙마다 비교한다."""
    ref = {c["id"]: c.get("states") or {} for c in run1["cases"]}
    rows = [(r, judgment(ref[c["id"]].get(r, [])), judgment((c.get("states") or {}).get(r, [])))
            for c in run2["cases"] if c["id"] in ref for r in sorted(set(ref[c["id"]]) | set(c.get("states") or {}))]
    decided = [(a, b) for _, a, b in rows if not b.startswith("판단불가")]
    per = defaultdict(list)
    for r, a, b in rows:
        per[r].append(a == b)
    return {"accuracy": prop(sum(a == b for _, a, b in rows), len(rows)),
            "abstain": prop(sum(b.startswith("판단불가") for *_, b in rows), len(rows)),
            "abstain_stage1": prop(sum(a.startswith("판단불가") for _, a, _ in rows), len(rows)),
            "selective": prop(sum(a == b for a, b in decided), len(decided)),
            "per_rule": {r: prop(sum(v), len(v)) for r, v in sorted(per.items()) if len(v) >= 3}}


def judgment_section(t1, t2, s1, s2) -> tuple[list[str], dict, list[str]]:
    lines = ["## 판정 (2단계를 1단계와 비교)", ""]
    data = {kind: agreement(r1, r2) for kind, r1, r2 in (("함정", t1, t2), ("합성", s1, s2)) if r1 and r2}
    lines += missing(("함정 1단계", t1), ("함정 2단계", t2), ("합성 1단계", s1), ("합성 2단계", s2))
    if not data:
        return lines, data, []
    head = lambda first: [f"| {first} | " + " | ".join(data) + " |", "|---" * (len(data) + 1) + "|"]  # noqa: E731
    lines += ["같은 계획서·같은 규칙의 판정 행(충족·미충족·판단불가)을 정답 사실로 낸 1단계와 비교한다. 경고(보완 제안)는 뺀다.", "",
              *head("지표"),
              "| 비교한 판정 | " + " | ".join(str(v["accuracy"]["n"]) for v in data.values()) + " |"]
    for name, key in (("일치율", "accuracy"), ("기권율 (2단계 판단불가)", "abstain"), ("기권율 (1단계, 참고)", "abstain_stage1"),
                      ("선택적 정확도 (2단계가 판정한 것만)", "selective")):
        lines.append(f"| {name} | " + " | ".join(show(v[key]) for v in data.values()) + " |")
    rules = sorted({r for v in data.values() for r in v["per_rule"]},  # I-CMC-3이 I-CMC-10보다 앞에 오게
                   key=lambda r: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", r)])
    appendix = ["### 판정 일치율 · 규칙별 (비교 3건 이상)", "", *head("규칙"),
                *(f"| {r} | " + " | ".join(show(v["per_rule"].get(r), True) for v in data.values()) + " |" for r in rules), ""]
    return lines + [""], data, appendix


# 사실 추출 ----------------------------------------------------------------------------------------------------------------
def stage_facts(run: dict) -> list[tuple[dict, dict, list[str]]]:
    """2단계: 정답 사실(facts_gold)과 AI 추출(facts_got). 정답에 적힌 항목만 채점한다."""
    return [(c["facts_gold"], c["facts_got"], [k for k in FACTS if k in c["facts_gold"]])
            for c in run["cases"] if c.get("facts_gold") is not None and c.get("facts_got") is not None]


def case_facts(m: dict) -> list[tuple[dict, dict, list[str]]]:
    """사례 10건 × 5회: data/cases의 정답 사실과 비교한다. 채점 안 하는 사실(expected.unscored_facts)은 뺀다."""
    gold = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data" / "cases").glob("*.json")}
    out = []
    for row in m["cases"]:
        case = gold[row["case"]]
        want = {f["key"]: f["value"] for f in case["pending"]["facts"]}
        keys = [k for k in FACTS if k not in case["expected"].get("unscored_facts", [])]
        out += [(want, got, keys) for got in row["e2e_fact_values"]]
    return out


def as_set(v) -> set[str]:
    return {"".join(str(x).split()).casefold() for x in v or []}


def set_prf(want, got) -> tuple[float, float, float]:
    """목록 한 건의 집합 정밀도·재현율·F1 (띄어쓰기·대소문자 무시). null은 빈 목록. 빈 목록끼리는 1, 한쪽만 비면 0."""
    w, g = as_set(want), as_set(got)
    if not w and not g:
        return 1.0, 1.0, 1.0
    hit = len(w & g)
    return hit / len(g) if g else 0.0, hit / len(w) if w else 0.0, 2 * hit / (len(w) + len(g))


def class_f1(c: Counter) -> float | None:
    """(정답 부류, 추출 부류) 개수 → 부류별 F1의 평균 (null은 '없음' 한 부류)."""
    labels = {x for pair in c for x in pair}
    return mean(f1(c[x, x], sum(v for (a, b), v in c.items() if b == x) - c[x, x],
                   sum(v for (a, b), v in c.items() if a == x) - c[x, x]) for x in labels)


def facts(items: list[tuple[dict, dict, list[str]]]) -> dict:
    """(정답, 추출, 채점 항목) → 항목별 정확도·범주형 매크로 F1·목록형 집합 F1·있다/없다 판별."""
    acc, cls, sets, found = defaultdict(list), defaultdict(Counter), defaultdict(list), Counter()
    for want, got, keys in items:
        for k in keys:
            w, g = want.get(k), got.get(k)
            acc[k].append(fact_equal(k, g, w))
            if k in CATEGORICAL:
                cls[k]["없음" if w is None else str(w), "없음" if g is None else str(g)] += 1
            if k in LISTS:
                sets[k].append(set_prf(w, g))
            found[w is not None, g is not None] += 1
    macro = {k: class_f1(cls[k]) for k in CATEGORICAL if cls[k]}
    prf = lambda xs: {n: mean(x[i] for x in xs) for i, n in enumerate(("precision", "recall", "f1"))}  # noqa: E731
    tp = found[True, True]
    return {"n": sum(map(len, acc.values())), "accuracy": prop(sum(map(sum, acc.values())), sum(map(len, acc.values()))),
            "per_key": {k: prop(sum(acc[k]), len(acc[k])) for k in FACTS if acc[k]},
            "macro_f1": mean(macro.values()), "macro_f1_per_key": macro,
            "set": prf([x for v in sets.values() for x in v]), "set_per_key": {k: prf(sets[k]) for k in LISTS if sets[k]},
            "found_precision": prop(tp, tp + found[False, True]), "found_recall": prop(tp, tp + found[True, False])}


def fact_section(t2, s2, m) -> tuple[list[str], dict, list[str]]:
    lines = ["## 사실 추출", ""] + missing(("함정 2단계", t2), ("합성 2단계", s2), ("사례 10건 × 5회", m))
    items = {name: f(r) for name, r, f in (("함정 2단계", t2, stage_facts), ("합성 2단계", s2, stage_facts),
                                           ("사례 10건 × 5회", m, case_facts)) if r}
    if not items:
        return lines, {}, []
    if len(items) > 1:
        items["합침"] = [x for v in list(items.values()) for x in v]
    data = {name: facts(v) for name, v in items.items()}
    head = ["| 지표 | " + " | ".join(data) + " |", "|---" * (len(data) + 1) + "|"]
    lines += ["F08·F16은 있고 없음만, F12는 개수만 비교한다 (규칙 엔진이 판정에 쓰는 방식). 목록형 집합 F1은 이름까지 본다.",
              "적혀 있지 않은 사실(null)은 범주형에서 '없음' 한 부류, 목록형에서 빈 목록으로 본다.", "", *head,
              "| 채점한 사실 (계획서 × 항목) | " + " | ".join(str(v["n"]) for v in data.values()) + " |",
              "| 항목 정확도 | " + " | ".join(show(v["accuracy"]) for v in data.values()) + " |",
              "| 범주형 매크로 F1 (12개 항목) | " + " | ".join(num(v["macro_f1"]) for v in data.values()) + " |",
              "| 목록형 집합 F1 (F07·F08·F12·F16) | " + " | ".join(num(v["set"]["f1"]) for v in data.values()) + " |",
              "| 있다/없다 정밀도 | " + " | ".join(show(v["found_precision"]) for v in data.values()) + " |",
              "| 있다/없다 재현율 | " + " | ".join(show(v["found_recall"]) for v in data.values()) + " |", ""]
    pooled = data[list(data)[-1]]
    appendix = ["### 사실 추출 · 항목별 정확도", "", "| 항목 | 이름 | " + " | ".join(data) + f" | F1 ({list(data)[-1]}) |",
                "|---" * (len(data) + 3) + "|"]
    for k in FACTS:
        score = pooled["macro_f1_per_key"].get(k) if k in CATEGORICAL else (pooled["set_per_key"].get(k) or {}).get("f1")
        appendix.append(f"| {k} | {FACT_LABELS[k]} | " + " | ".join(show(v["per_key"].get(k), True) for v in data.values())
                        + f" | {num(score)} |")
    return lines, data, appendix + [""]


# 합성 출처별 ------------------------------------------------------------------------------------------------------------
def origin(c: dict) -> str:
    return (c.get("strata") or {}).get("origin") or "없음"


def origin_section(s1: dict | None, s2: dict | None) -> tuple[list[str], dict]:
    """합성 계획서를 출처(시나리오 생성·CRIS 원본 변형)별로 나눠 경로·위원회·헛경고·사실 추출을 비교한다."""
    lines = ["## 합성 계획서 · 출처별", ""] + missing(("합성 1단계", s1), ("합성 2단계", s2))
    if not (s1 or s2):
        return lines, {}
    part = lambda run, o: run and {**run, "cases": [c for c in run["cases"] if origin(c) == o]}  # noqa: E731
    cols = {o: (part(s1, o), part(s2, o)) for o in ordered({origin(c) for r in (s1, s2) if r for c in r["cases"]}, ORIGINS)}
    cols["합침"] = (s1, s2)
    data = {}
    for name, (r1, r2) in cols.items():
        d = data[name] = {}
        for stage, r in (("1단계", r1), ("2단계", r2)):
            if r:
                d[f"경로 {stage}"], d[f"위원회 {stage}"] = routes(route_pairs(r))["accuracy"], committee(r)
        if r2:
            d["사실"] = facts(stage_facts(r2))
        if r1 and r2:
            d["헛경고"] = false_warnings(r1, r2)
    row = lambda name, f: f"| {name} | " + " | ".join(f(d) for d in data.values()) + " |"  # noqa: E731
    fact = lambda d, key: (d.get("사실") or {}).get(key)  # noqa: E731
    lines += ["CRIS 원본 변형은 실제 등록 연구(CRIS) 8건의 요약을 바꿔 만든 계획서라 문장이 실제에 가깝다. 시나리오 생성은 새로 지어낸 계획서다.", "",
              "| 지표 | " + " | ".join(data) + " |", "|---" * (len(data) + 1) + "|"]
    for stage in ("1단계", "2단계"):
        if f"경로 {stage}" in data["합침"]:
            lines += [row(f"경로 정확도 · {stage}", lambda d, s=stage: show(d.get(f"경로 {s}"), True)),
                      row(f"위원회 종류 정확도 · {stage}", lambda d, s=stage: show(d.get(f"위원회 {s}"), True))]
    if "헛경고" in data["합침"]:
        lines += [row("헛경고가 1건 이상인 계획서 · 2단계", lambda d: show((d.get("헛경고") or {}).get("cases"), True)),
                  row("계획서당 헛경고 (건) · 2단계", lambda d: num((d.get("헛경고") or {}).get("per_case")))]
    if "사실" in data["합침"]:
        lines += [row("사실 항목 정확도 · 2단계", lambda d: show(fact(d, "accuracy"), True)),
                  row("범주형 매크로 F1 · 2단계", lambda d: num(fact(d, "macro_f1"))),
                  row("목록형 집합 F1 · 2단계", lambda d: num((fact(d, "set") or {}).get("f1"))),
                  row("있다/없다 정밀도 · 2단계", lambda d: show(fact(d, "found_precision"))),
                  row("있다/없다 재현율 · 2단계", lambda d: show(fact(d, "found_recall")))]
    return lines + [""], data


# 개인정보 가림--------------------------------------------------------------------------------------------------------------
def masking(cases: list[dict]) -> dict:
    """심어 둔 가상 개인정보(pii_gold)를 지금 코드로 다시 가린다. 정답 항목이 가린 글에서 사라지면 맞힘, 남으면 놓침.
    헛가림 = 계획서마다 그 종류로 가린 수 − 정답 항목이 사라진 자리 수 (0 아래는 0). 같은 이름을 두 번 가려도 헛가림이 아니다."""
    tp, fn, fp, absent = Counter(), Counter(), Counter(), 0
    for c in cases:
        text, log = pii.mask(c["plan"])
        gone = Counter()
        for g in c["pii_gold"]:
            before, after = c["plan"].count(g["text"]), text.count(g["text"])
            absent += not before
            if before:
                (fn if after else tp)[g["type"]] += 1
                gone[g["type"]] += before - after
        for x in log:
            fp[x["type"]] += max(0, x["count"] - gone[x["type"]])
    score = lambda a, b, c: {"tp": a, "fn": b, "fp": c, "precision": prop(a, a + c), "recall": prop(a, a + b),  # noqa: E731
                             "f1": f1(a, c, b)}
    types = ordered({t for x in (tp, fn, fp) for t in x}, ["이름", "전화번호", "이메일", "주민번호"])
    return {"cases": len(cases), "absent": absent, "전체": score(sum(tp.values()), sum(fn.values()), sum(fp.values())),
            **{t: score(tp[t], fn[t], fp[t]) for t in types}}


def masking_section(runs: list[dict | None], pert: dict | None) -> tuple[list[str], dict]:
    seen, cases = set(), []
    for run in runs:
        for c in (run or {}).get("cases", []):
            if "plan" in c and "pii_gold" in c and (c["kind"], c["id"]) not in seen:
                seen.add((c["kind"], c["id"]))
                cases.append(c)
    lines, data = ["## 개인정보 가림", ""], {}
    if cases:
        data = masking(cases)
        lines += [f"심어 둔 가상 이름·전화번호·이메일을 지금 코드로 다시 가렸다 (계획서 {data['cases']}건).", "",
                  "| 종류 | 정답 항목 | 가린 정답 | 헛가림 | 정밀도 | 재현율 | F1 |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {t} | {v['tp'] + v['fn']} | {v['tp']} | {v['fp']} | {show(v['precision'])} | {show(v['recall'])} | "
                  f"{num(v['f1'])} |" for t, v in data.items() if isinstance(v, dict)]
        lines += [""] + ([f"정답 항목 {data['absent']}개는 계획서에 없어 뺐다.", ""] if data["absent"] else [])
    else:
        lines += ["가림 정답(pii_gold) 없음", ""]
    if pert:
        s = pert["summary"]
        data["이전 측정"] = prop(s["pii_ok"], s["pii_total"])
        lines += [f"이전 측정 (perturbation.json, 수정 전 코드) · 재현율만: {show(data['이전 측정'], True)}", ""]
    return lines, data


# 한계 -------------------------------------------------------------------------------------------------------------------
def limits(ind: dict | None, m: dict | None, t2: dict | None, s2: dict | None) -> list[str]:
    s, t = (ind or {}).get("synth"), (ind or {}).get("traps")
    both = f"{(s or {}).get('n', 20) + (t or {}).get('n', 20)}건(합성 {(s or {}).get('n', 20)}·함정 {(t or {}).get('n', 20)})"
    lines = [f"- 정답은 우리가 만들었다. 무작위 {both}을 만든 쪽이 아닌 에이전트가 원문만 보고 따로 단 정답과의 일치율로 보완한다."]
    lines += [f"  - 합성: 경로 {show(prop(s['agree_route'], s['n']), True)} · 위원회 종류 "
              f"{show(prop(s['agree_committee'], s['n']), True)}"] if s else []
    lines += [f"  - 함정: 기대 상태 {show(prop(t['agree_expect'], t['n']), True)} · 경로 "
              f"{show(prop(t['agree_route'], t['n']), True)}"] if t else []
    lines += [] if s or t else ["  - 독립 확인 결과 없음"]
    cris = (m or {}).get("summary", {})
    lines.append("- 실제 심의 통과·탈락 정답은 없다. 바깥 정답은 CRIS 실제 연구의 관할 유형뿐이다"
                 + (f" (소속 기관 IRB가 승인한 {cris['cris_same']}건 중 {cris['cris_match']}건 일치)." if "cris_match" in cris else "."))
    part = " · ".join(f"{k} {len(r['cases'])}건" for k, r in (("함정", t2), ("합성", s2)) if r) or "약 100건"
    lines += [f"- 가상 계획서다. 2단계는 층화해 뽑은 일부({part})이고 1회 실행이다.",
              "- 기존 함정 32건·대조군 10건은 개발 중 규칙을 고치는 데 쓴 '개발용'이라 이 표에서 뺐다. "
              "600건은 기능 동결 뒤 코드로 한 번만 쟀고, 결과를 보고 규칙을 고치지 않았다.",
              "- 신뢰구간은 건을 서로 독립으로 보고 계산했다. 한 계획서의 여러 규칙, 같은 계획서의 반복 실행이 묶여 있어 실제보다 좁을 수 있다.",
              "- 독립 확인 함정 불일치 3건 중 2건(E4·R-13)은 말뜻 차이다. 독립 쪽이 '해당'으로 답했지만 내용은 우리 정답과 같다. "
              "1건(C3 '구두 동의만')은 우리 정답이 틀렸을 수 있다. 경로 불일치 1건(S7 부정문)은 함정 문장에 가명처리 줄이 남아 생긴 모순이다. "
              "독립 채점자의 문맥에 프로젝트 CLAUDE.md(경로 규칙 요약 몇 줄)가 자동으로 들어갔다.",
              "- 두 정답표의 해석이 다른 곳이 있다. 가명 자료에 동의가 적혀 있지 않으면 합성은 A(동의 없음으로 봄), 함정은 미정(연구자에게 물음)으로 적었다. "
              "IRB 없는 기관에 협약 정보가 없으면 둘 다 미정인데, 엔진은 B로 낸다."]
    return lines


def main(a: argparse.Namespace) -> None:
    t1, t2, s1, s2, ind = (load(p) for p in (a.stage1, a.stage2, a.synth1, a.synth2, a.independent))
    m, pert = load(RESULTS / "metrics.json"), load(RESULTS / "perturbation.json")
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    commits = [f"{k} {r.get('commit') or '?'}" for k, r in (("합성 1단계", s1), ("합성 2단계", s2), ("함정 1단계", t1), ("함정 2단계", t2))
               if r] + [f"가림 재측정 {head or '?'}"]
    lines = [f"# 표준 지표 — 평가용 합성 데이터(Claude Code로 생성) · 측정 커밋 {head or '?'} · 엔진 동결본 206ba17", "",
             "계획서는 모두 가상(합성)이고, 정답은 T3 확인 전 초안이다.", "",
             f"입력 커밋: {' · '.join(commits)}", "",
             "1단계 = 정답 사실을 넣고 규칙 엔진만 돌렸다. 2단계 = AI가 뽑은 사실을 고치지 않고 판정했다. 대괄호는 윌슨 95% 신뢰구간이다.", ""]
    route_lines, route, route_app = route_section(t1, t2, s1, s2, m)
    trap_lines, trap = trap_section(t1, t2)
    warn_lines, warn = warning_section(s1, s2)
    warn_lines += negation_section(t2, (t2 or t1 or {}).get("alarm", {}))
    judge_lines, judge, judge_app = judgment_section(t1, t2, s1, s2)
    fact_lines, fact, fact_app = fact_section(t2, s2, m)
    origin_lines, by_origin = origin_section(s1, s2)
    mask_lines, mask = masking_section([t1, t2, s1, s2], pert)
    lines += [*route_lines, *trap_lines, *warn_lines, *judge_lines, *fact_lines, *origin_lines, *mask_lines,
              "## 한계", "", *limits(ind, m, t2, s2), ""]
    appendix = ([*(["### 경로 혼동행렬 (행 = 정답, 열 = 에이전트)", ""] if route_app else []), *route_app]
                + judge_app + fact_app)
    lines += ["## 부록", "", *appendix] if appendix else []
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "standard_metrics.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    data = {"commits": commits, "routes": route, "traps": trap, "false_warnings": warn, "judgments": judge, "facts": fact,
            "synth_by_origin": by_origin, "masking": mask, "independent": ind}
    (a.out / "standard_metrics.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage1", type=Path, default=RESULTS / "traps300_stage1.json", help="함정 1단계 (정답 사실)")
    ap.add_argument("--stage2", type=Path, default=RESULTS / "traps300_stage2.json", help="함정 2단계 (AI 추출)")
    ap.add_argument("--synth1", type=Path, default=RESULTS / "synth300_stage1.json", help="합성 1단계")
    ap.add_argument("--synth2", type=Path, default=RESULTS / "synth300_stage2.json", help="합성 2단계")
    ap.add_argument("--independent", type=Path, default=RESULTS / "independent40.json", help="독립 정답과의 일치 수")
    ap.add_argument("--out", type=Path, default=RESULTS, help="결과를 쓸 폴더")
    main(ap.parse_args())
