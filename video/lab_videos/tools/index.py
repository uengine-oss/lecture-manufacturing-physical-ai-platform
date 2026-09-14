"""실습 영상 목록 — README.md 와 index.html 을 final_report 들로 만든다. python tools/index.py"""
import json
from pathlib import Path

from common import BUILD, LV, SPECS, load_spec

SEC = {"title": "시작", "quiz": "퀴즈", "answer": "해답", "summary": "요약", "next": "다음 차수"}


def section(spec, i):
    seen = False
    for k, sc in enumerate(spec["scenes"][:i], 1):
        if sc["type"] in ("task", "run", "apply_fix"):
            seen = True
    t = spec["scenes"][i - 1]["type"]
    return SEC.get(t) or ("실습" if seen else "기본 개념")


def mmss(s):
    return f"{int(s // 60)}:{int(s % 60):02d}"


rows, cards = [], []
for sid in sorted((p.stem for p in SPECS.glob("*.json")), key=lambda x: (x[0] != "P", int(x[1:]))):
    rp = BUILD / sid / "final_report.json"
    spec = load_spec(sid)
    if not rp.exists():
        rows.append(f"| {spec['class']} {spec['session']}회 | {spec['title']} | (제작 전) | | |")
        continue
    r = json.loads(rp.read_text())
    video = Path(r["file"]).relative_to("video/lab_videos")
    runs = " → ".join(f"{x['expect']}" for x in r["runs"])
    # 구간 시작 시각
    marks, last = [], None
    for c in r["chapters"]:
        s = section(spec, c["scene"])
        if s != last:
            marks.append(f"{s} {mmss(c['start'])}")
            last = s
    rows.append(f"| {spec['class']} {spec['session']}회 | [{spec['title']}]({video}) | {mmss(r['duration_s'])} | {runs} | {' · '.join(marks)} |")
    cards.append(f"""<article><video controls preload="metadata" src="{video}"><track kind="subtitles" srclang="ko" label="한국어" src="{video.with_suffix('.srt')}"></video>
<h3>{spec['class']} {spec['session']}회 · {spec['title']}</h3><p class="m">{mmss(r['duration_s'])} · 장면 {r['scenes']} · 실행 {runs}</p><p class="c">{' · '.join(marks)}</p></article>""")

md = f"""# 차수별 실습 영상

교재 한 편마다 실습 과정을 녹화한 영상이다. 구성은 **기본 개념 → 실습 과정(실제 실행) → 퀴즈 → 해답 → 요약 → 다음 차수**이며, 나레이션 초안은 **gpt-6-astra** 로 자연스러운 한국어로 다듬고 OpenAI TTS 로 읽었다. 실습 장면의 테스트 결과는 녹화 중 실제로 실행한 출력이며, 사양에 적은 기대(실패/통과)와 다르면 제작이 멈춘다.

| 회차 | 영상 | 길이 | 실습 실행 (차례대로) | 구간 시작 |
|---|---|---|---|---|
""" + "\n".join(rows) + """

## 다시 만들기

```bash
cd lecture/video/lab_videos
tools/produce.sh P01          # 사양 검증(--run 없음) → gpt-6-astra 다듬기 → TTS → 렌더(실제 실행 녹화) → 합성
python tools/validate_spec.py P01 --run   # 작업 사본에서 실습 실행 기대값만 확인
```

사양 작성법은 [SPEC_GUIDE.md](SPEC_GUIDE.md), 장면 사양은 `specs/`, 자막은 영상과 같은 이름의 `.srt` 다.
"""
(LV / "README.md").write_text(md)
(LV / "index.html").write_text(f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>차수별 실습 영상</title>
<style>body{{margin:0;font-family:Pretendard,"Apple SD Gothic Neo",sans-serif;background:#0b1422;color:#e5edf7}}header{{padding:28px 36px}}h1{{margin:0}}header p{{color:#9fb3cc}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:20px;padding:0 36px 40px}}article{{background:#12213a;border:1px solid #22324d;border-radius:14px;overflow:hidden}}
video{{width:100%;display:block;background:#000}}h3{{margin:12px 16px 4px;font-size:17px}}.m{{margin:0 16px;color:#93c5fd;font-size:13px}}.c{{margin:6px 16px 14px;color:#9fb3cc;font-size:12.5px}}</style>
<header><h1>차수별 실습 영상</h1><p>기본 개념 → 실습(실제 실행) → 퀴즈 → 해답 → 요약 → 다음 차수 · 나레이션 gpt-6-astra 다듬기 · 한국어 자막</p></header><main>{''.join(cards)}</main></html>""")
print("index:", len(cards), "videos")
