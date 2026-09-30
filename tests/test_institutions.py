"""기관 프로필(data/institutions/profiles/*.yaml) 형식 검사. 기관을 더하면 이 검사를 통과해야 한다."""
import csv
from datetime import date
from pathlib import Path

import pytest
import yaml

from agent.nodes import judge

ROOT = Path(__file__).resolve().parents[1]
PROFILES = sorted((ROOT / "data" / "institutions" / "profiles").glob("*.yaml"))
STD = yaml.safe_load((ROOT / "data" / "institutions" / "standard.yaml").read_text(encoding="utf-8"))
WHEN = {"always", "drb", "exempt", "export", "received_data"}


def ok_when(when) -> bool:
    """조건: 이름 하나, 목록(모두 만족), kind=연구유형|연구유형."""
    if isinstance(when, list):
        return bool(when) and all(ok_when(w) for w in when)
    return when in WHEN or (isinstance(when, str) and when.startswith("kind="))
LEVEL = {"보완 필요", "확인 필요", "안내"}


@pytest.mark.parametrize("path", PROFILES, ids=[p.stem for p in PROFILES])
def test_profile_shape(path):
    p = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert p["id"] == path.stem
    for key in ("name", "short", "aliases", "submit", "source", "plan_form", "docs", "schedule"):
        assert p.get(key), key
    assert p["id"] == "public" or p["short"] in p["aliases"]           # 화면의 기관 전환이 short로 찾는다
    assert "http" in p["source"] and "확인" in p["source"]              # 출처 URL과 확인일
    assert set(p["docs"]) <= set(STD["docs"]) and set(p.get("plan", {})) <= set(STD["plan"])
    ids = [r["id"] for r in p.get("rules", [])]
    assert len(ids) == len(set(ids))
    for r in p.get("rules", []):
        assert r["id"].startswith("I-") and ok_when(r["when"]) and r["level"] in LEVEL and r["warning"] and r["source"]
    for k, v in p["docs"].items():                                      # 서류 칸은 이름, 또는 {name, when}
        assert isinstance(v, str) or (v.get("name") and ok_when(v["when"])), k
    for v in p.get("variants", []):                                     # 연구 유형·면제별 서식 변형
        assert ok_when(v["when"]) and set(v.get("docs", {})) <= set(STD["docs"]) and set(v.get("plan", {})) <= set(STD["plan"])
    assert p.get("drb_order", "drb_first") in ("drb_first", "irb_first", "unknown")
    for f in p.get("forms", []):                                        # 서식 목록: 이름은 필수, doc은 표준 서류 키
        assert f.get("name") and (f.get("doc") is None or f["doc"] in STD["docs"]), f
    checks = {"past_tense", "mixed_style", "age_without_man", "sample_size_rationale", "period_before_review",
              "recruit_doc", "crf_identifiers", "english_title"}
    assert all(r.get("check") in (None, *checks) for r in p.get("rules", [])), p["id"]
    s = p["schedule"]
    assert s["kind"] in ("public", "csv", "none")
    if s["kind"] == "csv":
        rows = list(csv.DictReader((ROOT / s["path"]).open(encoding="utf-8-sig")))
        assert rows and list(rows[0])[:5] == ["위원회", "회의일", "접수마감", "출처", "확인일"]
        for r in rows:
            assert date.fromisoformat(r["접수마감"]) < date.fromisoformat(r["회의일"])
        assert s["result_days"] > 0 and s["cycle_days"] > 0


@pytest.mark.parametrize("path", PROFILES, ids=[p.stem for p in PROFILES])
def test_profile_runs_through_engine(path):
    """샘플 2(가명·DRB)와 샘플 1(식별)을 이 기관 소속으로 판정해도 오류 없이 이 기관 기준 결과가 나온다."""
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    from test_rules import IDENTIFIED, run
    p = yaml.safe_load(path.read_text(encoding="utf-8"))
    name = "없음" if p["id"] == "public" else p["short"]
    for overrides in ({}, IDENTIFIED):
        state = run(overrides, name)
        assert state["venue"]["id"] == p["id"]
        assert state["documents"] and all(s["warning"] for s in state["suggestions"])
