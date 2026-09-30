"""S1: 연구계획 입력. 샘플은 입력만 채우고 추출은 start()에 맡긴다."""
import datetime as dt
import streamlit as st
from agent import api
from ui.common import badge, clear_review, go, heading
from ui.demo_inputs import DEMO_INPUTS


def _load_sample(sample_id: str) -> None:
    sample = next(s for s in DEMO_INPUTS if s['id'] == sample_id)
    clear_review()
    st.session_state.plan_text = sample['plan_text']
    st.session_state.institution_name = sample['institution_name']
    st.session_state.start_date = dt.date(2026, 12, 1)


def render() -> None:
    if 'last_input' in st.session_state:
        prior_text, prior_institution, prior_date = st.session_state.last_input
        st.session_state.setdefault('plan_text', prior_text)
        st.session_state.setdefault('institution_name', prior_institution)
        if prior_date:
            st.session_state.setdefault('start_date', prior_date)
    heading('연구계획을 입력해 주세요', '필요한 심의 경로와 서류를 확인하는 첫 단계입니다.')
    st.markdown('<div class="notice">입력 후 이름과 연락처를 가리는 단계를 거칩니다. ' + badge('규칙 엔진', 'rule') + '</div>', unsafe_allow_html=True)
    left, right = st.columns([3, 2], gap='medium')
    with right:
        with st.container(border=True):
            st.subheader('판정에 꼭 필요한 정보')
            institution = st.text_input('소속기관명', key='institution_name', placeholder='기관명을 입력해 주세요', disabled=api.FAKE)
            st.session_state.setdefault('start_date', dt.date(2026, 12, 1))
            start_date = st.date_input('목표 연구 개시일', key='start_date', disabled=api.FAKE)
            if api.FAKE:
                st.caption('예시 모드에서는 샘플의 기관과 연구 개시일을 사용합니다.')
        with st.container(border=True):
            st.subheader('샘플로 체험하기')
            st.caption('가상의 연구계획으로 진행 과정을 확인하세요.')
            for sample in DEMO_INPUTS:
                st.button(sample['title'].replace(' · ', ': '), key=f"sample_{sample['id']}",
                          on_click=_load_sample, args=(sample['id'],), use_container_width=True, icon=':material/description:')
    with left.container(border=True):
        st.subheader('연구계획 문서 입력')
        text = st.text_area('연구계획 요약', key='plan_text', height=310, placeholder='연구 목적, 방법, 데이터 형태와 동의 계획을 붙여넣으세요', label_visibility='collapsed')
        st.caption(f'{len(text):,}자 입력됨')
        st.markdown('<div class="upload-note">PDF / DOCX 문서가 있나요?<br>현재는 문서의 연구계획 요약을 위 입력란에 붙여넣어 주세요.</div>', unsafe_allow_html=True)
    if api.FAKE:
        st.caption('예시 모드(FAKE=1): 샘플 원문으로만 실행됩니다. 수정한 계획서의 판정은 실제 모드에서 지원합니다.')
    _, action = st.columns([3, 2])
    if action.button('사실 추출 시작', type='primary', disabled=not text.strip(), use_container_width=True):
        try:
            with st.spinner('계획서를 마스킹하고 사실을 추출하고 있어요…'):
                pending = api.start(text, institution, start_date.isoformat())
        except Exception:
            st.error('사실 추출을 완료하지 못했습니다. 예시 모드에서는 샘플 버튼으로 원문을 불러오고, 실제 모드에서는 서버 연결을 확인한 뒤 다시 시도해 주세요.')
            return
        clear_review()
        st.session_state.last_input = (text, institution, start_date)
        st.session_state.pending = pending
        go(1)
