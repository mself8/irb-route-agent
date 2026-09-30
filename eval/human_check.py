"""사람 표본 검수(④): 무작위 40건(독립 확인과 같은 표본)의 우리 정답이 맞는지 팀원이 브라우저에서 표시하고 결과 파일을 내려받는다.

  python eval/human_check.py build              # → eval/results/human_check40.html (인터넷 없이 파일로 연다)
  python eval/human_check.py score 파일.json …  # 팀원이 보낸 결과 파일 → 정답 정확도 (합격선 95%)
"""
import difflib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from independent import CHECK_TOPIC, TOLD_TOPIC, TOPIC, pick  # noqa: E402

RES = ROOT / "eval" / "results"
STATE = {"미충족": "위반이다", "경고": "위반이다(보완 필요)", "충족": "해당한다", "판단불가(나)": "계획서로는 알 수 없어 연구자에게 물어야 한다",
         "판단불가(①)": "위원회가 판단할 사항이다", "판단불가(②)": "평가·데이터 보유기관이 판단할 사항이다",
         "판단불가(③)": "기관 규정·기관 간 합의에 맡겨진 사항이다"}
ROUTE = {"A": "A · 가명 데이터를 동의 없이 → 데이터 보유기관 DRB + IRB", "B": "B · 공용기관생명윤리위원회", "C": "C · 소속 기관 IRB",
         "임상시험": "임상시험 · 식약처 승인 + 실시기관 심사위원회", "범위 밖": "범위 밖 · 배아·유전자 연구", "미정": "미정 · 계획서로는 관할을 정할 수 없음"}
COMMITTEE = {"own": "소속 기관 IRB", "public": "공용위원회", "contract": "위탁 협약한 다른 기관 IRB", "trial": "임상시험 심사위원회",
             "out": "범위 밖", "unknown": "정할 수 없음"}


import re  # noqa: E402

import yaml  # noqa: E402

ABBR = {"YR": "의약품 등의 안전에 관한 규칙 ", "MR": "의료기기법 시행규칙 ", "GL": "보건의료데이터 활용 가이드라인 ",
        "JG": "공용위원회 고시 ", "CG": "임상시험안전지원기관 고시 ", "L": "생명윤리법 ", "R": "생명윤리법 시행규칙 ",
        "P": "개인정보 보호법 ", "Y": "약사법 ", "M": "의료기기법 "}
FACT_NAME = {"F01": "연구 유형", "F02": "연구자가 식별정보 직접 열람", "F03": "받는 데이터 형태", "F04": "가명처리 주체", "F06": "타 기관 결합·반출",
             "F07": "민감정보", "F08": "취약 대상", "F09": "인체유래물", "F10": "의약품·기기 임상시험", "F11": "동의", "F12": "수행기관",
             "F14": "배아·유전자", "F16": "기록하는 식별자", "F17": "연구용 번호", "F18": "대응표 보관"}
SAY = {"미충족": "이 계획서는 요건을 지키지 못한다 → 위반", "경고": "요건이 요구하는 서술이 빠졌다 → 보완 필요", "충족": "이 계획서는 여기에 해당한다",
       "판단불가(나)": "계획서에 판단할 정보가 없다 → 연구자에게 묻는다", "판단불가(①)": "법이 위원회 판단에 맡긴 사항이다",
       "판단불가(②)": "평가어이거나 데이터 보유기관이 판단할 사항이다", "판단불가(③)": "기관 규정이나 기관 사이 합의에 맡겨진 사항이다"}


def plain(text: str) -> str:
    """판정규칙표의 링크·약어를 읽을 수 있는 글로 (예: [L제15조](…) → 생명윤리법 제15조)."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text).replace("**", "")
    text = re.sub(r"(?<![A-Za-z가-힣])(YR|MR|GL|JG|CG|L|R|P|Y|M)(?=제|\s|$| 부록| FAQ| 개요)", lambda m: ABBR[m[1]], text)
    return re.sub(r" {2,}", " ", text).strip()


def prep_table() -> dict:
    rows = {}
    for line in (ROOT.parent / "prep" / "laws" / "01_판정규칙표.md").read_text(encoding="utf-8").splitlines():
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"[A-Z]\d+", cells[0]):
            rows[cells[0]] = {"q": plain(cells[1]), "then": plain(cells[2]), "law": plain(cells[3]), "quote": plain(cells[4]).strip('"')}
    return rows


def legal_rules() -> dict:
    data = yaml.safe_load((ROOT / "data" / "rules" / "rules.yaml").read_text(encoding="utf-8"))
    return {r["id"]: r for r in (data if isinstance(data, list) else data.get("rules", data))}


def inst_rules() -> dict:
    out = {}
    for p in (ROOT / "data" / "institutions" / "profiles").glob("*.yaml"):
        prof = yaml.safe_load(p.read_text(encoding="utf-8"))
        out |= {r["id"]: {**r, "short": prof.get("short", prof["name"])} for r in prof.get("rules", [])}
    return out


def evidence(rule: str, state: str, legal: dict, inst: dict) -> dict:
    """규칙 하나의 판단 근거: 요건 · 판단 · 조문(또는 기관 공지)과 원문."""
    if rule in inst:
        r = inst[rule]
        return {"rule": rule, "need": f"{r['short']} 규정: {r['warning']}", "say": SAY.get(state, state),
                "src": r.get("source", ""), "quote": ""}
    r = legal.get(rule, {})
    b = r.get("basis", {})
    return {"rule": rule, "need": r.get("requirement", rule), "say": SAY.get(state, state),
            "src": f"{b.get('law', '')} {b.get('article', '')}".strip(), "quote": b.get("text", "")}


def topic(c: dict) -> str:
    r = c["rule"]
    return (f"{c['institution']} IRB 안내의 '{TOLD_TOPIC.get(r) or CHECK_TOPIC.get(c.get('check') or '', r)}'" if r.startswith("I-")
            else TOPIC.get(r, r))


def lines(base: str | None, plan: str) -> list[list]:
    """[종류, 글]: s 같음 · i 함정으로 넣거나 바꾼 줄 · d 뺀 줄."""
    if not base:
        return [["s", x] for x in plan.splitlines()]
    a, b, out = base.splitlines(), plan.splitlines(), []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        out += [["s", x] for x in b[j1:j2]] if op == "equal" else [["d", x] for x in a[i1:i2]] + [["i", x] for x in b[j1:j2]]
    return out


def build() -> None:
    traps, synth = pick()
    all_traps = {c["id"]: c for c in json.loads((ROOT / "eval/traps/traps300.json").read_text(encoding="utf-8"))["cases"]}
    legal, inst, prep = legal_rules(), inst_rules(), prep_table()
    fact_line = lambda g: " · ".join(f"{FACT_NAME[k]}={'없음' if v == [] else ', '.join(v) if isinstance(v, list) else v}"  # noqa: E731
                                     for k, v in g.items() if k in FACT_NAME and v is not None)
    items = []
    for c in traps:
        rule = c["rule"] if c["rule"] in c["expect"] else next(iter(c["expect"]))
        base = all_traps.get(f"CTL-{c['base']}", {}).get("plan")
        ls = lines(base, c["plan"])
        changed = [t for k, t in ls if k == "i"] or [f"(삭제) {t}" for k, t in ls if k == "d"]
        items.append({"id": c["id"], "kind": "함정", "inst": c["institution"], "lines": ls,
                      "question": f"주제: {topic(c)}", "answer": f"{STATE.get(c['expect'][rule], c['expect'][rule])}",
                      "route": ROUTE.get(c["route_expected"], c["route_expected"]), "changed": changed,
                      "why": [evidence(r, st, legal, inst) for r, st in c["expect"].items()],
                      "facts": fact_line(c["facts_gold"]), "basis": c["source"]})
    for c in synth:
        steps = [{"id": t, **prep[t]} for t in c.get("decision_trace", []) if t in prep]
        items.append({"id": c["id"], "kind": "합성", "inst": c["institution"], "lines": lines(None, c["plan"]),
                      "question": "이 연구계획서는 어디에 심의를 신청해야 하나?",
                      "answer": COMMITTEE.get(c.get("committee_expected"), c.get("committee_expected")),
                      "route": ROUTE.get(c["route_expected"], c["route_expected"]), "steps": steps,
                      "facts": fact_line(c["facts_gold"]), "basis": "사전 판정규칙표의 결정 순서"})
    page = (Path(__file__).with_name("human_check_template.html").read_text(encoding="utf-8")
            .replace("/*DATA*/[]", json.dumps(items, ensure_ascii=False)).replace("{{DATE}}", date.today().isoformat()))
    (RES / "human_check40.html").write_text(page, encoding="utf-8")
    print(f"{len(items)}건 → {RES / 'human_check40.html'}")


def score(paths: list[str]) -> None:
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        v = [x["verdict"] for x in d["items"] if x.get("verdict")]
        ok, bad = v.count("O"), v.count("X")
        rate = ok / (ok + bad) if ok + bad else 0
        print(f"{d.get('checker', '?')}: 표시 {len(v)}/40 · 맞음 {ok} · 틀림 {bad} · 모름 {v.count('?')} · "
              f"정답 정확도 {100 * rate:.1f}% ({'합격' if rate >= 0.95 else '미달'}, 합격선 95%)")
        for x in d["items"]:
            if x.get("verdict") == "X":
                print(f"  틀림 {x['no']} {x['id']}: {x.get('memo', '')}")


if __name__ == "__main__":
    build() if sys.argv[1] == "build" else score(sys.argv[2:])
