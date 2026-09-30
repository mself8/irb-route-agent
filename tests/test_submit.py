"""⑪ 제출 도우미 테스트. 실제 그래프(FAKE=0)·LLM=0으로, 모의 e-IRB를 스레드로 띄워 headless 브라우저로 돈다.

샘플 2: 게이트 막힘((나) F05·서류 미준비) → F05 답 → IRB 서류 체크 → 채우기(최종 제출 앞에서 멈춤) → 승인 → 접수번호.
Playwright Chromium이 없으면 브라우저가 필요한 테스트는 건너뛴다.
"""
import os
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from agent import api, samples, submit
from test_app_smoke import paste_sample

ROOT = Path(__file__).resolve().parents[1]


def _has_browser() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


needs_browser = pytest.mark.skipif(not _has_browser(), reason="Playwright Chromium이 없음")


@pytest.fixture(scope="module")
def mock_site():
    sys.path.insert(0, str(ROOT / "demo" / "mock_eirb"))
    import server
    srv = server.serve(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    old = os.environ.get("MOCK_EIRB_URL")
    os.environ["MOCK_EIRB_URL"] = f"http://127.0.0.1:{srv.server_port}"
    yield srv
    srv.shutdown()
    if old is None:
        os.environ.pop("MOCK_EIRB_URL", None)
    else:
        os.environ["MOCK_EIRB_URL"] = old


@pytest.fixture
def real(monkeypatch, mock_site):
    monkeypatch.setattr(api, "FAKE", False)
    s = samples.load("sample2_pseudo")
    p = api.start(s["plan_text"], s["institution_name"], "2026-12-01")
    api.confirm(p.run_id, [f.model_dump() for f in p.facts])
    yield p.run_id
    for d in Path("/tmp").glob("nais_*"):  # 이 테스트가 만든 캡처·첨부 사본
        shutil.rmtree(d, ignore_errors=True)


def ready(run_id: str) -> dict:
    """F05를 답해 (나)를 없애고, IRB에 내는 서류를 모두 준비됨으로 체크한 checklist."""
    result = api.rejudge(run_id, {"F05": "기관 내부"})
    return {d: True for d in submit.irb_docs(result.model_dump())}


def test_gate_rules():
    ok = {"route": {"route": "A"}, "suggestions": [{"rule_id": "C3", "level": "확인 필요", "warning": "w"}],
          "abstain": [{"kind": "가", "question": "q"}], "documents": [{"doc": "신청서"}, {"doc": "DRB 신청서", "to": "DRB"}]}
    assert submit.gate(ok, {"신청서": True}) == []                     # DRB에 내는 서류는 IRB 게이트에 걸지 않는다
    assert submit.gate({**ok, "route": {"route": "임상시험"}}, {"신청서": True})
    assert submit.gate({**ok, "decision": {"irb": "contract"}}, {"신청서": True})  # 위탁 협약 전: 제출처 미정
    assert submit.gate({**ok, "suggestions": [{"rule_id": "I-UOS-2", "level": "보완 필요", "warning": "공문"}]}, {"신청서": True})
    assert submit.gate({**ok, "suggestions": [{"rule_id": "I-UOS-P", "level": "보완 필요", "warning": "칸"}]}, {"신청서": True}) == []
    assert submit.gate({**ok, "abstain": [{"kind": "나", "ask_input": "누가 분석하나요?"}]}, {"신청서": True})
    assert submit.gate(ok, {}) == ["서류 준비 안 됨 · 신청서"]


def test_only_mock_site_is_allowed():
    assert submit.allowed("http://127.0.0.1:8765/") and submit.allowed("http://localhost:1/x")
    for url in ["https://example.com/", "https://public.irb.or.kr/", "file://localhost/etc/passwd", "ftp://127.0.0.1/",
                "http://127.0.0.2:8765/", "http://evil.example\\@127.0.0.1:8765", "http://user:pw@127.0.0.1/",
                " http://127.0.0.1/", "http://localhost./", "javascript:alert(1)"]:
        assert not submit.allowed(url), url
    with pytest.raises(PermissionError):
        submit.fill({"docs": [], "plan": "", "basic": {}, "fields": [], "venue_name": "", "plan_form": ""},
                    base="https://example.com")


@pytest.mark.parametrize("text, title", [("연구 제목: 정상", "정상"), ("연구 제목：전각 콜론", "전각 콜론"),
                                         ("연구 제목은 「가상 연구」이다.\n연구 방법: 기록", "연구 제목은 「가상 연구」이다."),
                                         ("연구 제목\n가상 연구", "연구 제목")])
def test_title_never_crashes(text, title):
    pkg = submit.package({"route": {"route": "A", "committees": ["x"]}}, text)
    assert pkg["basic"]["title"] == title


def test_review_type_follows_decision_only():
    base = {"route": {"route": "A", "committees": ["소속 기관 IRB · 심의면제 신청 후보"]}}
    assert submit.package({**base, "decision": {"exempt": "unknown"}}, "")["basic"]["review_type"] == "위원회 확인 후 결정"
    assert submit.package({**base, "decision": {"exempt": "yes"}}, "")["basic"]["review_type"] == "심의면제 신청"
    assert submit.package(base, "")["basic"]["review_type"] == "위원회 확인 후 결정"


@needs_browser
def test_browser_cannot_leave_loopback_allowlist():
    """127.0.0.1 페이지가 리다이렉트·이미지·meta·새 창·웹소켓·beacon으로 127.0.0.2에 보내도 한 번도 닿지 않는다."""
    hits = []

    class Sink(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        do_POST = do_GET

    sink = ThreadingHTTPServer(("127.0.0.2", 0), Sink)
    target = f"http://127.0.0.2:{sink.server_port}"

    class Evil(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/redir"):
                self.send_response(302)
                self.send_header("Location", f"{target}/redirect")
                self.end_headers()
                return
            body = {"/img": f"<img src='{target}/img'>", "/meta": f"<meta http-equiv=refresh content='0;url={target}/meta'>",
                    "/popup": f"<script>window.open('{target}/popup')</script>",
                    "/ws": f"<script>try{{new WebSocket('ws://127.0.0.2:{sink.server_port}/ws')}}catch(e){{}}</script>",
                    "/beacon": f"<script>navigator.sendBeacon('{target}/beacon','x')</script>"}.get(self.path, "<p>x</p>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())

    evil = ThreadingHTTPServer(("127.0.0.1", 0), Evil)
    for s in (sink, evil):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = submit._browser(p)
        for path in ("/redir", "/img", "/meta", "/popup", "/ws", "/beacon"):
            try:
                page.goto(f"http://127.0.0.1:{evil.server_port}{path}", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(800)
        browser.close()
    sink.shutdown()
    evil.shutdown()
    assert hits == []


@needs_browser
def test_blocked_then_fill_approve_receipt(real):
    first = api.request_submission(real, {}).submission
    assert first.status == "blocked"
    assert any("연구자 입력 필요" in b for b in first.blockers) and any("서류 준비 안 됨" in b for b in first.blockers)

    waiting = api.request_submission(real, ready(real)).submission
    assert waiting.status == "awaiting_approval" and not waiting.blockers
    assert Path(waiting.screenshot).exists() and waiting.screenshot.startswith("/tmp/")
    assert waiting.fields and all({"표준 항목", "기관 칸", "값"} <= set(f) for f in waiting.fields)
    assert waiting.label_source and "표준 항목" in waiting.label_source   # 프로필 없는 기관은 기관 칸 이름인 척하지 않는다

    done = api.approve_submission(real, True).submission
    assert done.status == "submitted" and done.receipt.startswith("MOCK-2026-")
    assert "보내지 않았습니다" in done.email_draft


@needs_browser
def test_cancel_gives_no_receipt(real):
    api.request_submission(real, ready(real))
    done = api.approve_submission(real, False).submission
    assert done.status == "cancelled" and done.receipt is None


@needs_browser
def test_final_submit_failure_is_reported(real, monkeypatch):
    api.request_submission(real, ready(real))
    monkeypatch.setenv("MOCK_EIRB_URL", "http://127.0.0.1:9")  # 모의 사이트가 꺼진 것처럼
    done = api.approve_submission(real, True).submission
    assert done.status == "blocked" and "최종 제출에 실패" in done.blockers[0] and done.receipt is None


@needs_browser
def test_rejudge_resets_submission(real):
    checklist = ready(real)
    assert api.request_submission(real, checklist).submission.status == "awaiting_approval"
    again = api.rejudge(real, {"F05": "기관 내부"})
    assert again.submission is None  # 다시 판정하면 제출 준비는 처음부터 (저절로 다시 제출되지 않는다)
    assert api.request_submission(real, checklist).submission.status == "awaiting_approval"


def test_fake_mode_keeps_answers_and_never_submits(monkeypatch):
    monkeypatch.setattr(api, "FAKE", True)
    s = samples.load("sample2_pseudo")
    p = api.start(s["plan_text"], s["institution_name"], "2026-12-01")
    api.rejudge(p.run_id, {"F05": "기관 내부"})
    sub = api.request_submission(p.run_id, {}).submission
    assert not any("연구자 입력" in b for b in sub.blockers)  # S5에서 답한 F05를 잃지 않는다
    assert sub.status in ("blocked", "preview") and sub.receipt is None and "예시 모드" in sub.message


@needs_browser
def test_ui_demo_flow(monkeypatch, mock_site):
    """데모 클릭 순서 그대로: 샘플 2 → 확정 → 제출 준비(막힘) → 판단불가에서 F05 답 → 제출 준비 → 서류 체크 → 채우기 → 승인."""
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(api, "FAKE", False)
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    click = lambda label: next(b for b in app.button if b.label == label).click().run(timeout=90)  # noqa: E731
    paste_sample(app, "sample2_pseudo")
    click("사실 추출 시작")
    click("사실 확정하고 판정")
    click("제출 준비 (모의 e-IRB)")
    click("제출 사이트로 이동")
    assert app.session_state.result.submission.status == "blocked"
    click("판단불가 화면에서 입력하기")
    next(r for r in app.radio if "누가 분석" in r.label).set_value("기관 내부").run(timeout=30)
    click("입력한 값으로 다시 판정")
    click("제출 준비 (모의 e-IRB)")
    for box in app.checkbox:
        box.check()
    app.run(timeout=30)
    click("제출 사이트로 이동")
    assert app.session_state.result.submission.status == "awaiting_approval"
    click("승인하고 최종 제출")
    assert not app.exception
    assert app.session_state.result.submission.receipt.startswith("MOCK-2026-")
    assert any("접수번호" in s.value for s in app.success)
    assert not any(b.label == "제출 사이트로 이동" for b in app.button)  # 접수 뒤에는 다시 채우지 않는다
    for d in Path("/tmp").glob("nais_*"):
        shutil.rmtree(d, ignore_errors=True)
