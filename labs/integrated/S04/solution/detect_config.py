"""S04 · 감지 설정 (정답본).

두 가지 감지 설정을 채운다.
1) UCI 재생 데이터: 정상 위상 기준 + 이동평균 잔차 → hydops.b5_detect.evaluate.evaluate(**설정)
2) 시뮬레이터 스트림: 유효 온도 경보 → hydops.b5_detect.detector.ThresholdDetector(STREAM)
모든 기준은 교육용 가정값이다 (UCI 설비의 운전 기준이 아니다).
"""
from hydops.config import Thresholds

# 시험 구간을 고정하는 난수 시드 (hydops/b5_detect/evaluate.py 의 SPLIT_SEED 와 같아야 한다)
SPLIT_SEED = 2026

# ① 지속 10초 설정: 5초 이동평균, 허용 한계 max(4σ, 3°C), 10초 연속 초과
STRICT = {"k_sigma": 4.0, "min_delta_c": 3.0, "sustain_s": 10, "smooth_s": 5}

# ② 지속 조건 없음 설정: 평활 없음(1초), 허용 한계 max(2σ, 1°C), 1초만 넘어도 이상
LOOSE = {"k_sigma": 2.0, "min_delta_c": 1.0, "sustain_s": 1, "smooth_s": 1}

# ③ 시뮬레이터 스트림 경보: 유효 온도가 60°C 를 넘는 상태가 10초 연속
STREAM = Thresholds(alarm_temp_c=60.0, alarm_sustain_s=10)
