"""⑨ 판단불가 처리 (AI), ⑩ 결과 리포트 (AI). 판정 결과는 바꾸지 않고 글만 쓴다.

지금은 샘플 계획서에 한해 예시 값을 돌려주는 자리표시자다.
"""
from .. import samples
from ..state import GraphState


def abstain(state: GraphState) -> dict:
    """⑨ (가) 위원회 판단 사항 → 사무국 질문, (나) 계획서에 정보 없음 → 연구자 입력 요청.

    TODO: 판단불가 행에서 질문 문장 생성 (조문과 계획서 원문 인용).
    """
    items = samples.require(state["raw_text"])["result"]["abstain"]
    answered = state.get("extra_inputs", {})
    return {"abstain": [a for a in items if a.get("input_key") not in answered]}


def report(state: GraphState) -> dict:
    """⑩ 쉬운 설명문. 문장마다 근거(규칙 ID·사실 키)를 붙이고, 근거 없는 문장은 지운다."""
    return {"report": samples.require(state["raw_text"])["result"]["report"]}
