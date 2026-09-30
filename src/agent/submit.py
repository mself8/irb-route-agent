"""⑪ 제출 도우미. 제출 조건을 규칙으로 확인하고, 통과하면 모의 e-IRB에 칸을 채우고 서류를 올린 뒤 최종 제출 앞에서 멈춘다.
사람이 캡처와 입력값을 보고 승인하면 최종 제출을 눌러 접수번호를 받는다. 사무국 메일 초안은 만들기만 하고 보내지 않는다.

- 제출 조건(전부 만족): 경로 A·B·C / 보완 필요 0건 / (나) 연구자 입력 0건 / ⑧ 서류 목록을 모두 "준비됨"으로 체크 / 사람의 최종 승인.
  (가) 위원회 판단 항목은 막지 않는다. 사무국 메일 초안에 질문으로 넣는다.
- 채울 값: 확정 사실과 판정 결과, 보완 문구를 붙인 계획서. 칸 이름은 관할 기관 프로필(기관 서식 항목)에서, 없으면 표준 항목 이름.
- 안전: 접속은 허용 목록(127.0.0.1·localhost)의 모의 사이트만. 브라우저의 다른 주소 요청도 막는다. 실제 기관 사이트는 조작하지 않는다.
  캡처와 첨부 파일은 /tmp에만 둔다. 계정은 모의 사이트의 데모용 가짜 계정이다.
"""
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yaml
from langgraph.types import interrupt

ROOT = Path(__file__).resolve().parents[2]
STANDARD = yaml.safe_load((ROOT / "data" / "institutions" / "standard.yaml").read_text(encoding="utf-8"))
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
DEMO_ID, DEMO_PW = "demo", "demo"  # 모의 사이트의 데모용 가짜 계정
ROUTES = ("A", "B", "C")
FAKE_NOTE = "예시 모드라 모의 사이트에도 제출하지 않습니다. 실제 모드(FAKE=0)에서 모의 e-IRB에 채우고 제출합니다."


def mock_url() -> str:
    return os.getenv("MOCK_EIRB_URL", "http://127.0.0.1:8765")


def allowed(url: str) -> bool:
    return urlparse(url).hostname in ALLOWED_HOSTS


def _check(url: str) -> None:
    if not allowed(url):
        raise PermissionError(f"제출 도우미는 모의 사이트(127.0.0.1)만 조작합니다: {url}")


def required_docs(result: dict) -> list[str]:
    """⑧이 이 연구에 낸 서류 목록 (관할 기관 서식 이름이 반영돼 있다)."""
    return [d["doc"] for d in result.get("documents", [])]


def gate(result: dict, checklist: dict) -> list[str]:
    """제출을 막는 이유 목록. 비어 있으면 통과."""
    blockers = []
    route = (result.get("route") or {}).get("route")
    if route not in ROUTES:
        blockers.append(f"경로가 '{route}'라 이 도우미로 제출하지 않습니다 (A·B·C만)")
    blockers += [f"보완 필요 · {s['warning']}" for s in result.get("suggestions", []) if s.get("level") == "보완 필요"]
    blockers += [f"연구자 입력 필요 · {a.get('ask_input') or a.get('reason')}" for a in result.get("abstain", [])
                 if a.get("kind") == "나"]
    blockers += [f"서류 준비 안 됨 · {d}" for d in required_docs(result) if not checklist.get(d)]
    return blockers


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.다])\s+|\n", text) if s.strip()]


def _show(value) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value)) or "없음"
    return str(value)


def package(result: dict, masked_text: str) -> dict:
    """모의 사이트에 넣을 값: 기본 칸, 계획서 항목 칸([{표준 항목, 기관 칸, 값}]), 첨부할 서류, 사무국 메일 초안."""
    venue = result.get("venue") or {}
    facts = {f["key"]: f for f in result.get("facts", []) if f.get("status") != "not_found"}
    lines = _sentences(masked_text)
    title = next((line.split(":", 1)[1].strip() for line in masked_text.splitlines() if line.startswith("연구 제목")),
                 lines[0] if lines else "")
    route = result.get("route") or {}
    exempt = any("심의면제" in c for c in route.get("committees", []))
    basic = {"title": title, "review_type": "심의면제 신청" if exempt else "신규 심의",
             "route": f"경로 {route.get('route')} · " + " → ".join(route.get("committees", [])),
             "period": str((facts.get("F13") or {}).get("value") or ""),
             "size": str((facts.get("F15") or {}).get("value") or "")}
    items = venue.get("plan_items") or [{"item": k, "label": k} for k in STANDARD["plan"]]
    add_texts = [s["add_text"] for s in result.get("suggestions", []) if s.get("add_text")]
    fields = []
    for it in items:
        spec = STANDARD["plan"].get(it["item"], {})
        words = spec.get("words", [])
        found = [f"{facts[k]['label']}: {_show(facts[k]['value'])}" for k in spec.get("facts", []) if k in facts]
        found += [s for s in lines if any(w in s for w in words)]
        value = " / ".join(dict.fromkeys(found)) or "(계획서에 없음 · 제출 전 보완)"
        fields.append({"표준 항목": it["item"], "기관 칸": it.get("label") or it["item"], "값": value})
    plan = masked_text + ("\n\n[보완 문구 · [ ]는 연구자가 채움]\n" + "\n".join(add_texts) if add_texts else "")
    asks = [a.get("question") for a in result.get("abstain", []) if a.get("kind") == "가" and a.get("question")]
    where = venue.get("name") or " → ".join(route.get("committees", []))
    email = "\n".join([
        f"받는 곳: {where} 사무국", f"제목: [제출 전 문의] {title}", "",
        f"안녕하세요. 「{title}」의 {basic['review_type']}을 준비하는 연구책임자입니다. 제출 전에 아래 사항을 확인 부탁드립니다.",
        *[f"{n}. {q}" for n, q in enumerate(asks, 1)], "",
        "※ 연구행정 도우미 '여기까지'로 정리한 초안입니다. 심의 결과나 승인 여부를 예측하지 않습니다.",
        "※ 이 초안은 보내지 않았습니다. 복사해서 직접 보내 주세요.",
    ])
    return {"venue": venue.get("id") or "standard", "venue_name": venue.get("short") or "표준 서식 (기관 프로필 없음)",
            "basic": basic, "fields": fields, "docs": required_docs(result), "plan": plan, "email_draft": email}


def preview(result: dict, checklist: dict) -> dict:
    """예시 모드(FAKE=1): 게이트와 필드 표만 보여 주고 제출하지 않는다."""
    blockers = gate(result, checklist)
    pkg = package(result, result.get("masked_text", ""))
    return {"status": "blocked" if blockers else "preview", "venue": pkg["venue_name"], "blockers": blockers,
            "fields": pkg["fields"], "files": pkg["docs"], "email_draft": pkg["email_draft"], "message": FAKE_NOTE}


def _browser(p):
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.route("**/*", lambda route: route.continue_() if allowed(route.request.url) else route.abort())
    return browser, page


def _login(page, base: str, venue: str) -> None:
    page.goto(f"{base}/?venue={venue}")
    page.fill("input[name=id]", DEMO_ID)
    page.fill("input[name=pw]", DEMO_PW)
    page.click("#login")
    page.wait_for_url("**/checklist**")


def fill(pkg: dict, base: str | None = None) -> dict:
    """모의 사이트에 로그인 → 서류 확인 → 칸 채우기·첨부 → 신청 확인 화면(최종 제출 버튼 앞)에서 멈추고 캡처한다."""
    from playwright.sync_api import sync_playwright

    base = base or mock_url()
    _check(base)
    out = Path(tempfile.mkdtemp(prefix="nais_submit_", dir="/tmp"))
    uploads = []  # 한글 경로는 이 환경의 브라우저가 못 여니, 파일 내용과 이름을 직접 넘긴다. 사본은 /tmp에 ASCII 이름으로 둔다
    for i, doc in enumerate(pkg["docs"], 1):
        body = pkg["plan"] if "계획서" in doc else f"모의 업로드 파일 · {doc}\n데모용이며 실제 서류가 아닙니다."
        (out / f"doc{i}.txt").write_text(body, encoding="utf-8")
        name = re.sub(r"[\\/:*?\"<>|]+", " ", doc).strip()[:60] + ".txt"
        uploads.append({"name": name, "mimeType": "text/plain", "buffer": body.encode("utf-8")})
    with sync_playwright() as p:
        browser, page = _browser(p)
        _login(page, base, pkg["venue"])
        page.click("#next")
        page.wait_for_url("**/form**")
        for name, value in pkg["basic"].items():
            page.fill(f'input[name="{name}"]', value)
        labels = {f["표준 항목"]: f["값"] for f in pkg["fields"]}
        for area in page.locator("textarea").all():
            key = (area.get_attribute("name") or "").removeprefix("plan:")
            if key in labels:
                area.fill(labels[key])
        for i, upload in enumerate(uploads[:6], 1):
            page.set_input_files(f'input[name="attach{i}"]', upload)
        page.click("#save-draft")
        page.wait_for_url("**/review/**")
        draft_id = page.url.rsplit("/", 1)[-1]
        shot = out / "review.png"
        page.screenshot(path=str(shot), full_page=True)
        browser.close()
    return {"draft_id": draft_id, "screenshot": str(shot), "files": [u["name"] for u in uploads]}


def final_submit(draft_id: str, venue: str, base: str | None = None) -> dict:
    """승인 뒤에만 부른다. 신청 확인 화면에서 최종 제출을 누르고 접수번호를 읽는다."""
    from playwright.sync_api import sync_playwright

    base = base or mock_url()
    _check(base)
    with sync_playwright() as p:
        browser, page = _browser(p)
        _login(page, base, venue)
        page.goto(f"{base}/review/{draft_id}")
        page.click("#final-submit")
        page.wait_for_url("**/receipt/**")
        receipt = page.inner_text("#receipt")
        shot = Path(tempfile.mkdtemp(prefix="nais_receipt_", dir="/tmp")) / "receipt.png"
        page.screenshot(path=str(shot), full_page=True)
        browser.close()
    return {"receipt": receipt, "screenshot": str(shot)}


# ---- LangGraph 노드 (graph.py가 step10 뒤에 잇는다) ----

def prepare(state: dict) -> dict:
    """⑪-1 제출 조건 확인 → 통과하면 모의 e-IRB에 채우고 최종 제출 앞에서 멈출 준비를 한다."""
    view = {"route": state.get("route"), "suggestions": state.get("suggestions", []), "abstain": state.get("abstain", []),
            "documents": state.get("documents", []), "venue": state.get("venue"), "facts": state.get("confirmed_facts", [])}
    blockers = gate(view, state.get("checklist") or {})
    pkg = package(view, state.get("masked_text", ""))
    sub = {"venue": pkg["venue_name"], "blockers": blockers, "fields": pkg["fields"], "files": pkg["docs"],
           "email_draft": pkg["email_draft"]}
    if blockers:
        return {"submission": {**sub, "status": "blocked"}, "submit_requested": False}
    try:
        filled = fill(pkg)
    except Exception as e:  # 모의 사이트가 꺼져 있거나 화면이 바뀐 경우
        return {"submission": {**sub, "status": "blocked",
                               "blockers": [f"모의 사이트에 채우지 못했습니다 ({type(e).__name__}). "
                                            "python demo/mock_eirb/server.py 로 모의 사이트를 켜 주세요."]},
                "submit_requested": False}
    return {"submission": {**sub, "status": "awaiting_approval", "draft_id": filled["draft_id"], "venue_id": pkg["venue"],
                           "screenshot": filled["screenshot"], "files": filled["files"]}}


def approve(state: dict) -> dict:
    """⑪-2 사람의 최종 승인(interrupt). 승인하면 최종 제출을 눌러 접수번호를 받는다. 끝나면 제출 요청을 지운다."""
    sub = dict(state["submission"])
    answer = interrupt({"submission": sub})
    if answer.get("approved"):
        done = final_submit(sub["draft_id"], sub["venue_id"])
        sub.update(status="submitted", receipt=done["receipt"], screenshot=done["screenshot"])
    else:
        sub.update(status="cancelled", message="연구자가 제출을 취소했습니다. 모의 사이트에는 임시 저장본만 남습니다.")
    return {"submission": sub, "submit_requested": False}
