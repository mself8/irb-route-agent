# 실제 e-IRB 신청서 채우기 도구 (데모용, 제품 코드 아님)

개선된 연구계획서의 값을 기관 e-IRB 신청 화면에 채운다. 브라우저 에이전트(Claude in Chrome)가 사용자가 로그인한 화면에서 실행한다.
저장·제출 버튼, 파일 첨부, 동의·서약 체크는 누르지 않는다. 실제 개인정보는 넣지 않는다.

| 파일 | 내용 |
|---|---|
| `standard_application.json` | 표준 신청 데이터: 항목마다 값과, 그 값을 뽑은 계획서 문장(근거) |
| `adapter_public_eirb.json` | 공용위원회 e-IRB 대응표: 표준 항목 → 화면의 칸 이름(행 제목)·선택지 글자 |
| `fill_generic.js` | 범용 채우기: 칸 ID가 아니라 화면 글자로 칸을 찾아 채운다. 못 찾거나 둘 이상 맞으면 건너뛰고 사람 확인으로 남긴다 |
| `build_fill.py` | 위 셋을 실행용 스크립트 하나(`run_fill.js`)로 묶는다. 계획서를 주면 근거 문장이 그 계획서에 있는 값만 넣는다 |
| `sample_plan_public*.txt` | 가상 샘플 계획서 (보완 전 · 산출 근거를 채운 보완 후) |

```bash
python demo/eirb_fill/build_fill.py demo/eirb_fill/sample_plan_public_fixed.txt   # → demo/eirb_fill/run_fill.js
```

`run_fill.js`를 Claude Code(Chrome 연동)에게 "공용위원회 e-IRB 신규 심의 신청 탭에서 이 스크립트를 실행해 줘"라고 시키면 약 30초 동안 칸을 하나씩 채운다.
다른 기관은 대응표(`adapter_<기관>.json`)를 하나 더 만들면 된다.
