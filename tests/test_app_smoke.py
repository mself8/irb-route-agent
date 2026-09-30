"""화면이 에러 없이 뜨는지만 본다."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent import samples


def paste_sample(app, sample_id: str):
    """S1 샘플 버튼처럼 계획서와 기관을 입력칸에 넣는다. 화면의 샘플 목록(실제형)과 상관없이 테스트용 짧은 샘플을 쓴다."""
    s = samples.load(sample_id)
    app.session_state["plan_text"] = s["plan_text"]
    app.session_state["institution_name"] = s["institution_name"]
    return app.run(timeout=30)


def test_app_starts():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception


@pytest.mark.parametrize("fake", [False, True], ids=["real", "fake"])
def test_confirmed_result_and_questions_flow(monkeypatch, fake):
    """두 샘플의 입력/확정/결과/질문 이동에서 API 결과와 사무국 질문을 유지한다."""
    monkeypatch.setenv("LLM", "0")
    from agent import api
    monkeypatch.setattr(api, "FAKE", fake)
    for sample_id in ("sample1_crf", "sample2_pseudo"):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
        paste_sample(app, sample_id)
        next(b for b in app.button if b.label == "사실 추출 시작").click().run(timeout=60)
        assert not app.exception and app.session_state.step == 1
        pending = app.session_state.pending
        next(b for b in app.button if b.label == "사실 확정하고 판정").click().run(timeout=60)
        assert not app.exception and app.session_state.step == 2
        result = app.session_state.result
        assert result.run_id == pending.run_id
        assert result.facts == pending.facts
        assert result.route.route == samples.load(sample_id)["result"]["route"]["route"]
        next(b for b in app.button if b.label == "판단불가 / 질문").click().run(timeout=30)
        assert not app.exception and app.session_state.step == 3
        assert app.session_state.result == result
        shown_questions = [code.value for code in app.code]
        for item in result.abstain:
            if item.kind == "가" and item.question:
                assert item.question in shown_questions
            elif item.kind == "나" and item.input_key:
                inputs = list(app.radio) + list(app.text_input)
                assert any(widget.label == (item.ask_input or item.reason) for widget in inputs)
        next(b for b in app.button if b.label == "결과 대시보드로 돌아가기").click().run(timeout=30)
        assert not app.exception and app.session_state.step == 2
        assert app.session_state.result == result


def test_demo_samples(monkeypatch):
    """화면의 실제형 샘플 3건: 버튼 → 추출 → 확정이 실제 그래프로 돌고, 기관마다 그 기관 기준으로 판정한다."""
    monkeypatch.setenv("LLM", "0")
    from agent import api
    monkeypatch.setattr(api, "FAKE", False)
    expect = {"real1_cdw_cmc": ("A", "cmc", "I-CMC-10"), "real2_chart_khmc": ("C", "khmc", "I-KHMC-1"),
              "real3_survey_cuk": ("C", "cuk", "I-CUK-1")}
    for sample_id, (route, venue, rule) in expect.items():
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
        app.button(key=f"sample_{sample_id}").click().run(timeout=30)
        next(b for b in app.button if b.label == "사실 추출 시작").click().run(timeout=60)
        next(b for b in app.button if b.label == "사실 확정하고 판정").click().run(timeout=60)
        r = app.session_state.result
        assert not app.exception
        assert (r.route.route, r.venue.id) == (route, venue), sample_id
        assert any(j.rule_id == rule and j.result == "미충족" for j in r.judgments), sample_id
