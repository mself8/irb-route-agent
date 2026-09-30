"""S6 제출 준비 (⑪). 조건 확인 → 모의 e-IRB에 채우고 최종 제출 앞에서 멈춤 → 캡처·입력값 확인 → 승인하면 제출·접수번호.
모의 사이트(demo/mock_eirb, 127.0.0.1)만 조작한다. 실제 기관 사이트에는 제출하지 않는다.
"""
from pathlib import Path

import streamlit as st

from agent import api

STATUS = {"blocked": "제출 조건을 아직 못 넘었습니다", "awaiting_approval": "모의 e-IRB에 채웠습니다 · 최종 제출 앞에서 멈춤",
          "submitted": "모의 e-IRB에 제출했습니다", "cancelled": "제출을 취소했습니다", "preview": "예시 모드 미리보기"}


def render() -> None:
    result = st.session_state.result
    st.info(result.notice)
    st.subheader("제출 준비 · 모의 e-IRB (데모용, 실제 기관과 무관)")
    st.caption(f"경로 {result.route.route} · " + " → ".join(result.route.committees))
    sub = result.submission

    if not (sub and sub.status == "submitted"):  # 접수한 뒤에는 다시 채우지 않는다
        st.markdown("#### 1. IRB에 낼 서류 준비 체크")
        irb = [d for d in result.documents if getattr(d, "to", "IRB") == "IRB"]
        others = [d for d in result.documents if getattr(d, "to", "IRB") != "IRB"]
        checklist = {d.doc: st.checkbox(f"{d.doc} 준비됨", key=f"ready_{d.doc}") for d in irb}
        if others:
            st.caption("IRB가 아닌 곳에 내는 서류(체크·첨부하지 않음): " + " · ".join(f"{d.doc} → {d.to}" for d in others))
        if st.button("제출 조건 확인하고 모의 e-IRB에 채우기", type="primary"):
            with st.spinner("조건을 확인하고 모의 사이트에 채우는 중…"):
                st.session_state.result = result = api.request_submission(result.run_id, checklist)
                sub = result.submission

    if sub is None:
        st.caption("조건: 경로 A·B·C · 제출처 확정(위탁 협약 전이면 막음) · 보완 필요 0건 · 연구자 입력(나) 0건 · "
                   "IRB 서류 모두 준비됨 · 최종 승인. (가) 위원회 판단 항목은 막지 않고 사무국 메일 초안에 넣습니다.")
    else:
        st.markdown(f"#### 2. {STATUS.get(sub.status, sub.status)}")
        if sub.message:
            st.warning(sub.message)
        for b in sub.blockers:
            st.error(b)
        for w in sub.warnings:
            st.warning(w)
        if sub.blockers and any("연구자 입력" in b for b in sub.blockers) and st.button("판단불가 화면에서 입력하기"):
            st.session_state.step = 3
            st.rerun()
        if sub.fields:
            with st.expander(f"채울 값 · 칸 이름: {sub.label_source or sub.venue}", expanded=sub.status != "blocked"):
                st.dataframe(sub.fields, hide_index=True)
        if sub.screenshot and Path(sub.screenshot).exists():
            st.image(sub.screenshot, caption="모의 e-IRB 화면 캡처")
        if sub.status == "awaiting_approval":
            st.caption(f"올린 서류: {', '.join(sub.files) or '없음'}")
            left, right = st.columns(2)
            if left.button("승인하고 최종 제출", type="primary"):
                st.session_state.result = api.approve_submission(result.run_id, True)
                st.rerun()
            if right.button("취소"):
                st.session_state.result = api.approve_submission(result.run_id, False)
                st.rerun()
        if sub.receipt:
            st.success(f"접수번호 {sub.receipt} · 행정점검 대기 (모의 사이트)")
        if sub.email_draft:
            st.markdown("#### 사무국 메일 초안 (보내지 않았습니다 · 복사해서 쓰세요)")
            st.code(sub.email_draft, language=None, wrap_lines=True)

    if st.button("판정 결과로 돌아가기"):
        st.session_state.step = 2
        st.rerun()
