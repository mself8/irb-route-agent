"""③ 사실 추출 (AI). 로컬 Qwen3.8-27B-FP8을 vLLM의 OpenAI 호환 API로 부른다.

- 사실 18종(F01~F18)을 JSON 스키마로 강제해 뽑는다. 값은 규칙 엔진이 판정에 쓰는 문자열 그대로다.
- 값마다 근거 구간(span)을 받아 masked_text에 글자 그대로 있을 때만 채택한다. 없으면 not_found.
- 항목 순서를 뒤집은 두 번째 호출로 다시 뽑아, 값이 다르면 conflict로 표시한다 (④에서 사람이 확인).
- 판정은 하지 않는다. 판정은 규칙 엔진(judge.py)만 한다.
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from .state import FACT_LABELS

BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
MODEL = os.getenv("LLM_MODEL", "qwen3.8-27b")

# 규칙 엔진이 판정에 쓰는 값. 모델은 이 밖의 값을 낼 수 없다.
CHOICES = {
    "F01": ["중재", "관찰", "설문·면담", "기록 이용", "인체유래물"],
    "F02": ["예", "아니오"],
    "F03": ["원자료", "가명처리", "익명"],
    "F04": ["연구자", "기관 데이터팀", "외부 기관"],
    "F05": ["기관 내부", "제3자 제공(통제 환경)", "그 외"],
    "F06": ["예", "아니오"],
    "F09": ["예", "아니오"],
    "F10": ["예", "아니오"],
    "F11": ["서면동의", "동의면제 요청", "없음"],
    "F14": ["예", "아니오"],
    "F17": ["예", "아니오"],
    "F18": ["없음(폐기)", "연구책임자", "데이터팀·제3자"],
}
SENSITIVE = ["정신질환", "HIV", "성매개감염병", "희귀질환", "학대", "낙태"]  # F07
LIST_KEYS = {"F07", "F08", "F12", "F16"}

# 모델에게 주는 항목 설명. 규칙 엔진이 기대하는 뜻과 맞춘다.
GUIDE = {
    "F01": "연구 유형. 진료기록이나 그것을 가공한 데이터셋(가명처리 포함) 등 이미 있는 자료를 쓰는 연구는 "
           "제목에 '관찰연구'가 있어도 기록 이용이다. "
           "중재=약물·시술 등으로 대상자에게 개입, 관찰=개입 없이 대상자를 앞으로 관찰, 설문·면담, 인체유래물=검체 이용",
    "F02": "연구자가 이름·등록번호 같은 식별정보가 담긴 원자료(진료기록 등)를 직접 열람하는가. "
           "가명처리된 데이터셋만 받으면 아니오. 대상자와 접촉하는지와는 다른 질문이다",
    "F03": "연구자가 받아 쓰는 데이터의 형태. 원자료=식별정보가 든 기록 그대로, 가명처리, 익명",
    "F04": "가명처리를 누가 하는가",
    "F05": "가명정보를 쓰는 장소·환경. 분석 장소나 환경이 적혀 있을 때만 found (예: 원내 분석실이면 기관 내부)",
    "F06": "다른 기관 데이터와 결합하거나 데이터를 기관 밖으로 반출하는가",
    "F07": "데이터에 든 민감정보 중 해당하는 것: " + ", ".join(SENSITIVE)
           + ". 수집 항목이 나열돼 있고 해당이 없으면 빈 목록(근거=항목 목록)",
    "F08": "미성년자 등 취약한 대상 목록. 대상자의 나이 범위나 취약 집단이 명시돼 있을 때만 found이고, "
           "해당이 없으면 빈 목록. '환자'라고만 적혀 있으면 found=false",
    "F09": "조직·혈액·체액 등 인체유래물을 쓰는가",
    "F10": "의약품 또는 의료기기 임상시험에 해당하는가. 후향적·관찰·기록 연구라고 적혀 있으면 아니오(근거=그 표현)",
    "F11": "연구대상자 동의 계획",
    "F12": "연구를 수행하거나 참여하는 기관 이름 목록",
    "F13": "연구 기간을 'YYYY-MM-DD ~ YYYY-MM-DD' 형식으로",
    "F14": "배아·유전자 연구에 해당하는가. 연구 대상과 방법이 적혀 있고 배아·유전자와 무관하면 아니오(근거=연구 제목이나 방법)",
    "F15": "연구 대상자 수(정수)",
    "F16": "연구 자료로 수집하거나 기록하는 식별자 목록: 성명, 주민번호, 등록번호, 연락처, 전체 생년월일, 상세 주소 등. "
           "수집하거나 제공받는 항목이 나열돼 있고 식별자가 없으면 빈 목록(근거=항목 목록). 연구책임자 본인의 연락처는 제외",
    "F17": "대상자를 연구용 번호(식별코드)로 대체하는가",
    "F18": "식별코드와 실제 대상자를 잇는 대응표를 누가 보관하는가. 폐기하면 없음(폐기), "
           "연구자가 접근할 수 없게 데이터팀이나 제3자가 보관하면 데이터팀·제3자",
}

RULES = (
    "너는 연구계획서에서 사실만 뽑는 추출기다. 해석하거나 추측하지 않는다.\n"
    "1. 항목마다 계획서에 근거가 있으면 found=true, value는 정해진 형식으로, span은 근거가 되는 계획서 원문을 "
    "한 글자도 바꾸지 않고 복사한 가장 짧은 구간(한 문장 이내)이다.\n"
    "2. 근거가 없으면 found=false, span은 빈 문자열이다. value는 아무 값이나 두면 무시된다.\n"
    "3. '아니오'나 빈 목록도 계획서 문장이 뒷받침할 때만 found=true다.\n"
    "4. [이름] [전화번호] 같은 가림 표시는 그대로 둔다.\n"
)


def _value_schema(key: str) -> dict:
    if key in CHOICES:
        return {"type": "string", "enum": CHOICES[key]}
    if key == "F07":
        return {"type": "array", "items": {"type": "string", "enum": SENSITIVE}}
    if key in LIST_KEYS:
        return {"type": "array", "items": {"type": "string"}}
    if key == "F15":
        return {"type": "integer"}
    return {"type": "string"}  # F13


SCHEMA = {
    "type": "object",
    "properties": {
        key: {
            "type": "object",
            "properties": {"found": {"type": "boolean"}, "value": _value_schema(key), "span": {"type": "string"}},
            "required": ["found", "value", "span"],
            "additionalProperties": False,
        }
        for key in FACT_LABELS
    },
    "required": list(FACT_LABELS),
    "additionalProperties": False,
}


def _prompt(keys: list[str]) -> str:
    return RULES + "\n항목:\n" + "\n".join(f"- {k} {FACT_LABELS[k]}: {GUIDE[k]}" for k in keys)


def _call(system: str, masked_text: str) -> dict:
    """모델 한 번 호출. 스키마에 맞는 dict를 돌려준다."""
    client = OpenAI(base_url=BASE_URL, api_key="local", timeout=120)
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=2000,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": masked_text}],
        response_format={"type": "json_schema", "json_schema": {"name": "facts", "schema": SCHEMA}},
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return json.loads(resp.choices[0].message.content)


def locate(span: str, text: str) -> tuple[int, int] | None:
    """span이 text에 있으면 (시작, 끝). 공백·줄바꿈 차이만 허용하고, 위치는 text의 원래 글자 기준이다."""
    if not span or not span.strip():
        return None
    i = text.find(span)
    if i >= 0:
        return i, i + len(span)
    m = re.search(r"\s+".join(re.escape(part) for part in span.split()), text)
    return (m.start(), m.end()) if m else None


def _verified(raw: dict, masked_text: str) -> dict:
    """모델 출력 한 항목을 원문 대조해 {value, span, span_start, span_end} 또는 빈 dict로."""
    if not raw.get("found"):
        return {}
    pos = locate(raw.get("span", ""), masked_text)
    if pos is None:
        return {}  # 원문에 없는 인용은 버린다
    return {"value": raw["value"], "span": masked_text[pos[0]:pos[1]], "span_start": pos[0], "span_end": pos[1]}


def _same(a, b) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return sorted(a) == sorted(b)
    return a == b


def extract(masked_text: str) -> list[dict]:
    """③ 사실 추출. state.Fact 모양의 dict를 state.FACT_LABELS 순서(F01~F18)로 돌려준다."""
    keys = list(FACT_LABELS)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(lambda ks: _call(_prompt(ks), masked_text), [keys, keys[::-1]])

    facts = []
    for key in keys:
        a = _verified(first.get(key, {}), masked_text)
        b = _verified(second.get(key, {}), masked_text)
        fact = {"key": key, "label": FACT_LABELS[key], "value": None, "span": None,
                "span_start": None, "span_end": None, "status": "not_found", "cross_check": None}
        if a and b and _same(a["value"], b["value"]):
            fact.update(a, status="found", cross_check="agree")
        elif a or b:
            fact.update(a or b, status="conflict", cross_check="disagree")
        facts.append(fact)
    return facts
