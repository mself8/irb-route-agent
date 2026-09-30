"""함정 데이터 평가: 규칙을 정반대로 어긴 가상 계획서(eval/traps/traps.yaml)로 탐지·오경보·해소를 잰다.

모델 서버가 떠 있는 곳에서:
  python eval/trap_eval.py [--before eval/results/traps_v1.json]     # 실측 → traps.json·traps.md
  python eval/trap_eval.py --report eval/results/traps_v1.json         # 다시 돌리지 않고 표만 (→ traps_v1.md)
- 실제 모드(FAKE=0, LLM=1). 사람 확인 없이 ③ 추출값을 그대로 확정해 판정한다.
- 신호: 판정 행 "규칙:결과"(충족·미충족·판단불가), 보완 제안 "규칙:경고"(보완 필요·확인 필요), 경로 "경로:X".
  걸림 = 그 규칙의 미충족 또는 경고.
1. 탐지: 함정에서 뒤집은 규칙이 걸리고 대조군에서는 안 걸림(범위 규칙 T1·G1·S6은 충족이 새로 뜸). alt는 다른 규칙으로 드러난 것.
2. 오경보: (가) 규칙을 지킨 변형(expect 없음)에서 그 규칙이 걸림 (나) 대조군의 미충족 판정 (다) 함정에 기대 밖 새 경고.
   틀렸는지는 사람이 보고 VERDICT에 적는다.
3. 해소: 탐지된 함정에 그 규칙의 add_text를 넣고(fix: replace는 위반 문장 자리에, append는 끝에) 다시 돌려
   규칙이 풀리는가, 새 경고·경로 변화가 있는가.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

os.environ["FAKE"] = "0"  # 실제 그래프
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent import api  # noqa: E402

TARGET = "2026-12-01"
WORKERS = 4
FLAG = ("미충족", "경고")
RESULTS = ROOT / "eval" / "results"
# add_text의 [칸]을 채울 가상 값. 없는 칸은 괄호 안 글을 그대로 쓴다
FILL = {"기관명": "가나대학교", "항목": "나이·성별·처방 기록", "방법": "암호화 파일의 보안 전송", "데이터팀": "데이터팀",
        "담당 부서": "데이터팀", "결합전문기관": "결합전문기관", "가명화 절차": "가명처리", "반출 방법": "암호화 파일",
        "보안환경: 접근 통제·암호화 등": "접근 통제된 보안환경", "예: Case1": "Case1", "데이터 보관 기관": "가나보건연구원",
        "데이터 이름·항목·수집 기간": "노인 건강조사 데이터셋(나이, 성별, 거주 구, 우울 척도 점수)", "종류": "HIV 감염 여부",
        "접근 권한자": "데이터팀", "분석 장소": "원내 분석실", "이유": "후향적 기록 연구로", "N": "120", "n": "100", "x": "20",
        "선행연구(참고문헌) 또는 검정력 분석(효과크기·유의수준·검정력)": "검정력 분석(효과크기 0.3·유의수준 0.05·검정력 0.8)",
        "YYYY년 MM월 DD일": "2027년 8월 31일"}


def fill(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]", lambda m: FILL.get(m[1], m[1].split(":")[0].strip()), text)


def safe_run(job: tuple[str, str]) -> dict:
    """한 건이 실패해도(모델 서버 시간 초과 등) 나머지 결과는 남긴다. 한 번 더 시도한다."""
    for _ in range(2):
        try:
            return run(*job)
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
    return {"error": error, "route": "오류", "signals": [], "facts": {}, "add_text": {}, "seconds": 0}


def run(plan: str, institution: str) -> dict:
    """② 마스킹 → ③ 추출 → 추출값 그대로 확정 → 판정. 신호·경로·사실·보완 제안을 돌려준다."""
    t = time.time()
    p = api.start(plan, institution, TARGET)
    result = api.confirm(p.run_id, [f.model_dump() for f in p.facts]).model_dump()
    signals = {f"{r['rule_id']}:{r['result']}" for r in result["judgments"]}
    signals |= {f"{s['rule_id']}:경고" for s in result["suggestions"] or [] if s["level"] in ("보완 필요", "확인 필요")}
    return {"route": result["route"]["route"], "signals": sorted(signals),
            "facts": {f["key"]: f["value"] for f in result["facts"] if f.get("status") != "not_found"},
            "add_text": {s["rule_id"]: s.get("add_text") for s in result["suggestions"] or []},
            "seconds": round(time.time() - t, 1)}


def flagged(signals, rule: str) -> bool:
    return any(f"{rule}:{s}" in signals for s in FLAG)


def warnings(signals) -> set[str]:
    return {s for s in signals if s.rsplit(":", 1)[1] in FLAG}


def trap_plan(bases: dict, trap: dict) -> str:
    plan = bases[trap["base"]]["plan"]
    for old, new in trap["replace"]:
        assert plan.count(old) == 1, f"{trap['id']}: 대조군에 바꿀 글이 한 번만 있어야 한다 ({old[:30]}…)"
        plan = plan.replace(old, new)
    return plan


def fixed_plan(plan: str, trap: dict, add_text: str) -> str:
    text = fill(add_text)
    new = trap["replace"][0][1]
    return plan.replace(new, text) if trap["fix"] == "replace" and new else plan.rstrip() + "\n" + text


def score(spec: dict, raw: dict) -> list[dict]:
    """저장된 실행 결과로 함정마다 탐지·헛경고·해소를 매긴다. 실행 결과가 없는 함정(뒤에 추가한 것)은 건너뛴다."""
    rows = []
    for t in spec["traps"]:
        control, got = raw["controls"].get(t["base"]), raw["traps"].get(t["id"])
        if control is None or got is None:
            continue
        rule, expect, c, g = t["rule"], t["expect"], set(control["signals"]), set(got["signals"])
        hit, in_control = ((f"{rule}:충족" in g, f"{rule}:충족" in c) if expect == "충족" else (flagged(g, rule), flagged(c, rule)))
        alt = set(t.get("alt", []))
        row = {"id": t["id"], "rule": rule, "base": t["base"], "expect": expect,
               "scope": "지킨 변형" if expect == "없음" else "기관" if rule.startswith("I-") else "과거형" if rule == "PAST" else "법",
               "detected": hit and not in_control, "in_control": in_control, "alt_detected": sorted(alt & (g - c)),
               "trap_signals": sorted(s for s in g if s.split(":")[0] == rule),
               "unexpected": sorted(s for s in warnings(g - c) - alt if s.split(":")[0] != rule),
               "route_control": control["route"], "route_trap": got["route"], "error": control.get("error") or got.get("error")}
        fixed = raw.get("fixed", {}).get(t["id"])
        if fixed:
            f = set(fixed["signals"])
            row |= {"cleared": not flagged(f, rule), "route_fixed": fixed["route"],
                    "side_effects": sorted(warnings(f) - warnings(g) - warnings(c))}
        elif t.get("fix"):
            row["fix_result"] = "탐지 안 됨" if not row["detected"] else "add_text 없음"
        rows.append(row)
    return rows


def main(before: Path | None) -> None:
    spec = yaml.safe_load((ROOT / "eval" / "traps" / "traps.yaml").read_text(encoding="utf-8"))
    bases, traps = spec["bases"], spec["traps"]
    jobs = {f"base:{k}": (b["plan"], b["institution"]) for k, b in bases.items()}
    jobs |= {t["id"]: (trap_plan(bases, t), bases[t["base"]]["institution"]) for t in traps}
    api._graph()  # 그래프(체크포인터)를 먼저 하나 만든다. 스레드들이 처음에 동시에 만들면 서로 다른 그래프를 쥔다
    with ThreadPoolExecutor(WORKERS) as pool:
        out = dict(zip(jobs, pool.map(safe_run, jobs.values())))
    raw = {"commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                                    text=True).stdout.strip(),
           "controls": {k: out[f"base:{k}"] for k in bases}, "traps": {t["id"]: out[t["id"]] for t in traps}, "fixed": {}}
    by_id = {t["id"]: t for t in traps}
    fixes = {r["id"]: (fixed_plan(trap_plan(bases, by_id[r["id"]]), by_id[r["id"]], add), bases[r["base"]]["institution"])
             for r in score(spec, raw)
             if r["detected"] and by_id[r["id"]].get("fix") and (add := raw["traps"][r["id"]]["add_text"].get(r["rule"]))}
    with ThreadPoolExecutor(WORKERS) as pool:
        raw["fixed"] = dict(zip(fixes, pool.map(safe_run, fixes.values())))
    raw["rows"] = score(spec, raw)
    (RESULTS / "traps.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    report(spec, raw, RESULTS / "traps.md", before)


def report(spec: dict, raw: dict, dest: Path, before: Path | None = None) -> None:
    """실행 결과 → 규칙별 표 + 요약. 틀렸는지 사람이 본 것은 VERDICT, 한계는 LIMITS에 적는다."""
    rows = score(spec, raw)
    pct = lambda a, b: f"{a}/{b} ({round(100 * a / b)}%)" if b else "0/0"  # noqa: E731
    by = {s: [r for r in rows if r["scope"] == s] for s in ("법", "기관", "과거형", "지킨 변형")}
    control_bad = [(k, s) for k, c in raw["controls"].items() for s in c["signals"] if s.endswith(":미충족")]
    unexpected = [(r["id"], s) for r in rows for s in r["unexpected"]]
    tried = [r for r in rows if "cleared" in r]
    lines = [f"# 함정 데이터 평가 (커밋 {raw.get('commit', '?')} · 가상 계획서 · T3 확인 전 초안)", "",
             "규칙을 정반대로 어긴 계획서를 넣고, 사람 확인 없이 추출값 그대로 판정했다. 대조군은 같은 뼈대로 규칙을 지킨 계획서다.", "",
             "| 지표 | 값 |", "|---|---|",
             f"| 탐지율 · 법 규칙 | {pct(sum(r['detected'] for r in by['법']), len(by['법']))} |",
             f"| 탐지율 · 기관 규칙 | {pct(sum(r['detected'] for r in by['기관']), len(by['기관']))} |",
             f"| 기관 규칙을 못 잡았지만 법 규칙으로 드러남 | {sum(bool(r['alt_detected']) and not r['detected'] for r in by['기관'])}건 |",
             f"| 과거형 서술 (검사 없는 기관) | {pct(sum(r['detected'] for r in by['과거형']), len(by['과거형']))} |",
             f"| 헛경고 · 규칙을 지킨 변형 | {pct(sum(r['detected'] for r in by['지킨 변형']), len(by['지킨 변형']))} |",
             f"| 대조군 미충족 판정 | {len(control_bad)}건 (아래, 틀렸는지 사람이 확인) |",
             f"| 함정의 기대 밖 새 경고 | {len(unexpected)}건 (아래) |",
             f"| 해소율 | {pct(sum(r['cleared'] for r in tried), len(tried))} (보완 문장을 넣고 다시 판정) |",
             f"| 해소 부작용 | 새 경고 {sum(len(r['side_effects']) for r in tried)}건 · 경로가 대조군과 다름 "
             f"{sum(r['route_fixed'] != r['route_control'] for r in tried)}건 |", ""]
    if before:
        old = json.loads(before.read_text(encoding="utf-8"))
        prev = {r["id"]: r for r in score(spec, old)}
        lines += [f"## 1차({old.get('commit', '?')}) → 2차({raw.get('commit', '?')})", "",
                  "| 구분 | 1차 | 2차 |", "|---|---|---|"]
        for s in ("법", "기관", "과거형", "지킨 변형"):
            same = [r for r in by[s] if r["id"] in prev]
            lines.append(f"| {s} {'헛경고' if s == '지킨 변형' else '탐지'} (같은 함정 {len(same)}건) | "
                         f"{sum(prev[r['id']]['detected'] for r in same)} | {sum(r['detected'] for r in same)} |")
        changed = [f"- {r['id']}: {'O' if prev[r['id']]['detected'] else 'X'} → {'O' if r['detected'] else 'X'}"
                   for r in rows if r["id"] in prev and prev[r["id"]]["detected"] != r["detected"]]
        new = [r["id"] for r in rows if r["id"] not in prev]
        lines += ["", *(changed or ["- 결과가 바뀐 함정 없음"])]
        lines += [f"- 2차에 추가한 함정 {len(new)}건: {', '.join(new)}"] if new else []
        lines.append("")
    lines += ["## 규칙별", "", "| 규칙 | 함정 | 기대 | 함정에서 그 규칙 | 탐지 | 다른 신호 | 경로 대조→함정 | 해소 |",
              "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        fix = (("풀림" if r["cleared"] else "안 풀림") + (f" · 부작용 {', '.join(r['side_effects'])}" if r["side_effects"] else "")
               if "cleared" in r else r.get("fix_result", "—"))
        mark = ("헛경고" if r["detected"] else "헛경고 없음") if r["expect"] == "없음" else "O" if r["detected"] else "X"
        lines.append(f"| {r['rule']} | {r['id']} | {r['expect']} | {', '.join(r['trap_signals']) or '없음'} | "
                     f"{mark}{' (대조군에도 걸림)' if r['in_control'] else ''}{' · 실행 오류' if r['error'] else ''} | "
                     f"{', '.join(r['alt_detected']) or '—'} | {r['route_control']}→{r['route_trap']} | {fix} |")
    lines += ["", "## 대조군 미충족 판정 (규칙을 지킨 계획서)", ""]
    lines += [f"- {k}: {s} — {VERDICT.get((k, s), '확인 전')}" for k, s in control_bad] or ["- 없음"]
    lines += ["", "## 함정의 기대 밖 새 경고", ""]
    lines += [f"- {i}: {s} — {VERDICT.get((i, s), '확인 전')}" for i, s in unexpected] or ["- 없음"]
    lines += ["", "## 한계", "", *(LIMITS if dest.name == "traps.md" else ["- 최신 측정의 traps.md를 본다."])]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


ID_NEGATION = "틀림 · 추출 오류: '○○ 대신 연구번호를 쓴다'의 ○○를 기록하는 식별자(F16)로 뽑음"
EXPORT_ONLY = "틀림 · 사실 정의 문제: 반출만 하는데 결합 절차를 요구함. F06 하나에 결합과 반출이 묶여 D3(결합)이 충족으로 판정됨"
VERDICT: dict[tuple[str, str], str] = {  # (대조군·함정, 신호) → 사람이 본 판정
    ("smc", "E3:미충족"): ID_NEGATION, ("khmc", "E3:미충족"): ID_NEGATION,
    ("cmc", "R-13:미충족"): EXPORT_ONLY, ("snuh", "R-13:미충족"): EXPORT_ONLY,
    ("R11-no-idmgmt", "R-12:경고"): "맞음: 지운 문장에 대응표 분리 보관도 들어 있었음",
    ("R11-no-idmgmt", "R-12:미충족"): "맞음: 지운 문장에 대응표 분리 보관도 들어 있었음",
    ("PAST-done", "I-UOS-1:경고"): "추출 흔들림: 연구 유형(F01)을 대조군은 '관찰', 함정은 '기록 이용'으로 뽑아 심의면제 후보 여부가 갈림",
    ("cuk", "I-CUK-14:미충족"): "맞음: 대조군이 상담 비용 보호 조치를 적지 않음 (대조군은 I-CUK-1~6만 지키게 만들었다)",
    ("cuk", "I-CUK-15:미충족"): "헛경고: 연락처를 받지 않는 익명 설문인데 '즉시 파기' 문구를 요구함 (낱말 검사라 연락처를 받는지 보지 않음)"}
LIMITS = [
    "- 가상 계획서를 규칙마다 1~3건씩 한 번만 돌렸다. 비율보다 무엇을 잡고 놓쳤는지가 요점이다.",
    "- 추출 오류가 판정을 바꾼다.",
    "  - 신약을 12주 투여한다고 써도 제목이 '후향적 의무기록 연구'면 임상시험 아님(F10)으로 뽑아 경로 A로 간다 (T1).",
    "  - '○○ 대신 연구번호를 쓴다'의 ○○를 기록하는 식별자로 뽑아, 규칙을 지킨 계획서가 심의면제 불가(E3)가 된다 (대조군 smc·khmc).",
    "  - 받은 조사 데이터를 쓰는 연구의 유형이 '관찰'과 '기록 이용' 사이에서 흔들려 심의면제 후보 여부가 갈린다 (uos). "
    "그래서 I-UOS-2는 전제가 서지 않아 시험하지 못했다.",
    "- 사실 F06 하나에 결합과 반출이 묶여 있다. 반출만 하는 계획서에도 결합 절차(R-13) 경고가 뜬다 (대조군 cmc·snuh).",
    "- 기관 규정 검사는 낱말·정규식이다.",
    "  - 알린 낱말만 있으면 위반해도 충족이 된다 (I-KHMC-1-code-and-name: 연구번호와 함께 이름도 적음).",
    "  - 정규식에 없는 표현은 놓친다: 피동 과거 '진행되었다', 'ㅂ니다' 경어체 '드립니다'.",
    "  - 규정을 지킨 표현을 위반으로 잡는다: 선행연구를 과거형으로 소개한 문장, '만 19~24세'의 '24세'. "
    "연락처를 받지 않는 설문에도 '즉시 파기' 문구를 요구한다 (I-CUK-15).",
    "- 조건만 맞으면 늘 뜨는 기관 안내(I-SMC-4·I-AMC-1)는 위반 여부를 보지 않아 함정과 대조군을 가르지 못한다. 과거형 검사는 가톨릭대에만 있다.",
    "- 해소는 보완 문장을 넣고 다시 돌렸을 때 경고가 풀리는지만 본다. 대부분 낱말 검사라 문장만 넣으면 풀린다. 내용이 맞는지는 사람이 본다."]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, help="다시 돌리지 않고 이 실행 결과(json)로 표만 쓴다 (같은 이름의 .md)")
    ap.add_argument("--before", type=Path, help="비교할 이전 실행 결과(json)")
    a = ap.parse_args()
    if a.report:
        spec = yaml.safe_load((ROOT / "eval" / "traps" / "traps.yaml").read_text(encoding="utf-8"))
        report(spec, json.loads(a.report.read_text(encoding="utf-8")), a.report.with_suffix(".md"), a.before)
    else:
        main(a.before)
