# 고려대학교 안암병원 IRB (kumc) 조사 기록

확인일: 2026-09-30. 공식 공개 페이지만 봤다. 의료원 사이트는 JS 화면이라 헤드리스 브라우저와 사이트 API(`/api/content.do`, `/api/article/…`)로 본문을 읽었다.

## 확인한 페이지

| URL | 결과 |
|---|---|
| https://www.kumc.or.kr/kr/institution/hrpc/IRB.do | 찾음. 임상연구윤리센터 IRB 소개 |
| https://www.kumc.or.kr/kr/institution/hrpc/payment.do | 찾음. 심사접수료 |
| https://www.kumc.or.kr/kr/institution/hrpc/mutual-recognition.do | 찾음. 3개 병원 상호인정제도 |
| https://www.kumc.or.kr/kr/institution/hrpc/researcher.do | 찾음. 연구윤리 원칙 (교육) |
| https://www.kumc.or.kr/kr/informationPlaza-notice/list.do · informationPlaza-archives/list.do | 공지 2건(IRB 서식 아님), 자료실 0건 |
| https://anamrnd.kumc.or.kr/kr/reserch-support/irb.do | 찾음. 안암 IRB 소개와 심의 절차도(이미지 `resource/images/rndsub/irb-img01_anam.jpg`) |
| https://anamrnd.kumc.or.kr/kr/reserch-support/irb2.do | 찾음. HRPP 소개 |
| https://anamrnd.kumc.or.kr/kr/reserch-support/team.do | 찾음. 연구관리팀 임상연구보호파트 'IRB 심사지원' 연락처 (담당자 이름은 옮기지 않음) |
| https://anam.kumc.or.kr/ | 하단 링크 '안암 e-IRB' → irb.kumc.or.kr |
| https://irb.kumc.or.kr/Login.aspx | 로그인 화면만 공개. 서식·규정·일정은 로그인 필요 |
| https://irb.kumc.or.kr/Member/Clause.aspx | 이용약관만 공개 |
| https://www.kumc.or.kr/kr/medsh-newsLetter/view.do?article=270856 | 찾음. 임상연구지원실 뉴스레터 26.05 (IRB·DRB 순서) |
| https://www.kumc.or.kr/api/article/83?boardNo=83&instNo=0&startIndex=1&pageRow=60 (게시판 '연구대상자-2022년'), 84('연구대상자-2021년') | 찾음. 의료원 데이터 심의위원회 회의 결과 (2021~2022). 현재 메뉴에는 없고 사이트 API로만 보임 |
| https://www.kumc.or.kr/api/content.do?menuNo=378 | 참고만. '고려대학교의료원 데이터 심의위원회' 소개와 절차(심의신청 → 행정점검 → 본심의 → 승인 → 데이터 가공·계약·검수 → 제공). 비노출(exposeYn N) 콘텐츠라 프로필 근거로 쓰지 않음 |
| https://www.kumc.or.kr/kr/institution/hrpc/orgChart-contact.do | 찾음. IRB 심사지원 안암병원 02-920-6086, 6566, 6076, 6080 |
| https://crlms.kumc.or.kr/web/center/noticeView.do?boardIdx=14881 | 찾음. STEP '2026년도 생명윤리교육(GCP) 교육 안내' |
| https://crlms.kumc.or.kr/web/member/join03.do?cert=eIrb | STEP 가입 때 e-IRB 인증 |
| https://www.kumc.or.kr/kr/B022/view.do?article=267382 | 찾음. AAHRPP 전면 재인증 기사 (2025-12) |
| http://ctc.kumc.or.kr/ (안암 임상시험센터) | IRB 서식·일정 없음 |
| http://anam.kumcrnd.or.kr/support/irb_info/index.do | 접속 안 됨 (구 사이트) |
| https://irb.korea.ac.kr/ | 고려대학교(캠퍼스) 기관생명윤리위원회라 병원 IRB와 다름 → 쓰지 않음 |

## 찾은 것

- 위원회 이름: "고려대학교병원 의학연구심의위원회(이하 IRB)은 안암, 구로, 안산병원에 설치된" 위원회 (anamrnd IRB 소개). 의료원 연혁: 2022-03-11 "안암병원 보건복지부 인증 기관생명윤리위원회(IRB) 인증 획득".
- 제출 창구: 심의 절차도에 "책임연구자 → IRB 신청 (E-IRB시스템) → 행정점검 및 접수 → 정기/신속심사 → 승인". e-IRB 문의 "안암병원 02-920-6566".
  - e-IRB 로그인 화면: "처음으로 고려대학교 의료원 e-IRB 시스템에 접속하는 분은 회원가입 절차를 진행", "원내 사용자는 사번, 생년월일(YYMMDD)로 e-IRB 시스템 이용이 가능".
  - 가입 약관 화면: "소속 연구기관이 아닌 경우 사용에 제한이 있을 수 있습니다."
  - AAHRPP 기사: "E-IRB 시스템을 통한 연구 신청·심사·문서관리의 일관성".
- 신속심사: 절차도 주석 "신속심사는 승인/시정승인/정기심사 상정만 결정", "계약서담당 부서: 임상시험센터" (승인 뒤 계약서 검토 → 계약 완료 → 연구 시작).
- 심사면제: IRB 주요 기능에 "심사면제 타당성 확인". 면제 대상·서식은 공개 페이지에 없음.
- DRB: 뉴스레터 26.05 3항 "IRB와 별도로, 개인정보보호법에 따라 가명 정보 활용의 적절성을 심의하는 데이터심의위원회(DRB) 절차가 요구됩니다", "병원마다 IRB와 DRB의 접수 및 심의 순서(IRB 선 승인 후 DRB, 혹은 그 반대 등)가 모두 다릅니다". 의료원 데이터 심의위원회 회의 결과 게시(2022년 정기 1~17차·신속 1차, "DRB NO. 2022DRB0xx", 데이터 활용 안암·구로·안산 표시). 안암병원의 IRB·DRB 순서는 공개 자료에 없음.
- 교육: STEP 공지 "교육대상 - 모든 임상연구자 (단, 의약품 임상시험 종사자는 임상시험 종사자 교육을 이수해야 함)", 2026 생명윤리교육(GCP) 특강 운영기간 2026-01-02~12-31. HRPC 연구윤리 원칙 "실시기관 표준지침에서 정한 바에 따른 임상연구 실시에 필요한 교육과 훈련 및 경험을 갖추어야 한다".
- 심사접수료(안암병원 IRB 표): 연구자 주도 연구 신규심사 — 연구비 5천만원 이상 1,200,000원, 2천만원 이상~5천만원 미만 600,000원 (VAT 별도). "정부협약과제(국책과제), 원내연구비지원(원내지원과제), 현물지원 및 연구비가 없는 순수 학술 연구 등은 심사접수료가 부과되지 않습니다."
- 상호인정제도: 의료원 산하 2개 이상 병원 참여 다기관 연구 등에 적용. 단 "학술 목적의 단순 설문조사, 문헌고찰, 자료분석 등 규제심사 비대상 연구"는 제외. (규칙 조건 when에 공동연구가 없어 프로필 규칙에는 넣지 않음)
- 서류 이름: 연구자 페이지 "임상연구계획서", 연구대상자 페이지 "연구대상자를 위한 설명문 및 동의서". 서식 번호는 없음.

## 못 찾은 것 (프로필에 넣지 않음)

- 신규심사·심사면제 제출 서류 목록과 서식 번호, 심사면제 자가점검표: e-IRB 로그인 필요, 공개본 없음.
- 면제에 해당하지 않을 때 전환 규칙(신속/정규): 공개 규정 없음.
- 안암병원 IRB와 DRB의 제출 순서: 공개 자료 없음.
- 교육 인정 기관·유효기간: 공개 자료 없음.
- 정기회의 주기·접수 마감·결과 통보 기간·2026 회의 날짜: 공개 페이지 없음 → `schedule: none`.
- 연구계획서 서식 항목(후향 의무기록·개인정보 연구): 공개 서식 없음 → `plan` 비움.
- 공문·연구진 전원 제출·서명 같은 기관 고유 규칙, SOP·규정집 공개본: 없음.
