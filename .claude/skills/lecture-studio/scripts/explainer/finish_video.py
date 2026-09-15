"""녹화 원본 + 나레이션 → 최종 mp4 (소프트 자막 포함) + 검증 보고.

사용: python finish_video.py [--fast]
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

import os, sys
OUT = Path(os.environ.get("EXPLAINER_DIR", ".")).resolve()   # 설명 영상 폴더 (work/ 아래에 raw·narration·scenes-timing)
W = OUT / "work"
ASSEMBLE = str(Path(__file__).parent / "assemble_narrated_video.py")
PY = os.environ.get("PYTHON", sys.executable)
TITLE = os.environ.get("VIDEO_TITLE", "설명영상")


def ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    sfx = "-fast" if a.fast else ""
    raw = W / "raw" / f"explainer-raw{sfx}.webm"
    timing = json.loads((W / f"scenes-timing{sfx}.json").read_text())
    durs = {d["scene"]: d["duration"] for d in json.loads((W / "narration" / "durations.json").read_text())}
    nar = {d["scene"]: d for d in json.loads((W / "narration.json").read_text())}
    vdur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(raw)], capture_output=True, text=True).stdout)

    # C1 겹침 검사
    starts = {t["scene"]: t["start_sec"] for t in timing}
    report = ["CP-C 장면 수납 (scene start dur slack)"]
    overlap = 0
    for s in sorted(starts):
        nxt = starts.get(s + 1, vdur)
        slack = nxt - (starts[s] + durs[s])
        overlap += slack < -0.5
        report.append(f"  {s:>2} {starts[s]:>7.1f} {durs[s]:>5.1f} {slack:>6.1f} {'겹침!' if slack < -0.5 else ''}")
    report.append(f"  겹침 {overlap}건 · 영상 {vdur/60:.0f}분 {vdur%60:.0f}초")

    # 자막: 문장 단위로 나레이션 길이를 글자 수 비례 배분
    srt, k = [], 1
    for s in sorted(starts):
        sents = [x.strip() for x in re.split(r"(?<=[.?!])\s+", nar[s]["text"]) if x.strip()]
        total = sum(len(x) for x in sents)
        t = starts[s]
        for x in sents:
            d = durs[s] * len(x) / total
            srt.append(f"{k}\n{ts(t)} --> {ts(t + d)}\n{x}\n")
            k += 1
            t += d
    (OUT / f"{TITLE}{sfx}.srt").write_text("\n".join(srt))

    mid = W / f"narrated{sfx}.mp4"
    r = subprocess.run([PY, ASSEMBLE, "--video", str(raw), "--timing", str(W / f"scenes-timing{sfx}.json"), "--narration-dir", str(W / "narration"), "--out", str(mid)], capture_output=True, text=True)
    report.append(r.stdout[-900:])
    final = OUT / f"{TITLE}{sfx}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mid), "-i", str(OUT / f"{TITLE}{sfx}.srt"), "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=kor", str(final)], check=True)
    report.append(f"최종: {final} ({final.stat().st_size/1e6:.1f} MB)")
    (OUT / f"video_report{sfx}.txt").write_text("\n".join(report) + "\n\nCP-B 화면 검증\n" + (W / f"checks{sfx}.txt").read_text())
    print("\n".join(report))


if __name__ == "__main__":
    main()
