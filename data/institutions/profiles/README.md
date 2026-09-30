# 기관 프로필 형식 (한 기관 = 한 파일, `<id>.yaml`)

⑤~⑧이 관할 위원회의 프로필을 찾아 제출처·기관 서식 서류·기관 규칙·계획서 서식 항목·일정을 낸다.
표준 목록(서류 키·계획서 항목 키)은 `../standard.yaml`에 있다. 형식 검사는 `pytest tests/test_institutions.py`.

원칙
- 기관이 공개한 공식 페이지·규정·서식에서 확인한 사실만 쓴다. 로그인해야 보이는 것은 쓰지 않고 notes에 "비공개(로그인)"로 적는다.
- 원문(파일)은 레포에 넣지 않는다. 서류 이름·규칙 요지·날짜 같은 사실과 출처 URL·확인일만 옮긴다.
- 경고 문구는 "~해야 합니다 / ~할 수 있습니다"로 기관 안내를 옮길 뿐, 심의 결과를 예측하지 않는다.
- 조사 기록(출처 URL, 찾은 것, 못 찾은 것)은 `../notes/<id>.md`에 둔다.

```yaml
id: snuh                       # 파일 이름과 같다. 영문 소문자
name: 서울대학교병원 IRB        # 위원회 정식 이름
short: 서울대병원               # 화면·비교표 열 이름. aliases에도 넣는다
aliases: [서울대병원, 서울대학교병원]   # ⑤ 기관 대조가 이 이름들로 찾는다
submit: e-IRB(주소)에서 연구책임자가 신청     # 제출 창구와 방법
source: 문서 이름들 (대표 URL, 확인 2026-09-30)
plan_form: 연구계획서 서식 이름
exempt_regular: true           # (선택) 심의면제도 정규회의 안건이라 7일 빠른 길을 쓰지 않는 기관만
docs:                          # 표준 서류 키 → 이 기관 서식 이름. 없는 서류는 키를 빼고, 키는 standard.yaml의 docs만
  신청서: …
  계획서: …
plan:                          # 표준 계획서 항목 키 → 이 기관 서식의 칸 이름. 키는 standard.yaml의 plan만
  배경·목적: 1. 연구 배경 및 목적
rules:                         # 이 기관만의 요구. when: always | drb | exempt | export | received_data
  - id: I-SNUH-1               # I-<ID 대문자>-번호
    when: drb
    level: 확인 필요            # 보완 필요(계획서에 넣을 글) | 확인 필요(절차·서류) | 안내
    warning: 기관 안내를 옮긴 한두 문장
    add_text: (선택) 계획서에 넣을 문장, [ ]는 연구자가 채움
    told: [(선택) 이 낱말이 계획서에 있으면 이미 적은 것으로 보고 경고하지 않음]
    source: 근거 문서 이름·조항
schedule: {kind: none, note: "공개 여부와 규칙 요약"}
forms:                         # (선택) 기관이 공개한 서식 목록 — 자료실·체크리스트에서 확인한 것만
  - {name: 연구계획서(인간대상연구), number: 별지 제2-1호, version: ver.3.8, doc: 계획서, url: 내려받는 페이지 주소}
# 규칙에 check를 붙이면 엔진이 계획서 글을 검사해 판정표의 "기관 기준" 행(충족/미충족)으로 낸다. 쓸 수 있는 이름:
#   past_tense(연구 행위를 과거형으로 서술) · mixed_style(계획서에 경어체 혼용) · age_without_man(만 나이 아닌 나이 표기)
#   sample_size_rationale(대상자 수 산출근거 없음) · period_before_review(연구 시작이 심의 결과보다 이름)
#   recruit_doc(포스터·SNS 모집인데 모집 문건 없음) · crf_identifiers(CRF·분석 자료에 식별자 기록) · english_title(영문 제목 없음)
# 2026 정규회의 날짜와 접수 마감이 공개돼 있으면:
# schedule: {kind: csv, path: data/schedules/<id>_irb_2026.csv, result_days: 결과 통보 일수, cycle_days: 보완 한 번에 당길 최소 일수, note: "…"}
# CSV 열: 위원회,회의일,접수마감,출처,확인일,구분,차수 (구분=정규)
```
