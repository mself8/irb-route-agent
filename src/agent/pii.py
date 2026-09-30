"""② 개인정보 마스킹 (규칙). LLM에 넘기기 전에 계획서의 이름·전화번호·이메일·주민번호를 가린다.

- 검출: ko-pii 1.16.0(규칙·사전·체크섬 기반, ML 없음) + 정규식(전화번호·이메일·주민번호) 보강.
- 이름은 ko-pii가 "소화기내(과)"·"수행기관"처럼 일반 낱말도 잡으므로, 항목명("연구책임자:" 등) 바로 뒤이거나
  호칭("교수" 등) 앞에 올 때만 가린다. 가림이 지나치면 ③의 원문 인용이 깨지기 때문이다.
- 규칙 기반이라 같은 입력에 같은 결과가 나온다. 놓치는 개인정보가 있을 수 있어 화면에 "보조 수단"임을 밝힌다.
"""
import re

import ko_pii

TOKENS = {"PERSON": "이름", "PHONE": "전화번호", "EMAIL": "이메일", "RRN": "주민번호"}
ORDER = ["이름", "전화번호", "이메일", "주민번호"]

# 정규식 보강 (ko-pii가 놓칠 수 있는 형식)
PATTERNS = {
    "PHONE": re.compile(r"(?<!\d)(?:01[016789]|0\d{1,2})-\d{3,4}-\d{4}(?!\d)"),
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "RRN": re.compile(r"(?<!\d)\d{6}-[1-8]\d{6}(?!\d)"),
}
NAME_LABEL = re.compile(r"(연구책임자|책임연구자|공동연구자|연구자|담당자|성명|이름|대표)\s*[:：]?\s*$")
NAME_TITLE = re.compile(r"^\s*(교수|박사|선생|연구원|전공의|간호사|님)")
HANGUL_NAME = re.compile(r"^[가-힣]{2,4}$")
# ko-pii가 못 찾은 이름도 "항목명: 이름" 꼴이면 가린다 (콜론 필수, 뒤에 한글이 이어지면 낱말의 일부로 본다)
NAME_AFTER_LABEL = re.compile(r"(?:연구책임자|책임연구자|공동연구자|담당자|성명|이름)\s*[:：]\s*([가-힣]{2,4})(?![가-힣])")


def _is_name(text: str, start: int, end: int) -> bool:
    if not HANGUL_NAME.match(text[start:end]):
        return False
    line_before = text[:start].rsplit("\n", 1)[-1]
    return bool(NAME_LABEL.search(line_before) or NAME_TITLE.match(text[end:]))


def _spans(text: str) -> list[tuple[int, int, str]]:
    found = [(d.start, d.end, TOKENS[d.label]) for d in ko_pii.detect_all(text, include=TOKENS)
             if d.label != "PERSON" or _is_name(text, d.start, d.end)]
    found += [(m.start(), m.end(), TOKENS[label]) for label, pat in PATTERNS.items() for m in pat.finditer(text)]
    found += [(m.start(1), m.end(1), "이름") for m in NAME_AFTER_LABEL.finditer(text)]
    merged: list[tuple[int, int, str]] = []
    for s, e, t in sorted(found, key=lambda x: (x[0], -x[1])):
        if merged and s < merged[-1][1]:  # 겹치면 앞의 것(더 긴 것)을 둔다
            continue
        merged.append((s, e, t))
    return merged


def mask(text: str) -> tuple[str, list[dict]]:
    """(가린 계획서, mask_log). mask_log = [{"type": "이름", "count": 1}, …] 가린 것만."""
    out, last, counts = [], 0, dict.fromkeys(ORDER, 0)
    for s, e, t in _spans(text):
        out += [text[last:s], f"[{t}]"]
        last = e
        counts[t] += 1
    out.append(text[last:])
    return "".join(out), [{"type": t, "count": n} for t, n in counts.items() if n]
