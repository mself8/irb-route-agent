"""정답 전수 역검증과 교차 모델 합의: 693건(함정 300 · 대조군 93 · 합성 300)을 만든 쪽이 아닌 두 계열의 채점자가
원문만 보고 따로 정답을 단다(Claude 서브에이전트 · OpenAI Codex). 우리 정답과 비교해 일치율·합의율을 낸다.

  python eval/crosscheck.py sheet DIR    # DIR에 문제지(익명 번호·섞은 순서)와 허용 원문 사본을 만든다. 정답 대응표는 DIR 밖에 둔다
  python eval/crosscheck.py score DIR    # DIR/labels/<채점자>/*.json을 모아 eval/results/crosscheck.json · crosscheck.md
채점자는 DIR 안의 파일만 본다(규칙 파일·레포·우리 정답을 보지 않는다).
"""
import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from independent import CHECK_TOPIC, LABEL, TOLD_TOPIC, TOPIC  # noqa: E402

RES = ROOT / "eval" / "results"
KEY = RES / "crosscheck_key.json"  # 익명 번호 → 원래 id (채점자에게 주지 않는다)
SEED = 20261001
CHUNK = 100


def rule_topic(rule: str, inst: str, checks: dict) -> str:
    if rule.startswith("I-"):
        what = TOLD_TOPIC.get(rule) or CHECK_TOPIC.get(checks.get(rule, ""), "")
        return f"{inst} IRB 공개 안내의 '{what}'"
    return TOPIC.get(rule, rule)


def sheet(out: Path) -> None:
    traps = json.loads((ROOT / "eval/traps/traps300.json").read_text(encoding="utf-8"))["cases"]
    synth = json.loads((ROOT / "eval/synth/synth300.json").read_text(encoding="utf-8"))["cases"]
    checks = {c["rule"]: c["check"] for c in traps if c.get("check")}
    rng = random.Random(SEED)
    items, key = [], {}
    groups = [("T", [c for c in traps if c["kind"] == "trap"]), ("K", [c for c in traps if c["kind"] == "control"]), ("S", synth)]
    for prefix, cases in groups:
        cases = cases[:]
        rng.shuffle(cases)
        for i, c in enumerate(cases, 1):
            aid = f"{prefix}{i:03d}"
            item = {"id": aid, "institution": c["institution"], "plan": c["plan"]}
            if prefix == "T":
                item["topic"] = rule_topic(c["rule"], c["institution"], checks)
            elif prefix == "K":
                item["topics"] = [{"k": f"{aid}-{j}", "topic": rule_topic(r, c["institution"], checks)}
                                  for j, r in enumerate(c["satisfies"], 1)]
                key.update({f"{aid}-{j}": r for j, r in enumerate(c["satisfies"], 1)})
            else:
                item["target_start_date"] = c.get("target_start_date")
            key[aid] = c["id"]
            items.append(item)
    if out.exists():
        shutil.rmtree(out)
    (out / "sheet").mkdir(parents=True)
    for prefix in "TKS":
        part = [x for x in items if x["id"][0] == prefix]
        for n in range(0, len(part), CHUNK):
            (out / "sheet" / f"{prefix}{n // CHUNK + 1}.json").write_text(
                json.dumps({"items": part[n:n + CHUNK]}, ensure_ascii=False, indent=1), encoding="utf-8")
    src = out / "sources"
    for sub, pattern, base in (("laws", "10_원문_*.md", ROOT.parent / "prep" / "laws"),
                               ("notes", "*.md", ROOT / "data" / "institutions" / "notes"),
                               ("lists", "*.csv", ROOT / "data" / "lists"), ("schedules", "*.csv", ROOT / "data" / "schedules")):
        (src / sub).mkdir(parents=True)
        for p in base.glob(pattern):
            shutil.copy(p, src / sub / p.name)
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"문제지 {len(items)}건 → {out}/sheet ({len(list((out / 'sheet').glob('*.json')))}묶음) · 원문 {sum(1 for _ in src.rglob('*.*'))}개")


def score(out: Path) -> None:
    key = json.loads(KEY.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in json.loads((ROOT / "eval/traps/traps300.json").read_text(encoding="utf-8"))["cases"]}
    cases |= {c["id"]: c for c in json.loads((ROOT / "eval/synth/synth300.json").read_text(encoding="utf-8"))["cases"]}
    labels: dict[str, dict] = {}
    for d in sorted((out / "labels").iterdir()):
        got = {}
        for p in sorted(d.glob("*.json")):
            try:
                got |= {x["id"]: x for x in json.loads(p.read_text(encoding="utf-8"))["items"]}
            except Exception as e:  # noqa: BLE001
                print(f"{p}: 읽기 실패 {e}")
        labels[d.name] = got
    same = lambda a, b: a == b or {a, b} <= {"미충족", "경고"}  # noqa: E731
    rows = []
    for aid, cid in key.items():
        if "-" in aid:
            continue
        c = cases[cid]
        row = {"aid": aid, "id": cid, "set": {"T": "함정", "K": "대조군", "S": "합성"}[aid[0]]}
        for who, got in labels.items():
            x = got.get(aid)
            if x is None:
                row[who] = None
                continue
            r = {"route": x.get("route") == c["route_expected"]}
            if aid[0] == "T":
                rule = c["rule"] if c["rule"] in c["expect"] else next(iter(c["expect"]))
                r["answer"] = same(c["expect"][rule], LABEL.get(x.get("state"), x.get("state")))
            elif aid[0] == "K":
                marks = {y["k"]: y.get("state") for y in x.get("checks", [])}
                ks = [k for k in key if k.startswith(aid + "-")]
                r["answer"] = all(marks.get(k) not in (None, "위반") for k in ks) if ks else True
            else:
                r["answer"] = x.get("committee") == c.get("committee_expected")
            row[who] = r
        rows.append(row)
    who = list(labels)
    summary = {}
    for s in ("함정", "대조군", "합성"):
        part = [r for r in rows if r["set"] == s]
        summary[s] = {"n": len(part)}
        for w in who:
            done = [r[w] for r in part if r.get(w)]
            summary[s][w] = {"labelled": len(done), "answer": sum(x["answer"] for x in done), "route": sum(x["route"] for x in done)}
        both = [r for r in part if all(r.get(w) for w in who)]
        summary[s]["all_agree_answer"] = sum(all(r[w]["answer"] for w in who) for r in both)
        summary[s]["all_agree_route"] = sum(all(r[w]["route"] for w in who) for r in both)
        summary[s]["both_labelled"] = len(both)
        summary[s]["both_disagree_answer"] = sum(not any(r[w]["answer"] for w in who) for r in both)
    (RES / "crosscheck.json").write_text(json.dumps({"annotators": who, "summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    pct = lambda k, n: f"{k}/{n} ({100 * k / n:.1f}%)" if n else "—"  # noqa: E731
    lines = ["# 정답 전수 역검증 · 교차 모델 합의 (평가용 합성 데이터 693건)", "",
             "만든 쪽이 아닌 두 계열의 채점자가 법령 원문과 기관 조사 기록만 보고 정답을 따로 달았다. 번호는 익명, 순서는 섞었다. "
             "합의가 안 된 문항도 버리지 않고 남겼다(어려운 문항이 빠져 점수가 부풀지 않게).", "",
             "| 묶음 | 건수 | " + " | ".join(f"{w} · 정답 일치" for w in who) + " | " + " | ".join(f"{w} · 경로 일치" for w in who)
             + " | 셋 모두 정답 일치 | 둘 다 우리와 다름 |", "|---|---|" + "---|" * (2 * len(who) + 2)]
    for s, v in summary.items():
        lines.append(f"| {s} | {v['n']} | " + " | ".join(pct(v[w]["answer"], v[w]["labelled"]) for w in who) + " | "
                     + " | ".join(pct(v[w]["route"], v[w]["labelled"]) for w in who) + f" | {pct(v['all_agree_answer'], v['both_labelled'])}"
                     + f" | {v['both_disagree_answer']} |")
    lines += ["", "- 정답 일치: 함정은 뒤집은 규칙의 기대 결과, 대조군은 지킨 규칙을 위반으로 보지 않았는가, 합성은 위원회 종류.",
              "- '둘 다 우리와 다름'은 두 채점자가 모두 우리 정답과 다르게 답한 문항이다. 우리 정답이 틀렸을 가능성이 가장 큰 곳이라 사람이 먼저 본다.", ""]
    (RES / "crosscheck.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    {"sheet": sheet, "score": score}[sys.argv[1]](Path(sys.argv[2]))
