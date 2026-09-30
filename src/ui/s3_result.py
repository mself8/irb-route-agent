"""S3 결과 대시보드 (⑤~⑧). 세 카드: 어느 위원회 / 어떤 서류 / 언제까지. 그 아래 제출 전 보완과 계획서 표시."""
import html

import streamlit as st

from agent import api

YELLOW = "#FFE066"


def _card(s) -> None:
    with st.container(border=True):
        st.markdown(f"**{s.level}** · {s.rule_id} · {s.warning}")
        if s.add_text:
            st.caption("계획서에 넣을 문장. [ ]는 사실에 맞게 채우세요 (오른쪽 위 아이콘으로 복사)")
            st.code(s.add_text, language=None, wrap_lines=True)
        if s.basis:
            st.caption(f"근거: {s.basis}")


def _marked(text: str, highlights) -> str:
    """가린 계획서에서 문제 구간을 노란색으로 칠한다. 번호는 아래 설명 목록과 같다."""
    out, pos = [], 0
    for n, h in enumerate(highlights, 1):
        if h.span_start < pos:
            continue
        out += [html.escape(text[pos:h.span_start]),
                f'<mark style="background:{YELLOW};color:#1F2A44">{html.escape(text[h.span_start:h.span_end])}<sup>{n}</sup></mark>']
        pos = h.span_end
    out.append(html.escape(text[pos:]))
    # 줄바꿈을 <br>로 바꿔 빈 줄에서 HTML 블록이 끊겨 마크다운으로 읽히지 않게 한다
    return '<div style="line-height:1.8">' + "".join(out).replace("\n", "<br>") + "</div>"


def render() -> None:
    result = st.session_state.result
    route = result.route
    st.info(result.notice)
    need = [s for s in result.suggestions if s.level == "보완 필요"]
    if need:
        st.warning(f"제출 전 보완 {len(need)}건 · 확인 {len(result.suggestions) - len(need)}건 — 아래 「제출 전 보완」을 먼저 보세요.")
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.markdown("**어느 위원회**")
        st.markdown(f"### 경로 {route.route}" + (" · 빠른 길 발견" if route.fast_track else ""))
        for n, committee in zip(route.order, route.committees):
            st.write(f"{n}. {committee}")
        st.caption("근거 규칙 " + " · ".join(route.trace))
        if result.venue:
            st.markdown(f"**제출처** {result.venue.name}")
            st.caption(result.venue.submit)
    with c2.container(border=True):
        st.markdown("**어떤 서류**")
        for d in result.documents:
            st.write(f"- {d.doc} ({d.level})")
    with c3.container(border=True):
        st.markdown("**언제까지**")
        for sc in result.schedule.scenarios:
            default = " · 기본값" if sc.revisions == result.schedule.default else ""
            step = f" · {sc.step}" if sc.step else ""
            st.write(f"보완 {sc.revisions}회{default}: {sc.submit_by or '공개 수치 없음'}{step}")
        for line in result.schedule.missing:
            st.caption(line)
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
        st.session_state.last_input = (text, venues[choice], start_date)  # "보완 문구 넣고 다시"도 바꾼 기관으로 간다
        st.session_state.result = api.rejudge(result.run_id, change)
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
    st.markdown("#### 체크포인트")
    st.dataframe(
        [{"규칙": j.rule_id, "요건": j.requirement, "결과": j.result, "판정 유형": j.type, "근거": j.basis.law}
         for j in result.judgments],
        hide_index=True,
    )
    st.markdown("#### 설명")
    for sentence in result.report:
        st.write(f"{sentence.text}  `{' · '.join(sentence.refs)}`")
    if st.button(f"판단불가 {len(result.abstain)}건 보기", type="primary"):
        st.session_state.step = 3
        st.rerun()
    # ⑪ 제출 도우미: 조건을 확인하고 모의 e-IRB에 채운 뒤 최종 제출 앞에서 멈춘다
    if st.button("제출 준비 (모의 e-IRB)"):
        st.session_state.step = 4
        st.rerun()
