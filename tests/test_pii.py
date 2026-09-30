"""② 마스킹(agent/pii.py) 단위 테스트. 규칙 기반이라 서버 없이 돈다."""
import pytest

from agent import pii, samples


@pytest.mark.parametrize("sample_id", samples.all_ids())
def test_reproduces_sample_masking(sample_id):
    s = samples.load(sample_id)
    masked, log = pii.mask(s["plan_text"])
    assert masked == s["pending"]["masked_text"]
    assert log == s["pending"]["mask_log"]


def test_masks_contacts_and_ids():
    masked, log = pii.mask("연락처 010-1234-5678, 02-123-4567, a.b@example.com, 주민번호 900101-1234567")
    assert masked == "연락처 [전화번호], [전화번호], [이메일], 주민번호 [주민번호]"
    assert log == [{"type": "전화번호", "count": 2}, {"type": "이메일", "count": 1}, {"type": "주민번호", "count": 1}]


def test_masks_names_only_in_name_context():
    text = "연구책임자: 홍길동 (소화기내과)\n김철수 교수와 공동연구. 수행기관: 가상대학교병원\n담당자: 이영희\n연구자: 가상대학교병원 소속"
    masked, log = pii.mask(text)
    assert masked == ("연구책임자: [이름] (소화기내과)\n[이름] 교수와 공동연구. 수행기관: 가상대학교병원\n"
                      "담당자: [이름]\n연구자: 가상대학교병원 소속")
    assert log == [{"type": "이름", "count": 3}]


def test_no_pii_is_unchanged():
    text = "연구 방법: 가명처리한 데이터셋을 제공받아 원내 분석실에서 분석한다."
    assert pii.mask(text) == (text, [])
