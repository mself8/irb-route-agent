"""② 개인정보 마스킹 (규칙), ③ 사실 추출 (AI).

지금은 샘플 계획서에 한해 예시 값을 돌려주는 자리표시자다.
"""
from .. import samples
from ..state import GraphState


def mask(state: GraphState) -> dict:
    """② 이름·연락처·이메일·주민번호 형식을 가린다. TODO: ko-pii로 교체."""
    pending = samples.require(state["raw_text"])["pending"]
    return {"masked_text": pending["masked_text"], "mask_log": pending["mask_log"]}


def extract(state: GraphState) -> dict:
    """③ 사실 15종을 원문 그대로 뽑는다.

    TODO: LLM 구조화 출력 → 원문 글자 일치 검사(없으면 폐기) → 두 번째 호출로 교차 검토(다르면 conflict).
    """
    return {"facts": samples.require(state["raw_text"])["pending"]["facts"]}
