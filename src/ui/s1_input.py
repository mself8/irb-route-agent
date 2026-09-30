"""S1: 연구계획 입력. 샘플은 입력만 채우고 추출은 start()에 맡긴다."""
import datetime as dt
import streamlit as st
from agent import api
from ui.common import clear_document_upload, clear_review, go, heading
from ui.demo_inputs import DEMO_INPUTS
from ui.document_input import DocumentInputError, extract_document


def _load_document(widget_key: str) -> None:
    for key in ('document_message', 'document_error'):
        st.session_state.pop(key, None)
    uploaded = st.session_state.get(widget_key)
    if uploaded is None:
        return
    try:
        document = extract_document(uploaded.name, uploaded.getvalue())
    except DocumentInputError as exc:
        st.session_state.document_error = str(exc)
        return
    clear_review()
    st.session_state.pop('last_input', None)
    st.session_state.plan_text = document.text
    st.session_state.document_message = document.warnings


def _load_sample(sample_id: str) -> None:
    sample = next(s for s in DEMO_INPUTS if s['id'] == sample_id)
    clear_review()
    clear_document_upload()
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
    heading('연구계획을 입력해 주세요')
    left, right = st.columns([3, 2], gap='medium')
    with right:
        with st.container(border=True):
            st.subheader('연구 정보')
            institution = st.text_input('소속기관명', key='institution_name', placeholder='기관명을 입력해 주세요', disabled=api.FAKE)
            st.session_state.setdefault('start_date', dt.date(2026, 12, 1))
            start_date = st.date_input('목표 연구 개시일', key='start_date', disabled=api.FAKE)
        with st.container(border=True):
            st.subheader('예시 연구계획')
            for sample in DEMO_INPUTS:
                st.button(sample['title'].replace(' · ', ': '), key=f"sample_{sample['id']}",
                          on_click=_load_sample, args=(sample['id'],), use_container_width=True, icon=':material/description:')
    with left.container(border=True):
        st.subheader('연구계획 문서 입력')
        with st.expander('PDF / Word / TXT 파일 불러오기'):
            upload_key = f"document_upload_{st.session_state.get('document_upload_version', 0)}"
            st.file_uploader('연구계획서 파일', type=['pdf', 'docx', 'txt'], max_upload_size=20,
                             key=upload_key, on_change=_load_document, args=(upload_key,),
                             help='파일을 선택하면 아래 입력칸을 문서 내용으로 바꿉니다. 스캔 PDF는 문자 인식(OCR)이 필요합니다.')
        if st.session_state.get('document_error'):
            st.error(st.session_state.document_error)
        if 'document_message' in st.session_state:
            st.caption('파일 내용을 불러왔습니다. 원본과 대조하고 필요한 부분을 수정해 주세요.')
            for warning in st.session_state.document_message:
                st.warning(warning)
        text = st.text_area('연구계획 요약', key='plan_text', height=340, placeholder='연구 목적, 방법, 데이터 형태와 동의 계획을 붙여넣으세요', label_visibility='collapsed')
        st.caption(f'{len(text):,}자 입력됨')
    _, action = st.columns([3, 2])
    if action.button('사실 추출 시작', type='primary', disabled=not text.strip(), use_container_width=True):
        try:
            with st.spinner('연구계획을 확인하고 있어요…'):
                pending = api.start(text, institution, start_date.isoformat())
        except ValueError:
            if api.FAKE:
                st.error('현재 실행 모드에서는 오른쪽 예시 연구계획만 분석할 수 있습니다. 올린 문서를 분석하려면 실제 분석 모드로 실행해야 합니다.')
            else:
                st.error('입력 내용을 분석하지 못했습니다. 문서 내용과 실행 환경을 확인해 주세요.')
            return
        except Exception:
            st.error('입력 내용을 처리하지 못했습니다. 예시 연구계획을 선택해 다시 시도하거나 연결 상태를 확인해 주세요.')
            return
        clear_review()
        st.session_state.last_input = (text, institution, start_date)
        st.session_state.pending = pending
        go(1)
