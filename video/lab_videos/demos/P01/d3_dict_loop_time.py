# 시연 3 · 딕셔너리, for 반복, enumerate, 리스트 컴프리헨션, datetime
from datetime import datetime, timedelta, timezone

SENSOR_SPEC = {"TS1": {"hz": 1, "unit": "°C"}, "PS1": {"hz": 100, "unit": "bar"}}
print(SENSOR_SPEC["PS1"]["unit"])                 # 키로 꺼내기

for sid, spec in SENSOR_SPEC.items():             # 키와 값을 함께 꺼내며 반복
    print(sid, "→", spec["hz"], "Hz")

for i, cycle in enumerate([100, 101, 102]):       # 순번 i 와 값을 함께
    print("순번", i, "사이클", cycle)

squares = [x * x for x in [1, 2, 3]]              # 리스트 컴프리헨션
print(squares)

start = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
print(start + timedelta(seconds=90))              # 90초 뒤
print([str(start + timedelta(seconds=i * 60)) for i in range(3)])
