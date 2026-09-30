"""S3: API Result의 경로, 서류, 일정, 근거를 팀 목업에 맞춰 표시한다."""
import html
import streamlit as st
from ui.common import badge, go, heading, notice
from ui.result_details import render_checkpoints, render_forms, render_suggestions


def _committee_summary(text, venue):
    """Shorten known API labels for display; preserve the full text in details."""
    name, note = text, ''
    endings = {
        ' · 심의 또는 심의면제 (확인 필요)': '심의면제 여부 확인',
        ' · 심의면제 신청 후보': '심의면제 신청 검토',
        ' · 심의': '심의 신청',
        ' (가이드라인 권고 · 기관확인)': '검토 여부를 기관에 확인',
        ' (동의 없이 쓰는 경우 · 확인 필요)': '동의 없이 이용하는 경우 검토 여부 확인',
    }
    for ending, summary in endings.items():
        if text.endswith(ending):
            name, note = text[:-len(ending)], summary
            break
    if ' (IRB 승인 뒤 신청 · ' in text and text.endswith(' 안내)'):
        name, note = text.split(' (IRB 승인 뒤 신청 · ', 1)[0], 'IRB 승인 후 신청'
    if name == '소속 기관 IRB' and venue and venue.short:
        name = f'{venue.short} IRB'
    return name, note


def _documents(documents) -> None:
    with st.container(border=True):
        st.subheader('제출 서류')
        st.caption(f'준비할 서류 {len(documents)}건')
        if not documents:
            st.caption('응답에 안내된 서류가 없습니다.')
            return
        number = 1
        for level in ('법정', '기관'):
            docs = [doc for doc in documents if doc.level == level]
            if not docs:
                continue
            with st.expander(f'{level} 서류 {len(docs)}건', expanded=True):
                rows = []
                for doc in docs:
                    destination = (f'<span class="document-destination">제출처: {html.escape(doc.to)}</span>'
                                   if doc.to else '')
                    sources = list(dict.fromkeys(s for s in (doc.basis, doc.source) if s))
                    notes = ''.join(f'<p class="document-source">근거 / 출처: {html.escape(s)}</p>' for s in sources)
                    rows.append(
                        f'<li class="document-item"><span class="document-number" aria-hidden="true">{number:02d}</span>'
                        '<div class="document-content"><div class="document-heading">'
                        f'<p class="document-name">{html.escape(doc.doc)}</p>{destination}</div>{notes}</div></li>'
                    )
                    number += 1
                st.markdown(f'<ol class="document-list" start="{number - len(docs)}" aria-label="{level} 제출 서류">'
                            + ''.join(rows) + '</ol>', unsafe_allow_html=True)


def _report(result) -> None:
    with st.expander('결과 리포트', expanded=True):
        if not result.report:
            st.caption('응답에 리포트가 없습니다.')
            return
        # Keep the API's sentences and citations intact; only group their display.
        labels = {j.rule_id: j.requirement for j in result.judgments}
        labels.update({f.key: f.label for f in result.facts})
        rows = []
        for number, sentence in enumerate(result.report, 1):
            refs = []
            for ref in sentence.refs:
                description = labels.get(ref, '')
                refs.append(f'<li><b>{html.escape(ref)}</b> {html.escape(description)}</li>')
            evidence = ('<details class="report-evidence"><summary>근거 보기</summary><ul>'
                        + ''.join(refs) + '</ul></details>' if refs else '')
            rows.append(
                f'<li class="report-item"><span class="report-number" aria-hidden="true">{number:02d}</span>'
                f'<div class="report-content"><p class="report-text">{html.escape(sentence.text)}</p>{evidence}</div></li>'
            )
        st.markdown('<ol class="report-list" aria-label="결과 리포트 안내">' + ''.join(rows) + '</ol>', unsafe_allow_html=True)


def render() -> None:
    result = st.session_state.result
    route = result.route
    notice(result)
    heading('결과 대시보드', '심의 경로, 준비할 서류와 확인이 필요한 항목을 한눈에 살펴보세요.')
    c1, c3, c4 = st.columns([1.2, 1, 1], gap='medium')
    with c1.container(border=True):
        st.subheader('어느 위원회')
        if route.fast_track:
            st.markdown(badge('빠른 길 후보', 'rule'), unsafe_allow_html=True)
        for index, committee in enumerate(route.committees):
            n = route.order[index] if index < len(route.order) else index + 1
            name, note = _committee_summary(committee, result.venue)
            summary = f'<small class="route-note">{html.escape(note)}</small>' if note else ''
            st.markdown(f'<div class="route-node"><b>{n}</b><div><span class="route-name">{html.escape(name)}</span>{summary}</div></div>', unsafe_allow_html=True)
        if not route.committees:
            st.caption('응답에 지정된 위원회가 없습니다.')
        if result.venue:
            st.caption(f'담당 기관: {result.venue.short}')
        with st.expander('위원회와 제출 방법 자세히'):
            for committee in route.committees:
                st.write(committee)
            if result.venue:
                st.write(result.venue.name)
                st.write(result.venue.submit)
            st.caption('근거 규칙: ' + (', '.join(route.trace) or '없음'))
    with c3.container(border=True):
        st.subheader('언제까지')
        default = next((s for s in result.schedule.scenarios if s.revisions == result.schedule.default), None)
        date = default.submit_by if default and default.submit_by else '공개 수치 없음'
        st.markdown('<div class="deadline"><small>신청 기준일</small><strong>' + html.escape(date) + '</strong><small>' + html.escape(default.step or '' if default else '') + '</small></div>', unsafe_allow_html=True)
        if default:
            st.caption(f'보완 {default.revisions}회 기준 / 기관 확인 필요')
        with st.expander('일정 조건 보기'):
            for scenario in result.schedule.scenarios:
                st.write(f'보완 {scenario.revisions}회: {scenario.submit_by or "공개 수치 없음"}')
                if scenario.step:
                    st.caption(scenario.step)
            for line in result.schedule.missing:
                st.caption(line)
    with c4.container(border=True):
        st.markdown(badge('사람 확인', 'human'), unsafe_allow_html=True)
        st.subheader(f'판단불가 {len(result.abstain)}건')
        committee = sum(a.kind == '가' for a in result.abstain)
        researcher = sum(a.kind == '나' for a in result.abstain)
        st.caption(f'사무국 확인 {committee}건 / 연구자 입력 {researcher}건')
        st.write('확인이 필요한 항목과 사무국에 보낼 질문을 확인하세요.' if result.abstain else '현재 응답에 판단불가 항목이 없습니다.')
        if st.button(f'판단불가 {len(result.abstain)}건 보기', type='primary', use_container_width=True):
            go(3)
    _report(result)
    _documents(result.documents)
    with st.container(border=True):
        st.subheader('판정 근거 추적')
        by_id = {j.rule_id: j for j in result.judgments}
        trace = list(dict.fromkeys(route.trace))
        if not trace:
            st.caption('응답에 경로 근거 규칙이 없습니다.')
        for start in range(0, len(trace), 4):
            cols = st.columns(min(4, len(trace) - start))
            for col, rule_id in zip(cols, trace[start:start + 4]):
                with col:
                    judgment = by_id.get(rule_id)
                    if judgment:
                        tone = 'rule' if judgment.result == '충족' else 'human' if judgment.result == '판단불가' else 'danger'
                        st.markdown(f'<div class="trace-card {tone}">{badge(judgment.result, tone)}<p>{html.escape(judgment.requirement)}</p><small>{html.escape(rule_id)}</small></div>', unsafe_allow_html=True)
                    else:
                        st.markdown(badge(rule_id, 'public'), unsafe_allow_html=True)
                        st.caption('세부 근거가 응답에 없습니다.')
        with st.expander('전체 체크포인트와 근거 조문'):
            render_checkpoints(result.judgments)
    render_suggestions(result)
    render_forms(result)
    back, submit = st.columns(2)
    if back.button('사실 확인으로 돌아가기'):
        go(1)
    if submit.button('제출 준비 (모의 e-IRB)'):
        go(4)
