"""10단계를 LangGraph로 잇는다. 순서는 여기서만 정하고, LLM은 바꾸지 못한다.

① 입력은 api.start()가 받는다. ④에서 interrupt로 멈췄다가, 화면이 확정 사실을 넘기면 이어서 돈다.
"""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .nodes import judge, read, write
from .state import GraphState


def confirm(state: GraphState) -> dict:
    """④ 사실 확인 (사람). 연구자가 사실 카드를 확정할 때까지 멈춘다."""
    answer = interrupt({"facts": state["facts"]})
    return {"confirmed_facts": answer["confirmed_facts"], "edited_by_user": answer.get("edited_by_user", [])}


STEPS = [
    ("step2_mask", read.mask),                 # ② 개인정보 마스킹 (규칙)
    ("step3_extract", read.extract),           # ③ 사실 추출 (AI)
    ("step4_confirm", confirm),                # ④ 사실 확인 (사람)
    ("step5_institution", judge.institution),  # ⑤ 기관 대조 (규칙 + 공공 데이터)
    ("step6_gates", judge.gates),              # ⑥ 관문 판정 (규칙)
    ("step7_route", judge.route),              # ⑦ 경로 결정 (규칙)
    ("step8_docs", judge.docs_schedule),       # ⑧ 서류·일정 산출 (규칙 + 공공 데이터)
    ("step9_abstain", write.abstain),          # ⑨ 판단불가 처리 (AI)
    ("step10_report", write.report),           # ⑩ 결과 리포트 (AI)
]


def build_graph():
    g = StateGraph(GraphState)
    for name, fn in STEPS:
        g.add_node(name, fn)
    names = [name for name, _ in STEPS]
    g.add_edge(START, names[0])
    for a, b in zip(names, names[1:]):
        g.add_edge(a, b)
    g.add_edge(names[-1], END)
    return g.compile(checkpointer=InMemorySaver())
