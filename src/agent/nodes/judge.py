"""⑤~⑧ 규칙 엔진. 판정은 이 파일에서만 한다. LLM을 쓰지 않는다.

지금은 샘플 계획서에 한해 예시 값을 돌려주는 자리표시자다.
TODO: data/rules/rules.yaml과 확정 사실(confirmed_facts)로 판정하고, 판정 행마다 근거를 붙인다.
"""
from .. import samples
from ..state import GraphState


def _example(state: GraphState) -> dict:
    return samples.require(state["raw_text"])["result"]


def institution(state: GraphState) -> dict:
    """⑤ 기관명을 공공 명단(IRB 인증 공고, 식약처 실시기관)과 문자열로 대조한다."""
    return {"institution": _example(state)["institution"]}


def gates(state: GraphState) -> dict:
    """⑥ 관문 4개를 순서대로: 범위 → 가명 데이터(R-04) → DRB 사전 체크 → IRB·위탁."""
    return {"judgments": _example(state)["judgments"]}


def route(state: GraphState) -> dict:
    """⑦ 판정 행으로 경로(A·B·C·범위 밖)와 신청 순서를 정하고 trace를 남긴다."""
    return {"route": _example(state)["route"]}


def docs_schedule(state: GraphState) -> dict:
    """⑧ 경로별 법정 서류와, 목표 개시일에서 거꾸로 계산한 보완 0·1·2회 일정."""
    example = _example(state)
    return {"documents": example["documents"], "schedule": example["schedule"]}
