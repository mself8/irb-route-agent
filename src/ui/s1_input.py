"""S1 입력 (①). 샘플 버튼 2개로 데모를 시작한다."""
import datetime as dt

import streamlit as st

from agent import api, samples


def _load_sample(sample_id: str) -> None:
    sample = samples.load(sample_id)
    st.session_state.plan_text = sample["plan_text"]
    st.session_state.institution_name = sample["institution_name"]


def render() -> None:
    left, right = st.columns([3, 2])
    with right:
        st.subheader("샘플로 체험하기")
        for sid in samples.all_ids():
            st.button(samples.load(sid)["title"], key=f"sample_{sid}", on_click=_load_sample, args=(sid,))
        st.subheader("판정에 꼭 필요한 정보")
        institution = st.text_input("소속기관명", key="institution_name")
        st.session_state.setdefault("start_date", dt.date(2026, 12, 1))
        start_date = st.date_input("목표 연구 개시일", key="start_date")
    with left:
        text = st.text_area("연구계획 요약", key="plan_text", height=360, placeholder="연구계획 요약을 붙여넣으세요")
        st.caption("입력한 계획서의 이름·연락처는 자동으로 가려집니다.")
    if st.button("사실 추출 시작", type="primary", disabled=not text.strip()):
        st.session_state.last_input = (text, institution, start_date)  # S3의 "보완 문구 넣고 다시"가 쓴다
        try:
            st.session_state.pending = api.start(text, institution, start_date.isoformat())
        except (ValueError, NotImplementedError) as e:
            st.error(str(e))
            st.stop()
        st.session_state.step = 1
        st.rerun()
