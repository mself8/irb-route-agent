"""S3: API Result의 경로, 서류, 일정, 근거를 팀 목업에 맞춰 표시한다."""
import html
import streamlit as st
from agent import api
from ui.common import accept_result, badge, basis_details, go, heading, marked_text, notice


def _card(s) -> None:
    with st.container(border=True):
        st.markdown(f'**{s.level}** / {s.rule_id} / {s.warning}')
        if s.add_text:
            st.caption('계획서에 넣을 문장. [ ]는 사실에 맞게 채우세요. 오른쪽 위 아이콘으로 복사할 수 있습니다.')
            st.code(s.add_text, language=None, wrap_lines=True)
        if s.basis:
            st.caption(f'근거: {s.basis}')


def _marked(text, highlights):
    return marked_text(text, highlights)


def render() -> None:
    result = st.session_state.result
    route = result.route
    notice(result)
    heading('결과 대시보드', '심의 경로, 준비할 서류와 확인이 필요한 항목을 한눈에 살펴보세요.')
    c1, c2, c3, c4 = st.columns([1.1, 1.2, 1, .9], gap='small')
    with c1.container(border=True):
        st.subheader('어느 위원회')
        st.markdown(badge(f'경로 {route.route}') + (badge('빠른 길 후보', 'rule') if route.fast_track else ''), unsafe_allow_html=True)
        for index, committee in enumerate(route.committees):
            n = route.order[index] if index < len(route.order) else index + 1
            st.markdown(f'<div class="route-node"><b>{n}</b><span>{html.escape(committee)}</span></div>', unsafe_allow_html=True)
        if not route.committees:
            st.caption('응답에 지정된 위원회가 없습니다.')
        st.caption('근거 규칙: ' + (', '.join(route.trace) or '없음'))
        if result.venue:
            st.markdown(f'**제출처: {result.venue.name}**')
            st.caption(result.venue.submit)
    with c2.container(border=True):
        st.subheader('어떤 서류')
        st.markdown(f'**준비 서류 {len(result.documents)}건**')
        for level in ('법정', '기관'):
            docs = [d for d in result.documents if d.level == level]
            with st.expander(f'{level} 서류 {len(docs)}건', expanded=level == '법정'):
                if not docs:
                    st.caption('응답에 해당 서류가 없습니다.')
                for doc in docs:
                    st.write(doc.doc)
                    if doc.to:
                        st.caption(f'제출처: {doc.to}')
                    if doc.basis or doc.source:
                        st.caption(doc.basis or doc.source)
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
        with st.expander('체크포인트와 조문 원문 펼치기'):
            st.dataframe([{'규칙': j.rule_id, '요건': j.requirement, '결과': j.result, '판정 유형': j.type, '근거': j.basis.law} for j in result.judgments], hide_index=True)
            for j in result.judgments:
                basis_details(j)
                if j.result_detail:
                    st.caption(j.result_detail)
                st.divider()
    with st.expander('제출 전 보완 / 기관별 서식 / 계획서 표시'):
        _details(result)
    with st.expander('결과 리포트'):
        for sentence in result.report:
            st.write(sentence.text)
            st.caption('근거: ' + ', '.join(sentence.refs))
        if not result.report:
            st.caption('응답에 리포트가 없습니다.')
    back, submit = st.columns(2)
    if back.button('사실 확인으로 돌아가기'):
        go(1)
    if submit.button('제출 준비 (모의 e-IRB)'):
        go(4)


def _details(result) -> None:
    need = [s for s in result.suggestions if s.level == '보완 필요']
    law = [s for s in result.suggestions if s.scope == "법"]
    inst = [s for s in result.suggestions if s.scope == "기관"]
    if law:
        st.markdown("#### 제출 전 보완 · 법·가이드라인 기준")
        for s in law:
            _card(s)
    if result.venue:
        venue = result.venue
        st.markdown(f"#### 제출 전 보완 · {venue.short} 안내문 기준")
        found = sum(i["found"] for i in venue.plan_items)
        with st.container(border=True):
            st.markdown(f"**{venue.plan_form}** 항목 {len(venue.plan_items)}개 중 {found}개를 계획서에서 찾음")
            for i in venue.plan_items:
                st.write(("✅ " if i["found"] else "⬜ ") + f"{i['item']} — {i['label']}")
            st.caption("요약 계획서의 낱말로만 확인합니다. 제출 전 전체 계획서를 이 서식에 맞춰 쓰세요.")
        for s in inst:
            _card(s)
        st.caption(f"출처: {venue.source}")
    if result.suggestions:
        fixes = []
        for s in need:  # R-11 문구에 R-12 문구가 들어 있으면 한 번만 넣는다
            if s.add_text and s.add_text not in " ".join(fixes):
                fixes.append(s.add_text)
        if fixes and st.button("보완 문구를 계획서 끝에 넣고 처음부터 다시"):
            text, institution, start_date = st.session_state.get("last_input", ("", "", None))
            st.session_state.plan_text = text.rstrip() + "\n" + "\n".join(fixes)
            st.session_state.institution_name = institution
            if start_date:
                st.session_state.start_date = start_date
            st.session_state.step = 0
            st.rerun()
    st.markdown("#### 다른 기관에 낸다면")
    # 기관 프로필이 있는 곳(비교표의 열). 값은 ⑤ 기관 대조에 넣을 이름이고, 공용위원회는 '소속 없음'으로 간다
    names = [c for c in (result.compare[0] if result.compare else {}) if c not in ("구분", "표준 항목")]
    venues = {("소속 없음 → 공용위원회" if n == "공용위원회" else n): ("없음" if n == "공용위원회" else n) for n in names}
    left, right = st.columns([3, 1])
    choice = left.selectbox("기관", list(venues), index=None, placeholder="기관을 고르면 그 기관 기준으로 다시 판정합니다",
                            label_visibility="collapsed", disabled=api.FAKE)
    if right.button("이 기관 기준으로 다시 판정", disabled=choice is None or api.FAKE):
        # 같은 연구를 그 기관에서 한다고 보고 소속과 수행기관(F12)을 함께 바꾼다. 공용위원회는 소속 없는 연구자로 본다.
        # 공동연구면 첫 기관만 바꿔 다른 수행기관을 남긴다
        change = {"institution_name": venues[choice], "irb_exists": None, "contract": None}
        if venues[choice] != "없음":
            f12 = next((f.value for f in result.facts if f.key == "F12"), None)
            change["F12"] = [venues[choice], *f12[1:]] if isinstance(f12, list) and len(f12) >= 2 else [venues[choice]]
        text, _, start_date = st.session_state.get("last_input", ("", "", None))
        try:
            with st.spinner('선택한 기관 기준으로 다시 확인하고 있어요…'):
                updated = api.rejudge(result.run_id, change)
        except Exception:
            st.error('기관 변경 판정을 완료하지 못했습니다. 기존 결과는 유지됩니다. 잠시 후 다시 시도해 주세요.')
            return
        st.session_state.last_input = (text, venues[choice], start_date)
        accept_result(updated)
        st.rerun()
    if api.FAKE:
        st.caption("예시 모드(FAKE=1)는 미리 만든 결과라서 기관을 바꿔 다시 판정하지 않습니다. 실제 모드(FAKE=0)에서 쓰세요.")
    else:
        st.caption("같은 연구를 그 기관에서 한다고 보고(소속·수행기관을 함께 바꿔) 다시 판정합니다. 공용위원회는 소속 없는 연구자로 봅니다.")
    with st.expander("기관별 서식 비교 (서식 표준화: 표준 항목 한 줄에 기관마다 다른 서식 이름)"):
        st.dataframe(result.compare, hide_index=True)
    if result.highlights and result.masked_text:
        st.markdown("#### 계획서에서 볼 곳")
        st.markdown(_marked(result.masked_text, result.highlights), unsafe_allow_html=True)
        for n, h in enumerate(result.highlights, 1):
            st.caption(f"{n}. 「{h.span}」 {h.note}")
