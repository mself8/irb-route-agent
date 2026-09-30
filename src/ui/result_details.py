"""API가 반환한 판정, 보완 사항, 기관 서식을 읽기 쉽게 표시한다."""
from html import escape

import streamlit as st

from ui.common import badge


def _basis_html(basis) -> str:
    link = ''
    if basis.url and basis.url.startswith(('https://', 'http://')):
        link = f'<a class="basis-link" href="{escape(basis.url, quote=True)}" target="_blank" rel="noopener noreferrer">근거 원문 열기 ↗</a>'
    checked = '완료' if basis.team_checked else '미완료'
    effective = f' / 시행일: {escape(basis.effective)}' if basis.effective else ''
    return (
        '<details class="detail-disclosure"><summary>근거 조문과 출처 보기</summary>'
        f'<p class="basis-heading">{escape(basis.law)} / {escape(basis.article)}</p>'
        f'<blockquote class="basis-quote">{escape(basis.text)}</blockquote>'
        f'<p class="detail-meta">확인일: {escape(basis.checked_at or "응답에 없음")} / 팀 원문 대조: {checked}{effective}</p>'
        + link + '</details>'
    )


def render_checkpoints(judgments) -> None:
    if not judgments:
        st.caption('응답에 세부 판정이 없습니다.')
        return
    groups = [(status, [j for j in judgments if j.result == status])
              for status in ('미충족', '판단불가', '충족')]
    tabs = st.tabs([f'{status} {len(rows)}' for status, rows in groups])
    for tab, (status, rows) in zip(tabs, groups):
        with tab:
            if not rows:
                st.caption(f'{status} 항목이 없습니다.')
                continue
            tone = {'미충족': 'danger', '판단불가': 'human', '충족': 'rule'}[status]
            cards = []
            for number, row in enumerate(rows, 1):
                description = (f'<p class="detail-description">{escape(row.result_detail)}</p>'
                               if row.result_detail else '')
                cards.append(
                    f'<article class="checkpoint-card {tone}" data-rule="{escape(row.rule_id, quote=True)}">'
                    '<div class="detail-card-meta">' + badge(status, tone)
                    + f'<span>규칙 {escape(row.rule_id)}</span></div>'
                    f'<p class="detail-title">{number:02d}. {escape(row.requirement)}</p>{description}'
                    f'<p class="detail-meta">판정 유형: {escape(row.type)}</p>'
                    + _basis_html(row.basis) + '</article>'
                )
            st.markdown('<div class="checkpoint-list">' + ''.join(cards) + '</div>', unsafe_allow_html=True)


def _suggestion(suggestion, index) -> None:
    tone = {'보완 필요': 'danger', '확인 필요': 'human', '안내': 'ai'}[suggestion.level]
    scope = '법 / 가이드라인' if suggestion.scope == '법' else '기관 안내'
    with st.container(border=True, key=f's3_suggestion_{index}'):
        st.markdown(
            f'<div class="suggestion-heading" data-tone="{tone}" data-rule="{escape(suggestion.rule_id, quote=True)}">'
            '<div class="detail-card-meta">' + badge(suggestion.level, tone)
            + f'<span>{scope} / 규칙 {escape(suggestion.rule_id)}</span></div>'
            f'<p class="suggestion-text">{escape(suggestion.warning)}</p></div>',
            unsafe_allow_html=True,
        )
        if suggestion.add_text:
            with st.expander('계획서에 넣을 문장'):
                st.caption('[ ]를 실제 연구 내용에 맞게 채우세요. 오른쪽 위 아이콘으로 복사할 수 있습니다.')
                st.code(suggestion.add_text, language=None, wrap_lines=True)
        if suggestion.basis:
            with st.expander('근거와 출처'):
                st.write(suggestion.basis)


def render_suggestions(result) -> None:
    with st.expander('제출 전 보완'):
        if not result.suggestions:
            st.caption('응답에 보완 안내가 없습니다.')
            return
        groups = [(level, [(i, s) for i, s in enumerate(result.suggestions) if s.level == level])
                  for level in ('보완 필요', '확인 필요', '안내')]
        tabs = st.tabs([f'{level} {len(items)}' for level, items in groups])
        for tab, (level, items) in zip(tabs, groups):
            with tab:
                if not items:
                    st.caption(f'{level} 항목이 없습니다.')
                for index, suggestion in items:
                    _suggestion(suggestion, index)
        fixes = []
        for suggestion in result.suggestions:
            if suggestion.level == '보완 필요' and suggestion.add_text and suggestion.add_text not in ' '.join(fixes):
                fixes.append(suggestion.add_text)
        if fixes:
            st.divider()
            if st.button('보완 문구를 계획서 끝에 넣고 처음부터 다시'):
                text, institution, start_date = st.session_state.get('last_input', ('', '', None))
                st.session_state.plan_text = text.rstrip() + '\n' + '\n'.join(fixes)
                st.session_state.institution_name = institution
                if start_date:
                    st.session_state.start_date = start_date
                st.session_state.step = 0
                st.rerun()


def _form_items(venue) -> None:
    if venue.plan_form:
        st.markdown(f'<p class="form-title">{escape(venue.plan_form)}</p>', unsafe_allow_html=True)
    if not venue.plan_items:
        st.caption('응답에 이 기관의 계획서 항목 정보가 없습니다.')
        return
    found = sum(bool(item.get('found')) for item in venue.plan_items)
    total = len(venue.plan_items)
    st.markdown('<div class="form-counts">' + badge(f'전체 {total}개', 'public')
                + badge(f'원문에서 찾음 {found}개', 'rule') + badge(f'확인 필요 {total - found}개', 'human') + '</div>',
                unsafe_allow_html=True)
    st.progress(found / total, text=f'계획서 원문에서 {total}개 중 {found}개 항목을 찾았습니다.')
    st.caption('낱말을 기준으로 확인한 결과입니다. 제출 전 전체 계획서를 기관 서식과 대조해 주세요.')
    rows = []
    # Show missing items first without treating word matches as submission approval.
    for item in sorted(venue.plan_items, key=lambda item: bool(item.get('found'))):
        matched = bool(item.get('found'))
        tone = 'rule' if matched else 'human'
        label = '원문에서 찾음' if matched else '원문에서 찾지 못함'
        rows.append(
            f'<article class="form-item {tone}">' + badge(label, tone)
            + f'<p class="form-item-name">{escape(str(item.get("item", "")))}</p>'
            f'<p class="form-item-location">서식 위치: {escape(str(item.get("label", "")))}</p></article>'
        )
    st.markdown('<div class="form-item-grid">' + ''.join(rows) + '</div>', unsafe_allow_html=True)


def _form_comparison(compare) -> None:
    if not compare:
        st.caption('응답에 기관별 서식 비교 정보가 없습니다.')
        return
    kinds = list(dict.fromkeys(str(row.get('구분') or '서식') for row in compare))
    tabs = st.tabs(kinds)
    for tab, kind in zip(tabs, kinds):
        with tab:
            rows = []
            for row in compare:
                if str(row.get('구분') or '서식') != kind:
                    continue
                fields = []
                for institution, form in row.items():
                    if institution in ('구분', '표준 항목'):
                        continue
                    fields.append('<div class="comparison-entry">'
                                  f'<dt>{escape(str(institution))}</dt><dd>{escape(str(form)) if form is not None else "응답에 없음"}</dd></div>')
                rows.append('<details class="form-comparison"><summary>'
                            + escape(str(row.get('표준 항목') or '서식 항목')) + '</summary><dl>'
                            + ''.join(fields) + '</dl></details>')
            st.markdown('<div class="comparison-list">' + ''.join(rows) + '</div>', unsafe_allow_html=True)


def render_forms(result) -> None:
    with st.expander('기관 서식 확인'):
        if result.venue:
            venue = result.venue
            st.markdown(f'#### {venue.short} 안내문 기준')
            _form_items(venue)
            if venue.source:
                with st.expander('기관 안내문 출처'):
                    st.write(venue.source)
        else:
            st.caption('응답에 지정된 기관 서식이 없습니다.')
        with st.expander('기관별 서식 이름 비교'):
            _form_comparison(result.compare)
