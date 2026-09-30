"""S5 판단불가·사무국 질문 (⑨). (가)는 질문 복사, (나)는 입력한 뒤 ④부터 다시 판정."""
import streamlit as st

from agent import api


def render() -> None:
    result = st.session_state.result
    st.info(result.notice)
    st.subheader(f"판단하지 않은 항목 {len(result.abstain)}건")
    extra = {}
    for item in result.abstain:
        with st.container(border=True):
            st.markdown(f"**{item.rule_id}** · {item.reason}")
            if item.kind == "가":
                st.caption("사무국에 보낼 질문 (오른쪽 위 아이콘으로 복사)")
                st.code(item.question or "", language=None, wrap_lines=True)
            elif item.options:
                value = st.radio(item.ask_input or item.reason, item.options, index=None, key=f"in_{item.rule_id}")
                if value:
                    extra[item.input_key] = value
            else:
                value = st.text_input(item.ask_input or item.reason, key=f"in_{item.rule_id}")
                if value:
                    extra[item.input_key] = value
    left, right = st.columns(2)
    if left.button("입력한 값으로 다시 판정", type="primary", disabled=not extra):
        st.session_state.result = api.rejudge(result.run_id, extra)
        st.session_state.step = 2
        st.rerun()
    if right.button("처음으로"):
        st.session_state.clear()
        st.rerun()
