# 시연 5 · assert 는 "이게 참이어야 한다"는 약속
values = [3.0, 5.0, 4.0]
mean = sum(values) / len(values)
assert mean == 4.0            # 참이면 아무 일도 없다
print("첫 번째 약속 통과, 평균 =", mean)

unit = "°C"
try:
    assert unit == "bar", "압력의 단위는 bar 여야 한다"
except AssertionError as e:
    print("약속이 깨졌다 → AssertionError:", e)
