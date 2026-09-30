# 문서 입력 연결

S1의 `PDF / Word / TXT 파일 불러오기`를 열어 파일을 선택하면 본문을 읽어 입력칸에 넣는다.
사용자가 본문을 확인하고 `사실 추출 시작`을 눌렀을 때에만 기존 `agent.api.start()`를 호출한다.
문서 내용으로 사실이나 판정 결과를 화면에서 만들지 않는다.

## 설치

프로젝트 루트에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r src/ui/upload-requirements.txt
```

PDF: pypdf 6.10.0, BSD-3-Clause, https://github.com/py-pdf/pypdf

DOCX, TXT: Python 표준 라이브러리로 읽는다. 외부 변환 서버에 파일을 보내지 않는다.
파일은 Streamlit 실행 서버의 메모리에서 읽는다.

## 지원 범위

- PDF는 텍스트를 추출한다. 스캔 이미지의 OCR과 암호 입력은 지원하지 않는다.
- DOCX는 본문과 표 안의 텍스트를 문서 순서대로 읽는다. 이미지, 머리말, 꼬리말, 각주를 전체 문서처럼 재현하지 않는다.
- TXT는 UTF-8, BOM이 있는 UTF-16, CP949를 읽는다.
- HWP, HWPX, 구형 DOC는 PDF 또는 DOCX로 변환해서 입력한다.
- 최대 20MB, PDF 200쪽, 추출된 텍스트 20만 자까지 읽는다. 초과하면 오류를 표시하고 기존 입력을 보존한다.
- FAKE=1에서도 파일 텍스트를 불러올 수 있으나, 분석 API는 원래의 예시 연구계획만 처리한다.
- FAKE=0에서 업로드한 문서를 분석하려면 마스킹 모듈과 모델 서버를 사용할 수 있어야 한다. LLM=0이면 사실 추출은 샘플에 한정된다.

## 통합 담당자 요청

담당 범위가 app.py와 src/ui/이므로 루트 requirements.txt와 README는 수정하지 않았다.

1. requirements.txt에 `-r src/ui/upload-requirements.txt`를 추가한다.
2. README 출처표에 `pypdf 6.10.0 / BSD-3-Clause / https://github.com/py-pdf/pypdf / PDF 텍스트 추출`을 추가한다.
3. 실제 문서 분석용 모델 서버 주소(LLM_BASE_URL), 모델명(LLM_MODEL), 접속 가능 환경을 확인한다.

src/agent/의 API 변경은 필요 없다.
