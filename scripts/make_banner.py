"""README 배너(글꼴 Paperlogy, 페이지에 직접 넣는다): 이정표 로고 + '여기까지'(Paperlogy) + 부제 + 한 줄 특징. GitHub 밝은·어두운 테마용 투명 PNG 두 장.
  python scripts/make_banner.py → docs/banner-light.png, docs/banner-dark.png (Playwright Chromium으로 그린다)"""
from base64 import b64encode
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "src" / "ui" / "fonts"
THEMES = {  # 제목 그라데이션(규칙 엔진 초록 → AI 파랑), 부제, 특징, 로고 기둥
    "light": {"g1": "#1E8A5A", "g2": "#2F6FD1", "sub": "#4A5468", "tag": "#5E687C", "pole": "#1F2A44"},
    "dark": {"g1": "#3CC48A", "g2": "#5B9BFF", "sub": "#C3CAD8", "tag": "#9AA4B8", "pole": "#D5DAE3"},
}
LOGO = """<svg width="220" height="240" viewBox="0 0 220 240" xmlns="http://www.w3.org/2000/svg">
  <rect x="100" y="28" width="20" height="196" rx="6" fill="{pole}"/>
  <path d="M40 48 H176 L206 74 L176 100 H40 Z" fill="{g1}"/>
  <text x="112" y="85" text-anchor="middle" font-family="Paperlogy, Noto Sans CJK KR, sans-serif" font-weight="800" font-size="34" fill="#FFFFFF">IRB</text>
  <path d="M180 116 H44 L14 142 L44 168 H180 Z" fill="{g2}"/>
  <text x="104" y="153" text-anchor="middle" font-family="Paperlogy, Noto Sans CJK KR, sans-serif" font-weight="800" font-size="34" fill="#FFFFFF">DRB</text>
  <rect x="66" y="214" width="88" height="16" rx="8" fill="{pole}"/>
  <circle cx="110" cy="22" r="14" fill="#F28C28"/>
</svg>"""


def html(t):
    faces = "".join(
        f"@font-face{{font-family:'Paperlogy';src:url('data:font/woff2;base64,{b64encode((FONTS / f'Paperlogy-{w}.woff2').read_bytes()).decode()}') format('woff2');font-weight:{n}}}"
        for w, n in (("4Regular", 400), ("6SemiBold", 600), ("8ExtraBold", 800)))
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{faces}
html,body{{margin:0;background:transparent}}
#b{{display:flex;align-items:center;gap:44px;padding:28px 40px;width:max-content}}
h1{{margin:0;font:800 150px/1 'Paperlogy','Noto Sans CJK KR','Noto Sans KR',sans-serif;letter-spacing:-2px;background:linear-gradient(90deg,{t['g1']},{t['g2']});
   -webkit-background-clip:text;background-clip:text;color:transparent;padding-bottom:10px}}
.sub{{font:600 40px/1.3 'Paperlogy','Noto Sans CJK KR','Noto Sans KR',sans-serif;color:{t['sub']};margin-top:6px}}
.tag{{font:400 27px/1.4 'Paperlogy','Noto Sans CJK KR','Noto Sans KR',sans-serif;color:{t['tag']};margin-top:12px}}
</style></head><body><div id="b">{LOGO.format(**t)}<div><h1>여기까지</h1>
<div class="sub">연구계획서 심의 경로 판정 AI 에이전트</div>
<div class="tag">조문 근거 · 판단불가 명시 · 기관 11곳 · 보완 제안 · 모의 e-IRB 제출</div></div></div></body></html>"""


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 500}, device_scale_factor=2)
    for name, t in THEMES.items():
        page.set_content(html(t))
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)
        assert page.evaluate("[...document.fonts].every(f => f.status === 'loaded')"), "Paperlogy를 불러오지 못함"
        page.locator("#b").screenshot(path=str(ROOT / "docs" / f"banner-{name}.png"), omit_background=True)
    browser.close()
print("docs/banner-light.png · docs/banner-dark.png")
