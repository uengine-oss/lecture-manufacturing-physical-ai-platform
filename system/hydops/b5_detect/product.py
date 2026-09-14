"""제품 품질 확장 · 합성 검사값의 규격 이탈 → 로트 보류 제안.

설비 상태 라벨을 제품 불량으로 바꾸어 부르지 않는다. 제품 품질 사건은 설비 사건과 별도 유형으로 기록한다.
"""
from __future__ import annotations

from collections import defaultdict

from hydops.b3_tsdb import store


def check_lots(run_id: str, rows: list[dict]) -> list[dict]:
    lots = defaultdict(list)
    for r in rows:
        lots[(r["asset_id"], r["lot_id"])].append(r)
    events = []
    for (asset_id, lot_id), rs in lots.items():
        out = [r for r in rs if not (r["lsl"] <= r["value"] <= r["usl"])]
        if not out:
            continue
        ev, created = store.create_event(
            run_id, asset_id, "PRODUCT_QUALITY", rs[0]["ts"], rs[-1]["ts"], "lot-spec-v1",
            {"lot_id": lot_id, "measure": rs[0]["measure"], "out_of_spec": len(out), "samples": len(rs),
             "max": max(r["value"] for r in rs), "usl": rs[0]["usl"], "lsl": rs[0]["lsl"],
             "suggestion": "LOT_HOLD 제안 (합성 검사값, 설비 이상과 별도)", "is_synthetic": True},
        )
        if created:
            store.transition(ev["event_id"], "HOLD_NO_EVIDENCE", "product-check", {"suggestion": "LOT_HOLD"}, reason="로트 보류 제안 — 품질 담당 확인")
            events.append(ev)
    return events
