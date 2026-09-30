"""여기까지 · Streamlit 시작점.  실행: FAKE=1 streamlit run app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st  # noqa: E402

from ui import s1_input, s2_facts, s3_result, s5_abstain  # noqa: E402

st.set_page_config(page_title="여기까지", layout="wide")

SCREENS = [("입력", s1_input), ("사실 확인", s2_facts), ("판정 결과", s3_result), ("판단불가", s5_abstain)]
step = st.session_state.setdefault("step", 0)

st.title("여기까지")
st.caption("  →  ".join(
    f"**{i + 1}. {name}**" if i == step else f"{i + 1}. {name}" for i, (name, _) in enumerate(SCREENS)
))
SCREENS[step][1].render()
