"""모의 e-IRB (데모용, 실제 기관과 무관). ⑪ 제출 도우미가 칸 채우기·서류 올리기·최종 제출을 시연하는 가짜 사이트다.

- 표준 라이브러리 http.server만 쓰고 127.0.0.1에만 붙는다. 실제 심의 기관과 연결되지 않는다.
- 신청 양식(칸 이름·IRB 서류 목록)은 제출 도우미가 로그인 뒤 /layout으로 넘긴다. 칸 이름은 엔진이 서식 변형까지 적용한
  관할 기관 서식(result.venue)에서 오고, 실제 기관의 로고·디자인·이름을 흉내 내지 않는다.
- 단계는 공용위원회 공개 절차를 본떴다: 로그인 → 제출 서류 확인 → 입력·업로드 → 연구책임자 신청(최종 제출) → 접수(행정점검 대기).
- 계정은 데모용 가짜 계정(demo / demo)이고, 양식·초안·접수는 메모리에만 둔다(다시 시작하면 사라진다).
- 파이썬 3.10의 cgi 모듈로 첨부를 읽는다(3.13에서 제거됨).
실행: python demo/mock_eirb/server.py [--port 8765]
"""
import argparse
import cgi
import html
import itertools
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TITLE = "모의 e-IRB (데모용, 실제 기관과 무관)"
BASIC = [("title", "연구 제목"), ("review_type", "심의 유형"), ("route", "제출처·경로"), ("period", "연구 기간"),
         ("size", "대상자 수")]
SLOTS = 12  # 첨부 칸 수
LAYOUTS: dict[str, dict] = {}
DRAFTS: dict[str, dict] = {}
RECEIPTS = itertools.count(1)
LOCK = threading.Lock()


def esc(value) -> str:
    return html.escape(str(value))


def page(body: str) -> bytes:
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{TITLE}</title>
<style>body{{font-family:'Noto Sans CJK KR',sans-serif;margin:24px;max-width:860px;color:#222}}
.banner{{background:#eee;border:1px dashed #888;padding:8px 12px;margin-bottom:16px}}
label{{display:block;margin-top:10px;font-weight:600}} input[type=text],textarea{{width:100%;padding:6px}}
table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #bbb;padding:6px;text-align:left;vertical-align:top}}
button{{margin-top:14px;padding:8px 16px}}</style></head><body>
<div class="banner"><b>{TITLE}</b> · 이 사이트는 시연용 가짜 사이트이며 실제 심의 기관과 연결되지 않습니다.</div>
{body}</body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 조용히
        pass

    def _send(self, body: bytes, status: int = 200, headers: dict | None = None, ctype: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, to: str, cookie: str | None = None):
        # 이동 주소는 서버가 만든 경로와 16진 id만 쓴다(요청 값을 그대로 헤더에 넣지 않는다)
        headers = {"Location": to}
        if cookie:
            headers["Set-Cookie"] = cookie
        self._send(b"", 303, headers)

    def _logged_in(self) -> bool:
        return "session=demo" in (self.headers.get("Cookie") or "")

    def _layout(self, q: dict) -> dict | None:
        return LAYOUTS.get(q.get("layout", ""))

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/":
            return self._send(page("""<h2>로그인</h2><form method="post" action="/login">
<label>아이디</label><input type="text" name="id"><label>비밀번호</label><input type="password" name="pw">
<button id="login" type="submit">로그인</button></form>"""))
        if not self._logged_in():
            return self._redirect("/")
        if url.path == "/home":
            return self._send(page("<h2>로그인했습니다</h2><p>새 신청은 제출 도우미가 신청 양식을 등록한 뒤 시작합니다.</p>"))
        if url.path == "/checklist":
            lay = self._layout(q)
            if not lay:
                return self._send(page("<p>신청 양식이 없습니다.</p>"), 404)
            rows = "".join(f"<tr><td>{esc(d)}</td></tr>" for d in lay["docs"])
            return self._send(page(f"""<h2>① 제출 서류 확인 · {esc(lay['venue'])}</h2>
<table><tr><th>IRB에 낼 서류</th></tr>{rows}</table>
<a id="next" href="/form?layout={esc(lay['id'])}"><button>다음: 입력·업로드</button></a>"""))
        if url.path == "/form":
            lay = self._layout(q)
            if not lay:
                return self._send(page("<p>신청 양식이 없습니다.</p>"), 404)
            basic = "".join(f'<label>{esc(label)}</label><input type="text" name="{name}">' for name, label in BASIC)
            plan = "".join(f'<label>{esc(label)}</label><textarea name="plan:{esc(key)}" rows="3"></textarea>'
                           for key, label in lay["plan"])
            files = "".join(f'<label>첨부 {i}</label><input type="file" name="attach{i}">' for i in range(1, SLOTS + 1))
            return self._send(page(f"""<h2>② 입력·업로드 · {esc(lay['venue'])}</h2>
<form method="post" enctype="multipart/form-data" action="/draft?layout={esc(lay['id'])}">
<h3>기본 정보</h3>{basic}<h3>연구계획서 항목 {esc(lay['plan_form'])}</h3>{plan}
<h3>제출 서류</h3>{files}<button id="save-draft" type="submit">임시 저장하고 신청 화면으로</button></form>"""))
        if url.path.startswith("/review/"):
            d = DRAFTS.get(url.path.rsplit("/", 1)[-1])
            if not d:
                return self._send(page("<p>초안이 없습니다.</p>"), 404)
            rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in d["fields"].items())
            docs = "".join(f"<li>{esc(k)}: {esc(v)}</li>" for k, v in d["files"].items())
            button = ("<p>이미 제출했습니다.</p>" if d.get("receipt") else
                      f'<form method="post" action="/submit/{d["id"]}"><button id="final-submit" type="submit">최종 제출</button></form>')
            return self._send(page(f"""<h2>③ 연구책임자 신청 확인 · {esc(d['venue'])}</h2>
<table><tr><th>칸</th><th>입력값</th></tr>{rows}</table><h3>올린 서류</h3><ul>{docs}</ul>{button}"""))
        if url.path.startswith("/receipt/"):
            d = DRAFTS.get(url.path.rsplit("/", 1)[-1])
            if not d or not d.get("receipt"):
                return self._send(page("<p>접수 기록이 없습니다.</p>"), 404)
            return self._send(page(f"""<h2>④ 접수 완료 · 행정점검 대기</h2>
<p>접수번호 <b id="receipt">{esc(d['receipt'])}</b></p><p>모의 사이트라 실제 심의는 진행되지 않습니다.</p>"""))
        return self._send(page("<p>없는 화면입니다.</p>"), 404)

    def do_POST(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/login":
            length = int(self.headers.get("Content-Length") or 0)
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8")).items()}
            if form.get("id") == "demo" and form.get("pw") == "demo":
                return self._redirect("/home", "session=demo; Path=/")
            return self._send(page("<p>데모 계정은 demo / demo 입니다.</p>"), 401)
        if not self._logged_in():
            return self._redirect("/")
        if url.path == "/layout":
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            lay = {"id": uuid.uuid4().hex[:8], "venue": str(data.get("venue", "")), "plan_form": str(data.get("plan_form", "")),
                   "docs": [str(d) for d in data.get("docs", [])], "plan": [[str(k), str(v)] for k, v in data.get("plan", [])]}
            with LOCK:
                LAYOUTS[lay["id"]] = lay
            return self._send(json.dumps({"id": lay["id"]}).encode(), ctype="application/json")
        if url.path == "/draft":
            lay = self._layout(q)
            if not lay:
                return self._send(page("<p>신청 양식이 없습니다.</p>"), 404)
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
            fields = {label: form.getfirst(name, "") for name, label in BASIC}
            for key, label in lay["plan"]:
                fields[label] = form.getfirst(f"plan:{key}", "")
            files = {}
            for i in range(1, SLOTS + 1):
                item = form[f"attach{i}"] if f"attach{i}" in form else None
                if item is not None and item.filename:
                    files[f"첨부 {i}"] = item.filename
            draft_id = uuid.uuid4().hex[:8]
            with LOCK:
                DRAFTS[draft_id] = {"id": draft_id, "venue": lay["venue"], "fields": fields, "files": files}
            return self._redirect(f"/review/{draft_id}")
        if url.path.startswith("/submit/"):
            d = DRAFTS.get(url.path.rsplit("/", 1)[-1])
            if not d:
                return self._send(page("<p>초안이 없습니다.</p>"), 404)
            with LOCK:
                d.setdefault("receipt", f"MOCK-2026-{next(RECEIPTS):04d}")
            return self._redirect(f"/receipt/{d['id']}")
        return self._send(page("<p>없는 요청입니다.</p>"), 404)


def serve(port: int = 8765) -> ThreadingHTTPServer:
    """127.0.0.1에만 붙는 서버를 만들어 돌려준다 (테스트는 스레드로 띄운다)."""
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    server = serve(ap.parse_args().port)
    print(f"{TITLE}: http://127.0.0.1:{server.server_port}")
    server.serve_forever()
