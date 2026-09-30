"""규칙표 원문 대조: data/rules/rules.yaml의 basis.text가 prep 원문 자료에 글자 그대로 있는지,
법령 규칙이면 그 문장이 basis.article의 조문 절 안에 있는지 확인한다. rules.yaml은 고치지 않고 목록만 낸다.

실행: python eval/check_rules_text.py [prep 폴더]   (기본: 레포 옆의 ../prep)
대조 기준: 공백·줄바꿈 차이만 무시한다. 가운뎃점(ㆍ/·)과 인용 생략(…)도 원문 그대로여야 한다.
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREP = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "prep"
LAW_FILES = {  # rules.yaml basis.law 앞부분 → prep 원문 파일
    "생명윤리법 시행규칙": "10_원문_생명윤리법_시행규칙.md",
    "생명윤리법": "10_원문_생명윤리법.md",
    "개인정보 보호법": "10_원문_개인정보보호법.md",
    "약사법": "10_원문_약사법_의약품안전규칙.md",
    "의료기기법": "10_원문_의료기기법.md",
}


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s.replace("> ", ""))


def sections(md: str) -> dict[str, str]:
    """'## 제N조(…)' 절 제목 → 본문."""
    parts = re.split(r"^## ", md, flags=re.M)
    return {p.split("\n", 1)[0]: p for p in parts[1:]}


def found_in(text: str, corpus: str) -> bool:
    """인용 생략(…)이 있으면 조각들이 순서대로 모두 있어야 한다."""
    pos = 0
    for piece in [squash(p) for p in text.split("…") if p.strip()]:
        pos = corpus.find(piece, pos)
        if pos < 0:
            return False
        pos += len(piece)
    return True


def main() -> int:
    rules = yaml.safe_load((ROOT / "data" / "rules" / "rules.yaml").read_text(encoding="utf-8"))
    all_md = {p.name: p.read_text(encoding="utf-8") for p in sorted(PREP.rglob("*.md")) if "raw" not in p.parts}
    all_md.update({p.name: p.read_text(encoding="utf-8") for p in (PREP / "institutions" / "raw").rglob("eirb_*.txt")})
    corpus_all = {name: squash(md) for name, md in all_md.items()}

    problems = 0
    for r in rules:
        b = r["basis"]
        text, article, law = b.get("text", ""), str(b.get("article", "")), b.get("law", "")
        if law.startswith("팀"):
            print(f"[팀 결정] {r['id']}: 법령 인용이 아니라 팀 결정이라 대조하지 않음 — {text[:40]}")
            continue
        if "(현장 확인 후 기입)" in text:
            print(f"[미기입] {r['id']}: 원문 칸이 비어 있음")
            problems += 1
            continue
        hits = [name for name, c in corpus_all.items() if found_in(text, c)]
        if not hits:
            print(f"[원문 불일치] {r['id']} ({law} {article}): prep 어디에도 글자 그대로 없음 — {text[:60]}")
            problems += 1
            continue
        law_file = next((f for key, f in LAW_FILES.items() if law.startswith(key)), None)
        m = re.match(r"(제\d+조(?:의\d+)?)", article)
        if law_file and m:
            secs = sections(all_md[law_file])
            sec = next((body for title, body in secs.items() if title.startswith(m.group(1) + "(")), None)
            if sec is None:
                print(f"[조문 없음] {r['id']}: {law_file}에 {m.group(1)} 절이 없음")
                problems += 1
            elif not found_in(text, squash(sec)):
                where = [t.split("(")[0] for t, body in secs.items() if found_in(text, squash(body))]
                print(f"[조문 번호 불일치] {r['id']}: 원문은 {where or hits}에 있는데 article은 {article}")
                problems += 1
        print(f"[일치] {r['id']} ({law} {article}) ← {', '.join(hits[:2])}")
    print(f"\n규칙 {len(rules)}개 중 문제 {problems}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
