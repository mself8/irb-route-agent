"""S2 사실 확인 (④). 연구자가 AI가 뽑은 사실을 확인·수정해야 판정에 들어간다."""
import streamlit as st

from agent import api

STATUS = {"found": "찾음", "not_found": "계획서에 없음", "conflict": "확인 필요"}


def _show(value) -> str:
    if value is None:
        return ""
    return ", ".join(value) if isinstance(value, list) else str(value)


def _parse(text: str, original):
    text = (text or "").strip()
    if isinstance(original, list):
        return [x.strip() for x in text.split(",") if x.strip()]
    if not text:
        return None
    if isinstance(original, int) and text.isdigit():
        return int(text)
    return text


def render() -> None:
    pending = st.session_state.pending
    st.subheader("AI가 뽑은 사실을 확인해 주세요")
    st.caption("확정한 사실만 판정에 들어갑니다.")
    rows = [
        {"키": f.key, "사실": f.label, "값": _show(f.value), "계획서 원문": f.span or "", "상태": STATUS[f.status]}
        for f in pending.facts
    ]
    edited = st.data_editor(rows, hide_index=True, disabled=["키", "사실", "계획서 원문", "상태"], key="facts_editor")
    if st.button("사실 확정하고 판정", type="primary"):
        facts, changed = [], []
        for fact, row in zip(pending.facts, edited):
            value = _parse(row["값"], fact.value)
            if value != fact.value:
                changed.append(fact.key)
                fact = fact.model_copy(update={"value": value, "status": "found" if value not in (None, []) else "not_found"})
            facts.append(fact.model_dump())
        st.session_state.result = api.confirm(pending.run_id, facts, changed)
        st.session_state.step = 2
        st.rerun()
