"""제품 품질 확장 · 합성 검사값 (실제 제조 품질 데이터가 아님).

로트별 실린더 보어 직경을 합성한다. 규격 이탈은 '로트 보류 제안'으로 설비 이상과 별도 기록한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

LSL, USL, NOMINAL = 49.98, 50.02, 50.00


def synth_lots(asset_id: str, start: datetime, n_lots: int = 6, drift_from: int | None = 4, seed: int = 3) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_lots):
        drift = 0.0 if drift_from is None or i < drift_from else 0.012 * (i - drift_from + 1)
        for j in range(5):
            rows.append(
                {
                    "lot_id": f"LOT-{start:%m%d}-{i + 1:02d}",
                    "asset_id": asset_id,
                    "ts": start + timedelta(minutes=10 * i, seconds=30 * j),
                    "measure": "bore_diameter",
                    "value": round(NOMINAL + drift + float(rng.normal(0, 0.004)), 4),
                    "lsl": LSL,
                    "usl": USL,
                    "unit": "mm",
                }
            )
    return rows
