"""⑧ 역산 일정의 입력인 공개 심의 일정 CSV 형식 검사."""
import csv
from datetime import date, timedelta
from pathlib import Path

CSV = Path(__file__).resolve().parents[1] / "data" / "schedules" / "public_irb_2026.csv"


def test_public_irb_schedule():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    assert len(rows) == 103  # e-IRB 달력 2026년 1~103차
    for r in rows:
        assert list(r)[:5] == ["위원회", "회의일", "접수마감", "출처", "확인일"]
        assert date.fromisoformat(r["회의일"]) - timedelta(days=7) == date.fromisoformat(r["접수마감"])
        assert r["구분"] in ("정규", "특별")
