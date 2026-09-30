"""⑪ 제출 도우미 테스트. 실제 그래프(FAKE=0)·LLM=0으로, 모의 e-IRB를 스레드로 띄워 headless 브라우저로 돈다.

샘플 2: 게이트 막힘((나) F05·서류 미준비) → F05 답 → 서류 체크 → 채우기(최종 제출 앞에서 멈춤) → 승인 → 접수번호.
"""
import os
import sys
import threading
from pathlib import Path

import pytest

from agent import api, samples, submit

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def mock_site():
    sys.path.insert(0, str(ROOT / "demo" / "mock_eirb"))
    import server
    srv = server.serve(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["MOCK_EIRB_URL"] = f"http://127.0.0.1:{srv.server_port}"
    yield srv
    srv.shutdown()


@pytest.fixture
def real(monkeypatch, mock_site):
    monkeypatch.setattr(api, "FAKE", False)
    s = samples.load("sample2_pseudo")
    p = api.start(s["plan_text"], s["institution_name"], "2026-12-01")
    api.confirm(p.run_id, [f.model_dump() for f in p.facts])
    return p.run_id


def ready(run_id: str) -> dict:
    """F05를 답해 (나)를 없애고, ⑧ 서류를 모두 준비됨으로 체크한 checklist."""
    result = api.rejudge(run_id, {"F05": "기관 내부"})
    return {d.doc: True for d in result.documents}


def test_gate_rules():
    ok = {"route": {"route": "A"}, "suggestions": [{"level": "확인 필요", "warning": "w"}],
          "abstain": [{"kind": "가", "question": "q"}], "documents": [{"doc": "신청서"}]}
    assert submit.gate(ok, {"신청서": True}) == []
    assert submit.gate({**ok, "route": {"route": "임상시험"}}, {"신청서": True})
    assert submit.gate({**ok, "suggestions": [{"level": "보완 필요", "warning": "보완"}]}, {"신청서": True})
    assert submit.gate({**ok, "abstain": [{"kind": "나", "ask_input": "누가 분석하나요?"}]}, {"신청서": True})
    assert submit.gate(ok, {}) == ["서류 준비 안 됨 · 신청서"]


def test_only_mock_site_is_allowed():
    assert submit.allowed("http://127.0.0.1:8765/") and submit.allowed("http://localhost:1/x")
    assert not submit.allowed("https://example.com/") and not submit.allowed("https://public.irb.or.kr/")
    with pytest.raises(PermissionError):
        submit.fill({"docs": [], "plan": "", "basic": {}, "fields": [], "venue": "standard"}, base="https://example.com")


def test_blocked_then_fill_approve_receipt(real):
    first = api.request_submission(real, {}).submission
    assert first.status == "blocked"
    assert any("연구자 입력 필요" in b for b in first.blockers) and any("서류 준비 안 됨" in b for b in first.blockers)

    waiting = api.request_submission(real, ready(real)).submission
    assert waiting.status == "awaiting_approval" and not waiting.blockers
    assert Path(waiting.screenshot).exists() and waiting.screenshot.startswith("/tmp/")
    assert waiting.fields and all({"표준 항목", "기관 칸", "값"} <= set(f) for f in waiting.fields)

    done = api.approve_submission(real, True).submission
    assert done.status == "submitted" and done.receipt.startswith("MOCK-2026-")
    assert "보내지 않았습니다" in done.email_draft


def test_cancel_gives_no_receipt(real):
    api.request_submission(real, ready(real))
    done = api.approve_submission(real, False).submission
    assert done.status == "cancelled" and done.receipt is None


def test_rejudge_resets_submission(real):
    checklist = ready(real)
    assert api.request_submission(real, checklist).submission.status == "awaiting_approval"
    again = api.rejudge(real, {"F05": "기관 내부"})
    assert again.submission is None  # 다시 판정하면 제출 준비는 처음부터 (저절로 다시 제출되지 않는다)
    assert api.request_submission(real, checklist).submission.status == "awaiting_approval"


def test_fake_mode_never_submits(monkeypatch):
    monkeypatch.setattr(api, "FAKE", True)
    s = samples.load("sample2_pseudo")
    p = api.start(s["plan_text"], s["institution_name"], "2026-12-01")
    sub = api.request_submission(p.run_id, {d: True for d in submit.required_docs({"documents": []})}).submission
    assert sub.status in ("blocked", "preview") and sub.receipt is None and "예시 모드" in sub.message
