"""S3 결과 대시보드 (⑤~⑧). 세 카드: 어느 위원회 / 어떤 서류 / 언제까지. 그 아래 제출 전 보완과 계획서 표시."""
import html

import streamlit as st

YELLOW = "#FFE066"


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
    if result.suggestions:
        st.markdown("#### 제출 전 보완")
        for s in result.suggestions:
            with st.container(border=True):
                st.markdown(f"**{s.level}** · {s.rule_id} · {s.warning}")
                if s.add_text:
                    st.caption("계획서에 넣을 문장. [ ]는 사실에 맞게 채우세요 (오른쪽 위 아이콘으로 복사)")
                    st.code(s.add_text, language=None, wrap_lines=True)
                if s.basis:
                    st.caption(f"근거: {s.basis}")
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
