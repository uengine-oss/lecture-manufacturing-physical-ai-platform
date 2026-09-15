#!/usr/bin/env python3
"""나레이션 대본 검사 — 금지 표현·장면 길이·도입부 인프라 용어.

    python3 check_narration.py narration.json [--exclude robo-architect,아키텍트]

서사 기준이 흔들리면 영상을 다시 찍게 된다. 대본 단계에서 잡는 것이 가장 싸다.
"""
import argparse, json, re, sys

BANNED = ["세 제품", "3개", "세 개의 제품", "통합 시연", "한 머신", "함께 떠", "합쳐", "연동"]
INFRA  = ["포트", "컨테이너", "팟맨", "Podman", "도커", "호스트 프로세스"]
INTRO_SCENES = 3
MIN_SEC, MAX_SEC = 20, 40
CHARS_PER_SEC = 7.2          # 한국어 TTS 실측 (marin) — durations.json 으로 재보정할 것

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--exclude", default="", help="이번 시나리오에서 뺄 낱말 (쉼표 구분)")
    a = ap.parse_args()

    scenes = json.load(open(a.script))
    blob = json.dumps(scenes, ensure_ascii=False)
    fails = []

    hits = {w: len(re.findall(re.escape(w), blob)) for w in BANNED}
    hits = {w: n for w, n in hits.items() if n}
    print(f"A1 금지 표현 : {sum(hits.values())}건 {hits or ''}")
    if hits: fails.append("A1")

    ex = [w.strip() for w in a.exclude.split(",") if w.strip()]
    exhits = {w: len(re.findall(re.escape(w), blob, re.I)) for w in ex}
    exhits = {w: n for w, n in exhits.items() if n}
    print(f"A2 제외 대상 : {sum(exhits.values())}건 {exhits or ''}")
    if exhits: fails.append("A2")

    intro = " ".join(s["text"] for s in scenes if s["scene"] <= INTRO_SCENES)
    bad = [w for w in INFRA if w in intro]
    print(f"A4 도입부 인프라 용어: {bad or '없음'}")
    if bad: fails.append("A4")

    print(f"\n장면 {len(scenes)}개 · 예상 길이")
    long_short = []
    for s in scenes:
        est = len(s["text"]) / CHARS_PER_SEC
        flag = ""
        if est > MAX_SEC: flag, = ("길다",); long_short.append(s["scene"])
        elif est < MIN_SEC: flag = "짧다"
        print(f"  {s['scene']:>2}  {len(s['text']):>4}자  ~{est:>5.1f}s  {flag}")
    total = sum(len(s['text']) for s in scenes) / CHARS_PER_SEC
    print(f"  합계 ~{total/60:.1f}분")
    if long_short: print(f"  ! 40초 초과 예상: {long_short}")

    print("\n결과:", "PASS" if not fails else "FAIL " + ", ".join(fails))
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
