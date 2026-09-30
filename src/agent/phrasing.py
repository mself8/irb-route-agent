"""⑨ 사무국 질문 다듬기 (AI). 판단불가 (가) 항목의 틀 문장을 사무국에 바로 보낼 문장으로 바꾼다.

- 여러 항목을 한 번의 호출로 묶어 JSON으로 받는다 (데모 대기 시간).
- 항목마다 관련 조문·가이드라인 문단 1~2개를 근거 검색(retrieve.search, BM25)으로 찾아 참고로 넣는다 (RAG).
  검색은 판정에 쓰지 않는다. 같은 문단은 references(item)로 화면 근거 보기에도 쓴다.
- 다듬은 문장은 아래 검사를 모두 통과해야 쓴다. 하나라도 걸리면 그 항목은 None이고, 틀 문장을 그대로 쓴다.
  1. 큰따옴표 인용은 입력으로 준 글(계획서·참고 문단·근거·쟁점)에 글자 그대로 있어야 한다.
  2. 근거의 법령명과 조문을 basis 값 그대로 쓴다.
  3. 입력(계획서·근거·참고 문단)에 없던 숫자를 만들지 않는다.
  4. "승인됩니다"·"면제 대상입니다"처럼 판정하는 말을 쓰지 않는다 (인용문 밖에서).
  5. 2~3문장, 존댓말 (인용문 밖에서).
- 판정은 바꾸지 않는다. 판정은 규칙 엔진(judge.py)만 한다.
"""
import json
import re

from openai import OpenAI

from . import retrieve
from .llm import BASE_URL, MODEL, locate

VERDICT = re.compile(r"승인됩니다|승인될|승인받을 수 있|면제됩니다|면제될|면제 대상입니다|면제 대상에 해당|해당합니다|해당됩니다|"
                     r"대상입니다|필요 없습니다|필요하지 않습니다|문제없|문제가 없|가능합니다|불가능합니다|불가합니다|통과")
QUOTE = re.compile(r"[\"“]([^\"”]+)[\"”]")
NUMBER = re.compile(r"\d+|[①-⑳]")
HONORIFIC_END = re.compile(r"(니다|니까|세요|십시오|까요)[.?]$")
REF_CHARS = 400  # 프롬프트에 넣는 참고 문단 길이

SYSTEM = (
    "너는 연구윤리 사무국에 보낼 문의 문장을 다듬는다. 판정하지 않고 확인을 요청할 뿐이다.\n"
    "항목마다 2~3문장의 존댓말 문의를 쓴다.\n"
    "1. 첫 문장에 근거 법령명과 조문을 주어진 글자 그대로 쓴다.\n"
    "2. 연구 내용은 계획서에 있는 사실만 쓴다. 계획서를 인용할 때는 큰따옴표로 감싸고 한 글자도 바꾸지 않는다.\n"
    "3. 참고 근거는 필요할 때만 쓰고, 인용할 때는 큰따옴표로 감싸 원문 그대로 옮긴다. 참고 근거에 없는 내용은 쓰지 않는다.\n"
    "4. 새 조문·숫자·결론을 만들지 않는다. '승인됩니다', '면제 대상입니다', '해당합니다', '가능합니다'처럼 "
    "판정하는 말을 쓰지 않는다.\n"
    "5. 마지막 문장은 위원회나 사무국의 확인을 요청하는 문장이다."
)


def _refs(item: dict, k: int = 2) -> list[dict]:
    """판정 행의 요건·근거로 관련 문단을 찾는다.

    이미 근거로 단 문단, 점수가 1위의 40%에 못 미치는 약한 문단, 인체유래물 연구가 아닌데 걸린 인체유래물 조문은 뺀다.
    """
    basis = item.get("basis") or {}
    query = " ".join(str(x) for x in (item.get("reason"), basis.get("law"), basis.get("article"), basis.get("text")) if x)
    hits = retrieve.search(query, k + 4)
    if not hits:
        return []
    own = re.sub(r"\s+", "", basis.get("text") or "")[:20]
    keep = [r for r in hits
            if r["점수"] >= 0.4 * hits[0]["점수"]
            and not (own and own in re.sub(r"\s+", "", r["원문"]))
            and ("인체유래물" not in r["조항"] or "인체유래물" in query)]
    return keep[:k]


def references(item: dict) -> list[dict]:
    """화면 근거 보기용 참고 근거 [{문서명, 조항, url}]. 모델 없이 검색만 한다 (같은 항목엔 늘 같은 결과)."""
    return [{"문서명": r["문서명"], "조항": r["조항"], "url": r["url"]} for r in _refs(item)]


def _schema(n: int) -> dict:
    item = {"type": "object", "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
            "required": ["id", "text"], "additionalProperties": False}
    return {"type": "object", "properties": {"questions": {"type": "array", "items": item, "minItems": n, "maxItems": n}},
            "required": ["questions"], "additionalProperties": False}


def _call(payload: dict, n: int) -> dict:
    client = OpenAI(base_url=BASE_URL, api_key="local", timeout=30, max_retries=0)  # 늦으면 틀 문장으로 간다
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=300 * n + 200,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        response_format={"type": "json_schema", "json_schema": {"name": "questions", "schema": _schema(n)}},
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return json.loads(resp.choices[0].message.content)


def check(text: str, item: dict, masked_text: str, refs: list[dict] = ()) -> bool:
    """다듬은 문장이 조건을 모두 지키는가."""
    basis = item.get("basis") or {}
    law, article = basis.get("law", ""), str(basis.get("article", ""))
    if not law or law not in text or article not in text:
        return False
    # 인용해도 되는 글: 계획서, 참고 문단(문서명·조항·원문), 근거, 쟁점과 틀 문장. 이 밖의 인용은 지어낸 것으로 본다
    given = [law, article, basis.get("text", ""), item.get("reason", ""), item.get("question", "")]
    sources = [masked_text, *given, *(r[key] for r in refs for key in ("문서명", "조항", "원문"))]
    if any(all(locate(q, s) is None for s in sources if s) for q in QUOTE.findall(text)):
        return False
    allowed = set(NUMBER.findall(" ".join(sources)))
    if not set(NUMBER.findall(text)) <= allowed:
        return False
    bare = QUOTE.sub('"인용"', text)  # 인용문 안의 마침표·법령 문구는 문장 검사에서 뺀다
    if VERDICT.search(bare):
        return False
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", bare.strip()) if s]
    return 2 <= len(sentences) <= 3 and all(HONORIFIC_END.search(s) for s in sentences)


def polish(items: list[dict], masked_text: str, facts: list[dict]) -> list[str | None]:
    """(가) 항목마다 다듬은 문장 또는 None (검사에 걸리거나 모델 호출이 실패하면 None → 틀 문장 사용)."""
    if not items:
        return []
    refs = [_refs(it) for it in items]
    known = [{"사실": f["label"], "값": f["value"]} for f in facts if f.get("status") == "found"]
    payload = {
        "계획서": masked_text,
        "확인된 사실": known,
        "문의할 항목": [{"id": i, "법령명": (it.get("basis") or {}).get("law"), "조문": (it.get("basis") or {}).get("article"),
                     "쟁점": it.get("reason"), "틀 문장": it.get("question"),
                     "참고 근거": [{"문서명": r["문서명"], "조항": r["조항"], "원문": r["원문"][:REF_CHARS]} for r in refs[i]]}
                    for i, it in enumerate(items)],
    }
    try:
        answers = {q["id"]: q["text"].strip() for q in _call(payload, len(items))["questions"]}
    except Exception:  # 서버가 없거나 응답이 깨지면 틀 문장으로 간다
        return [None] * len(items)
    out = []
    for i, it in enumerate(items):
        text = answers.get(i)
        out.append(text if text and check(text, it, masked_text, refs[i]) else None)
    return out
