"""S6 제출 준비 (⑪). 조건 확인 → 모의 e-IRB에 채우고 최종 제출 앞에서 멈춤 → 캡처·입력값 확인 → 승인하면 제출·접수번호.
모의 사이트(demo/mock_eirb, 127.0.0.1)만 조작한다. 실제 기관 사이트에는 제출하지 않는다.
"""
from html import escape
from pathlib import Path

import streamlit as st

from agent import api
from ui.common import go, heading, notice

STATUS = {
    "blocked": ("보완 필요", "danger"),
    "awaiting_approval": ("최종 확인 필요", "human"),
    "submitted": ("모의 접수 완료", "rule"),
    "cancelled": ("제출 취소", "public"),
    "preview": ("입력 내용 미리보기", "ai"),
}


def _summary(result) -> None:
    sub = result.submission
    label, tone = STATUS[sub.status] if sub else ("서류 준비", "ai")
    venue = (sub.venue if sub else None) or (result.venue.short if result.venue else None) or result.institution.name or '기관 정보 없음'
    st.markdown(
        f'<div class="submission-summary {tone}" role="status">'
        f'<div><span class="submission-label">현재 단계</span><strong>{escape(label)}</strong></div>'
        f'<div><span class="submission-label">기관</span><b>{escape(venue)}</b></div></div>',
        unsafe_allow_html=True,
    )
    if sub and sub.status == 'preview':
        st.caption('입력 내용을 미리보기만 하며, 접수되지 않았습니다.')
    if sub and sub.receipt:
        st.success(f'모의 접수번호: {sub.receipt}')


def _messages(title: str, items: list[str], tone: str) -> None:
    if not items:
        return
    rows = ''.join(f'<li>{escape(item)}</li>' for item in items)
    st.markdown(
        f'<section class="submission-alert {tone}"><h3>{escape(title)} {len(items)}건</h3>'
        f'<ol>{rows}</ol></section>', unsafe_allow_html=True,
    )


def _documents(result) -> None:
    sub = result.submission
    # A prepared draft must be approved or cancelled before preparing another one.
    if sub and sub.status in ('awaiting_approval', 'submitted'):
        return
    irb = [d for d in result.documents if d.to == 'IRB']
    others = [d for d in result.documents if d.to != 'IRB']
    with st.expander('서류 준비', expanded=sub is None or sub.status in ('blocked', 'cancelled')):
        progress = st.empty()
        checklist = {}
        with st.container(key='eirb_document_checklist'):
            for number, doc in enumerate(irb, 1):
                key = f'ready_{doc.doc}'
                draft_key = key + '_draft'
                st.session_state.setdefault(key, st.session_state.get(draft_key, False))
                checked = st.checkbox(f'{number:02d}. {doc.doc}', key=key)
                st.session_state[draft_key] = checked
                checklist[doc.doc] = checked
        if irb:
            count = sum(checklist[doc.doc] for doc in irb)
            progress.progress(count / len(irb), text=f'준비한 서류 {count} / {len(irb)}건')
        else:
            progress.info('응답에 IRB 제출 서류가 없습니다.')
        if others:
            with st.expander(f'다른 제출처 서류 {len(others)}건'):
                rows = ''.join(f'<li><strong>{escape(doc.doc)}</strong><span>제출처: {escape(doc.to)}</span></li>' for doc in others)
                st.markdown(f'<ol class="submission-file-list">{rows}</ol>', unsafe_allow_html=True)
        if st.button('제출 사이트로 이동', type='primary', use_container_width=True):
            try:
                with st.spinner('서류와 입력 내용을 확인하고 있어요…'):
                    updated = api.request_submission(result.run_id, checklist)
            except Exception:
                st.error('제출 준비를 완료하지 못했습니다. 서류 선택은 유지됩니다. 다시 시도해 주세요.')
            else:
                st.session_state.result = updated
                st.rerun()


def _fields(sub) -> None:
    if not sub.fields:
        return
    with st.expander(f'입력 내용 확인 ({len(sub.fields)}개 항목)'):
        if sub.label_source or sub.venue:
            st.caption('서식 기준: ' + (sub.label_source or sub.venue))
        cards = []
        for number, field in enumerate(sub.fields, 1):
            title = str(field.get('표준 항목') or '항목 이름 없음')
            location = str(field.get('기관 칸') or '서식 위치 정보 없음')
            raw_value = field.get('값')
            value = '' if raw_value is None else str(raw_value)
            missing = not value.strip() or value.startswith('(계획서에 없음')
            badge = '<span class="submission-missing">내용 확인 필요</span>' if missing else ''
            cards.append(
                f'<details class="submission-field{" missing" if missing else ""}">'
                f'<summary><span>{number:02d}. {escape(title)}</span>{badge}</summary>'
                f'<p class="submission-location">서식 위치: {escape(location)}</p>'
                f'<p class="submission-value">{escape(value or "입력값 없음")}</p></details>'
            )
        st.markdown('<div class="submission-fields">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def _details(sub) -> None:
    _fields(sub)
    if sub.screenshot and Path(sub.screenshot).is_file():
        with st.expander('모의 e-IRB 화면 보기'):
            st.image(sub.screenshot, caption='모의 e-IRB 화면')
    if sub.files:
        with st.expander(f'서류 목록 ({len(sub.files)}건)'):
            rows = ''.join(f'<li>{escape(name)}</li>' for name in sub.files)
            st.markdown(f'<ol class="submission-file-list">{rows}</ol>', unsafe_allow_html=True)


def _approval(result) -> None:
    if result.submission.status != 'awaiting_approval':
        return
    with st.container(border=True):
        st.subheader('최종 확인')
        st.caption('입력 내용과 첨부 서류를 확인한 뒤 모의 사이트에 제출하세요.')
        left, right = st.columns(2)
        approve = left.button('승인하고 최종 제출', type='primary', use_container_width=True)
        cancel = right.button('취소', use_container_width=True)
        if approve or cancel:
            try:
                with st.spinner('모의 제출 상태를 확인하고 있어요…'):
                    updated = api.approve_submission(result.run_id, approve)
            except Exception:
                st.error('요청을 완료하지 못했습니다. 현재 상태를 확인한 뒤 다시 시도해 주세요.')
            else:
                st.session_state.result = updated
                st.rerun()


def render() -> None:
    result = st.session_state.result
    notice(result)
    heading('모의 e-IRB', '실제 기관에 전송되지 않는 제출 체험입니다.')
    _summary(result)
    sub = result.submission
    if sub:
        _messages('먼저 보완할 항목', sub.blockers, 'danger')
        if any('연구자 입력' in item for item in sub.blockers):
            if st.button('판단불가 화면에서 입력하기'):
                go(3)
        _messages('제출 전 확인', sub.warnings, 'human')
    _documents(result)
    if sub:
        _details(sub)
        _approval(result)
        if sub.email_draft:
            with st.expander('사무국 메일 초안'):
                st.caption('내용을 확인한 뒤 복사해서 직접 전달하세요.')
                st.code(sub.email_draft, language=None, wrap_lines=True)
                st.download_button('메일 초안 내려받기', sub.email_draft, file_name='irb_submission_questions.txt', mime='text/plain')
        if sub.message:
            with st.expander('상세 안내'):
                st.write(sub.message)
    if st.button('판정 결과로 돌아가기'):
        go(2)
