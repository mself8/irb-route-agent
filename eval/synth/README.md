# 합성 계획서 300건 (synth300)

- IRB·DRB 경로 탐색 에이전트를 평가하려고 만든 합성 연구계획서 요약 300건과 정답이다.
- 시드는 20260930이다. 같은 시드와 같은 CRIS 원본이면 같은 파일이 나온다.
- 다시 만들기: `python eval/synth/generate.py` → `synth300.json`. 검증: `python eval/synth/generate.py --check` (허용값·사실 문장 유무·정답 재계산·재현성 확인, 층별 개수 출력).
- 정답 경로는 prep 결정 순서(`prep/laws/01_판정규칙표.md`, `02_판단불가_항목.md`)를 `gold_route()`로 옮겨 정했다. 에이전트 규칙 엔진(judge.py·rules.yaml)은 쓰지 않았다.
- 사례마다 사실 정답 F01~F18(계획서에 없으면 null), 경로·위원회, 규칙 ID, 심어 둔 가상 개인정보(pii_gold)가 있다.
- 일부(약 80건)는 CRIS 공개 등록 연구 8건 요약을 변형 (seq 29626·29627·29675·29685·29703·29714·29814·29826). 원본은 `data/cases/cris/`에서 읽고, 결과는 `strata.origin`으로 나눠 본다.
- Claude Code로 만든 합성 데이터다. 실제 연구나 개인정보가 아니다. 이름·전화(010-0XXX 대역)·이메일(example 도메인)은 모두 지어낸 값이다.
