# 시연 1 · 원본 데이터 파일은 어떻게 생겼을까
from pathlib import Path

RAW = Path("data/raw")          # lecture/system 에서 실행한다

for name in ["TS1.txt", "FS1.txt", "PS1.txt"]:
    with open(RAW / name) as f:
        first_line = f.readline()          # 첫 줄 = 사이클 0
    values = first_line.split("\t")        # 탭으로 잘라 숫자 조각 목록으로
    print(name, "한 줄의 값 개수:", len(values), "앞 3개:", values[:3])
