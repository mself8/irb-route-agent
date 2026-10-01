"""data/samples의 데모 샘플(가상 계획서 + 예시 결과). FAKE 모드가 쓰고, LLM=0이면 ②③ 대신 쓴다."""
import json
from functools import lru_cache
from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


@lru_cache(maxsize=None)
def load(sample_id: str) -> dict:
    return json.loads((SAMPLE_DIR / f"{sample_id}.json").read_text(encoding="utf-8"))


def all_ids() -> list[str]:
    return sorted(p.stem for p in SAMPLE_DIR.glob("*.json"))


def match(plan_text: str) -> dict | None:
    """입력한 계획서가 샘플과 같으면 그 샘플을 돌려준다."""
    return next((load(i) for i in all_ids() if load(i)["plan_text"].strip() == plan_text.strip()), None)


def require(plan_text: str) -> dict:
    sample = match(plan_text)
    if sample is None:
        raise NotImplementedError("실제 노드를 구현하기 전에는 샘플 계획서만 판정할 수 있습니다.")
    return sample
