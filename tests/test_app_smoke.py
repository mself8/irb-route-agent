"""화면이 에러 없이 뜨는지만 본다."""
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_starts():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception


def test_switch_institution(monkeypatch):
    """샘플 2를 확정한 뒤 '다른 기관에 낸다면'으로 서울시립대를 고르면 그 기관 기준으로 다시 판정한다 (그래프, 모델 없이)."""
    monkeypatch.setenv("LLM", "0")
    from agent import api
    monkeypatch.setattr(api, "FAKE", False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    app.button(key="sample_sample2_pseudo").click().run(timeout=30)
    next(b for b in app.button if b.label == "사실 추출 시작").click().run(timeout=60)
    next(b for b in app.button if b.label == "사실 확정하고 판정").click().run(timeout=60)
    app.selectbox[0].select("서울시립대").run(timeout=30)
    next(b for b in app.button if b.label == "이 기관 기준으로 다시 판정").click().run(timeout=60)
    assert not app.exception
    assert app.session_state.result.venue.id == "uos"
    assert any("서울시립대 안내문 기준" in m.value for m in app.markdown)


def test_switch_disabled_in_fake_mode(monkeypatch):
    """예시 모드는 미리 만든 결과라 기관 전환을 막고 그 이유를 적는다 (9차 리뷰)."""
    from agent import api
    monkeypatch.setattr(api, "FAKE", True)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    app.button(key="sample_sample2_pseudo").click().run(timeout=30)
    next(b for b in app.button if b.label == "사실 추출 시작").click().run(timeout=30)
    next(b for b in app.button if b.label == "사실 확정하고 판정").click().run(timeout=30)
    assert not app.exception and app.selectbox[0].disabled
    assert any("예시 모드(FAKE=1)" in c.value for c in app.caption)
