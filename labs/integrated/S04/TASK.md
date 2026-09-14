# 통합반 S04 · 지속 조건과 사건 유형 구분 (교재 I04 §7)

빈칸 `____` 을 채운다. DB·서버 없이 돈다(UCI 축약본 + 메모리 시뮬레이터).

| 파일 | 채울 곳 |
|---|---|
| `detect_config.py` | `SPLIT_SEED`, `STRICT`(지속 10초: 4σ·3°C·10초·5초 평활), `LOOSE`(지속 없음: 2σ·1°C·1초·1초), `STREAM = Thresholds(60°C, 10초)` |
| `event_types.py` | `classify_sensor_window` 센서 오류 조건(결측 5초·STUCK·유효 70%)과 반환 유형, 온도 지속 조건 / `classify_lot` 규격 필드·사건 필드 / `LABEL_KIND` / `EVENT_DISPLAY`(app.js `TYPE_KO`) / `TYPICAL_END_STATUS` |

점검 내용
- 고정 시험 구간: `STRICT` → TP 120 · FP 1 · FN 0 · 지연 9.0초, `LOOSE` → FP 4
- 시뮬레이터(시드 42, t=31 주입): 단발 급등 → 사건 없음, 결측 → t=35 `SENSOR_FAULT`, 냉각 0.4 → t=52 `COOLING_ANOMALY`
- 다섯 상황의 유형 판정이 `recent_summary` 의 `sensor_state` 와 일치
- 합성 로트 중 `LOT-0127-06` 만 `PRODUCT_QUALITY`
- `cooler_pct` 는 `EQUIPMENT_STATE`(설비 상태 라벨) — 제품 불량이 아니다

```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S04 -q          # 모두 채우면 16 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S04 -q   # 정답본
```
