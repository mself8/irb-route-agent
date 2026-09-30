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
    items = []
    for c in traps:
        rule = c["rule"] if c["rule"] in c["expect"] else next(iter(c["expect"]))
        base = all_traps.get(f"CTL-{c['base']}", {}).get("plan")
        items.append({"id": c["id"], "kind": "함정", "inst": c["institution"], "lines": lines(base, c["plan"]),
                      "question": f"주제: {topic(c)}", "answer": f"{STATE.get(c['expect'][rule], c['expect'][rule])}",
                      "route": ROUTE.get(c["route_expected"], c["route_expected"]), "basis": c["source"]})
    for c in synth:
        items.append({"id": c["id"], "kind": "합성", "inst": c["institution"], "lines": lines(None, c["plan"]),
                      "question": "이 연구계획서는 어디에 심의를 신청해야 하나?",
                      "answer": COMMITTEE.get(c.get("committee_expected"), c.get("committee_expected")),
                      "route": ROUTE.get(c["route_expected"], c["route_expected"]), "basis": " → ".join(c.get("decision_trace", []))})
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
