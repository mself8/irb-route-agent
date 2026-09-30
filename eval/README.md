# eval

평가용 합성 데이터(모두 가상 계획서, Claude Code로 생성)로 사실 추출과 판정을 잰다. 실제 개인정보는 없다. 저작권 표시가 있는 원본 자료는 올리지 않는다.

- `traps/`: 함정 300(규칙마다 정면·다른 표현·부정문·경계값)과 대조군 93. 생성기 `traps/generate.py`, 개발용 함정 `traps/traps.yaml`
- `synth/`: 합성 계획서 300(시나리오 220 + CRIS 형식 80). 생성기 `synth/generate.py`
- `trap_eval.py`: 봉인 측정. 1단계는 정답 사실로 규칙 엔진만, 2단계는 층화 표본으로 AI 추출부터 끝까지
- `standard_metrics.py`: Precision·Recall·F1·MCC·Balanced Accuracy와 Wilson 95% 구간 → `results/standard_metrics.md`
- `crosscheck.py`: 정답 역검증. Claude·GPT 두 계열이 원문만 보고 693건을 따로 채점 → `results/crosscheck.md`
- `independent.py`, `human_check.py`: 독립 확인 40건, 팀원 검수 페이지(`results/human_check40.html`)
- `extract_eval.py`, `perturb.py`, `metrics.py`: 사실 추출 정확도, 표현 바꾸기 견고성, 초기 지표
- `build_cases.py`: 사실 추출 평가용 가상 계획서와 정답 라벨(`data/cases/`)
- `check_rules_text.py`: 규칙표의 원문 문장이 사전 조사한 법령 원문에 글자 그대로 있는지 점검
- 결과 파일은 `results/`에 둔다
