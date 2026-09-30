"""② 개인정보 마스킹 (규칙), ③ 사실 추출 (AI).

실제 구현은 따로 둔다. 파일이 생기면 자동으로 그걸 쓰고, 없으면 샘플 계획서만 예시 값으로 돌려준다.
    agent/pii.py   mask(text) -> (masked_text, mask_log)      mask_log = [{"type": "이름", "count": 1}, …]
    agent/llm.py   extract(masked_text) -> list[dict]         state.Fact 모양으로 F01~F16 전부, 원문 구간은 masked_text 기준
환경변수 LLM=0이면 파일이 있어도 샘플 예시를 쓴다 (테스트·데모 비상용).
"""
import importlib
import importlib.util
import os

from .. import samples
from ..state import GraphState

PACKAGE = __package__.rsplit(".", 1)[0]  # "agent"


def _impl(name: str):
    """agent.<name> 파일이 있으면 그 모듈, 없거나 LLM=0이면 None."""
    module = f"{PACKAGE}.{name}"
    if os.getenv("LLM", "1") == "0" or importlib.util.find_spec(module) is None:
        return None
    return importlib.import_module(module)


def mask(state: GraphState) -> dict:
    """② 이름·연락처·이메일·주민번호 형식을 가린다 (ko-pii + 정규식)."""
    impl = _impl("pii")
    if impl:
        masked_text, mask_log = impl.mask(state["raw_text"])
        return {"masked_text": masked_text, "mask_log": mask_log}
    pending = samples.require(state["raw_text"])["pending"]
    return {"masked_text": pending["masked_text"], "mask_log": pending["mask_log"]}


def extract(state: GraphState) -> dict:
    """③ 사실 16종을 원문 그대로 뽑는다. 원문과 글자가 다르면 버리고, 두 번째 호출과 다르면 conflict."""
    impl = _impl("llm")
    if impl:
        return {"facts": impl.extract(state["masked_text"])}
    return {"facts": samples.require(state["raw_text"])["pending"]["facts"]}
