"""완성 영상 장면별 프레임 모음 — python tools/sheet.py <ID>"""
import json, subprocess, sys
from pathlib import Path
from common import BUILD, LV, load_spec
sid = sys.argv[1]
r = json.loads((BUILD / sid / "final_report.json").read_text())
video = LV.parent.parent / r["file"]
out = BUILD / sid / "frames"; out.mkdir(exist_ok=True)
files = []
for c in r["chapters"]:
    t = c["start"] + min(c["len"] - 0.5, max(3, c["len"] * 0.65))
    f = out / f"s{c['scene']:02d}.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=480:-1", str(f)], check=True)
    files.append(f)
while len(files) % 4:
    files.append(files[-1])
args = sum((["-i", str(f)] for f in files), [])
rows = len(files) // 4
fc = "".join(f"{''.join(f'[{r*4+k}]' for k in range(4))}hstack=4[r{r}];" for r in range(rows)) + "".join(f"[r{r}]" for r in range(rows)) + f"vstack={rows}"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args, "-filter_complex", fc, str(out / "sheet.png")], check=True)
print(out / "sheet.png")
