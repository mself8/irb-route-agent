"""화면(ui)과 로직(agent)이 주고받는 데이터 모양.

팀 구글 문서 「단계별 기능 명세」 3장의 JSON 예시를 옮겼다.
필드를 바꾸면 화면이 깨지므로, 바꾸기 전에 상대에게 알린다.
"""
from typing import Literal, Optional, TypedDict

from pydantic import BaseModel

NOTICE = "본 결과는 심의 결과나 승인 여부를 예측하지 않으며, 사무국 확인용 초안입니다."

# ③ 사실 추출이 뽑는 사실 15종
FACT_LABELS = {
    "F01": "연구 유형",
    "F02": "연구자가 식별정보를 직접 열람하는가",
    "F03": "제공받는 데이터 형태",
    "F04": "가명처리 수행 주체",
    "F05": "데이터 이용 환경",
    "F06": "타 기관 데이터 결합·반출",
    "F07": "민감정보 5종 포함",
    "F08": "취약 대상 포함 (미성년 등)",
    "F09": "인체유래물 사용",
    "F10": "의약품·의료기기 임상시험 해당",
    "F11": "동의 계획",
    "F12": "수행기관·참여기관",
    "F13": "연구 기간",
    "F14": "배아·유전자 연구 해당",
    "F15": "연구 참여 인원 규모",
    # F16~F18: 데이터 상태(식별·코드화·가명·익명)를 가른다. 심의면제 후보(E3)와 DRB 판정에 필요
    "F16": "수집·기록하는 식별자",       # 목록 (성명·주민번호·등록번호·연락처 등), 없으면 []
    "F17": "연구용 식별코드 사용",       # 예/아니오
    "F18": "대응표 보관 주체",           # 없음(폐기) / 연구책임자 / 데이터팀·제3자
}


class Fact(BaseModel):
    key: str                                   # F01~F15
    label: str
    value: str | int | list[str] | None = None
    span: Optional[str] = None                 # 가린 계획서의 원문 구간 (글자 그대로)
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    status: Literal["found", "not_found", "conflict"] = "found"
    cross_check: Optional[Literal["agree", "disagree"]] = None


class MaskLog(BaseModel):
    type: str                                  # 이름·전화번호·이메일 …
    count: int


class Pending(BaseModel):
    """start()가 돌려준다. ④ 사실 확인 화면(S2)이 보여 줄 내용."""
    run_id: str
    masked_text: str
    mask_log: list[MaskLog]
    facts: list[Fact]


class InstitutionCheck(BaseModel):
    """⑤ 기관 대조 결과. 공공 명단과 문자열로만 대조한다."""
    name: Optional[str] = None
    affiliated: Optional[bool] = True          # False면 소속 없음 → 공용위원회(J8), None이면 모름
    irb_exists: Optional[bool] = None
    irb_certified: Optional[bool] = None
    clinical_trial_site: Optional[bool] = None
    source: list[str] = []
    checked_at: Optional[str] = None


class Basis(BaseModel):
    """판정 근거. article·text는 T1이 현행 원문과 대조한 뒤에만 채운다."""
    law: str
    article: str = "(현장 확인 후 기입)"
    text: str = "(현장 확인 후 기입)"
    effective: Optional[str] = None
    checked_at: Optional[str] = None
    url: Optional[str] = None
    team_checked: bool = False                 # T1이 현행 원문과 다시 대조했는가


class JudgmentRow(BaseModel):
    """⑥ 관문 판정의 한 행."""
    rule_id: str                               # prep 규칙표 ID (G·T·S·J·E·C·D) 또는 팀 ID (R-xx)
    team_id: Optional[str] = None              # 팀 문서의 R-xx와 같은 규칙이면 그 번호
    requirement: str
    result: Literal["충족", "미충족", "판단불가"]
    abstain_reason: Optional[Literal["①", "②", "③", "나"]] = None  # ①위원회 판단 ②평가어 ③기관 재량 (나)정보 없음
    result_detail: Optional[str] = None
    type: str                                  # 사실형, 사실형(목록), 판단불가(②) …
    basis: Basis
    fact_refs: list[str] = []


class Route(BaseModel):
    """⑦ 경로 결정."""
    route: Literal["A", "B", "C", "임상시험", "비대상", "범위 밖", "미정"]
    committees: list[str]
    order: list[int]
    fast_track: bool = False
    trace: list[str] = []                      # 경로를 정한 규칙 ID


class DocItem(BaseModel):
    doc: str
    level: Literal["법정", "기관"]
    basis: Optional[str] = None                # 법정 서류의 근거 규칙 ID
    source: Optional[str] = None               # 기관 서류의 출처 (안내문서 쪽수 등)
    to: Optional[str] = None                   # 어디에 내는가: IRB · DRB · 결합전문기관 · 공동 수행기관 IRB · 위탁 협약 · 식약처 · IRB 이후


class ScheduleScenario(BaseModel):
    revisions: int                             # 보완 횟수 0·1·2
    submit_by: Optional[str] = None            # None이면 공개 수치 없음
    step: Optional[str] = None                 # 이 날짜가 무엇의 마감인지 (예: 공용위원회 접수 마감)


class Schedule(BaseModel):
    """⑧ 역산 일정. 공개된 회의일·마감일만 쓴다."""
    scenarios: list[ScheduleScenario]
    default: int = 1
    missing: list[str] = []


class AbstainItem(BaseModel):
    """⑨ 판단불가 처리. (가)는 사무국 질문, (나)는 연구자 입력 요청."""
    rule_id: str
    kind: Literal["가", "나"]
    reason: str
    question: Optional[str] = None             # (가) 사무국에 보낼 질문
    ask_input: Optional[str] = None            # (나) 연구자에게 물을 문장
    options: list[str] = []                    # (나) 고를 수 있는 값
    input_key: Optional[str] = None            # (나) 입력값이 들어갈 사실 키 (예: F05)
    cites: list[str] = []
    references: list[dict] = []                # (가) 설명용 참고 근거 [{문서명, 조항, url}] (근거 검색, 판정에는 안 씀)


class Suggestion(BaseModel):
    """제출 전 보완: 사무국·DRB가 되물을 것을 미리 막는 경고와 계획서에 넣을 문장."""
    rule_id: str
    level: Literal["보완 필요", "확인 필요", "안내"]
    scope: Literal["법", "기관"] = "법"        # 법·가이드라인 기준인지, 관할 기관 안내문 기준인지
    warning: str
    add_text: Optional[str] = None            # 계획서에 넣을 문장 초안 (○○는 연구자가 채움)
    basis: Optional[str] = None               # 근거 법령·조항


class Highlight(BaseModel):
    """계획서 원문에서 노란색으로 표시할 곳 (가린 계획서 기준 위치)."""
    key: str
    span: str
    span_start: int
    span_end: int
    note: str


class Venue(BaseModel):
    """관할 위원회의 기관 층 (data/institutions/profiles.yaml). 기관 프로필이 있는 위원회만 채운다."""
    id: str
    name: str
    short: str
    submit: str                                # 제출 창구
    source: str                                # 기관 안내문 출처·확인일
    plan_form: str = ""                        # 이 기관의 연구계획서 서식 이름
    plan_items: list[dict] = []                # [{item: 표준 항목, label: 이 기관 서식의 칸, found: 요약 계획서에 있는가}]
    rules: list[dict] = []                     # 이 계획서에 해당하는 기관 규칙 [{id, level, warning, add_text, source}]


class ReportSentence(BaseModel):
    """⑩ 결과 리포트 한 문장. 근거 없는 문장은 만들지 않는다."""
    text: str
    refs: list[str]


class Submission(BaseModel):
    """⑪ 제출 도우미. blocked(조건 미충족) → awaiting_approval(모의 사이트에 채우고 최종 제출 앞에서 멈춤) → submitted/cancelled.
    preview는 예시 모드(FAKE=1): 게이트와 필드 표만 보여 주고 제출하지 않는다."""
    status: Literal["blocked", "awaiting_approval", "submitted", "cancelled", "preview"]
    venue: Optional[str] = None
    blockers: list[str] = []
    fields: list[dict] = []                    # [{표준 항목, 기관 칸, 값}]
    files: list[str] = []
    screenshot: Optional[str] = None           # /tmp에 둔 캡처 (레포에 넣지 않는다)
    receipt: Optional[str] = None              # 모의 사이트 접수번호
    email_draft: Optional[str] = None          # 사무국 메일 초안 (보내지 않고 복사만)
    message: Optional[str] = None


class Result(BaseModel):
    """confirm()·rejudge()가 돌려준다. 결과 화면(S3~S8)은 이것만 읽는다."""
    run_id: str
    facts: list[Fact]
    institution: InstitutionCheck
    judgments: list[JudgmentRow]
    route: Route
    documents: list[DocItem]
    schedule: Schedule
    abstain: list[AbstainItem]
    report: list[ReportSentence]
    suggestions: list[Suggestion] = []
    highlights: list[Highlight] = []
    masked_text: str = ""                      # 노란색 표시를 그릴 가린 계획서
    venue: Optional[Venue] = None              # 관할 위원회의 기관 층 (제출 창구·기관 규칙·서식 항목)
    compare: list[dict] = []                   # 서식 표준화: 표준 서류·계획서 항목별로 기관마다 다른 서식 이름
    submission: Optional[Submission] = None    # ⑪ 제출 도우미 (제출 준비를 눌렀을 때만)
    notice: str = NOTICE


class GraphState(TypedDict, total=False):
    """LangGraph가 단계 사이에 넘기는 상태. 값은 JSON으로 둔다."""
    raw_text: str
    institution_name: str
    target_start_date: str
    masked_text: str
    mask_log: list[dict]
    facts: list[dict]
    confirmed_facts: list[dict]
    edited_by_user: list[str]
    extra_inputs: dict
    institution: dict
    decision: dict                             # ⑥이 ⑦·⑧에 넘기는 판정 요약
    judgments: list[dict]
    route: dict
    documents: list[dict]
    schedule: dict
    abstain: list[dict]
    report: list[dict]
    suggestions: list[dict]
    highlights: list[dict]
    venue: dict
    submit_requested: bool                     # ⑪ 제출 준비를 눌렀는가 (끝나면 지운다)
    checklist: dict                            # ⑪ 서류별 준비됨 체크
    submission: dict
