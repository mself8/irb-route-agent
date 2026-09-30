# 심의 경로 판정 AI 에이전트

> 조문 근거 추적과 판단불가 영역 명시를 통한 연구윤리 행정 지원

2026 국가과학기술연구회 국가과학AI연구센터(NAIS) AI 해커톤 본선 출품작 · 팀 **m-M-m (media-Mediate-medicine)**

연구계획 요약을 입력받아 필요한 심의 경로(기관 IRB·공용위원회·중앙IRB·DRB), 서류 목록, 역산 일정을 조문 근거와 함께 제시합니다.
판정할 수 없는 항목은 추정하지 않고 '판단불가'로 표시해 사무국 확인 대상으로 넘깁니다.

> 본 에이전트는 심의 결과를 예측하거나 승인 여부를 판정하지 않습니다. 산출물은 연구자가 사무국에 확인할 항목을 정리한 초안입니다.

## 흐름

① 입력(사람) → ② 개인정보 마스킹(규칙) → ③ 사실 추출(AI) → ④ 사실 확인(사람) → ⑤ 기관 대조 → ⑥ 관문 판정 → ⑦ 경로 결정 → ⑧ 서류·일정(규칙) → ⑨ 판단불가 처리 → ⑩ 결과 리포트(AI)

- 판정은 규칙 엔진만 합니다. AI는 사실을 뽑고, 사무국 질문과 설명문을 씁니다.
- ④에서 연구자가 사실을 확정해야 판정이 시작됩니다.
- 계획서에 정보가 없는 항목은 연구자에게 입력을 받아 ④부터 다시 판정합니다.

## 구조

```
app.py            화면 시작점 (Streamlit)
src/ui/           화면 S1~S8
src/agent/        로직 (LangGraph 10단계)
  api.py          화면이 부르는 함수 3개: start · confirm · rejudge
  state.py        화면과 로직이 주고받는 데이터 모양
  graph.py        10단계 연결 (④에서 멈춤)
  nodes/          ②③ 읽기 · ⑤~⑧ 판정 · ⑨⑩ 작성
data/             규칙표 · 공공 명단 · 공개 일정 · 샘플 (data/README.md)
tests/            약속 검사
docs/ scripts/    설계 문서 · 보조 스크립트
```

## 실행

```bash
python -m venv .venv && source .venv/bin/activate   # 파이썬 3.10
pip install -r requirements.txt
FAKE=1 streamlit run app.py   # 예시 결과로 화면만 (기본)
FAKE=0 streamlit run app.py   # 실제 그래프
pytest                        # 합치기 전에
```

## 개발 기간

대회 규정에 따라 모든 개발은 본선 기간(2026-09-30 ~ 10-01) 안에 진행합니다. 이 레포는 본선 시작 전 README만으로 생성했습니다.

## 팀

이종현(대표) · 이진주 · 장다연 · 정송윤 · 김고은

## 사용한 모델·라이브러리·데이터 출처

본선 중 추가하는 대로 여기에 전량 기록합니다.

- AI 코딩 도구: Claude Code (Anthropic, Claude Opus 5.5) — 코드·테스트·문서 작성 전반. 개발자(송윤)가 지시하고 검토했으며, 세션 2개가 나눠 맡았다(규칙 엔진·화면 / 추출·마스킹·평가). 커밋마다 별도 Claude 리뷰 에이전트가 검토했고, 커밋 메시지에 Co-Authored-By로 표기
- 기획 단계 생성형 AI: OpenAI Codex CLI — 참가신청서를 바탕으로 한 초기 구조도 초안(본선 전). 발표자료·목업 이미지에 쓴 도구는 제출 전 팀이 확인해 추가
- 라이브러리: Streamlit 1.64.0 (Apache-2.0), LangGraph 1.2.12 (MIT), Pydantic 2.13.5 (MIT), PyYAML 6.0.3 (MIT), pytest (MIT), OpenAI Python SDK 3.20.0 (Apache-2.0, vLLM의 OpenAI 호환 API 호출용), ko-pii 1.16.0 (MIT, https://github.com/Marker-Inc-Korea/ko-pii, 규칙 기반 개인정보 검출 — ② 마스킹)
- LLM: Qwen3.8-27B-FP8 (Qwen, Hugging Face `Qwen/Qwen3.8-27B-FP8`, 리비전 017b9c7, Apache-2.0)
- LLM 서빙: vLLM 0.25.1 (Apache-2.0), 로컬 GPU(RTX A6000 2장). 계획서가 서버 밖으로 나가지 않습니다.
- 법령 원문 (국가법령정보센터 law.go.kr, 확인일 2026-09-29): 생명윤리 및 안전에 관한 법률·시행령·시행규칙, 개인정보 보호법·시행령, 약사법, 의약품 등의 안전에 관한 규칙, 의료기기법·시행규칙, 공용기관생명윤리위원회 고시. 정리본은 `data/laws/` (본선 전 수집)
- 근거 검색(RAG): `src/agent/retrieve.py` — `data/laws/`를 조문·소제목 단위로 나눠 글자 2-gram BM25로 찾음(직접 구현, 외부 검색 라이브러리·임베딩 모델 없음). 판정에는 쓰지 않고 ⑨ 사무국 질문의 참고 근거와 근거 보기에만 씀
- 가이드라인: 가명정보 처리 가이드라인 2026.03. (개인정보보호위원회, https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&mCode=G010030000&nttId=11931, 확인일 2026-09-30), 보건의료데이터 활용 가이드라인 2025.12 (보건복지부·개인정보보호위원회, https://www.mohw.go.kr/boardDownload.es?bid=0003&list_no=1488471&seq=1), 공용기관생명윤리위원회 운영기관 안내 (https://public.irb.or.kr/), AI Hub 안심존 공용 기관생명윤리위원회(IRB) 심의신청 가이드라인 v3.2 (팀 문서 인용, 2차 출처 — R-11 제출 전 보완 경고의 근거)
- 판정 규칙표(`data/rules/rules.yaml`)의 원문은 팀이 본선 전(09-29)에 모은 사전 조사 자료에서 옮겼습니다.
- 공개 심의 일정: 공용기관생명윤리위원회 2026 심의일정 103회 (`data/schedules/public_irb_2026.csv`, e-IRB 심의일정 달력 https://public.irb.or.kr/pt/pt01/PT0103/PT0103R05.do, 확인일 2026-09-29, 본선 전 수집). 접수 마감은 공용위원회 SOP ver5.5 제31조④(심의 7일 전까지 접수)로 계산
- 기관 층(`data/institutions/profiles.yaml`, `data/schedules/uos_irb_2026.csv`, 확인일 2026-09-29, 본선 전 수집한 사전 조사 자료에서 서류 이름·규칙 요지·일정 같은 사실만 옮김): 공용기관생명윤리위원회 e-IRB 제출서류 안내·SOP ver5.5·연구계획서 권고서식 제37호 (https://public.irb.or.kr/), 서울시립대학교 생명윤리위원회 표준운영지침 Ver.2.3·FAQ v3·R-BAY 공지·2026 정규심의 일정 (https://research.uos.ac.kr/institutionalbioethicscommittee), 가톨릭중앙의료원 CMC 임상연구윤리규정집 Ver.10.0 별표1·신규과제 유의사항·심사면제 절차 안내·개인정보 관련 IRB 심의 안내 (https://cmcirb.cmcnu.or.kr/), 질병관리청 IRB 표준운영지침 개정 내용 소개 (PHWR 2026;19(5):268, CC BY 4.0, https://doi.org/10.56786/PHWR.2026.19.5.3)
- 실제 연구 비교 자료: CRIS(임상연구정보서비스, 질병관리청) 공개 등록 연구 8건 — seq 29626·29627·29675·29685·29703·29714·29814·29826 (https://cris.nih.go.kr/cris/search/detailSearch.do?seq=번호, 확인일 2026-09-30). 연구책임자 성명 등 개인정보는 빼고 연구 요약만 입력으로 쓰며, 승인 위원회와 관할 유형만 비교한다(`data/cases/cris/`)
- 평가용 가상 계획서 10건(`data/cases/`): 팀이 만든 가상 자료, 정답은 T3 확인 전 초안
- 데이터: `data/samples/`의 계획서 4건과 `data/lists/demo_institutions.csv`의 기관은 팀이 만든 가상 자료입니다. 공공 데이터는 추가하는 대로 URL과 확인일을 적습니다.
