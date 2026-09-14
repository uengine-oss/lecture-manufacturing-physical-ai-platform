"""S04 · 사건 유형 구분과 화면 표시 매핑 — 빈칸 ____ 을 채운다.

세 가지 사건은 서로 다른 데이터에서 나온다.
- SENSOR_FAULT    : 센서 품질 플래그(결측·고착) — 설비가 아니라 측정이 의심스럽다
- COOLING_ANOMALY : 품질이 OK 인 온도 관측이 기준을 넘은 채 지속 — 설비 상태가 의심스럽다
- PRODUCT_QUALITY : 합성 제품 검사값(보어 직경)의 규격 이탈 — 로트 보류 제안
설비 상태 라벨(UCI cooler_pct)은 제품 불량이 아니다.
참고: hydops/b5_detect/detector.py(recent_summary), hydops/b5_detect/product.py, hydops/b1_data/inspection.py,
      hydops/b9_dashboard/static/app.js(TYPE_KO, STATUS_KO)
"""
from hydops.config import TH

____ = None  # 빈칸 표시

SENSOR_FAULT, COOLING_ANOMALY, PRODUCT_QUALITY, NORMAL = "SENSOR_FAULT", "COOLING_ANOMALY", "PRODUCT_QUALITY", "NORMAL"


def classify_sensor_window(ts1: dict, th=TH) -> str:
    """ts1 = hydops.b5_detect.detector.recent_summary(rows)["TS1"] (최근 60초 요약)."""
    q = ts1["quality"]
    # ① 센서 오류를 먼저 본다: 결측 5초 이상 연속, 고착 플래그 1개 이상, 유효 관측 비율 70% 미만
    if q["longest_gap_s"] >= ____ or q["flags"].get("____", 0) > 0 or q["valid_ratio"] < ____:
        return ____
    # ② 센서가 정상일 때만: 유효 온도가 경보 온도를 넘은 채 지속 시간 이상 이어졌는가
    if ts1["longest_valid_above_alarm_s"] >= th.____:
        return ____
    return NORMAL


def classify_lot(rows: list[dict]) -> dict | None:
    """한 로트의 합성 검사값 목록 → 규격 이탈이면 제품 품질 사건 요약, 아니면 None."""
    out = [r for r in rows if not (r["____"] <= r["value"] <= r["____"])]
    if not out:
        return None
    return {
        "event_type": ____,
        "lot_id": rows[0]["lot_id"],
        "out_of_spec": len(out),
        "samples": len(rows),
        "is_synthetic": ____,
        "suggestion": "LOT_HOLD",
    }


# 어떤 값이 무엇을 말하는가 — EQUIPMENT_STATE(설비 상태) / PRODUCT_QUALITY(제품 품질) / SENSOR_QUALITY(센서 품질)
LABEL_KIND = {
    "profile.cooler_pct": "____",  # UCI 냉각기 상태 라벨 (평가에만 쓴다)
    "inspection.bore_diameter": "____",  # 합성 제품 검사값
    "observation.quality_flag": "____",  # B2 품질 플래그
}

# 제공 관제 화면(app.js TYPE_KO)과 같은 사건 유형 표시 이름
EVENT_DISPLAY = {
    "COOLING_ANOMALY": "____",
    "SENSOR_FAULT": "____",
    "PRODUCT_QUALITY": "____",
}

# 사건 유형별로 사건이 흔히 끝나는 상태 (제공 화면 STATUS_KO 의 키)
TYPICAL_END_STATUS = {
    "SENSOR_FAULT": "____",  # 설비 조치 보류, 센서 점검
    "PRODUCT_QUALITY": "____",  # 로트 보류 제안 — 품질 담당 확인
}
