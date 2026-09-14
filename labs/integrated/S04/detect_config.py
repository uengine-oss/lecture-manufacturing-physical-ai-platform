"""S04 · 감지 설정 — 빈칸 ____ 을 값으로 바꾼다.

두 가지 감지 설정을 채운다.
1) UCI 재생 데이터: 정상 위상 기준 + 이동평균 잔차 → hydops.b5_detect.evaluate.evaluate(**설정)
2) 시뮬레이터 스트림: 유효 온도 경보 → hydops.b5_detect.detector.ThresholdDetector(STREAM)
모든 기준은 교육용 가정값이다 (UCI 설비의 운전 기준이 아니다).
참고: 교재 I04 §2 표, hydops/b5_detect/evaluate.py, hydops/config.py 의 Thresholds
"""
from hydops.config import Thresholds

____ = None  # 빈칸 표시. 모든 ____ 를 채우면 이 줄은 남아 있어도 된다.

# 시험 구간을 고정하는 난수 시드 (hydops/b5_detect/evaluate.py 의 SPLIT_SEED 와 같아야 한다)
SPLIT_SEED = ____

# ① 지속 10초 설정: 5초 이동평균, 허용 한계 max(4σ, 3°C), 10초 연속 초과
STRICT = {"k_sigma": ____, "min_delta_c": ____, "sustain_s": ____, "smooth_s": ____}

# ② 지속 조건 없음 설정: 평활 없음(1초), 허용 한계 max(2σ, 1°C), 1초만 넘어도 이상
LOOSE = {"k_sigma": ____, "min_delta_c": ____, "sustain_s": ____, "smooth_s": ____}

# ③ 시뮬레이터 스트림 경보: 유효 온도가 60°C 를 넘는 상태가 10초 연속
STREAM = Thresholds(alarm_temp_c=____, alarm_sustain_s=____)
