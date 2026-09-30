"""어댑터 + 표준 신청 데이터 + 범용 채우기를 한 스크립트로 묶는다(Claude in Chrome javascript_tool에 넣을 글).
  python build_fill.py [계획서.txt]   # 계획서(앱에서 읽어 온 개선본)를 주면 근거 문장이 그 계획서에 있는 값만 채운다. 없으면 비워 사람 확인으로 남긴다."""
import json
import sys
from pathlib import Path

here = Path(__file__).parent
adapter = json.loads((here / "adapter_public_eirb.json").read_text(encoding="utf-8"))
std = json.loads((here / "standard_application.json").read_text(encoding="utf-8"))["data"]
plan = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else None
flat = " ".join(plan.split()) if plan else None
data, gone = {}, []
for k, v in std.items():
    if flat is None or " ".join(v["근거"].split()) in flat:
        data[k] = v["값"]
    else:
        gone.append(k)
fill = (here / "fill_generic.js").read_text(encoding="utf-8")
body = fill[fill.index("(ADAPTER, DATA) =>"):].rstrip()
js = f"({body})({json.dumps(adapter, ensure_ascii=False)}, {json.dumps(data, ensure_ascii=False)});\n"
(here / "run_fill.js").write_text(js, encoding="utf-8")
print(f"{len(data)}개 값 채움 · 근거 없어 비움 {len(gone)}개 {gone} → run_fill.js ({len(js)}자)")
