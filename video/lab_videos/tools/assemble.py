"""장면 클립 → 최종 영상 · 자막 · 보고. python tools/assemble.py <ID>"""
import json
import re
import subprocess
import sys

from common import BUILD, LV, load_spec

LEAD = 0.45


def ts(sec):
    ms = int(round(sec * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def probe(p, what="format=duration"):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", what, "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True).stdout.split()[0])


def main(sid):
    spec = load_spec(sid)
    d = BUILD / sid
    nar = json.loads((d / "narration.json").read_text())
    durs = {x["scene"]: x["duration"] for x in json.loads((d / "durations.json").read_text())}
    rr = json.loads((d / "render_report.json").read_text())
    clips = [d / "clips" / f"{i:02d}.mp4" for i in range(1, len(spec["scenes"]) + 1)]
    missing = [c.name for c in clips if not c.exists()]
    if missing:
        raise SystemExit(f"missing clips {missing}")
    (d / "concat.txt").write_text("".join(f"file '{c}'\n" for c in clips))
    title = re.sub(r"[^\w가-힣]+", "_", spec["title"]).strip("_")
    out_dir = LV / spec["class"]
    base = out_dir / f"{sid}_{title}"
    tmp = d / "joined.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(d / "concat.txt"), "-c", "copy", str(tmp)], check=True)
    # 자막: 장면 시작 + LEAD 부터 문장 단위로 나레이션 길이를 글자 수 비례 배분
    srt, k, t = [], 1, 0.0
    chapters = []
    for i, c in enumerate(clips, 1):
        clip_len = probe(c)
        sc = spec["scenes"][i - 1]
        text = next(x["text"] for x in nar if x["scene"] == i)
        sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]
        tot = sum(len(s) for s in sents)
        st = t + LEAD
        for s in sents:
            du = durs[i] * len(s) / tot
            srt.append(f"{k}\n{ts(st)} --> {ts(st + du)}\n{s}\n"); k += 1; st += du
        chapters.append({"scene": i, "type": sc["type"], "start": round(t, 2), "len": round(clip_len, 2), "caption": sc.get("caption")})
        t += clip_len
    base.with_suffix(".srt").write_text("\n".join(srt))
    final = base.with_suffix(".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-i", str(base.with_suffix(".srt")), "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text",
                    "-metadata", f"title={spec['class']} {spec['session']}회 {spec['title']} — 실습 영상", "-metadata:s:s:0", "language=kor", str(final)], check=True)
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"], capture_output=True, text=True).stderr.strip()
    vol = subprocess.run(["ffmpeg", "-i", str(final), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    mean = re.search(r"mean_volume: ([-\d.]+) dB", vol)
    runs = [s for s in rr["scenes"] if s["type"] == "run"]
    rep = {
        "id": sid, "file": str(final.relative_to(LV.parent.parent)), "duration_s": round(probe(final), 1), "scenes": len(clips),
        "decode_errors": len(dec.splitlines()) if dec else 0, "mean_volume_db": float(mean.group(1)) if mean else None,
        "polish_model": nar[0]["model"], "runs": [{k2: r.get(k2) for k2 in ("scene", "expect", "got", "summary")} for r in runs],
        "app_checks": [{"scene": s["scene"], "checks": s.get("checks")} for s in rr["scenes"] if s["type"] == "app"], "chapters": chapters,
    }
    rep["ok"] = rep["decode_errors"] == 0 and all(r["expect"] == r["got"] for r in rep["runs"]) and (rep["mean_volume_db"] or -99) > -40
    (d / "final_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    tmp.unlink()
    print(f"{sid}: {final.name} {rep['duration_s']/60:.1f}분 · runs {[(r['expect'], r['got']) for r in rep['runs']]} · decode {rep['decode_errors']} · {'PASS' if rep['ok'] else 'CHECK'}")


if __name__ == "__main__":
    for sid in sys.argv[1:]:
        main(sid)
