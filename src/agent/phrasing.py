"""⑨ 사무국 질문 다듬기 (AI). 판단불가 (가) 항목의 틀 문장을 사무국에 바로 보낼 문장으로 바꾼다.

- 여러 항목을 한 번의 호출로 묶어 JSON으로 받는다 (데모 대기 시간).
- 다듬은 문장은 아래 검사를 모두 통과해야 쓴다. 하나라도 걸리면 그 항목은 None이고, 틀 문장을 그대로 쓴다.
  1. 계획서 인용(큰따옴표 안)은 가린 계획서에 글자 그대로 있어야 한다.
  2. 근거의 법령명과 조문을 basis 값 그대로 쓴다.
  3. 입력에 없던 숫자를 만들지 않는다 (조문 번호·기간·건수 등).
  4. "승인됩니다"·"면제 대상입니다"처럼 판정하는 말을 쓰지 않는다.
  5. 2~3문장, 존댓말.
- 판정은 바꾸지 않는다. 판정은 규칙 엔진(judge.py)만 한다.
"""
import json
import re

from openai import OpenAI

from .llm import BASE_URL, MODEL, locate

VERDICT = re.compile(r"승인됩니다|승인될|승인받을 수 있|면제됩니다|면제될|면제 대상입니다|면제 대상에 해당|해당합니다|해당됩니다|"
                     r"대상입니다|필요 없습니다|필요하지 않습니다|문제없|문제가 없|가능합니다|불가능합니다|불가합니다|통과")
QUOTE = re.compile(r"[\"“]([^\"”]+)[\"”]")
NUMBER = re.compile(r"\d+|[①-⑳]")
HONORIFIC_END = re.compile(r"(니다|니까|세요|십시오|까요)[.?]$")

SYSTEM = (
    "너는 연구윤리 사무국에 보낼 문의 문장을 다듬는다. 판정하지 않고 확인을 요청할 뿐이다.\n"
    "항목마다 2~3문장의 존댓말 문의를 쓴다.\n"
    "1. 첫 문장에 근거 법령명과 조문을 주어진 글자 그대로 쓴다.\n"
    "2. 연구 내용은 계획서에 있는 사실만 쓴다. 계획서를 인용할 때는 큰따옴표로 감싸고 한 글자도 바꾸지 않는다.\n"
    "3. 새 조문·숫자·결론을 만들지 않는다. '승인됩니다', '면제 대상입니다', '해당합니다', '가능합니다'처럼 "
    "판정하는 말을 쓰지 않는다.\n"
    "4. 마지막 문장은 위원회나 사무국의 확인을 요청하는 문장이다."
)


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


def check(text: str, item: dict, masked_text: str) -> bool:
    """다듬은 문장이 조건을 모두 지키는가."""
    basis = item.get("basis") or {}
    law, article = basis.get("law", ""), str(basis.get("article", ""))
    if not law or law not in text or article not in text:
        return False
    if any(locate(q, masked_text) is None for q in QUOTE.findall(text)):
        return False
    allowed = set(NUMBER.findall(" ".join([masked_text, law, article, basis.get("text", ""), item.get("question", "")])))
    if not set(NUMBER.findall(text)) <= allowed:
        return False
    if VERDICT.search(text):
        return False
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
    return 2 <= len(sentences) <= 3 and all(HONORIFIC_END.search(s) for s in sentences)


def polish(items: list[dict], masked_text: str, facts: list[dict]) -> list[str | None]:
    """(가) 항목마다 다듬은 문장 또는 None (검사에 걸리거나 모델 호출이 실패하면 None → 틀 문장 사용)."""
    if not items:
        return []
    known = [{"사실": f["label"], "값": f["value"]} for f in facts if f.get("status") == "found"]
    payload = {
        "계획서": masked_text,
        "확인된 사실": known,
        "문의할 항목": [{"id": i, "법령명": (it.get("basis") or {}).get("law"), "조문": (it.get("basis") or {}).get("article"),
                     "쟁점": it.get("reason"), "틀 문장": it.get("question")} for i, it in enumerate(items)],
    }
    try:
        answers = {q["id"]: q["text"].strip() for q in _call(payload, len(items))["questions"]}
    except Exception:  # 서버가 없거나 응답이 깨지면 틀 문장으로 간다
        return [None] * len(items)
    out = []
    for i, it in enumerate(items):
        text = answers.get(i)
        out.append(text if text and check(text, it, masked_text) else None)
    return out
