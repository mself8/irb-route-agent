"""⑪ 제출 도우미. 제출 조건을 규칙으로 확인하고, 통과하면 모의 e-IRB에 칸을 채우고 서류를 올린 뒤 최종 제출 앞에서 멈춘다.
사람이 캡처와 입력값을 보고 승인하면 최종 제출을 눌러 접수번호를 받는다. 사무국 메일 초안은 만들기만 하고 보내지 않는다.

- 제출 조건(전부 만족): 경로 A·B·C / 위탁 협약 전이 아님(제출처가 정해짐) / 보완 필요 0건 / (나) 연구자 입력 0건 /
  IRB에 내는 서류를 모두 "준비됨"으로 체크 / 사람의 최종 승인. (가) 위원회 판단 항목은 막지 않고 메일 초안에 질문으로 넣는다.
  기관 계획서 서식 칸 누락(I-*-P, 넣을 문장이 없는 경고)은 막지 않고 승인 전에 "빈 칸 N개"로 알린다(기관마다 기준이 뒤집히지 않게).
- 채울 값: 확정 사실과 판정 결과, 보완 문구를 붙인 계획서. 칸 이름은 엔진이 변형까지 적용한 관할 기관 서식(result.venue)에서,
  서식이 비공개거나 프로필이 없으면 표준 항목 이름이라고 밝힌다. 심의 유형은 판정(decision.exempt)으로만 정한다.
- 안전: 접속 주소는 http(s)://127.0.0.1·localhost만 허용한다(역슬래시·@·공백이 든 주소는 파서마다 다르게 읽혀 거부).
  브라우저에는 쓸 수 없는 프록시(127.0.0.1:9)를 걸고 127.0.0.1·localhost만 예외로 둬서, 리다이렉트·새 창·웹소켓을 포함해
  그 밖(127.0.0.2 같은 다른 루프백 주소 포함)으로 나가는 요청이 모두 실패한다. 컨텍스트 전체 요청도 허용 목록으로 한 번 더 거른다.
  캡처와 첨부 사본은 /tmp에만 두고 오래된 것은 지운다. 계정은 모의 사이트의 데모용 가짜 계정이다.
"""
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import yaml
from langgraph.types import interrupt

ROOT = Path(__file__).resolve().parents[2]
STANDARD = yaml.safe_load((ROOT / "data" / "institutions" / "standard.yaml").read_text(encoding="utf-8"))
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
DEMO_ID, DEMO_PW = "demo", "demo"  # 모의 사이트의 데모용 가짜 계정
ROUTES = ("A", "B", "C")
SLOTS = 12                          # 모의 사이트 첨부 칸 수
TIMEOUT_MS = 10_000
PLAN_FORM_GAP = re.compile(r"^I-[A-Z]+-P$")  # 기관 계획서 서식 칸 누락 경고
EMPTY = "(계획서에 없음 · 제출 전 보완)"
FAKE_NOTE = "예시 모드라 모의 사이트에도 제출하지 않습니다. 실제 모드(FAKE=0)에서 모의 e-IRB에 채우고 제출합니다."
REVIEW_TYPE = {"yes": "심의면제 신청", "no": "신규 심의"}


def mock_url() -> str:
    return os.getenv("MOCK_EIRB_URL", "http://127.0.0.1:8765")


def allowed(url: str) -> bool:
    """http(s)://127.0.0.1·localhost만. 파서마다 다르게 읽히는 문자(역슬래시·@·공백)가 있으면 거부한다."""
    if not isinstance(url, str) or url != url.strip() or re.search(r"[\\@\s]", url):
        return False
    u = urlparse(url)
    return u.scheme in ("http", "https") and u.hostname in ALLOWED_HOSTS


def _check(url: str) -> None:
    if not allowed(url):
        raise PermissionError(f"제출 도우미는 모의 사이트(127.0.0.1)만 조작합니다: {url}")


def irb_docs(result: dict) -> list[str]:
    """⑧ 서류 중 IRB에 내는 것만. DRB·결합전문기관 등 다른 곳에 내는 서류는 체크·첨부하지 않는다(to가 없으면 IRB)."""
    return [d["doc"] for d in result.get("documents", []) if d.get("to", "IRB") == "IRB"]


required_docs = irb_docs


def gate(result: dict, checklist: dict) -> list[str]:
    """제출을 막는 이유 목록. 비어 있으면 통과."""
    blockers = []
    route = (result.get("route") or {}).get("route")
    if route not in ROUTES:
        blockers.append(f"경로가 '{route}'라 이 도우미로 제출하지 않습니다 (A·B·C만)")
    if (result.get("decision") or {}).get("irb") == "contract":
        blockers.append("위탁 협약 전이라 제출할 위원회(협약 상대)가 아직 정해지지 않았습니다. 협약을 맺은 뒤 다시 판정해 주세요.")
    blockers += [f"보완 필요 · {s['warning']}" for s in result.get("suggestions", [])
                 if s.get("level") == "보완 필요" and not PLAN_FORM_GAP.match(s.get("rule_id", ""))]
    blockers += [f"연구자 입력 필요 · {a.get('ask_input') or a.get('reason')}" for a in result.get("abstain", [])
                 if a.get("kind") == "나"]
    blockers += [f"서류 준비 안 됨 · {d}" for d in irb_docs(result) if not checklist.get(d)]
    return blockers


def _show(value) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value)) or "없음"
    return str(value)


def _title(masked_text: str) -> str:
    m = re.search(r"연구\s*제목\s*[:：]\s*(.+)", masked_text)
    if m:
        return m.group(1).strip()
    return next((line.strip() for line in masked_text.splitlines() if line.strip()), "")[:80]


def package(result: dict, masked_text: str) -> dict:
    """모의 사이트에 넣을 값: 기본 칸, 계획서 항목 칸([{표준 항목, 기관 칸, 값}]), IRB 서류, 사무국 메일 초안."""
    venue = result.get("venue") or {}
    facts = {f["key"]: f for f in result.get("facts", []) if f.get("status") != "not_found"}
    lines = [s.strip() for s in re.split(r"(?<=[.다])\s+|\n", masked_text) if s.strip()]
    title = _title(masked_text)
    route = result.get("route") or {}
    kind = REVIEW_TYPE.get((result.get("decision") or {}).get("exempt"), "위원회 확인 후 결정")
    basic = {"title": title, "review_type": kind,
             "route": f"경로 {route.get('route')} · " + " → ".join(route.get("committees", [])),
             "period": _show((facts.get("F13") or {}).get("value") or ""),
             "size": _show((facts.get("F15") or {}).get("value") or "")}
    items = venue.get("plan_items") or []
    if items:
        source = f"{venue.get('short', '')} 서식 ({venue.get('plan_form', '')})"
    else:
        items = [{"item": k} for k in STANDARD["plan"]]
        source = "표준 항목 (이 기관 계획서 서식은 비공개)" if venue else "표준 항목 (기관 프로필 없음)"
    fields = []
    for it in items:
        spec = STANDARD["plan"].get(it["item"], {})
        found = [f"{facts[k]['label']}: {_show(facts[k]['value'])}" for k in spec.get("facts", []) if k in facts]
        found += [s for s in lines if any(w in s for w in spec.get("words", []))]
        fields.append({"표준 항목": it["item"], "기관 칸": it.get("label") or f"{it['item']} (표준 항목)",
                       "값": " / ".join(dict.fromkeys(found)) or EMPTY})
    add_texts = [s["add_text"] for s in result.get("suggestions", []) if s.get("add_text")]
    plan = masked_text + ("\n\n[보완 문구 · [ ]는 연구자가 채움]\n" + "\n".join(add_texts) if add_texts else "")
    asks = [a.get("question") for a in result.get("abstain", []) if a.get("kind") == "가" and a.get("question")]
    where = venue.get("name") or " → ".join(route.get("committees", []))
    email = "\n".join([
        f"받는 곳: {where} 사무국", f"제목: [제출 전 문의] {title}", "",
        f"안녕하세요. 「{title}」의 IRB 제출(심의 유형: {kind})을 준비하는 연구책임자입니다. 제출 전에 아래 사항을 확인 부탁드립니다.",
        *[f"{n}. {q}" for n, q in enumerate(asks, 1)], "",
        "※ 연구행정 도우미 '여기까지'로 정리한 초안입니다. 심의 결과나 승인 여부를 예측하지 않습니다.",
        "※ 이 초안은 보내지 않았습니다. 복사해서 직접 보내 주세요.",
    ])
    empty = sum(f["값"] == EMPTY for f in fields)
    return {"venue_name": venue.get("short") or "표준 서식 (기관 프로필 없음)", "plan_form": venue.get("plan_form", ""),
            "label_source": source, "basic": basic, "fields": fields, "docs": irb_docs(result), "plan": plan,
            "email_draft": email, "warnings": [f"빈 칸 {empty}개: 요약 계획서에 없는 항목입니다. 제출 전에 채워 주세요."] if empty else []}


def preview(result: dict, checklist: dict) -> dict:
    """예시 모드(FAKE=1): 게이트와 필드 표만 보여 주고 제출하지 않는다."""
    blockers = gate(result, checklist)
    pkg = package(result, result.get("masked_text", ""))
    return {"status": "blocked" if blockers else "preview", "venue": pkg["venue_name"], "blockers": blockers,
            "fields": pkg["fields"], "files": pkg["docs"], "email_draft": pkg["email_draft"], "message": FAKE_NOTE,
            "warnings": pkg["warnings"], "label_source": pkg["label_source"]}


def _cleanup(hours: float = 6) -> None:
    """오래된 캡처·첨부 사본(/tmp/nais_*)을 지운다."""
    for d in Path("/tmp").glob("nais_*"):
        if d.is_dir() and time.time() - d.stat().st_mtime > hours * 3600:
            shutil.rmtree(d, ignore_errors=True)


def _browser(p):
    browser = p.chromium.launch(headless=True,
                                proxy={"server": "http://127.0.0.1:9", "bypass": "<-loopback>,127.0.0.1,localhost"})
    context = browser.new_context(service_workers="block")
    context.route("**/*", lambda route: route.continue_() if allowed(route.request.url) else route.abort())
    context.set_default_timeout(TIMEOUT_MS)
    return browser, context.new_page()


def _login(page, base: str) -> None:
    page.goto(f"{base}/")
    page.fill("input[name=id]", DEMO_ID)
    page.fill("input[name=pw]", DEMO_PW)
    page.click("#login")
    page.wait_for_url("**/home")


def fill(pkg: dict, base: str | None = None) -> dict:
    """모의 사이트에 로그인 → 신청 양식 등록 → 서류 확인 → 칸 채우기·첨부 → 신청 확인 화면(최종 제출 앞)에서 멈추고 캡처한다."""
    from playwright.sync_api import sync_playwright

    base = base or mock_url()
    _check(base)
    _cleanup()
    out = Path(tempfile.mkdtemp(prefix="nais_submit_", dir="/tmp"))
    uploads = []  # 한글 경로는 이 환경의 브라우저가 못 여니, 파일 내용과 이름을 직접 넘긴다. 사본은 /tmp에 ASCII 이름으로 둔다
    for i, doc in enumerate(pkg["docs"][:SLOTS], 1):
        body = pkg["plan"] if "계획서" in doc else f"모의 업로드 파일 · {doc}\n데모용이며 실제 서류가 아닙니다."
        (out / f"doc{i}.txt").write_text(body, encoding="utf-8")
        name = re.sub(r"[\\/:*?\"<>|]+", " ", doc).strip()[:60] + ".txt"
        uploads.append({"name": name, "mimeType": "text/plain", "buffer": body.encode("utf-8")})
    layout = {"venue": pkg["venue_name"], "plan_form": pkg["plan_form"], "docs": pkg["docs"],
              "plan": [[f["표준 항목"], f["기관 칸"]] for f in pkg["fields"]]}
    with sync_playwright() as p:
        browser, page = _browser(p)
        try:
            _login(page, base)
            resp = page.request.post(f"{base}/layout", data=json.dumps(layout, ensure_ascii=False),
                                     headers={"Content-Type": "application/json; charset=utf-8"})
            layout_id = resp.json()["id"]
            page.goto(f"{base}/checklist?layout={layout_id}")
            page.click("#next")
            page.wait_for_url("**/form**")
            for name, value in pkg["basic"].items():
                page.fill(f'input[name="{name}"]', value)
            values = {f["표준 항목"]: f["값"] for f in pkg["fields"]}
            for area in page.locator("textarea").all():
                key = (area.get_attribute("name") or "").removeprefix("plan:")
                if key in values:
                    area.fill(values[key])
            for i, upload in enumerate(uploads, 1):
                page.set_input_files(f'input[name="attach{i}"]', upload)
            page.click("#save-draft")
            page.wait_for_url("**/review/**")
            draft_id = page.url.rsplit("/", 1)[-1]
            shot = out / "review.png"
            page.screenshot(path=str(shot), full_page=True)
        finally:
            browser.close()
    skipped = pkg["docs"][SLOTS:]
    return {"draft_id": draft_id, "screenshot": str(shot), "files": [u["name"] for u in uploads],
            "warnings": [f"첨부 칸 {SLOTS}개를 넘어 올리지 못한 서류: {', '.join(skipped)}"] if skipped else []}


def final_submit(draft_id: str, base: str | None = None) -> dict:
    """승인 뒤에만 부른다. 신청 확인 화면에서 최종 제출을 누르고 접수번호를 읽는다."""
    from playwright.sync_api import sync_playwright

    base = base or mock_url()
    _check(base)
    with sync_playwright() as p:
        browser, page = _browser(p)
        try:
            _login(page, base)
            page.goto(f"{base}/review/{draft_id}")
            page.click("#final-submit")
            page.wait_for_url("**/receipt/**")
            receipt = page.inner_text("#receipt")
            shot = Path(tempfile.mkdtemp(prefix="nais_receipt_", dir="/tmp")) / "receipt.png"
            page.screenshot(path=str(shot), full_page=True)
        finally:
            browser.close()
    return {"receipt": receipt, "screenshot": str(shot)}


# ---- LangGraph 노드 (graph.py가 step10 뒤에 잇는다) ----

def prepare(state: dict) -> dict:
    """⑪-1 제출 조건 확인 → 통과하면 모의 e-IRB에 채우고 최종 제출 앞에서 멈출 준비를 한다."""
    view = {"route": state.get("route"), "decision": state.get("decision"), "suggestions": state.get("suggestions", []),
            "abstain": state.get("abstain", []), "documents": state.get("documents", []), "venue": state.get("venue"),
            "facts": state.get("confirmed_facts", [])}
    try:
        pkg = package(view, state.get("masked_text", ""))
    except Exception as e:  # 계획서 모양이 예상과 달라도 화면이 멈추지 않게
        return {"submission": {"status": "blocked", "blockers": [f"제출 값을 만들지 못했습니다 ({type(e).__name__})."]},
                "submit_requested": False}
    blockers = gate(view, state.get("checklist") or {})
    sub = {"venue": pkg["venue_name"], "blockers": blockers, "fields": pkg["fields"], "files": pkg["docs"],
           "email_draft": pkg["email_draft"], "warnings": pkg["warnings"], "label_source": pkg["label_source"]}
    if blockers:
        return {"submission": {**sub, "status": "blocked"}, "submit_requested": False}
    try:
        filled = fill(pkg)
    except Exception as e:  # 모의 사이트가 꺼져 있거나 화면이 바뀐 경우
        return {"submission": {**sub, "status": "blocked",
                               "blockers": [f"모의 사이트에 채우지 못했습니다 ({type(e).__name__}). "
                                            "python demo/mock_eirb/server.py 로 모의 사이트를 켜 주세요."]},
                "submit_requested": False}
    return {"submission": {**sub, "status": "awaiting_approval", "draft_id": filled["draft_id"],
                           "screenshot": filled["screenshot"], "files": filled["files"],
                           "warnings": pkg["warnings"] + filled["warnings"]}}


def approve(state: dict) -> dict:
    """⑪-2 사람의 최종 승인(interrupt). 승인하면 최종 제출을 눌러 접수번호를 받는다. 끝나면 제출 요청을 지운다."""
    sub = dict(state["submission"])
    answer = interrupt({"submission": sub})
    if not answer.get("approved"):
        sub.update(status="cancelled", message="연구자가 제출을 취소했습니다. 모의 사이트에는 임시 저장본만 남습니다.")
        return {"submission": sub, "submit_requested": False}
    try:
        done = final_submit(sub["draft_id"])
        sub.update(status="submitted", receipt=done["receipt"], screenshot=done["screenshot"])
    except Exception as e:  # 모의 사이트가 꺼졌거나 다시 시작돼 임시 저장본이 사라진 경우
        sub.update(status="blocked", blockers=[f"최종 제출에 실패했습니다 ({type(e).__name__}). 모의 사이트가 꺼졌거나 "
                                               "다시 시작돼 임시 저장본이 사라졌을 수 있습니다. 제출 준비를 다시 눌러 주세요."])
    return {"submission": sub, "submit_requested": False}
