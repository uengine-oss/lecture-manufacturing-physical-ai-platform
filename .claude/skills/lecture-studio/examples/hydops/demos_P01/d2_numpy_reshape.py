# 시연 2 · 넘파이 배열과 reshape
import numpy as np

a = np.arange(12)              # 0부터 11까지 12개
print("a =", a)
t = a.reshape(3, 4)            # 3줄 × 4칸 표로 다시 접는다
print("t =\n", t)
print("줄마다 평균:", t.mean(axis=1))

# 실제 압력 PS1: 사이클 100 은 6000개 → 60초 × 100개
line = open("data/raw/PS1.txt").readlines()[100]
ps = np.array(line.split("\t"), dtype=float)
sec = ps.reshape(60, 100)
print("모양:", ps.shape, "→", sec.shape)
first = sec[0]
print("0초 구간 첫 샘플:", first[0], "| 평균:", round(first.mean(), 2), "최소:", first.min(), "최대:", first.max(), "개수:", first.size)
