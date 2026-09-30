"""S3 결과 대시보드 (⑤~⑧). 세 카드: 어느 위원회 / 어떤 서류 / 언제까지."""
import streamlit as st


def render() -> None:
    result = st.session_state.result
    route = result.route
    st.info(result.notice)
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
            st.write(f"보완 {sc.revisions}회{default}: {sc.submit_by or '공개 수치 없음'}")
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
