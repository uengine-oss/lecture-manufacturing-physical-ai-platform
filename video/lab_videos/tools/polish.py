"""나레이션 다듬기 — gpt-6-astra (OpenAI Responses API).

python tools/polish.py <ID|all>
결과: build/<ID>/narration.json  [{scene, type, draft, text, model}] — 초안이 바뀌지 않았으면 캐시를 쓴다.
"""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import dotenv_values
from openai import OpenAI

from common import BUILD, ENV_FILE, SPECS, load_spec

MODEL = "gpt-6-astra"
STYLE = """너는 한국어 강의 영상 나레이션 편집자다. 아래 '초안'을 대학 2~4학년이 처음 들어도 이해할 수 있는 자연스러운 한국어 강의 말투로 다듬어라.

규칙:
- 뜻·사실·숫자·단위·파일명·함수명·명령·상태 이름(예: SENSOR_FAULT, REDUCE_LOAD)은 절대 바꾸거나 새로 만들지 않는다. 초안에 없는 사실을 더하지 않는다.
- 말하듯 쓴다. 번역투와 딱딱한 문어체("~것입니다" 남발, "~에 대하여")를 피하고 "~습니다/~죠/~거든요/~입니다"를 자연스럽게 섞는다. 한 문장에 생각 하나.
- 음성 합성으로 읽힌다. 괄호·기호·마크다운·이모지를 쓰지 않는다. 화살표는 말로 푼다.
- 숫자는 읽기 쉽게 적되 값은 그대로 둔다 (예: 60°C → 섭씨 60도, 0.8 → 영 점 팔, 10초 → 10초).
- 영어 약어·코드 이름은 그대로 두되, 처음 나오는 어려운 용어는 쉬운 말로 한 번 풀어 준다(초안에 풀이가 있으면 유지).
- 길이는 초안의 85~115% 로 맞춘다.
- 다듬은 나레이션 본문만 출력한다. 설명이나 따옴표를 붙이지 않는다."""


def client():
    return OpenAI(api_key=dotenv_values(ENV_FILE)["OPENAI_API_KEY"])


def polish_one(c, ctx: str, draft: str) -> str:
    r = c.responses.create(model=MODEL, instructions=STYLE, input=f"[장면 맥락]\n{ctx}\n\n[초안]\n{draft}")
    return r.output_text.strip()


def run(sid: str):
    spec = load_spec(sid)
    out_dir = BUILD / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "narration.json"
    cache = {x["hash"]: x for x in json.loads(cache_path.read_text())} if cache_path.exists() else {}
    c = client()
    jobs = []
    for i, sc in enumerate(spec["scenes"], 1):
        ctx = f"{spec['class']} {spec['session']}회 「{spec['title']}」 · 장면 {i} ({sc['type']}) · 화면 자막: {sc.get('caption', '')}"
        h = hashlib.sha1((MODEL + STYLE + ctx + sc["narration"]).encode()).hexdigest()[:16]
        jobs.append((i, sc, ctx, h))

    def work(job):
        i, sc, ctx, h = job
        if h in cache:
            return cache[h] | {"scene": i}
        text = polish_one(c, ctx, sc["narration"])
        ratio = len(text) / max(len(sc["narration"]), 1)
        if not (0.7 <= ratio <= 1.35):  # 지나치게 늘거나 줄면 한 번 더
            text = polish_one(c, ctx + f"\n(이전 결과 길이 비율 {ratio:.2f} — 초안 길이에 맞출 것)", sc["narration"])
        return {"scene": i, "type": sc["type"], "hash": h, "draft": sc["narration"], "text": text, "model": MODEL}

    with ThreadPoolExecutor(6) as ex:
        res = sorted(ex.map(work, jobs), key=lambda x: x["scene"])
    cache_path.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    chars = sum(len(x["text"]) for x in res)
    print(f"{sid}: {len(res)} scenes polished by {MODEL} · {chars}자")


if __name__ == "__main__":
    ids = sorted(p.stem for p in SPECS.glob("*.json")) if sys.argv[1] == "all" else sys.argv[1:]
    for sid in ids:
        run(sid)
