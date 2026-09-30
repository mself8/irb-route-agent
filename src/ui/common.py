"""공통 표시와 화면 이동. 판정 데이터는 API 응답에서만 받는다."""
from html import escape
from pathlib import Path

import streamlit as st

from ui.typography import font_face_css


def badge(text: str, tone: str = "ai") -> str:
    return f'<span class="badge {tone}">{escape(str(text))}</span>'


def go(step: int) -> None:
    st.session_state.step = step
    st.rerun()


def clear_review() -> None:
    """같은 FAKE run_id를 다시 열어도 이전 편집/질문 답이 섞이지 않는다."""
    for key in list(st.session_state):
        if key.startswith(("fact_", "answer_", "mail_", "ready_")) or key in ("pending", "result", "facts_editor"):
            del st.session_state[key]


def reset() -> None:
    clear_review()
    clear_document_upload()
    for key in ("plan_text", "institution_name", "start_date", "last_input"):
        st.session_state.pop(key, None)
    st.session_state.step = 0


def clear_document_upload() -> None:
    """새 연구나 예시를 선택하면 이전에 올린 파일 선택도 비운다."""
    st.session_state.document_upload_version = st.session_state.get('document_upload_version', 0) + 1
    for key in ('document_message', 'document_error'):
        st.session_state.pop(key, None)


def accept_result(result) -> None:
    """재판정 응답을 사실 확인 화면에도 반영하고 이전 편집 상태를 비운다."""
    st.session_state.result = result
    pending = st.session_state.get("pending")
    if pending is not None and pending.run_id == result.run_id:
        st.session_state.pending = pending.model_copy(update={"facts": result.facts})
    for key in list(st.session_state):
        if key.startswith(("fact_", "answer_", "mail_")):
            del st.session_state[key]


def shell(step: int, fake: bool) -> None:
    css = Path(__file__).with_name("style.css").read_text(encoding="utf-8")
    st.markdown('<style>' + font_face_css() + css + '</style>', unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('<div class="brand">❖ 여기까지</div><p class="muted">연구윤리 행정지원 시스템</p>', unsafe_allow_html=True)
        st.button("새 연구 입력", icon=":material/add_circle:", on_click=reset, use_container_width=True)
        st.button("사실 확인", icon=":material/fact_check:", disabled="pending" not in st.session_state,
                  on_click=lambda: st.session_state.update(step=1), use_container_width=True)
        st.button("결과 대시보드", icon=":material/dashboard:", disabled="result" not in st.session_state,
                  on_click=lambda: st.session_state.update(step=2), use_container_width=True)
        st.button("판단불가 / 질문", icon=":material/help:", disabled="result" not in st.session_state,
                  on_click=lambda: st.session_state.update(step=3), use_container_width=True)
        st.button("모의 e-IRB", icon=":material/assignment:", disabled="result" not in st.session_state,
                  on_click=lambda: st.session_state.update(step=4), use_container_width=True)
    st.markdown('<div class="topbar"><div><b>여기까지</b><span>연구윤리 행정지원 시스템</span></div></div>', unsafe_allow_html=True)
    labels = ["입력", "사실 확인", "판정", "판단불가", "모의 e-IRB"]
    steps = []
    for i, label in enumerate(labels):
        state = "done" if i < step else "current" if i == step else "future"
        steps.append(f'<div class="step {state}"><b>{"✓" if i < step else i + 1}</b><span>{label}</span></div>')
    st.markdown('<nav class="steps" aria-label="진행 단계">' + ''.join(steps) + '</nav>', unsafe_allow_html=True)


def notice(result) -> None:
    st.markdown('<div class="notice">ⓘ ' + escape(result.notice) + '</div>', unsafe_allow_html=True)


def heading(title: str, subtitle: str = "") -> None:
    description = f'<p>{escape(subtitle)}</p>' if subtitle else ''
    st.markdown(f'<div class="page-title"><h2>{escape(title)}</h2>{description}</div>', unsafe_allow_html=True)


def marked_text(text: str, spans) -> str:
    """응답의 마스킹된 원문만 표시한다. 겹치는 span과 HTML 입력을 방어한다."""
    ranges = []
    for span in spans:
        start, end = span.span_start, span.span_end
        if start is not None and end is not None and 0 <= start < end <= len(text):
            ranges.append((start, end))
    output, pos = [], 0
    for start, end in sorted(set(ranges)):
        if start < pos:
            continue
        output.extend([escape(text[pos:start]), '<mark>' + escape(text[start:end]) + '</mark>'])
        pos = end
    output.append(escape(text[pos:]))
    return '<div class="plan-paper">' + ''.join(output).replace('\n', '<br>') + '</div>'


def basis_details(judgment) -> None:
    basis = judgment.basis
    st.write(f"**{judgment.rule_id} / {basis.law} / {basis.article}**")
    st.write(basis.text)
    st.caption(f"확인일: {basis.checked_at or '응답에 없음'} / 팀 원문 대조: {'완료' if basis.team_checked else '미완료'}")
    if basis.url and basis.url.startswith(("https://", "http://")):
        st.link_button("근거 원문 보기", basis.url)
