"""화면(ui)이 부르는 함수는 이 파일의 세 개뿐이다.

    start()    ①~③을 돌리고 ④ 사실 확인 앞에서 멈춘다        → Pending
    confirm()  연구자가 확정한 사실로 ⑤~⑩을 돌린다            → Result
    rejudge()  (나) 항목에 입력한 값을 넣고 ④부터 다시 판정한다 → Result

FAKE=1(기본)이면 그래프를 돌리지 않고 data/samples의 예시 결과를 돌려준다.
화면 개발과 데모 비상용이다. 실제 그래프는 FAKE=0.
"""
import os
import uuid
from functools import lru_cache

from langgraph.types import Command

from . import samples
from .state import FACT_LABELS, Pending, Result

FAKE = os.getenv("FAKE", "1") == "1"


@lru_cache(maxsize=1)
def _graph():
    from .graph import build_graph
    return build_graph()


def _cfg(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


def start(plan_text: str, institution_name: str, target_start_date: str) -> Pending:
    if FAKE:
        sample = samples.match(plan_text)
        if sample is None:
            raise ValueError("예시 모드(FAKE=1)에서는 샘플 계획서만 판정합니다. 고친 계획서는 실제 모드(FAKE=0)에서 판정하세요.")
        return Pending(run_id=f"fake:{sample['id']}", **sample["pending"])
    run_id = uuid.uuid4().hex[:8]
    _graph().invoke(
        {"raw_text": plan_text, "institution_name": institution_name, "target_start_date": target_start_date},
        _cfg(run_id),
    )
    v = _graph().get_state(_cfg(run_id)).values
    return Pending(run_id=run_id, masked_text=v["masked_text"], mask_log=v["mask_log"], facts=v["facts"])


def confirm(run_id: str, confirmed_facts: list[dict], edited_by_user: list[str] | None = None) -> Result:
    if FAKE:
        sample = samples.load(run_id.removeprefix("fake:"))
        return Result(run_id=run_id, facts=confirmed_facts or sample["pending"]["facts"], **sample["result"])
    _graph().invoke(
        Command(resume={"confirmed_facts": confirmed_facts, "edited_by_user": edited_by_user or []}),
        _cfg(run_id),
    )
    return _result(run_id)


def rejudge(run_id: str, extra_inputs: dict) -> Result:
    if FAKE:
        result = confirm(run_id, [])
        result.abstain = [a for a in result.abstain if a.input_key not in extra_inputs]
        return result
    cfg = _cfg(run_id)
    v = _graph().get_state(cfg).values
    facts = [
        {**f, "value": extra_inputs[f["key"]], "status": "found"} if f["key"] in extra_inputs else f
        for f in v["confirmed_facts"]
    ]
    known = {f["key"] for f in facts}
    facts += [{"key": k, "label": FACT_LABELS[k], "value": val, "status": "found"}
              for k, val in extra_inputs.items() if k in FACT_LABELS and k not in known]
    # ④가 이 값을 확정한 것으로 기록하고 ⑤부터 다시 돌린다
    _graph().update_state(
        cfg,
        {"confirmed_facts": facts, "extra_inputs": {**v.get("extra_inputs", {}), **extra_inputs}},
        as_node="step4_confirm",
    )
    _graph().invoke(None, cfg)
    return _result(run_id)


def _result(run_id: str) -> Result:
    v = _graph().get_state(_cfg(run_id)).values
    return Result(
        run_id=run_id,
        facts=v["confirmed_facts"],
        institution=v["institution"],
        judgments=v["judgments"],
        route=v["route"],
        documents=v["documents"],
        schedule=v["schedule"],
        abstain=v["abstain"],
        report=v["report"],
        suggestions=v.get("suggestions", []),
        highlights=v.get("highlights", []),
        masked_text=v.get("masked_text", ""),
    )
