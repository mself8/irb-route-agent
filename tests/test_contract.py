"""화면과 로직의 약속(state.py)을 지키는지 본다. 합치기 전에 꼭 돌린다: pytest"""
import pytest

from agent import api, samples
from agent.state import FACT_LABELS, Pending, Result


@pytest.mark.parametrize("sample_id", samples.all_ids())
def test_sample_fits_contract(sample_id):
    sample = samples.load(sample_id)
    pending = Pending(run_id="t", **sample["pending"])
    Result(run_id="t", facts=sample["pending"]["facts"], **sample["result"])
    assert [(f.key, f.label) for f in pending.facts] == list(FACT_LABELS.items())
    for f in pending.facts:  # 원문 구간은 가린 계획서에 글자 그대로 있어야 한다
        if f.span:
            assert pending.masked_text[f.span_start:f.span_end] == f.span


@pytest.mark.parametrize("fake", [True, False], ids=["fake", "graph"])
def test_start_confirm_rejudge(monkeypatch, fake):
    monkeypatch.setattr(api, "FAKE", fake)
    for sample_id, route in {"sample1_crf": "C", "sample2_pseudo": "A"}.items():
        sample = samples.load(sample_id)
        pending = api.start(sample["plan_text"], sample["institution_name"], "2026-12-01")
        result = api.confirm(pending.run_id, [f.model_dump() for f in pending.facts])
        assert result.route.route == route
        asks = [a for a in result.abstain if a.kind == "나"]
        if asks:  # (나) 입력 후 ④부터 다시 판정하면 그 항목이 사라진다
            again = api.rejudge(pending.run_id, {a.input_key: a.options[0] for a in asks})
            assert not [a for a in again.abstain if a.kind == "나"]
