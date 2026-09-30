"""README 오버뷰 그림: 역할별 가로 줄(사람 · AI · 규칙 엔진 · 공공 데이터)에 ①~⑪ 흐름을 놓는다.
색은 앱의 약속(AI 파랑 · 규칙 엔진 초록 · 사람 확인 주황 · 공공 데이터 회색, 기본 남색)만 쓰고, 그림 안에는 단계 이름만 넣는다.
  python scripts/make_overview.py → docs/overview.svg, docs/overview.png (rsvg-convert, 2배)"""
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "docs"
W, H = 1800, 700
NAVY = "#1F2A44"
C = {  # 선 · 채움 · 글자
    "human": ("#D9822B", "#FDF1E4", "#7A4312"),
    "ai": ("#2F6FD1", "#E9F1FD", "#163C7A"),
    "rule": ("#1E8A5A", "#E7F5EE", "#0F4D32"),
    "data": ("#7A8494", "#F1F3F6", "#3A4250"),
}
FONT = "Noto Sans CJK KR, Noto Sans KR, Apple SD Gothic Neo, Malgun Gothic, sans-serif"
LANES = [("human", "사람", None), ("ai", "AI", "Qwen3.8"), ("rule", "규칙 엔진", None), ("data", "공공 데이터", None)]
LANE_Y, LANE_H, LEFT = 30, 158, 150


def lane_mid(i):
    return LANE_Y + LANE_H * i + LANE_H / 2


out = []
add = out.append
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">')
add('<defs>'
    f'<marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{NAVY}"/></marker>'
    f'<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C["human"][0]}"/></marker>'
    '</defs>')
add(f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>')
# 가로 줄: 왼쪽 이름 칸 + 옅은 띠
for i, (k, name, sub) in enumerate(LANES):
    y = LANE_Y + LANE_H * i
    add(f'<rect x="0" y="{y}" width="{W}" height="{LANE_H}" fill="{C[k][1]}" opacity="0.35"/>')
    add(f'<rect x="0" y="{y}" width="8" height="{LANE_H}" fill="{C[k][0]}"/>')
    add(f'<text x="26" y="{y + LANE_H / 2 + (0 if sub else 8)}" font-size="22" font-weight="700" fill="{C[k][2]}">{name}</text>')
    if sub:
        add(f'<text x="26" y="{y + LANE_H / 2 + 26}" font-size="17" fill="{C[k][2]}" opacity="0.85">{sub}</text>')
    if i:
        add(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="#D5DAE3" stroke-width="1.5"/>')
add(f'<line x1="{LEFT}" y1="{LANE_Y}" x2="{LEFT}" y2="{LANE_Y + LANE_H * 4}" stroke="#D5DAE3" stroke-width="1.5"/>')


def box(x, lane, w, title, sub=None, h=96, dy=0, kind=None, dash=False):
    """상자: (x, 줄 번호)에 가운데 맞춤. 돌려주는 값: 왼·오른·위·아래 가운데 점."""
    k = kind or LANES[lane][0]
    cy = lane_mid(lane) + dy
    y = cy - h / 2
    d = ' stroke-dasharray="7 5"' if dash else ''
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{C[k][1]}" stroke="{C[k][0]}" stroke-width="2.5"{d}/>')
    ty = cy + (8 if not sub else -4)
    add(f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" font-size="23" font-weight="700" fill="{C[k][2]}">{title}</text>')
    if sub:
        add(f'<text x="{x + w / 2}" y="{cy + 24}" text-anchor="middle" font-size="16" fill="{C[k][2]}" opacity="0.85">{sub}</text>')
    return {"l": (x, cy), "r": (x + w, cy), "t": (x + w / 2, y), "b": (x + w / 2, y + h), "x": x, "w": w, "cy": cy, "y": y, "h": h}


def arrow(p, q, color=NAVY, dash=False, marker="a", via=None, width=2.4):
    d = ' stroke-dasharray="8 6"' if dash else ''
    pts = [p] + (via or []) + [q]
    path = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pts)
    add(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width}"{d} marker-end="url(#{marker})"/>')


# 흐름
plan = box(172, 0, 150, "연구계획서", "입력 · 문서")
mask = box(352, 2, 150, "② 마스킹", "ko-pii · 규칙")
ext = box(532, 1, 170, "③ 사실 추출", "F01–F18 · 근거 문장")
chk = box(732, 0, 150, "④ 사실 확인", "수정 · 확정")
# 판정 묶음(⑤~⑧): 규칙 엔진 줄에 넓게
jx, jw = 912, 330
judge = box(jx, 2, jw, "", None, h=124)
steps = [("⑤ 기관 대조", 0, 0), ("⑥ 관문 판정", 1, 0), ("⑦ 경로 결정", 0, 1), ("⑧ 서류·일정", 1, 1)]
for t, cx, cy in steps:
    bx, by = jx + 14 + cx * 156, judge["y"] + 12 + cy * 54
    add(f'<rect x="{bx}" y="{by}" width="146" height="46" rx="10" fill="#FFFFFF" stroke="{C["rule"][0]}" stroke-width="1.8"/>')
    add(f'<text x="{bx + 73}" y="{by + 30}" text-anchor="middle" font-size="19" font-weight="700" fill="{C["rule"][2]}">{t}</text>')
# 공공 데이터(판정 근거)
srcs = [("법령 원문", 912), ("규칙표", 996), ("기관 11곳", 1080), ("일정·명단", 1164)]
for name, x in srcs:
    s = box(x, 3, 78, "", None, h=70)
    add(f'<text x="{x + 39}" y="{s["cy"] + 7}" text-anchor="middle" font-size="16" font-weight="700" fill="{C["data"][2]}">{name}</text>')
    arrow(s["t"], (x + 39, judge["b"][1] + 4), color=C["data"][0])
# 결과
qa = box(1282, 1, 170, "⑨ 사무국 질문", "판단불가", h=62, dy=-36)
rep = box(1282, 1, 170, "⑩ 결과 리포트", "조문 근거", h=62, dy=36)
route = box(1282, 2, 170, "경로", "A · B · C · 임상시험", h=96)
fix = box(1482, 0, 150, "보완 제안", "넣을 문장", h=96, kind="rule")
sub = box(1642, 0, 150, "⑪ 제출", "사람 승인")
eirb = box(1642, 3, 150, "e-IRB", "모의 · 공용위원회", h=90)

# 화살표: 본 흐름
arrow(plan["b"], mask["t"], via=[(plan["b"][0], mask["cy"] - 110), (mask["t"][0], mask["cy"] - 110)])
arrow(mask["r"], ext["b"], via=[(ext["b"][0], mask["cy"])])
arrow(ext["t"], chk["l"], via=[(ext["t"][0], chk["cy"])])
arrow((807, chk["b"][1]), judge["l"], via=[(807, judge["cy"])])
arrow(judge["r"], route["l"])
jy = judge["cy"] - 40
arrow((judge["r"][0], jy), qa["l"], via=[(judge["r"][0] + 20, jy), (judge["r"][0] + 20, qa["cy"])])
arrow((judge["r"][0], jy), rep["l"], via=[(judge["r"][0] + 20, jy), (judge["r"][0] + 20, rep["cy"])])
arrow(route["r"], fix["b"], via=[(fix["b"][0], route["cy"])])
arrow(route["r"], (1680, sub["b"][1]), via=[(1680, route["cy"])])
arrow((1756, sub["b"][1]), (1756, eirb["t"][1]))
# 되돌아가는 고리(사람): 보완 문구로 계획서 수정 · 판단불가(나)는 연구자 입력 후 ④부터
arrow(fix["t"], plan["t"], color=C["human"][0], dash=True, marker="ah",
      via=[(fix["t"][0], LANE_Y + 10), (plan["t"][0], LANE_Y + 10)])
arrow(qa["t"], (850, chk["b"][1]), color=C["human"][0], dash=True, marker="ah",
      via=[(qa["t"][0], LANE_Y + LANE_H - 14), (850, LANE_Y + LANE_H - 14)])
add('</svg>')

svg = HERE / "overview.svg"
svg.write_text("\n".join(out), encoding="utf-8")
subprocess.run(["rsvg-convert", "-z", "2", "-o", str(HERE / "overview.png"), str(svg)], check=True)
print("overview.svg · overview.png")
