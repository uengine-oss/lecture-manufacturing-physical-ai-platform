"""OpenAI TTS — python tools/tts.py <ID|all>  → build/<ID>/audio/scene-NN.wav + durations.json (문장 바뀐 장면만 다시 만든다)"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import dotenv_values
from openai import OpenAI

from common import BUILD, ENV_FILE, SPECS

VOICE = "marin"
INSTR = "차분하고 친절한 한국어 강의 나레이션. 또박또박, 자연스러운 쉼, 학생에게 설명하듯 담백하게."


def dur(p):
    return round(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True).stdout), 3)


def run(sid):
    d = BUILD / sid
    nar = json.loads((d / "narration.json").read_text())
    (d / "audio").mkdir(exist_ok=True)
    meta_p = d / "audio" / "meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    c = OpenAI(api_key=dotenv_values(ENV_FILE)["OPENAI_API_KEY"])

    def work(x):
        p = d / "audio" / f"scene-{x['scene']:02d}.wav"
        if meta.get(str(x["scene"])) == x["text"] and p.exists():
            return x["scene"], dur(p)
        with c.audio.speech.with_streaming_response.create(model="gpt-4o-mini-tts", voice=VOICE, input=x["text"], instructions=INSTR, response_format="wav") as r:
            r.stream_to_file(p)
        meta[str(x["scene"])] = x["text"]
        return x["scene"], dur(p)

    with ThreadPoolExecutor(6) as ex:
        res = dict(ex.map(work, nar))
    meta_p.write_text(json.dumps(meta, ensure_ascii=False))
    (d / "durations.json").write_text(json.dumps([{"scene": k, "duration": v} for k, v in sorted(res.items())], indent=1))
    print(f"{sid}: {len(res)} clips · {sum(res.values())/60:.1f}분")


if __name__ == "__main__":
    ids = sorted(p.stem for p in SPECS.glob("*.json")) if sys.argv[1] == "all" else sys.argv[1:]
    for sid in ids:
        run(sid)
